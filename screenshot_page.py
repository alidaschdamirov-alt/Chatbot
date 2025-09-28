# screenshot_page.py
import argparse, asyncio, time, sys
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

NAV_TIMEOUT = 45_000
SEL_TIMEOUT = 25_000
RETRIES = 2
FULLPAGE_SCROLL_PAUSE = 280

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# набор разумных селекторов для investing (можно дополнять через --wait-for)
DEFAULT_SELECTORS = [
    "#onetrust-accept-btn-handler",                 # cookie banner
    "text=U.S. Unemployment Rate",                  # заголовок страницы
    "table.genTbl",                                 # общие таблицы сайта
    ".common-table", "table",                       # запасные
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

async def maybe_click(page, selector, timeout=4000):
    try:
        btn = page.locator(selector).first
        await btn.wait_for(state="visible", timeout=timeout)
        await btn.click(timeout=timeout)
        print(f"[click] {selector}")
        return True
    except Exception:
        return False

async def goto_with_retries(page, url: str):
    last_err = None
    for attempt in range(1, RETRIES+1):
        try:
            print(f"[goto] attempt {attempt} -> {url}")
            await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT)
            return
        except Exception as e:
            last_err = e
            print(f"[goto] fail #{attempt}: {e}")
            await asyncio.sleep(1.0*attempt)
            try:
                await page.reload(wait_until="load", timeout=NAV_TIMEOUT)
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
    ap.add_argument("--wait-for", action="append", help="доп. CSS-селектор(ы) для мягкого ожидания")
    ap.add_argument("--sleep-ms", type=int, default=1500, help="пауза после load")
    args = ap.parse_args()

    out_path = Path(args.out)
    wait_selectors = (args.wait_for or []) + DEFAULT_SELECTORS

    async with async_playwright() as pw:
        bt = pw.chromium
        launch_kwargs = dict(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )

        # persistent context сохраняет куки (важно для investing/cf)
        if args.user_data_dir:
            context = await bt.launch_persistent_context(
                args.user_data_dir,
                **launch_kwargs,
                user_agent=UA,
                locale="en-US",
                viewport={"width": args.width, "height": args.height},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9,ru;q=0.6"},
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await bt.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=UA,
                locale="en-US",
                viewport={"width": args.width, "height": args.height},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9,ru;q=0.6"},
            )
            page = await context.new_page()

        # простые анти-бот скрипты
        await page.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            window.chrome={runtime:{}};
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4]});
        """)

        # навигация
        await goto_with_retries(page, args.url)

        # закрыть cookie баннер, если есть
        await maybe_click(page, "#onetrust-accept-btn-handler", 5000)

        # иногда всплывает баннер авторизации
        await maybe_click(page, "button[aria-label='Close']", 2000)
        await maybe_click(page, ".popupCloseIcon", 2000)

        # мягкое ожидание нужных блоков (но не критично)
        found = False
        for sel in wait_selectors:
            try:
                await page.wait_for_selector(sel, timeout=SEL_TIMEOUT, state="visible")
                print(f"[wait] visible: {sel}")
                found = True
                break
            except PWTimeout:
                continue

        # пауза после load и лёгкий скролл
        if args.sleep_ms > 0:
            await asyncio.sleep(args.sleep_ms/1000)
        await gentle_scroll(page)

        # делаем скрин в любом случае
        await page.screenshot(path=str(out_path), full_page=True)
        print(f"[ok] saved screenshot -> {out_path.resolve()}")

        await context.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        sys.exit(1)
