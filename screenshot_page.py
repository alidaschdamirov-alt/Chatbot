#!/usr/bin/env python3
import argparse, os, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

def parse_args():
    p = argparse.ArgumentParser(description="Full-page screenshot via Playwright")
    p.add_argument("--url", required=True, help="HTTP(S) URL или путь к локальному файлу (page.html)")
    p.add_argument("--out", default="page.png", help="PNG файл для сохранения")
    p.add_argument("--wait", type=float, default=6.0, help="Секунды подождать после загрузки")
    p.add_argument("--timeout", type=int, default=45000, help="Таймаут загрузки, мс")
    p.add_argument("--user-data-dir", default=None, help="Папка профиля (для куков)")
    # Управление headless: по умолчанию True (на сервере), можно выключить локально через ENV HEADFUL=1
    p.add_argument("--headless", action="store_true", help="Принудительно headless=True")
    return p.parse_args()

def normalize_url(raw: str) -> str:
    """Если это путь к существующему файлу — вернём file://… URI; иначе оставим как есть."""
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https", "file"):
        return raw
    # нет схемы — возможно, это локальный файл
    p = Path(raw)
    if p.exists():
        return p.resolve().as_uri()  # file:///abs/path.html
    # иначе это действительно невалидный URL/путь
    raise ValueError(f"Invalid URL or file path: {raw}")

def main():
    a = parse_args()
    # headless по умолчанию True; локально можно выставить HEADFUL=1
    headless = not (os.getenv("HEADFUL", "0") == "1")
    if a.headless:
        headless = True

    target = normalize_url(a.url)

    with sync_playwright() as p:
        # важные флаги для контейнеров: no-sandbox, disable-dev-shm-usage
        launch_kwargs = dict(headless=headless, args=["--disable-dev-shm-usage", "--no-sandbox"])
        # (опционально) если грузите локальные ресурсы из file://, можно добавить:
        # launch_kwargs["args"] += ["--allow-file-access-from-files"]

        if a.user_data_dir:
            ctx = p.chromium.launch_persistent_context(a.user_data_dir, **launch_kwargs)
            page = ctx.new_page()
        else:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context()
            page = ctx.new_page()

        try:
            page.goto(target, wait_until="networkidle", timeout=a.timeout)
        except PWTimeoutError:
            page.wait_for_load_state("domcontentloaded")

        if a.wait > 0:
            time.sleep(a.wait)

        page.screenshot(path=a.out, full_page=True)
        print(f"✅ saved: {a.out}")
        ctx.close()

if __name__ == "__main__":
    main()
