import json
import os
import asyncio
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKENS_FILE = "tokens.json"

def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return {}
    with open(TOKENS_FILE, "r") as f:
        return json.load(f)

def save_tokens(data):
    with open(TOKENS_FILE, "w") as f:
        json.dump(data, f, indent=2)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Codespace Monitor Bot*\n\n"
        "Available commands:\n"
        "/start - Show this help message\n"
        "/token <GitHub_token> - Save your GitHub token\n"
        "/check - List saved tokens and GitHub usernames\n"
        "/status - Check your Codespaces status immediately\n\n"
        "This bot will check your Codespaces every 5 minutes and restart any shutdown ones."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /token <GitHub Personal Access Token>")
        return
    github_token = context.args[0]
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    tokens = load_tokens()
    tokens[user_id] = {
        "github_token": github_token,
        "chat_id": chat_id
    }
    save_tokens(tokens)

    await update.message.reply_text("✅ GitHub token saved. Checking Codespaces now...")
    await check_and_report_codespaces(user_id, chat_id, github_token, context)

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tokens = load_tokens()
    if not tokens:
        await update.message.reply_text("No tokens saved yet.")
        return

    msg = "🗂️ *Saved tokens info:*\n"
    for user_id, data in tokens.items():
        github_token = data.get("github_token")
        username = "Unknown"
        if github_token:
            try:
                headers = {
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github+json"
                }
                resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
                if resp.status_code == 200:
                    username = resp.json().get("login", "Unknown")
                else:
                    username = f"Error {resp.status_code}"
            except Exception:
                username = "Error"
        msg += f"- GitHub user: `{username}`\n  Telegram user_id: `{user_id}`\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    tokens = load_tokens()
    data = tokens.get(user_id)
    if not data:
        await update.message.reply_text("You have not saved a token yet. Use /token <token>")
        return
    github_token = data.get("github_token")
    chat_id = update.effective_chat.id

    await check_and_report_codespaces(user_id, chat_id, github_token, context)

async def check_and_report_codespaces(user_id, chat_id, github_token, context):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        resp = requests.get("https://api.github.com/user/codespaces", headers=headers, timeout=15)
        if resp.status_code != 200:
            await context.bot.send_message(chat_id, f"❗ Failed to get Codespaces: HTTP {resp.status_code}")
            return
        codespaces = resp.json().get("codespaces", [])
        if not codespaces:
            await context.bot.send_message(chat_id, "ℹ️ No Codespaces found for your account.")
            return

        for cs in codespaces:
            name = cs.get("name")
            state = cs.get("state") or cs.get("status") or "UNKNOWN"
            msg = f"🔍 Codespace: *{name}*\nStatus: *{state}*"
            await context.bot.send_message(chat_id, msg, parse_mode="Markdown")

            if state.lower() != "available" and state.lower() != "running":
                await context.bot.send_message(chat_id, "⚠️ Not running. Attempting restart...")
                restart_url = cs.get("url") + "/stop"  # We'll fix below
                # The GitHub API restart endpoint:
                restart_url = f"https://api.github.com/user/codespaces/{name}/start"
                restart_resp = requests.post(restart_url, headers=headers, timeout=10)
                if restart_resp.status_code == 204:
                    await context.bot.send_message(chat_id, "✅ Restart succeeded.")
                else:
                    await context.bot.send_message(chat_id, f"❌ Restart failed: HTTP {restart_resp.status_code}")
    except Exception as e:
        await context.bot.send_message(chat_id, f"❗ Error checking Codespaces: {str(e)}")

async def monitor_codespaces_job(context: ContextTypes.DEFAULT_TYPE):
    tokens = load_tokens()
    for user_id, data in tokens.items():
        github_token = data.get("github_token")
        chat_id = data.get("chat_id")
        if github_token and chat_id:
            await check_and_report_codespaces(user_id, chat_id, github_token, context)

def main():
    telegram_token = os.environ.get("7788865701:AAH0RXiPO73BtQuRWzieAdhs2nQerscAvk0")
    if not telegram_token:
        print("Error: TELEGRAM_TOKEN env variable not set.")
        return

    app = ApplicationBuilder().token(telegram_token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("token", token_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("status", status_command))

    app.job_queue.run_repeating(monitor_codespaces_job, interval=300, first=0)

    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
