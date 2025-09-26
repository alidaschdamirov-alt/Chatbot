import asyncio
import argparse
from pathlib import Path

from playwright.async_api import async_playwright


async def take_screenshot(url: str, out_png: Path, wait_seconds: int,
                          user_data_dir: Path, headless: bool):
    """
    Делает полноэкранный скрин страницы.
    - user_data_dir: persistent context (куки/локальное хранилище сохраняются).
    - headless: можно снять галку при первичном обходе Cloudflare в локальном запуске.
    """
    user_data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Запускаем persistent context (как полноценный профиль браузера)
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1920,1080",
            ],
        )

        try:
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})

            # Бывает полезно задать user agent
            await page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8"
            })

            # Загружаем страницу и ждём сетевую тишину
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if not resp or resp.status >= 400:
                # пробуем ещё дождаться networkidle для тяжелых страниц
                await page.wait_for_load_state("networkidle", timeout=60000)

            # Дополнительное ожидание от окружения
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            # Скролл до низа, чтобы прогрузить ленивые блоки (если есть)
            await page.evaluate(
                """() => new Promise(resolve => {
                    let h = 0;
                    const step = 600;
                    const id = setInterval(() => {
                        window.scrollBy(0, step);
                        h += step;
                        if (h > document.body.scrollHeight * 1.2) {
                            clearInterval(id); resolve();
                        }
                    }, 200);
                })"""
            )
            # Немного подождать после скролла
            await asyncio.sleep(1.2)

            # Скрин всей страницы
            await page.screenshot(path=str(out_png), full_page=True)
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Full page screenshot via Playwright")
    parser.add_argument("--url", required=True, help="URL страницы")
    parser.add_argument("--out", required=True, help="Куда сохранить PNG")
    parser.add_argument("--wait", default="5", help="Ожидание после загрузки, сек")
    parser.add_argument("--user-data-dir", default="./user-data", help="Папка профиля браузера")
    parser.add_argument("--headless", action="store_true", help="Режим без интерфейса")
    parser.add_argument("--headed", action="store_true", help="Принудительно с интерфейсом (debug)")

    args = parser.parse_args()
    out_png = Path(args.out)
    user_data_dir = Path(args.user_data_dir)

    # приоритет флагов: --headed перекрывает --headless
    headless = True
    if args.headed:
        headless = False
    elif args.headless:
        headless = True

    wait_seconds = int(args.wait)

    asyncio.run(
        take_screenshot(
            url=args.url,
            out_png=out_png,
            wait_seconds=wait_seconds,
            user_data_dir=user_data_dir,
            headless=headless,
        )
    )


if __name__ == "__main__":
    main()
