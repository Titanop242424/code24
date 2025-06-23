import json
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from flask import Flask
import threading

TOKEN_FILE = 'tokens.json'


def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        return {}
    with open(TOKEN_FILE, 'r') as f:
        tokens = json.load(f)

    # Upgrade old format (token string) to new dict format
    upgraded = {}
    for user_id, value in tokens.items():
        if isinstance(value, str):
            upgraded[user_id] = {
                "chat_id": int(user_id),
                "github_token": value
            }
        else:
            upgraded[user_id] = value
    return upgraded


def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)


def add_token(user_id, chat_id, github_token):
    tokens = load_tokens()
    tokens[str(user_id)] = {"chat_id": chat_id, "github_token": github_token}
    save_tokens(tokens)


def list_codespaces(github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.get("https://api.github.com/user/codespaces", headers=headers)
    if response.status_code == 200:
        return response.json().get('codespaces', [])
    return []


def restart_codespace(github_token, name):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    url = f"https://api.github.com/user/codespaces/{name}/start"
    response = requests.post(url, headers=headers, json={})
    if response.status_code == 202:
        print(f"Restarted codespace: {name}")
        return True, ""
    else:
        print(f"Failed to restart codespace {name}: {response.status_code} {response.text}")
        return False, f"{response.status_code} {response.text}"


async def monitor_codespaces_job(context: ContextTypes.DEFAULT_TYPE):
    tokens = load_tokens()
    for user_id, data in tokens.items():
        chat_id = data['chat_id']
        github_token = data['github_token']
        try:
            codespaces = list_codespaces(github_token)
            if not codespaces:
                await context.bot.send_message(chat_id, "🚫 No Codespaces found or token invalid.")
                continue

            for cs in codespaces:
                name = cs['name']
                state = cs['state']
                message = f"🔍 Codespace: `{name}`\nStatus: *{state.upper()}*"
                if state.lower() != 'available':
                    message += "\n⚠️ Not running. Attempting restart..."
                    restarted, error = restart_codespace(github_token, name)
                    if restarted:
                        message += "\n✅ Restart initiated."
                    else:
                        message += f"\n❌ Restart failed.\nError: {error}"
                await context.bot.send_message(chat_id, message, parse_mode='Markdown')
        except Exception as e:
            await context.bot.send_message(chat_id, f"❗ Error checking Codespaces: {e}")


async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if context.args:
        github_token = context.args[0]
        add_token(user_id, chat_id, github_token)
        await update.message.reply_text("✅ GitHub token saved. Checking Codespaces now...")

        # Immediate check after saving token
        codespaces = list_codespaces(github_token)
        if not codespaces:
            await update.message.reply_text("🚫 No Codespaces found or token may be invalid.")
            return
        for cs in codespaces:
            name = cs['name']
            state = cs['state']
            message = f"🔍 Codespace: `{name}`\nStatus: *{state.upper()}*"
            if state.lower() != 'available':
                message += "\n⚠️ Not running. Attempting restart..."
                restarted, error = restart_codespace(github_token, name)
                if restarted:
                    message += "\n✅ Restart initiated."
                else:
                    message += f"\n❌ Restart failed.\nError: {error}"
            await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text("Usage:\n/token <your_github_token>")


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tokens = load_tokens()
    if not tokens:
        await update.message.reply_text("No tokens saved yet.")
        return

    msg = "🗂️ *Saved tokens info:*\n"
    for user_id, data in tokens.items():
        chat_id = data.get('chat_id', 'N/A')
        github_token = data.get('github_token', None)
        username = "Unknown"

        if github_token:
            try:
                headers = {
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github+json"
                }
                resp = requests.get("https://api.github.com/user", headers=headers)
                if resp.status_code == 200:
                    username = resp.json().get("login", "Unknown")
                else:
                    username = f"Error {resp.status_code}"
            except Exception as e:
                username = f"Error"

        msg += f"- GitHub user: `{username}`\n  Telegram user_id: `{user_id}` => chat_id: `{chat_id}`\n"

    await update.message.reply_text(msg, parse_mode='Markdown')



async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tokens = load_tokens()
    if not tokens:
        await update.message.reply_text("No tokens saved yet.")
        return

    await update.message.reply_text("⏳ Checking all Codespaces status...")
    for user_id, data in tokens.items():
        chat_id = data['chat_id']
        github_token = data['github_token']
        try:
            codespaces = list_codespaces(github_token)
            if not codespaces:
                await update.message.reply_text(f"User `{user_id}`: 🚫 No Codespaces found or token invalid.", parse_mode='Markdown')
                continue

            for cs in codespaces:
                name = cs['name']
                state = cs['state']
                message = f"User `{user_id}` Codespace: `{name}`\nStatus: *{state.upper()}*"
                await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"User `{user_id}`: ❗ Error checking Codespaces: {e}", parse_mode='Markdown')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
👋 *Welcome to the GitHub Codespace Monitor Bot!*

Here are the available commands:

• `/token <github_token>` — Save your GitHub token to start monitoring your Codespaces.
• `/check` — List all saved users and chat IDs (tokens are kept secret).
• `/status` — Check Codespaces status immediately for all saved tokens.
• `/start` — Show this help message.

_The bot automatically checks your Codespaces every 5 minutes and restarts any that are shutdown._

If you have any questions, just ask!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


def run_flask():
    app = Flask(__name__)

    @app.route('/')
    def home():
        return "🤖 Bot is running!"

    port = int(os.environ.get("PORT", 10000))  # Render will inject PORT
    app.run(host="0.0.0.0", port=port)

def main():
    telegram_token = "7788865701:AAHFVFbSdhpRuMTmLj987J8BmwKLR3j4brk"

    application = ApplicationBuilder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("token", token_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("status", status_command))

    if application.job_queue:
        application.job_queue.run_repeating(monitor_codespaces_job, interval=300, first=0)
    else:
        print("⚠️ JobQueue not available")

    print("🤖 Telegram bot started...")

    # Run Flask server in another thread
    threading.Thread(target=run_flask).start()

    # Run the Telegram bot (polling)
    application.run_polling()

if __name__ == "__main__":
    main()
