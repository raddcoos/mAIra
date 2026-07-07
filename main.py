import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from supabase import create_client, Client

# 1. Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Initialize Supabase Client
# We grab the credentials from Railway's environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create the client if variables exist
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.warning("Supabase credentials missing! Database queries will fail.")
    supabase = None

# 3. Core Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_user.first_name
    await update.message.reply_text(
        text=f"Hello {user_first_name}! I am your personal AI assistant. Send /contact <name> to test the database."
    )

async def get_contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches a phone number from Supabase based on a name."""
    if not supabase:
        await update.message.reply_text("Database connection is not configured.")
        return
        
    # Check if the user actually typed a name after /contact
    if not context.args:
        await update.message.reply_text("Please provide a name. Example: /contact David")
        return
        
    # Combine arguments into a single search string (e.g., "David" or "John Doe")
    name_to_search = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching Supabase for '{name_to_search}'...")
    
    try:
        # Query Supabase: Select 'phone' where 'name' matches the search term (case-insensitive)
        response = supabase.table("contacts").select("phone").ilike("name", f"%{name_to_search}%").execute()
        data = response.data
        
        if data and len(data) > 0:
            # We found a match! Extract the phone number from the first result
            phone_number = data[0].get("phone")
            await update.message.reply_text(f"✅ Found {name_to_search}'s phone number: {phone_number}")
        else:
            await update.message.reply_text(f"❌ Could not find a contact named '{name_to_search}'.")
            
    except Exception as e:
        logger.error(f"Supabase query failed: {e}")
        await update.message.reply_text("⚠️ An error occurred while searching the database.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info(f"Received text: '{user_text}'")
    await update.message.reply_text(text=f"Echo: {user_text}\n(AI logic will replace this soon!)")

# 4. Main application entry point
def main():
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN. Exiting.")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("contact", get_contact_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
