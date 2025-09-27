# utils_telegram.py
from html import escape
from telegram.ext import ContextTypes

TG_LIMIT = 4096  # лимит символов в одном сообщении

def _chunks(s: str, size: int):
    for i in range(0, len(s), size):
        yield s[i:i+size]

async def send_table_or_text(chat_id: int, context: ContextTypes.DEFAULT_TYPE, content: str):
    """
    Если content выглядит как Markdown-таблица (строки, начинающиеся с '|'),
    отправляем её как <pre>...</pre> (HTML), чтобы сохранить выравнивание,
    иначе — обычным текстом.
    Длинные тексты режем по лимиту Telegram.
    """
    looks_like_table = content.strip().startswith("|")
    if looks_like_table:
        # экранируем спецсимволы и шлём моноширинно
        payload = f"<pre>{escape(content)}</pre>"
        # режем по лимиту (оставляя место под <pre></pre>)
        # но проще и безопаснее порезать сырое содержимое
        for chunk in _chunks(content, TG_LIMIT - 20):
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"<pre>{escape(chunk)}</pre>",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        for chunk in _chunks(content, TG_LIMIT):
            await context.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                disable_web_page_preview=True,
            )
