import os
import sys
import asyncio
import subprocess
import datetime as dt
from pathlib import Path
from html import escape

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
    raise RuntimeError("Set BOT_TOKEN env")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # если зададите, Telegram будет слать тот же secret_token

# Минимальный скрипт, который делает полный скрин страницы (лежит рядом с этим файлом)
SCRAPER = Path(__file__).with_name("screenshot_page.py")

# Куда сохраняем готовую картинку
OUT_PNG = Path(__file__).with_name("page.png")

# Директория с persistent cookies (для Cloudflare); можно закоммитить её, чтобы куки переживали деплой
USER_DATA_DIR = Path(__file__).with_name("user-data")

# URL из вашего iframe (страница, которую надо сфотографировать)
CALENDAR_URL = os.environ.get(
    "CAL_URL",
    "https://www.investing.com/economic-calendar/cpi-68"
)

# Тайминги для скриншота
WAIT_SECONDS = int(os.environ.get("CAL_WAIT", "50"))          # подождать после загрузкиdd
RUN_TIMEOUT = int(os.environ.get("CAL_TIMEOUT", "90"))        # таймаут выполнения, сек

# ===== FastAPI app =====
app = FastAPI(title="TG Bot Webhook + Screenshot")

# ===== PTB Application (v20+) =====
application = ApplicationBuilder().token(BOT_TOKEN).build() 
 


# ===== ХЭНДЛЕРЫ КОМАНД =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я работаю на вебхуках 🤖\n"
        "Команда: /calendar — пришлю скрин страницы календаря."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды: /start /help /btc /eth /avax /calendar")

async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("BTC: 🟠")

async def eth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ETH: 🔷")

async def avax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("AVAX: 🔺")


async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает внешний скрипт скринера и отправляет PNG в чат."""
    chat_id = update.effective_chat.id

    if not SCRAPER.exists():
        await update.message.reply_text(
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

    await update.message.reply_text("⏳ Делаю скрин страницы…")

    # Команда запуска минимального скрипта скринера
    # ВАЖНО: screenshot_page.py поддерживает именно эти флаги
    cmd = [
        sys.executable, str(SCRAPER),
        "--url", CALENDAR_URL,
        "--out", str(OUT_PNG),
        "--wait", str(WAIT_SECONDS),
        "--user-data-dir", str(USER_DATA_DIR),
        "--headless",
    ]

    loop = asyncio.get_running_loop()
    try:
        # subprocess.run блокирующий — выносим в executor
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT
            )
        )
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏳ Время ожидания вышло. Попробуйте ещё раз.")
        return
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка запуска: {e}")
        return

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1800:]
        # Безопасный HTML, чтобы не падать на разметке Telegram
        await update.message.reply_text(
            f"❌ Скрипт завершился с кодом {proc.returncode}.<pre>{escape(tail)}</pre>",
            parse_mode="HTML",
        )
        return

    if not OUT_PNG.exists():
        await update.message.reply_text(
            "❌ Скрин не найден. Возможно, блокировка Cloudflare.\n"
            "Откройте скрипт локально без --headless, пройдите проверку 1 раз, "
            "куки сохранятся в user-data."
        )
        return

    # Отправляем картинку
    caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
    with OUT_PNG.open("rb") as f:
        await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)


# Регистрируем команды
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("btc", btc))
application.add_handler(CommandHandler("eth", eth))
application.add_handler(CommandHandler("avax", avax))
application.add_handler(CommandHandler("calendar", calendar))


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
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
