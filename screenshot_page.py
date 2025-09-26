#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path
import sys

from playwright.async_api import async_playwright

async def main():
    parser = argparse.ArgumentParser(description="Скриншот страницы")
    parser.add_argument("--url", required=True, help="URL страницы")
    parser.add_argument("--out", required=True, help="Путь к PNG")
    parser.add_argument("--wait", type=int, default=10, help="Сколько секунд ждать после загрузки")
    parser.add_argument("--user-data-dir", default=None, help="Директория профиля Chromium")
    parser.add_argument("--headless", action="store_true", help="Запуск без интерфейса")
    parser.add_argument("--extra-chrome-flags", default="", help="Доп. флаги для Chromium")
    args = parser.parse_args()

    # Парсим флаги для Chromium
    extra_args = []
    if args.extra_chrome_flags:
        extra_args = args.extra_chrome_flags.split()

    # Используем Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=args.user_data_dir or None,
            headless=args.headless,
            args=extra_args,
            viewport={"width": 1200, "height": 1600}
        )
        page = await browser.new_page()
        try:
            print(f"[INFO] Открываю {args.url}")
            await page.goto(args.url, wait_until="networkidle")
            await page.wait_for_timeout(args.wait * 1000)

            out_path = Path(args.out)
            await page.screenshot(path=str(out_path), full_page=True)
            print(f"[INFO] Скриншот сохранён в {out_path.resolve()}")
        finally:
            await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
