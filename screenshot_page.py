# screenshot_page.py
import argparse, asyncio, time
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Настройки по умолчанию
NAV_TIMEOUT = 120_000          # 120с
SEL_TIMEOUT = 120_000
FULLPAGE_SCROLL_PAUSE = 350    # мс между скроллами
RETRIES = 3                    # число попыток goto
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Под конкретную страницу выберите один из селекторов ниже или передайте через --wait-for
DEFAULT_WAIT_SELECTORS = [
    "#economicCalendar",                      # пример общий
    ".common-table",                          # таблица на investing
    "[data-test=calendar-table]",             # возможный data-test
    "table",                                  # запасной
]

async def gentle_scroll(page):
    last_height = await page.evaluate("() => document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(FULLPAGE_SCROLL_PAUSE/1000)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

async def goto_with_retries(page, url: str, referrer: str | None = None):
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"[goto] attempt {attempt} -> {url}")
            await page.goto(
                url,
                wait_until="domcontentloaded",  # НЕ networkidle
                timeout=NAV_TIMEOUT,
                referer=referrer,
            )
            return
        except PlaywrightTimeout as e:
            last_err = e
            print(f"[goto] timeout on attempt {attempt}: {e}")
            # маленькая пауза и твёрдый reload как альтернатива
            await asyncio.sleep(1.5 * attempt)
            try:
                await page.reload(wait_until="load", timeout=NAV_TIMEOUT)
                return
            except Exception as re:
                print(f"[reload] failed after attempt {attempt}: {re}")
    raise last_err

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="page.png")
    ap.add_argument("--width", type=int, default=1366)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--user-data-dir", default=None)  # для persistent контекста
    ap.add_argument("--wait-for", action="append", help="CSS селектор(ы) для ожидания")
    ap.add_argument("--lang", default="ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
    args = ap.parse_args()

    wait_selectors = args.wait_for or DEFAULT_WAIT_SELECTORS
    out_path = Path(args.out)

    async with async_playwright() as pw:
        browser_type = pw.chromium

        launch_kwargs = dict(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # persistent context — лучше переживает Cloudflare (куки сохраняются)
        if args.user_data_dir:
            context = await browser_type.launch_persistent_context(
                args.user_data_dir,
                **launch_kwargs,
                user_agent=UA,
                locale="ru-RU",
                viewport={"width": args.width, "height": args.height},
                extra_http_headers={
                    "Accept-Language": args.lang,
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await browser_type.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=UA,
                locale="ru-RU",
                viewport={"width": args.width, "height": args.height},
                extra_http_headers={
                    "Accept-Language": args.lang,
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = await context.new_page()

        # лёгкая «маскировка» автомации (часто помогает против челленджа)
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU','ru','en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)

        # Навигация с ретраями
        await goto_with_retries(page, args.url)

        # Доп. ожидание конкретного контента (любой из списка)
        found = False
        start = time.time()
        for sel in wait_selectors:
            try:
                await page.wait_for_selector(sel, timeout=SEL_TIMEOUT, state="visible")
                print(f"[wait] visible selector: {sel}")
                found = True
                break
            except PlaywrightTimeout:
                print(f"[wait] not found: {sel}")
                continue

        if not found:
            # как минимум дождёмся полной стадии 'load', но без networkidle
            try:
                await page.wait_for_load_state("load", timeout=SEL_TIMEOUT//2)
            except Exception:
                pass
            print(f"[warn] ни один селектор не найден за {time.time()-start:.1f}s — делаем скрин как есть")

        # Прокрутка для ленивых таблиц
        await gentle_scroll(page)

        # Скрин
        await page.screenshot(path=str(out_path), full_page=True)
        print(f"[ok] saved screenshot -> {out_path.resolve()}")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
