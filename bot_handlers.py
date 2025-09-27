import sys, tempfile, datetime as dt
from html import escape
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from settings import settings
from idempotency import chat_lock
from screenshot_service import build_scraper_cmd, run_scraper
from ai_analysis import analyze_calendar_image_openai

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Используй /calendar, чтобы получить скрин и анализ.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды: /start /help /btc /eth /avax /calendar")

async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("BTC: 🟠")

async def eth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ETH: 🔷")

async def avax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("AVAX: 🔺")

async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lock = chat_lock(chat_id)

    if lock.locked():
        await update.message.reply_text("⏳ Уже делаю предыдущий скрин...")
        return

    async with lock:
        await update.message.reply_text("🧑‍💻 Делаю скрин страницы…")
        cmd = build_scraper_cmd(sys.executable, settings.SCRAPER, settings.CALENDAR_URL, settings.OUT_PNG, settings.USER_DATA_DIR, settings.WAIT_FOR)

        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "scraper.log"
            try:
                proc = await context.application.run_in_executor(None, lambda: run_scraper(cmd, settings.RUN_TIMEOUT, log_path))
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка запуска: {e}")
                return
            if proc.returncode != 0:
                tail = log_path.read_text(encoding="utf-8", errors="ignore")[-1500:]
                await update.message.reply_text(f"❌ Ошибка скрина<pre>{escape(tail)}</pre>", parse_mode="HTML")
                return

        if not settings.OUT_PNG.exists():
            await update.message.reply_text("❌ Скрин не получен, возможно защита сайта.")
            return

        # Фото
        caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
        with settings.OUT_PNG.open("rb") as f:
            await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)

        # Анализ
        if settings.OPENAI_API_KEY:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            analysis = await context.application.run_in_executor(
                None, lambda: analyze_calendar_image_openai(settings.OUT_PNG, settings.OPENAI_API_KEY)
            )
            await context.bot.send_message(chat_id=chat_id, text=analysis)
        else:
            await context.bot.send_message(chat_id=chat_id, text="ℹ️ Анализ отключён: задайте OPENAI_API_KEY.")

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("btc", btc))
    app.add_handler(CommandHandler("eth", eth))
    app.add_handler(CommandHandler("avax", avax))
    app.add_handler(CommandHandler("calendar", calendar))
