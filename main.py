import os
import subprocess
import datetime as dt
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, CallbackContext

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "ВАШ_ТОКЕН"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

app = FastAPI()

# ===== ВСТАВЛЯЕМ ВАШ /embed =====
IFRAME_HTML = """
<!doctype html><meta charset="utf-8">
<style>html,body,iframe{margin:0;height:100%;width:100%;border:0;}</style>
<iframe src="https://sslecal2.investing.com?columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous&category=_employment,_economicActivity,_inflation,_credit,_centralBanks,_confidenceIndex,_balance,_Bonds&importance=2,3&features=datepicker,timezone&countries=37,5&calType=week&timeZone=73&lang=1"></iframe>
<div class="poweredBy" style="position:fixed;left:0;right:0;bottom:0;text-align:center;font:12px Arial;">Real Time Economic Calendar provided by <a href="https://www.investing.com/" target="_blank">Investing.com</a>.</div>
"""

@app.get("/embed", response_class=HTMLResponse)
def embed():
    return IFRAME_HTML

# ===== ИНИЦИАЛИЗАЦИЯ PTB =====
updater = Updater(BOT_TOKEN, use_context=True)
dp: Dispatcher = updater.dispatcher

# ===== ХЭНДЛЕРЫ БОТА =====
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Я работаю на вебхуках 🤖\nКоманда: /calendar — пришлю скрин календаря.")

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("Команды: /start /help /calendar")

def calendar(update: Update, context: CallbackContext):
    """Запускает внешний скрипт для скрина /embed и шлёт PNG."""
    chat = update.effective_chat
    SCRAPER = Path(__file__).with_name("screenshot_page.py")
    OUT_PNG = Path(__file__).with_name("page.png")
    USER_DATA_DIR = Path(__file__).with_name("user-data")

    if not SCRAPER.exists():
        update.message.reply_text("❌ Скрипт screenshot_page.py не найден.")
        return

    try:
        if OUT_PNG.exists():
            OUT_PNG.unlink()
    except Exception:
        pass

    update.message.reply_text("⏳ Делаю скрин /embed ...")

    cmd = [
        "python", str(SCRAPER),
        "--url", "http://127.0.0.1:8000/embed",  # скриним встроенную страницу
        "--out", str(OUT_PNG),
        "--wait", "8",
        "--user-data-dir", str(USER_DATA_DIR),
        "--headless"
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        update.message.reply_text("⏳ Скрин не успел создаться, попробуйте снова.")
        return

    if proc.returncode != 0 or not OUT_PNG.exists():
        update.message.reply_text(f"❌ Ошибка: {proc.stderr or proc.stdout}")
        return

    caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
    with OUT_PNG.open("rb") as f:
        context.bot.send_photo(chat_id=chat.id, photo=f, caption=caption)

# Регистрируем команды
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("help", help_cmd))
dp.add_handler(CommandHandler("calendar", calendar))

# ===== ХЭЛСЧЕК И ВЕБХУК =====
@app.get("/")
def healthcheck():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    if WEBHOOK_SECRET:
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if given != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="bad secret token")

    data = await request.json()
    update = Update.de_json(data, dp.bot)
    dp.process_update(update)
    return {"ok": True}
