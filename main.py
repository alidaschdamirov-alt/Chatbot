import os
import subprocess
import datetime as dt
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, CallbackContext

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "PUT_YOUR_TOKEN_HERE"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # если зададите, Telegram будет слать тот же secret_token

# Минимальный скрипт, который делает полный скрин страницы (лежит рядом с этим файлом)
# см. screenshot_page.py из предыдущего сообщения
SCRAPER = Path(__file__).with_name("screenshot_page.py")

# Куда сохраняем готовую картинку
OUT_PNG = Path(__file__).with_name("page.png")

# Директория с persistent cookies (для Cloudflare); можно закоммитить её, чтобы куки переживали деплой
USER_DATA_DIR = Path(__file__).with_name("user-data")

# URL из вашего iframe (страница, которую надо сфотографировать)
CALENDAR_URL = (
    "https://www.investing.com/economic-calendar/s-p-global-composite-pmi-1492"
  
)

# Тайминги для скриншота
WAIT_SECONDS = os.environ.get("CAL_WAIT", "20")           # подождать после загрузки
RUN_TIMEOUT = int(os.environ.get("CAL_TIMEOUT", "90"))   # таймаут выполнения, сек

app = FastAPI()



# ===== Инициализация PTB (без polling) =====
updater = Updater(BOT_TOKEN, use_context=True)
dp: Dispatcher = updater.dispatcher


# ===== ХЭНДЛЕРЫ КОМАНД =====
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Привет! Я работаю на вебхуках 🤖\n"
        "Команда: /calendar — пришлю скрин страницы календаря."
    )

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("Команды: /start /help /btc /eth /avax /calendar")

def btc(update: Update, context: CallbackContext):
    update.message.reply_text("BTC: 🟠")

def eth(update: Update, context: CallbackContext):
    update.message.reply_text("ETH: 🔷")

def avax(update: Update, context: CallbackContext):
    update.message.reply_text("AVAX: 🔺")


def calendar(update: Update, context: CallbackContext):
    """Запускает внешний скрипт скринера и отправляет PNG в чат."""
    chat_id = update.effective_chat.id

    if not SCRAPER.exists():
        update.message.reply_text(
            f"❌ Не найден скрипт: {SCRAPER.name}\n"
            f"Создайте рядом файл screenshot_page.py (минимальный скрипт скрина)."
        )
        return

    # Сносим старую картинку, чтобы не отправить прошлую
    try:
        if OUT_PNG.exists():
            OUT_PNG.unlink()
    except Exception:
        pass

    update.message.reply_text("⏳ Делаю скрин страницы…")

    # Команда запуска минимального скрипта скринера
    # ВАЖНО: screenshot_page.py поддерживает именно эти флаги
    cmd = [
        "python", str(SCRAPER),
        "--url", CALENDAR_URL,
        "--out", str(OUT_PNG),
        "--wait", str(WAIT_SECONDS),
        "--user-data-dir", str(USER_DATA_DIR),
        "--headless",
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
        update.message.reply_text(
            f"❌ Скрипт завершился с кодом {proc.returncode}.\n```\n{tail}\n```",
            parse_mode="Markdown",
        )
        return

    if not OUT_PNG.exists():
        update.message.reply_text(
            "❌ Скрин не найден. Возможно, блокировка Cloudflare.\n"
            "Откройте скрипт локально без --headless, пройдите проверку 1 раз, "
            "куки сохранятся в user-data."
        )
        return

    # Отправляем картинку
    caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
    with OUT_PNG.open("rb") as f:
        context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)


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
