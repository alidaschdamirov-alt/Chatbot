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


def get_iframe_handle(page, frame_url_substr=None, frame_selector=None):
    if frame_selector:
        el = page.locator(frame_selector).first
        try:
            el.wait_for(timeout=8000)
            return el
        except Exception:
            return None
    if frame_url_substr:
        sel = f'iframe[src*="{frame_url_substr}"]'
        el = page.locator(sel).first
        try:
            el.wait_for(timeout=8000)
            return el
        except Exception:
            return None
    el = page.locator("iframe").first
    try:
        el.wait_for(timeout=3000)
        return el
    except Exception:
        return None

def unlock_overflow_styles(page_like):
    try:
        page_like.evaluate("""
            () => {
              for (const el of [document.documentElement, document.body]) {
                if (!el) continue;
                el.style.overflowY = 'auto';
                el.style.overflowX = 'auto';
                el.style.overscrollBehavior = 'auto';
              }
              const blockers = document.querySelectorAll('[class*="no-scroll"], [class*="modal-open"]');
              blockers.forEach(n => n.classList.remove('no-scroll','modal-open'));
            }
        """)
    except Exception:
        pass

def scroll_in_page(page_like, pixels: int):
    page_like.evaluate("""
        (px)=>{
          const el = document.scrollingElement || document.documentElement || document.body;
          if (!el) { window.scrollBy(0, px); return; }
          if (el.scrollBy) el.scrollBy(0, px);
          else el.scrollTop = (el.scrollTop || 0) + px;
        }
    """, pixels)

def scroll_element(page_like, selector: str, pixels: int) -> bool:
    return page_like.evaluate("""
        ({sel, px})=>{
          const el = document.querySelector(sel);
          if (!el) return false;
          if (el.scrollBy) el.scrollBy(0, px);
          else el.scrollTop = (el.scrollTop || 0) + px;
          return true;
        }
    """, {"sel": selector, "px": pixels})

def pick_scroll_target_selector(page_like):
    return page_like.evaluate("""
        ()=>{
          const root = document.scrollingElement || document.documentElement || document.body;
          if (root && (root.scrollHeight||0) > (root.clientHeight||0)) return null;
          let best = null, bestDelta = 0;
          for (const e of document.querySelectorAll('*')) {
            const ch = e.scrollHeight||0, cc = e.clientHeight||0, d = ch-cc;
            if (d > bestDelta) { best=e; bestDelta=d; }
          }
          if (!best) return null;
          best.setAttribute('data-scroll-target','1');
          return '[data-scroll-target=\"1\"]';
        }
    """)

def scroll_to_bottom_smart(page_like, selector: str | None = None, step: int = 800, pause: float = 0.6, max_steps: int = 250):
    def state(sel):
        return page_like.evaluate("""
            (sel)=>{
              const el = sel ? document.querySelector(sel)
                             : (document.scrollingElement || document.documentElement || document.body);
              if (!el) return {h:0,t:0,c:0};
              return {h: el.scrollHeight||0, t: el.scrollTop||0, c: el.clientHeight||0};
            }
        """, sel)
    prev_h = state(selector)["h"]
    for _ in range(max_steps):
        if selector:
            ok = scroll_element(page_like, selector, step)
            if not ok: break
        else:
            scroll_in_page(page_like, step)
        time.sleep(pause)
        cur = state(selector)
        reached = (cur["t"] + cur["c"] + 4 >= cur["h"])
        grew = cur["h"] > prev_h
        if grew: prev_h = cur["h"]
        if reached and not grew: break

# --- Фоллбэк: колесо мыши внутри iframe (или страницы) с фиксированным deltaY ---
def wheel_over(page, iframe_el, delta_y: int):
    try:
        if iframe_el:
            box = iframe_el.bounding_box()
            if not box: return False
            page.mouse.move(box["x"] + box["width"]/2, box["y"] + min(120, box["height"]/2))
            iframe_el.click(position={"x": 10, "y": 10})
        else:
            page.mouse.move(200, 200)
            page.click("body")
        step = 1200 if delta_y > 0 else -1200
        left = delta_y
        while left != 0:
            d = step if abs(left) > abs(step) else left
            page.mouse.wheel(0, d)
            time.sleep(0.25)
            left -= d
        return True
    except Exception:
        return False

# --- Фоллбэк: колесо мыши "по времени" (самое надёжное для бесконечных лент) ---
def wheel_for_seconds(page, iframe_el, duration_sec: float, per_step: int = 1200, delay: float = 0.2):
    """Крутит колёсико вниз duration_sec секунд небольшими порциями."""
    try:
        if iframe_el:
            box = iframe_el.bounding_box()
            if not box:
                return False
            page.mouse.move(box["x"] + box["width"]/2, box["y"] + min(120, box["height"]/2))
            iframe_el.click(position={"x": 10, "y": 10})
        else:
            page.mouse.move(200, 200)
            page.click("body")
        t0 = time.time()
        while time.time() - t0 < duration_sec:
            page.mouse.wheel(0, per_step)
            time.sleep(delay)
        return True
    except Exception:
        return False

# --- Фоллбэк: PageDown/End внутри iframe (или страницы) ---
def keyboard_scroll(page, iframe_el, page_downs: int = 0, press_end: bool = False):
    try:
        if iframe_el:
            # пробуем получить фокус внутри фрейма
            iframe_el.click(position={"x": 10, "y": 10})
        else:
            page.click("body", timeout=5000)
    except Exception:
        try:
            if iframe_el: iframe_el.click()
        except Exception:
            pass
    for _ in range(max(0, page_downs)):
        page.keyboard.press("PageDown")
        time.sleep(0.15)
    if press_end:
        page.keyboard.press("End")

# ----------------------------- Main -----------------------------
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
