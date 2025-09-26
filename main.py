import os
import sys
import asyncio
import subprocess
import datetime as dt
from pathlib import Path
from html import escape
import tempfile
import time
from collections import OrderedDict, defaultdict

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
    raise RuntimeError("Set BOT_TOKEN env")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

SCRAPER = Path(__file__).with_name("screenshot_page.py")
OUT_PNG = Path(__file__).with_name("page.png")
USER_DATA_DIR = Path(__file__).with_name("user-data")
USER_DATA_DIR.mkdir(exist_ok=True)

CALENDAR_URL = os.environ.get("CAL_URL", "https://ru.investing.com/economic-calendar/unemployment-rate-300")
RUN_TIMEOUT = int(os.environ.get("CAL_TIMEOUT", "150"))  # таймаут подпроцесса

# ===== ИДЕМПОТЕНТНОСТЬ & ЛОКИ =====
SEEN_TTL = 600  # сек хранить update_id (10 минут)
SEEN_MAX = 2000
_seen_updates: "OrderedDict[int, float]" = OrderedDict()  # update_id -> ts
_chat_locks: "defaultdict[int, asyncio.Lock]" = defaultdict(asyncio.Lock)

def remember_update(update_id: int) -> bool:
    """True если это НОВЫЙ update_id; False если уже видели (дубликат)."""
    now = time.time()
    # удалить протухшие
    while _seen_updates and now - next(iter(_seen_updates.values())) > SEEN_TTL:
        _seen_updates.popitem(last=False)
    if update_id in _seen_updates:
        return False
    _seen_updates[update_id] = now
    # не раздувать память
    while len(_seen_updates) > SEEN_MAX:
        _seen_updates.popitem(last=False)
    return True

# ===== FastAPI app & PTB =====
app = FastAPI(title="TG Bot Webhook + Screenshot")
application = ApplicationBuilder().token(BOT_TOKEN).build()

@app.on_event("startup")
async def _on_startup():
    await application.initialize()
    await application.start()

@app.on_event("shutdown")
async def _on_shutdown():
    await application.stop()
    await application.shutdown()

# ===== ХЭНДЛЕРЫ =====
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
    chat_id = update.effective_chat.id
    lock = _chat_locks[chat_id]

    # предотвращаем повторный запуск, если предыдущий ещё идёт
    if lock.locked():
        await update.message.reply_text("⏳ Уже делаю предыдущий скрин. Подождите пару секунд…")
        return

    if not SCRAPER.exists():
        await update.message.reply_text(f"❌ Не найден {SCRAPER.name}. Положите рядом screenshot_page.py")
        return

    # всё внутри лока
    async with lock:
        try:
            if OUT_PNG.exists():
                OUT_PNG.unlink()
        except Exception:
            pass

        await update.message.reply_text("🧑‍💻 Делаю скрин страницы…")

        cmd = [
            sys.executable, str(SCRAPER),
            "--url", CALENDAR_URL,
            "--out", str(OUT_PNG),
            "--user-data-dir", str(USER_DATA_DIR),
            "--wait-for", ".common-table",
            "--wait-for", "table",
        ]

        loop = asyncio.get_running_loop()
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "scraper.log"
            with log_path.open("w", encoding="utf-8") as lf:
                try:
                    proc = await loop.run_in_executor(
                        None,
                        lambda: subprocess.run(
                            cmd,
                            stdout=lf,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=RUN_TIMEOUT,
                        )
                    )
                except subprocess.TimeoutExpired:
                    await update.message.reply_text("⏳ Таймаут. Попробуйте ещё раз.")
                    return
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Ошибка запуска: {e}")
                    return

            if proc.returncode != 0:
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="ignore")[-1800:]
                except Exception:
                    tail = ""
                await update.message.reply_text(
                    f"❌ Скрипт завершился с кодом {proc.returncode}.<pre>{escape(tail)}</pre>",
                    parse_mode="HTML",
                )
                return

        if not OUT_PNG.exists():
            await update.message.reply_text(
                "❌ Скрин не получен (возможна защита сайта). "
                "Откройте локально без headless, чтобы сохранить куки в user-data."
            )
            return

        caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
        with OUT_PNG.open("rb") as f:
            await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)

# регистрируем команды
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("btc", btc))
application.add_handler(CommandHandler("eth", eth))
application.add_handler(CommandHandler("avax", avax))
application.add_handler(CommandHandler("calendar", calendar))

# ===== Вебхук =====
@app.post("/webhook")
async def telegram_webhook(request: Request):
    if WEBHOOK_SECRET:
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if given != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="bad secret token")

    data = await request.json()
    update = Update.de_json(data, application.bot)

    # --- ИДЕМПОТЕНТНОСТЬ ---
    if not remember_update(update.update_id):
        # дубликат — подтверждаем и выходим
        return {"ok": True}

    # обрабатываем в фоне, чтобы ответить Telegram сразу (без 499/повторов)
    asyncio.create_task(application.process_update(update))
    return {"ok": True}

@app.get("/")
def healthcheck():
    return {"status": "ok"}
