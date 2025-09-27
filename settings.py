from pathlib import Path
import os

class Settings:
    def __init__(self):
        # === ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ===
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
        if not self.BOT_TOKEN or self.BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
            raise RuntimeError("Set BOT_TOKEN env")

        # секрет вебхука (если задан)
        self.WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

        # ключ OpenAI для анализа скринов
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

        # === ПУТИ ===
        self.APP_DIR = Path(__file__).resolve().parent
        self.SCRAPER = self.APP_DIR / "screenshot_page.py"
        self.OUT_PNG = self.APP_DIR / "page.png"
        self.USER_DATA_DIR = self.APP_DIR / "user-data"
        self.USER_DATA_DIR.mkdir(exist_ok=True)

        # === ССЫЛКИ ДЛЯ СКРИНОВ ===
        # Список страниц через запятую: CAL_URLS="https://a.com/x,https://b.com/y"
        urls_env = os.environ.get("CAL_URLS", "").strip()
        if not urls_env:
            raise RuntimeError(
                "Не задан CAL_URLS — укажите список страниц через запятую, "
                "например: CAL_URLS='https://a.com/page1,https://a.com/page2'"
            )
        self.BATCH_URLS = [u.strip() for u in urls_env.split(",") if u.strip()]
        if not self.BATCH_URLS:
            raise RuntimeError("CAL_URLS пуст — укажите хотя бы один URL")

        # === НАСТРОЙКИ ОЖИДАНИЯ И ТАЙМАУТОВ ===
        # Селекторы для ожидания загрузки (по умолчанию пусто, ждём только load+sleep)
        extra_sel = os.environ.get("CAL_WAIT_FOR", "")
        self.WAIT_FOR = (
            [s for s in extra_sel.split(",") if s.strip()] if extra_sel else []
        )

        # пауза после load перед скрином (мс)
        self.SLEEP_MS = int(os.environ.get("CAL_SLEEP_MS", "2000"))  # 2 секунды

        # пауза между страницами (batch mode)
        self.BATCH_SLEEP_MS = int(os.environ.get("BATCH_SLEEP_MS", "250"))

        # общий таймаут работы скрипта (сек)
        self.RUN_TIMEOUT = int(os.environ.get("CAL_TIMEOUT", "150"))

settings = Settings()
