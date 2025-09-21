import os
import subprocess
import datetime as dt
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, CallbackContext

# ===== НАСТРОЙКИ =====
# РЕКОМЕНДУЮ: держите токен в переменной окружения BOT_TOKEN (Render → Environment)
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8351457188:AAFQZAI19EVjSbhLsjwfn7eFXtp79td3274"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # если зададите, Telegram должен слать тот же secret_token

# Путь к скрипту, который делает картинку (лежит рядом с этим файлом)
SCRAPER = Path(__file__).with_name("scrape_investing_calendar.py")
OUT_PNG = Path(__file__).with_name("table_only.png")
USER_DATA_DIR = Path(__file__).with_name("user-data")  # для сохранения cookies (Cloudflare)
WAIT_SECONDS = os.environ.get("CAL_WAIT", "5")        # доп.ожидание после загрузки страницы
RUN_TIMEOUT = int(os.environ.get("CAL_TIMEOUT", "90"))  # таймаут выполнения, сек

# URL из вашего iframe
CALENDAR_URL = (
    "https://sslecal2.investing.com?"
    "columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous"
    "&category=_employment,_economicActivity,_inflation,_credit,_centralBanks,_confidenceIndex,_balance,_Bonds"
    "&importance=2,3&features=datepicker,timezone&countries=37,5&calType=week&timeZone=73&lang=1"
)

app = FastAPI()

# ===== Инициализация PTB (без polling) =====
updater = Updater(BOT_TOKEN, use_context=True)
dp: Dispatcher = updater.dispatcher

# ===== Хэндлеры команд =====
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Я работаю на вебхуках 🤖\nКоманда: /calendar — пришлю скрин календаря.")

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("Команды: /start /help /btc /eth /avax /calendar")

def btc(update: Update, context: CallbackContext):
    update.message.reply_text("BTC: 🟠")

def eth(update: Update, context: CallbackContext):
    update.message.reply_text("ETH: 🔷")

def avax(update: Update, context: CallbackContext):
    update.message.reply_text("AVAX: 🔺")

def calendar(update: Update, context: CallbackContext):
    """Запускает внешний скрипт скриннера и шлёт PNG в чат."""
    chat = update.effective_chat

    # Проверки наличия скрипта
    if not SCRAPER.exists():
        update.message.reply_text(f"❌ Не найден скрипт: {SCRAPER.name}\n"
                                  f"Сохраните файл рядом с main.py.")
        return

    # Удалим старый PNG
    try:
        if OUT_PNG.exists():
            OUT_PNG.unlink()
    except Exception:
        pass

    update.message.reply_text("⏳ Делаю скрин экономического календаря…")

    # Команда запуска Playwright-скринера
    cmd = [
        "python", str(SCRAPER),
        "--url", CALENDAR_URL,
        "--out", str(OUT_PNG),
        "--wait", str(WAIT_SECONDS),
        "--user-data-dir", str(USER_DATA_DIR),
        "--headless"
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        update.message.reply_text("⏳ Время ожидания вышло. Попробуйте ещё раз.")
        return
    except Exception as e:
        update.message.reply_text(f"⚠️ Ошибка запуска: {e}")
        return

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        update.message.reply_text(f"❌ Скрипт завершился с кодом {proc.returncode}.\n```\n{tail}\n```",
                                  parse_mode="Markdown")
        return

    if not OUT_PNG.exists():
        update.message.reply_text("❌ Скрин не найден. Возможна блокировка Cloudflare.\n"
                                  "Откройте скрипт локально без --headless, пройдите проверку 1 раз, "
                                  "куки сохранятся в user-data.")
        return

    # Отправляем фото
    caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
    with OUT_PNG.open("rb") as f:
        context.bot.send_photo(chat_id=chat.id, photo=f, caption=caption)

# Регистрируем команды
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("help", help_cmd))
dp.add_handler(CommandHandler("btc", btc))
dp.add_handler(CommandHandler("eth", eth))
dp.add_handler(CommandHandler("avax", avax))
dp.add_handler(CommandHandler("calendar", calendar))

# ===== FastAPI endpoints =====
@app.get("/")
def healthcheck():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    # Проверяем секрет (если задан)
    if WEBHOOK_SECRET:
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if given != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="bad secret token")

    data = await request.json()
    update = Update.de_json(data, dp.bot)
    dp.process_update(update)
    return {"ok": True}
