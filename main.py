# main.py
import os
import logging
import json
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from supabase import create_client, Client
from ai_brain import get_ai_response
from gmail_helper import send_gmail

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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passes natural language text to Gemini and intercepts action commands."""
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    ai_reply = await get_ai_response(user_text)

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

            await update.message.reply_text(f"📧 Drafting and sending email to {recipient_email}...")
            send_gmail(recipient_email, subject, body)
            await update.message.reply_text(f"✅ Email sent successfully to {recipient_email}!")
        else:
            await update.message.reply_text(ai_reply)

    except json.JSONDecodeError:
        # If no valid JSON is found, treat it as normal text chat
        await update.message.reply_text(text=ai_reply)
    except Exception as e:
        logger.error(f"Execution error: {e}")
        await update.message.reply_text(f"⚠️ Failed to execute task: {e}")

# 4. Main application entry point
def main():
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN. Exiting.")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("contact", get_contact_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
