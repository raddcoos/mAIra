import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# 1. Configure logging to see updates in Railway's console logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Command handler for /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_user.first_name
    await update.message.reply_text(
        text=f"Hello {user_first_name}! I am your personal AI assistant control panel. Listening for commands..."
    )

# 3. Message handler to capture incoming text instructions
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.effective_chat.id
    
    logger.info(f"Received message from chat_id {chat_id}: '{user_text}'")
    
    # Simple acknowledgement for testing
    await update.message.reply_text(text=f"Received: '{user_text}'. Processing logic will go here.")

# 4. Main application entry point
def main():
    # Retrieve the token safely from environment variables
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN environment variable. Exiting.")
        return

    # Build the application
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot using long polling
    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
