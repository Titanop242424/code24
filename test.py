from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update
import sys

print("Python version:", sys.version)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")

def main():
    token = "7788865701:AAH0RXiPO73BtQuRWzieAdhs2nQerscAvk0"
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))

    app.run_polling()

if __name__ == "__main__":
    main()
