# screenshot_page.py
import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# Таймауты и попытки
NAV_TIMEOUT = 30_000     # навигация до DOMContentLoaded
SEL_TIMEOUT = 15_000     # ожидание селекторов
RETRIES     = 1          # меньше ретраев -> быстрее фэйл

# Глобальный сторож выполнения всего скрипта (должен быть меньше RUN_TIMEOUT у подпроцесса)
GLOBAL_TIMEOUT = 95      # секунд

# User-Agent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Селекторы для кликов
COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",     # Onetrust (Investing)
    "text=Accept All",
    "text=I Accept",
    "[data-qa-id='accept-all']",
]
POPUP_SELECTORS = [
    "button[aria-label='Close']",
    ".popupCloseIcon",
    ".closeBtn",
    ".icon-close",
    ".close",
]


async def gentle_scroll(page, step_ms=280):
    """Плавный скролл вниз до упора, чтобы подгрузились ленивые блоки."""
    last = await page.evaluate("() => document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(step_ms / 1000)
        new = await page.evaluate("() => document.body.scrollHeight")
        if new == last:
            break
        last = new


async def maybe_click(page, selector: str, timeout: int = 3000) -> bool:
    try:
        loc = page.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout)
        await loc.click(timeout=timeout)
        print(f"[click] {selector}")
        return True
    except Exception:
        return False


async def goto_with_retries(page, url: str):
    """Навигация без ожидания 'load': ждём domcontentloaded + короткое networkidle."""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"[goto] attempt {attempt} -> {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout= NAV_TIMEOUT)
            code = resp.status if resp else "n/a"
            print(f"[goto] status={code}")
            # мягкая попытка дождаться networkidle (не критично)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            return
        except Exception as e:
            last_err = e
            print(f"[goto] fail #{attempt}: {e}")
    if last_err:
        raise last_err


async def _core(args, out_path: Path, debug_html: Path, debug_png: Path):
    async with async_playwright() as pw:
        bt = pw.chromium
        launch_kwargs = dict(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # persistent-профиль (куки) предпочтительнее
        if args.user_data_dir:
            context = await bt.launch_persistent_context(
                args.user_data_dir,
                **launch_kwargs,
                user_agent=UA,
                locale="en-US",
                viewport={"width": args.width, "height": args.height},
                timezone_id="America/New_York",
                geolocation={"longitude": -73.9857, "latitude": 40.7484},
                permissions=["geolocation"],
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9,ru;q=0.6"},
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await bt.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=UA,
                locale="en-US",
                viewport={"width": args.width, "height": args.height},
                timezone_id="America/New_York",
                geolocation={"longitude": -73.9857, "latitude": 40.7484},
                permissions=["geolocation"],
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9,ru;q=0.6"},
            )
            page = await context.new_page()

        # Небольшая "облегчалка": режем тяжёлое/трекеры (картинки не трогаем)
        await context.route("**/*", lambda route: (
            route.abort()
            if route.request.resource_type in {"media", "font"}
               or "doubleclick" in route.request.url
               or "googletag" in route.request.url
            else route.continue_()
        ))

        # Небольшой анти-бот
        await page.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            window.chrome={runtime:{}};
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4]});
        """)

        # Навигация
        await goto_with_retries(page, args.url)

        # Куки/попапы
        for sel in COOKIE_SELECTORS:
            await maybe_click(page, sel, 4000)
        for sel in POPUP_SELECTORS:
            await maybe_click(page, sel, 1500)

        # Пауза после загрузки
        if args.sleep_ms > 0:
            await asyncio.sleep(args.sleep_ms / 1000)

        # Если переданы свои селекторы — мягко подождём любой из них
        for sel in (args.wait_for or []):
            try:
                await page.wait_for_selector(sel, timeout=SEL_TIMEOUT, state="visible")
                print(f"[wait] visible: {sel}")
                break
            except PWTimeout:
                continue

        # Сколлим — для ленивых таблиц
        await gentle_scroll(page)

        # Сохранить HTML-дамп (для диагностики)
        try:
            html = await page.content()
            debug_html.write_text(html, encoding="utf-8", errors="ignore")
            print(f"[dump] html -> {debug_html}")
        except Exception as e:
            print(f"[dump] html fail: {e}")

        # Скрин (в любом случае)
        await page.screenshot(path=str(out_path), full_page=True)
        await page.screenshot(path=str(debug_png), full_page=True)
        print(f"[ok] saved screenshot -> {out_path}")
        print(f"[ok] saved debug screenshot -> {debug_png}")

        await context.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="page.png")
    ap.add_argument("--width", type=int, default=1366)
    ap.add_argument("--height", type=int, default=1100)
    ap.add_argument("--user-data-dir", default=None)
    ap.add_argument("--wait-for", action="append", help="доп. CSS-селекторы (можно несколько)")
    ap.add_argument("--sleep-ms", type=int, default=1500)
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    debug_html = out_path.parent / f"debug_{stamp}.html"
    debug_png  = out_path.parent / f"debug_{stamp}.png"

    try:
        await asyncio.wait_for(_core(args, out_path, debug_html, debug_png), timeout=GLOBAL_TIMEOUT)
    except asyncio.TimeoutError:
        # Запишем, что именно был глобальный таймаут — бот вытащит это из лога
        print("[fatal] global timeout", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # На любой фатальной ошибке — попробуем сохранить дампы для диагностики
        try:
            print(f"[fatal] {e}", file=sys.stderr)
        finally:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
