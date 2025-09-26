
#!/usr/bin/env python3
# screenshot_page.py — скрин страницы + умный скролл (страница/контейнер/iframe)
# Поддержка: wheel/PageDown/End, прокрутка по времени, финальная пауза дорисовки.

import argparse, os, time, sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# ----------------------------- CLI -----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Full-page screenshot via Playwright (скролл: страница/контейнер/iframe, wheel, PageDown)")
    p.add_argument("--url", required=True, help="HTTP(S) URL или путь к локальному файлу (page.html)")
    p.add_argument("--out", default="page.png", help="PNG файл для сохранения")
    p.add_argument("--wait", type=float, default=6.0, help="Секунды подождать после загрузки")
    p.add_argument("--timeout", type=int, default=45000, help="Таймаут загрузки, мс")
    p.add_argument("--user-data-dir", default=None, help="Папка профиля (для куков)")
    p.add_argument("--headless", action="store_true", help="Принудительно headless=True")
    p.add_argument("--viewport-width", type=int, default=1440, help="Ширина окна браузера")
    p.add_argument("--viewport-height", type=int, default=900, help="Высота окна браузера")

    # Основные режимы скролла
    p.add_argument("--scroll", type=int, default=0, help="Прокрутить на N px (плюс — вниз, минус — вверх)")
    p.add_argument("--scroll-bottom", action="store_true", help="Плавно прокрутить до самого низа")

    # Где скроллить
    p.add_argument("--scroll-target-selector", default=None, help="CSS селектор скроллируемого контейнера (если не body/html)")
    p.add_argument("--frame-url-substr", default=None, help="Подстрока URL iframe, внутри которого нужно скроллить (напр. 'tradingview.com')")
    p.add_argument("--frame-selector", default=None, help="CSS селектор iframe (альтернатива frame-url-substr)")

    # Фоллбэки, если обычный скролл не работает
    p.add_argument("--wheel", type=int, default=0, help="Имитация прокрутки колёсиком (суммарно deltaY). Работает и в iframe.")
    p.add_argument("--page-downs", type=int, default=0, help="Сколько раз нажать PageDown внутри цели")
    p.add_argument("--press-end", action="store_true", help="Нажать End внутри цели (в самый низ)")

    # Прокрутка по времени + финальная пауза дорисовки
    p.add_argument("--wheel-run-secs", type=float, default=0.0, help="Сколько секунд непрерывно крутить колесо вниз")
    p.add_argument("--idle-secs", type=float, default=2.0, help="Пауза после прокрутки для дорисовки данных")

    # Снять блокировки скролла
    p.add_argument("--unlock-overflow", action="store_true", help="Снять overflow:hidden у html/body")
    return p.parse_args()

# ----------------------------- Utils -----------------------------
def normalize_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https", "file"):
        return raw
    p = Path(raw)
    if p.exists():
        return p.resolve().as_uri()
    raise ValueError(f"Invalid URL or file path: {raw}")

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
    a = parse_args()
    headless = not (os.getenv("HEADFUL", "0") == "1")
    if a.headless:
        headless = True

    target = normalize_url(a.url)

    with sync_playwright() as p:
        args = ["--disable-dev-shm-usage", "--no-sandbox"]
        if a.user_data_dir:
            ctx = p.chromium.launch_persistent_context(
                a.user_data_dir, headless=headless, args=args,
                viewport={"width": a.viewport_width, "height": a.viewport_height}
            )
            page = ctx.new_page()
            browser = None
        else:
            browser = p.chromium.launch(headless=headless, args=args)
            ctx = browser.new_context(viewport={"width": a.viewport_width, "height": a.viewport_height})
            page = ctx.new_page()

        try:
            page.goto(target, wait_until="networkidle", timeout=a.timeout)
        except PWTimeoutError:
            page.wait_for_load_state("domcontentloaded")

        if a.wait > 0:
            time.sleep(a.wait)

        if a.unlock_overflow:
            unlock_overflow_styles(page)

        # ---- Определяем цель скролла: страница или iframe ----
        iframe_el = get_iframe_handle(page, a.frame_url_substr, a.frame_selector)

        # ---- Обычные способы (evaluate) ----
        if a.scroll != 0 or a.scroll_bottom:
            target_selector = a.scroll_target_selector
            # если целевого фрейма нет — подберём контейнер
            if not target_selector and not iframe_el:
                target_selector = pick_scroll_target_selector(page)

            try:
                if a.scroll != 0:
                    if iframe_el:
                        # Внутри TradingView обычно лучше сразу фоллбэки (колесо/клавиши)
                        pass
                    else:
                        if target_selector:
                            ok = scroll_element(page, target_selector, a.scroll)
                            if not ok: scroll_in_page(page, a.scroll)
                        else:
                            scroll_in_page(page, a.scroll)

                if a.scroll_bottom:
                    if iframe_el:
                        pass  # для iframe ниже используем фоллбэки
                    else:
                        scroll_to_bottom_smart(page, selector=target_selector)
            except Exception:
                pass  # перейдём к фоллбэкам

        # ---- Фоллбэки (для TradingView/iframe): колесо и/или клавиатура ----
        used_fallback = False
        if a.wheel != 0:
            used_fallback |= wheel_over(page, iframe_el, a.wheel)
        if a.page_downs or a.press_end:
            keyboard_scroll(page, iframe_el, page_downs=a.page_downs, press_end=a.press_end)
            used_fallback = True

        # Прокрутка по времени (самый надёжный способ для бесконечных лент)
        if a.wheel_run_secs and a.wheel_run_secs > 0:
            wheel_for_seconds(page, iframe_el, a.wheel_run_secs)
            used_fallback = True

        # Если просили scroll-bottom и обычные способы не сработали — нажмём End и чуть «докрутим»
        if a.scroll_bottom and not used_fallback:
            keyboard_scroll(page, iframe_el, page_downs=0, press_end=True)
            time.sleep(0.5)
            wheel_over(page, iframe_el, 8000)

        # Финальная пауза на дорисовку данных/скелетонов
        if a.idle_secs and a.idle_secs > 0:
            time.sleep(a.idle_secs)

        # ---- Скриншот ----
        page.screenshot(path=a.out, full_page=True)
        print(f"✅ saved: {a.out}")

        ctx.close()
        if browser: browser.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
