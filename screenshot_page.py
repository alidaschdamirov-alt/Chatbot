#!/usr/bin/env python3
"""
Минимальный скрипт: открыть страницу в Playwright и сделать полный скриншот.

Пример запуска:
  python screenshot_page.py --url "https://sslecal2.investing.com?..." --out page.png --wait 5 --headless
"""

import argparse
import time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

def parse_args():
    p = argparse.ArgumentParser(description="Take full-page screenshot with Playwright")
    p.add_argument("--url", required=True, help="URL страницы для скриншота")
    p.add_argument("--out", default="page.png", help="Куда сохранить PNG")
    p.add_argument("--wait", type=float, default=4.0, help="Секунд подождать после загрузки")
    p.add_argument("--timeout", type=int, default=35000, help="Таймаут загрузки, мс")
    p.add_argument("--user-data-dir", default=None, help="Каталог для сохранения cookies (если нужен обход Cloudflare)")
    return p.parse_args()

def main():
    args = parse_args()

    with sync_playwright() as p:
        if args.user_data_dir:
            ctx = p.chromium.launch_persistent_context(args.user_data_dir, headless=args.headless)
            page = ctx.new_page()
        else:
            browser = p.chromium.launch(headless=args.headless)
            page = browser.new_page()

        try:
            page.goto(args.url, wait_until="networkidle", timeout=args.timeout)
        except PWTimeoutError:
            page.wait_for_load_state("domcontentloaded")

        if args.wait > 0:
            time.sleep(args.wait)

        page.screenshot(path=args.out, full_page=True)
        print(f"✅ Скриншот сохранён: {args.out}")

        if args.user_data_dir:
            ctx.close()
        else:
            page.context.browser.close()

if __name__ == "__main__":
    main()
