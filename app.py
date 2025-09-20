import os
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, CallbackContext

BOT_TOKEN = os.environ["8351457188:AAFQZAI19EVjSbhLsjwfn7eFXtp79td3274"]  # зададим в настройках PaaS
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # для верификации запросов (рекомендуется)

app = FastAPI()

# Инициализируем PTB (только dispatcher, без polling)
updater = Updater("8351457188:AAFQZAI19EVjSbhLsjwfn7eFXtp79td3274", use_context=True)
dp: Dispatcher = updater.dispatcher

# --- handlers ---
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Я работаю на вебхуках 🤖")

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("Команды: /start /help /btc /eth /avax")

def btc(update: Update, context: CallbackContext):
    update.message.reply_text("BTC: 🟠")

def eth(update: Update, context: CallbackContext):
    update.message.reply_text("ETH: 🔷")

def avax(update: Update, context: CallbackContext):
    update.message.reply_text("AVAX: 🔺")

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("help", help_cmd))
dp.add_handler(CommandHandler("btc", btc))
dp.add_handler(CommandHandler("eth", eth))
dp.add_handler(CommandHandler("avax", avax))

# --- FastAPI endpoints ---
@app.get("/")
def healthcheck():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    # Проверяем секрет для безопасности (советуются одинаковые WEBHOOK_SECRET в вашем боте и setWebhook)
    if WEBHOOK_SECRET:
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if given != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="bad secret token")

    data = await request.json()
    update = Update.de_json(data, dp.bot)
    dp.process_update(update)
    return {"ok": True}
