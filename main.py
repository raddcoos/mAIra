# main.py
import os
import logging
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from supabase import create_client, Client
from ai_brain import get_ai_response, rewrite_email, transcribe_audio
from gmail_helper import send_gmail
from contacts_insert import insert_command, handle_contact_insert

# 1. Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

# The exact name to sign emails off with. Set this in Railway's Service Variables.
# Falls back to the user's Telegram first name if not set, so the bot doesn't break
# if you forget to configure it — but for a reliable, exact sign-off, set this.
SENDER_NAME = os.getenv("SENDER_NAME")

# 3. Core Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_user.first_name
    await update.message.reply_text(
        text=f"Hello {user_first_name}! I am your personal AI assistant. I am online and ready to help."
    )

async def get_contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not supabase:
        await update.message.reply_text("Database connection is not configured.")
        return
    if not context.args:
        await update.message.reply_text("Please provide a name. Example: /contact ismyralda")
        return

    name_to_search = " ".join(context.args)
    try:
        response = supabase.table("contacts").select("phone").ilike("name", f"%{name_to_search}%").execute()
        data = response.data
        if data and len(data) > 0:
            phone_number = data[0].get("phone")
            await update.message.reply_text(f"✅ Found {name_to_search}'s phone number: {phone_number}")
        else:
            await update.message.reply_text(f"❌ Could not find a contact named '{name_to_search}'.")
    except Exception as e:
        logger.error(f"Supabase query failed: {e}")
        await update.message.reply_text("⚠️ An error occurred while searching the database.")


def resolve_contact_email(name: str):
    """
    Looks up a contact by (partial, case-insensitive) name match in Supabase.
    Returns a tuple: (email_or_None, error_message_or_None)
    """
    if not supabase:
        return None, "Database connection is not configured."

    response = supabase.table("contacts").select("name,email").ilike("name", f"%{name}%").execute()
    matches = response.data or []

    if len(matches) == 0:
        return None, f"❌ I couldn't find a contact named '{name}'. Check the spelling, or tell me their email directly."

    if len(matches) > 1:
        matched_names = ", ".join(m.get("name", "?") for m in matches)
        return None, f"⚠️ I found more than one contact matching '{name}': {matched_names}. Please tell me the full name."

    contact = matches[0]
    email = contact.get("email")
    if not email:
        return None, f"⚠️ I found {contact.get('name')}, but there's no email on file for them."

    return email, None


def build_confirmation_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Send", callback_data="confirm_send_email"),
            InlineKeyboardButton("🔄 Rewrite", callback_data="rewrite_send_email"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_send_email"),
        ]
    ])


def format_preview(recipient_email: str, subject: str, body: str) -> str:
    return (
        f"Here's the email I'll send to *{recipient_email}*:\n\n"
        f"*Subject:* {subject}\n\n"
        f"{body}\n\n"
        f"Send it?"
    )


