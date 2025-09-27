from pathlib import Path
import os

class Settings:
    def __init__(self):
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
        if not self.BOT_TOKEN or self.BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
            raise RuntimeError("Set BOT_TOKEN env")

        self.WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

        self.APP_DIR = Path(__file__).resolve().parent
        self.SCRAPER = self.APP_DIR / "screenshot_page.py"
        self.OUT_PNG = self.APP_DIR / "page.png"
        self.USER_DATA_DIR = self.APP_DIR / "user-data"
        self.USER_DATA_DIR.mkdir(exist_ok=True)

        self.CALENDAR_URL = os.environ.get(
            "CAL_URL", "https://www.investing.com/economic-calendar/unemployment-rate-300"
        )
        self.RUN_TIMEOUT = int(os.environ.get("CAL_TIMEOUT", "150"))
        self.WAIT_FOR = [".common-table", "table"]

settings = Settings()
