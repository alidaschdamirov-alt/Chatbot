# bot_handlers.py
from __future__ import annotations

import sys
import tempfile
import datetime as dt
import asyncio
from html import escape
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from settings import settings
from idempotency import chat_lock
from screenshot_service import (
    build_scraper_cmd,
    run_scraper,
    capture_page,   # утилита-обёртка (если нет — можно заменить на build_scraper_cmd+run_scraper)
    sleep_ms,       # короткая пауза между страницами
)
from ai_analysis import analyze_calendar_image_openai
from utils_telegram import send_table_or_text


# ---------- Базовые команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я умею:\n"
        "• /calendar — сделать скрин, извлечь таблицу показателей и прислать\n"
        "• /batch — собрать таблицы с заданного списка страниц (CAL_URLS)\n"
        "Дополнительно доступны /btc /eth /avax /help"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "• /calendar — скрин + извлечение таблицы (Actual/Forecast/Previous)\n"
        "• /batch — пройтись по списку CAL_URLS и вернуть все таблицы одним сообщением\n"
        "• /btc /eth /avax — тестовые команды\n"
    )


async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("BTC: 🟠")


async def eth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ETH: 🔷")


async def avax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("AVAX: 🔺")


# ---------- Одна страница: скрин + анализ ----------

async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lock = chat_lock(chat_id)

    if lock.locked():
        await update.message.reply_text("⏳ Уже выполняется предыдущая задача…")
        return

    async with lock:
        # на всякий случай уберём старый файл
        try:
            if settings.OUT_PNG.exists():
                settings.OUT_PNG.unlink()
        except Exception:
            pass

        await update.message.reply_text("🧑‍💻 Делаю скрин страницы…")

        # Команда для скриншота
        cmd = build_scraper_cmd(
            python_exec=sys.executable,
            scraper=settings.SCRAPER,
            url=settings.BATCH_URLS[0],  # берём ПЕРВУЮ страницу из списка как «основную»
            out_png=settings.OUT_PNG,
            user_data_dir=settings.USER_DATA_DIR,
            wait_for=settings.WAIT_FOR,
            sleep_ms=settings.SLEEP_MS,
        )

        # Запуск подпроцесса в executor
        loop = asyncio.get_running_loop()
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "scraper.log"
            try:
                proc = await loop.run_in_executor(
                    None,
                    lambda: run_scraper(cmd, settings.RUN_TIMEOUT, log_path),
                )
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка запуска: {e}")
                return

            if proc.returncode != 0:
                # прикрепим хвост лога — удобно дебажить
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="ignore")[-1500:]
                except Exception:
                    pass
                await update.message.reply_text(
                    f"❌ Ошибка скринера (код {proc.returncode}).<pre>{escape(tail)}</pre>",
                    parse_mode="HTML",
                )
                return

        if not settings.OUT_PNG.exists():
            await update.message.reply_text("❌ Скрин не получен (возможна защита сайта).")
            return

        # 1) фото
        caption = f"Экономический календарь • {dt.datetime.now():%Y-%m-%d %H:%M}"
        with settings.OUT_PNG.open("rb") as f:
            await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)

        # 2) извлечение таблицы
        if settings.OPENAI_API_KEY:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            table = await loop.run_in_executor(
                None,
                lambda: analyze_calendar_image_openai(settings.OUT_PNG, settings.OPENAI_API_KEY),
            )
            await send_table_or_text(chat_id, context, table)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text="ℹ️ Анализ отключён: задайте OPENAI_API_KEY."
            )


# ---------- Батч по конкретному списку URL-ов ----------

async def batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lock = chat_lock(chat_id)

    if lock.locked():
        await update.message.reply_text("⏳ Уже выполняется другая операция…")
        return

    urls = settings.BATCH_URLS
    total = len(urls)
    if total == 0:
        await update.message.reply_text("❌ Список CAL_URLS пуст.")
        return

    await update.message.reply_text(f"🚀 Стартую сбор с {total} страниц. Это может занять несколько минут…")

    async with lock:
        combined_parts: list[str] = []
        loop = asyncio.get_running_loop()

        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)

            for idx, url in enumerate(urls, start=1):
                out_png = tmpdir / f"page_{idx:02d}.png"
                log_path = tmpdir / f"scraper_{idx:02d}.log"

                # — 1) скрин
                try:
                    proc = await loop.run_in_executor(
                        None,
                        lambda: capture_page(
                            sys.executable, settings.SCRAPER, url, out_png,
                            settings.USER_DATA_DIR, settings.WAIT_FOR, settings.SLEEP_MS,
                            settings.RUN_TIMEOUT, log_path
                        ),
                    )
                    ok = proc.returncode == 0 and out_png.exists()
                except Exception as e:
                    ok = False
                    err = str(e)

                if not ok:
                    # читаем хвост лога, если есть
                    tail = ""
                    try:
                        tail = log_path.read_text(encoding="utf-8", errors="ignore")[-800:]
                    except Exception:
                        pass
                    header = f"| Источник {idx}: {url} |\n|---|"
                    table = "| Показатель | Факт | Прогноз | Предыдущий |\n|---|---:|---:|---:|\n| Ошибка захвата |  |  |  |"
                    if tail:
                        table = f"| Показатель | Факт | Прогноз | Предыдущий |\n|---|---:|---:|---:|\n| Ошибка: {escape(tail)[:200]} |  |  |  |"
                    combined_parts.append(header + "\n" + table)
                    sleep_ms(settings.BATCH_SLEEP_MS)
                    continue

                # — 2) извлечение таблицы
                table = await loop.run_in_executor(
                    None,
                    lambda: analyze_calendar_image_openai(out_png, settings.OPENAI_API_KEY),
                )

                if not table.strip().startswith("|"):
                    table = (
                        "| Показатель | Факт | Прогноз | Предыдущий |\n"
                        "|---|---:|---:|---:|\n"
                        "| Нет распознаваемых показателей |  |  |  |"
                    )

                header = f"| Источник {idx}: {url} |\n|---|"
                combined_parts.append(header + "\n" + table)

                # — 3) пауза между страницами
                sleep_ms(settings.BATCH_SLEEP_MS)

        # — 4) финальная склейка и отправка
        big = "\n\n".join(combined_parts)
        await send_table_or_text(chat_id, context, big)


# ---------- Регистрация хендлеров ----------

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("btc", btc))
    app.add_handler(CommandHandler("eth", eth))
    app.add_handler(CommandHandler("avax", avax))
    app.add_handler(CommandHandler("calendar", calendar))
    app.add_handler(CommandHandler("batch", batch))
