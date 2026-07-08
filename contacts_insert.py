# contacts_insert.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def insert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /insert — starts the "add a contact" flow. The actual parsing happens in
    handle_contact_insert() below, called from main.py's handle_message once
    the user replies with their next message.
    """
    context.user_data["awaiting_contact_insert"] = True
    await update.message.reply_text(
        "Send me the contact's details in this format:\n\n"
        "name, number, email\n\n"
        "Example: john, 01234567890, john@outlook.com"
    )


async def handle_contact_insert(update: Update, context: ContextTypes.DEFAULT_TYPE, supabase):
    """
    Parses "name, number, email" from the user's message and inserts it into
    the Supabase 'contacts' table. Called from main.py's handle_message when
    context.user_data['awaiting_contact_insert'] is True.

    'supabase' is passed in rather than imported directly, to avoid a circular
    import with main.py (which owns the Supabase client).
    """
    # Clear the flag immediately so the bot doesn't get stuck waiting forever
    # even if this specific attempt fails.
    context.user_data["awaiting_contact_insert"] = False

    text = update.message.text.strip()
    parts = [p.strip() for p in text.split(",")]

    if len(parts) != 3:
        await update.message.reply_text(
            "⚠️ That doesn't look right. Please use the format: name, number, email\n"
            "Example: john, 01234567890, john@outlook.com\n\n"
            "Type /insert to try again."
        )
        return

    name, number, email = parts

    if not name:
        await update.message.reply_text("⚠️ Name can't be empty. Type /insert to try again.")
        return

    if not number:
        await update.message.reply_text("⚠️ Number can't be empty. Type /insert to try again.")
        return

    if "@" not in email or "." not in email.split("@")[-1]:
        await update.message.reply_text("⚠️ That email doesn't look like a valid address. Type /insert to try again.")
        return

    if not supabase:
        await update.message.reply_text("⚠️ Database connection is not configured.")
        return

    try:
        supabase.table("contacts").insert({
            "name": name,
            "phone": number,
            "email": email,
        }).execute()
        await update.message.reply_text(
            f"✅ Added to your contacts:\nName: {name}\nNumber: {number}\nEmail: {email}"
        )
    except Exception as e:
        logger.error(f"Supabase insert failed: {e}")
        await update.message.reply_text(f"⚠️ Failed to save contact: {e}")
