# main.py
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from supabase import create_client, Client
from ai_brain import get_ai_response

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passes natural language text to the separated Gemini module."""
    user_text = update.message.text

    # Show a "typing..." action in Telegram so you know it's thinking
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Call the function from ai_brain.py
    ai_reply = await get_ai_response(user_text)
    
    await update.message.reply_text(text=ai_reply)

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