async def process_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    """
    Core command-handling logic, shared by typed messages and transcribed voice
    messages. Whatever text comes in here is treated identically regardless of
    whether it was typed or spoken.
    """
    # If the user is mid-way through /insert, route to that flow instead of the AI.
    if context.user_data.get("awaiting_contact_insert"):
        await handle_contact_insert(update, context, supabase)
        return

    # Prefer the fixed SENDER_NAME setting; fall back to Telegram's first name.
    sender_name = SENDER_NAME or update.effective_user.first_name

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    ai_reply = await get_ai_response(user_text, sender_name=sender_name)

    try:
        # Use Regex to hunt down the JSON object anywhere in the text
        json_string = ai_reply
        match = re.search(r'\{.*\}', ai_reply, re.DOTALL)
        if match:
            json_string = match.group(0)

        # Try to parse the extracted string
        data = json.loads(json_string)

        if data.get("action") == "send_email":
            to_field = (data.get("to") or "").strip()
            subject = data.get("subject", "(No subject)")
            body = data.get("body", "")

            if not to_field:
                await update.message.reply_text("⚠️ I couldn't tell who to send this to. Please include a name or email.")
                return

            # If it already looks like an email address, use it directly.
            # Otherwise, treat it as a contact name and look it up in Supabase.
            if "@" in to_field:
                recipient_email = to_field
            else:
                recipient_email, error = resolve_contact_email(to_field)
                if error:
                    await update.message.reply_text(error)
                    return

            # Stash the draft so the callback handler can send/rewrite it after approval.
            # Keyed per-user via context.user_data. original_request + sender_name are
            # kept so the Rewrite button can ask Gemini for a fresh version later.
            context.user_data["pending_email"] = {
                "to": recipient_email,
                "subject": subject,
                "body": body,
                "original_request": user_text,
                "sender_name": sender_name,
            }

            await update.message.reply_text(
                format_preview(recipient_email, subject, body),
                parse_mode="Markdown",
                reply_markup=build_confirmation_keyboard(),
            )
        else:
            await update.message.reply_text(ai_reply)

    except json.JSONDecodeError:
        # If no valid JSON is found, treat it as normal text chat
        await update.message.reply_text(text=ai_reply)
    except Exception as e:
        logger.error(f"Execution error: {e}")
        await update.message.reply_text(f"⚠️ Failed to execute task: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for typed text messages."""
    await process_text_command(update, context, update.message.text)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point for voice notes. Downloads the audio, transcribes it via Gemini,
    then runs it through the exact same pipeline as a typed message.
    """
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    voice = update.message.voice
    if not voice:
        return

    try:
        telegram_file = await context.bot.get_file(voice.file_id)
        audio_bytes = await telegram_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Failed to download voice note: {e}")
        await update.message.reply_text("⚠️ I couldn't download that voice message. Please try again.")
        return

    mime_type = voice.mime_type or "audio/ogg"
    transcript = await transcribe_audio(audio_bytes, mime_type=mime_type)

    if not transcript:
        await update.message.reply_text(
            "⚠️ Sorry, I couldn't understand that voice message. Please try again or type your command instead."
        )
        return

    await update.message.reply_text(f"🎙️ Heard: \"{transcript}\"")
    await process_text_command(update, context, transcript)


async def handle_email_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the Send / Rewrite / Cancel button taps under an email preview."""
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_email")

    if query.data == "cancel_send_email":
        context.user_data.pop("pending_email", None)
        await query.edit_message_text("❌ Cancelled. That email was not sent.")
        return

    if not pending:
        await query.edit_message_text("⚠️ This draft has expired (e.g. the bot restarted). Please ask me again.")
        return

    if query.data == "confirm_send_email":
        try:
            send_gmail(pending["to"], pending["subject"], pending["body"])
            await query.edit_message_text(f"✅ Email sent successfully to {pending['to']}!")
        except Exception as e:
            logger.error(f"Failed to send confirmed email: {e}")
            await query.edit_message_text(f"⚠️ Failed to send: {e}")
        finally:
            context.user_data.pop("pending_email", None)
        return

    if query.data == "rewrite_send_email":
        await query.edit_message_text("🔄 Rewriting the email...")

        raw_reply = await rewrite_email(
            original_request=pending["original_request"],
            previous_subject=pending["subject"],
            previous_body=pending["body"],
            sender_name=pending.get("sender_name"),
        )

        if not raw_reply:
            # Rewrite failed — restore the previous draft so it isn't lost.
            await query.edit_message_text(
                format_preview(pending["to"], pending["subject"], pending["body"]) +
                "\n\n⚠️ (Rewrite failed, showing the previous draft again.)",
                parse_mode="Markdown",
                reply_markup=build_confirmation_keyboard(),
            )
            return

        try:
            match = re.search(r'\{.*\}', raw_reply, re.DOTALL)
            json_string = match.group(0) if match else raw_reply
            new_draft = json.loads(json_string)

            pending["subject"] = new_draft.get("subject", pending["subject"])
            pending["body"] = new_draft.get("body", pending["body"])
            context.user_data["pending_email"] = pending

            await query.edit_message_text(
                format_preview(pending["to"], pending["subject"], pending["body"]),
                parse_mode="Markdown",
                reply_markup=build_confirmation_keyboard(),
            )
        except json.JSONDecodeError:
            await query.edit_message_text(
                format_preview(pending["to"], pending["subject"], pending["body"]) +
                "\n\n⚠️ (Rewrite failed, showing the previous draft again.)",
                parse_mode="Markdown",
                reply_markup=build_confirmation_keyboard(),
            )


# 4. Main application entry point
def main():
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN. Exiting.")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("contact", get_contact_command))
    application.add_handler(CommandHandler("insert", insert_command))
    application.add_handler(CallbackQueryHandler(handle_email_confirmation))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
