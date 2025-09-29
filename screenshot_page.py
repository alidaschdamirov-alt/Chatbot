# screenshot_page.py
import argparse, asyncio, time, sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

NAV_TIMEOUT = 45_000
SEL_TIMEOUT = 20_000
RETRIES = 2
FULLPAGE_SCROLL_PAUSE = 280

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",                # Onetrust (часто на investing)
    "text=Accept All", "text=I Accept",            # англ. варианты
    "[data-qa-id='accept-all']",
]

POPUP_SELECTORS = [
    "button[aria-label='Close']", ".popupCloseIcon",
    ".closeBtn", ".close", ".icon-close",
]

async def gentle_scroll(page):
    last = await page.evaluate("() => document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(FULLPAGE_SCROLL_PAUSE/1000)
        new = await page.evaluate("() => document.body.scrollHeight")
        if new == last:
            break
        last = new

async def maybe_click(page, selector, timeout=3000):
    try:
        loc = page.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout)
        await loc.click(timeout=timeout)
        print(f"[click] {selector}")
        return True
    except Exception:
        return False

async def goto_with_retries(page, url: str):
    last_err = None
    for attempt in range(1, RETRIES+1):
        try:
            print(f"[goto] attempt {attempt} -> {url}")
            resp = await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT)
            code = resp.status if resp else "n/a"
            print(f"[goto] status={code}")
            return
        except Exception as e:
            last_err = e
            print(f"[goto] fail #{attempt}: {e}")
            await asyncio.sleep(1.0*attempt)
            try:
                resp = await page.reload(wait_until="load", timeout=NAV_TIMEOUT)
                code = resp.status if resp else "n/a"
                print(f"[reload] status={code}")
                return
            except Exception as e2:
                last_err = e2
    if last_err:
        raise last_err

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="page.png")
    ap.add_argument("--width", type=int, default=1366)
    ap.add_argument("--height", type=int, default=1100)
    ap.add_argument("--user-data-dir", default=None)
    ap.add_argument("--wait-for", action="append")
    ap.add_argument("--sleep-ms", type=int, default=1500)
    args = ap.parse_args()

    out_path = Path(args.out)
    debug_dir = out_path.parent
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    debug_html = debug_dir / f"debug_{stamp}.html"
    debug_png  = debug_dir / f"debug_{stamp}.png"

    async with async_playwright() as pw:
        bt = pw.chromium
        launch_kwargs = dict(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        if args.user_data_dir:
            context = await bt.launch_persistent_context(
                args.user_data_dir,
                **launch_kwargs,
                user_agent=UA, locale="en-US",
                viewport={"width": args.width, "height": args.height},
                extra_http_headers={"Accept-Language":"en-US,en;q=0.9,ru;q=0.6"},
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await bt.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=UA, locale="en-US",
                viewport={"width": args.width, "height": args.height},
                extra_http_headers={"Accept-Language":"en-US,en;q=0.9,ru;q=0.6"},
            )
            page = await context.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            window.chrome={runtime:{}};
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4]});
        """)

        try:
            await goto_with_retries(page, args.url)

            # cookies / popups
            for sel in COOKIE_SELECTORS:
                await maybe_click(page, sel, 4000)
            for sel in POPUP_SELECTORS:
                await maybe_click(page, sel, 1500)

            # мягкая пауза и скролл
            if args.sleep_ms > 0:
                await asyncio.sleep(args.sleep_ms/1000)
            await gentle_scroll(page)

            # сохранить HTML для диагностики
            try:
                html = await page.content()
                debug_html.write_text(html, encoding="utf-8", errors="ignore")
                print(f"[dump] html -> {debug_html}")
            except Exception as e:
                print(f"[dump] html fail: {e}")

            # делаем скрин в любом случае
            await page.screenshot(path=str(out_path), full_page=True)
            await page.screenshot(path=str(debug_png), full_page=True)
            print(f"[ok] saved screenshot -> {out_path}")
            print(f"[ok] saved debug screenshot -> {debug_png}")

            await context.close()
        except Exception as e:
            # при фатальной ошибке попробуем хоть что-то сохранить
            try:
                html = await page.content()
                debug_html.write_text(html, encoding="utf-8", errors="ignore")
                await page.screenshot(path=str(debug_png), full_page=True)
                print(f"[dump-on-error] html={debug_html}, png={debug_png}")
            except Exception:
                pass
            print(f"[fatal] {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    import asyncio as _a
    _a.run(main())
