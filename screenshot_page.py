#!/usr/bin/env python3
import argparse, time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

def parse_args():
    p = argparse.ArgumentParser(description="Full-page screenshot with visible browser")
    p.add_argument("--url", required=True)
    p.add_argument("--out", default="page.png")
    p.add_argument("--wait", type=float, default=6.0)
    p.add_argument("--timeout", type=int, default=45000)
    p.add_argument("--user-data-dir", default=None)
    p.add_argument("--user-agent", default=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ))
    p.add_argument("--timezone", default="Etc/GMT")
    return p.parse_args()

def main():
    a = parse_args()
    with sync_playwright() as p:
        launch_kwargs = dict(headless=False, args=["--disable-dev-shm-usage"])
        if a.user_data_dir:
            ctx = p.chromium.launch_persistent_context(
                a.user_data_dir,
                **launch_kwargs,
                user_agent=a.user_agent,
                locale="en-US",
                timezone_id=a.timezone,
                viewport={"width": 1600, "height": 1200},
            )
            page = ctx.new_page()
        else:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                user_agent=a.user_agent,
                locale="en-US",
                timezone_id=a.timezone,
                viewport={"width": 1600, "height": 1200},
            )
            page = ctx.new_page()

        try:
            page.goto(a.url, wait_until="networkidle", timeout=a.timeout)
        except PWTimeoutError:
            page.wait_for_load_state("domcontentloaded")

        if a.wait > 0:
            time.sleep(a.wait)

        page.screenshot(path=a.out, full_page=True)
        print(f"✅ Скриншот сохранён: {a.out}")
        ctx.close()

if __name__ == "__main__":
    main()
