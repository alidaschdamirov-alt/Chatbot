# screenshot_service.py
import subprocess
import time
from pathlib import Path
from typing import Sequence, List


def build_scraper_cmd(
    python_exec: str,
    scraper: Path,
    url: str,
    out_png: Path,
    user_data_dir: Path,
    wait_for: Sequence[str] | None = None,
    sleep_ms: int = 0,
) -> List[str]:
    """
    Собирает команду запуска screenshot_page.py.
    Поддерживает:
      - несколько --wait-for
      - опциональный --sleep-ms (мягкая пауза после load)
    """
    cmd = [
        python_exec,
        str(scraper),
        "--url", url,
        "--out", str(out_png),
        "--user-data-dir", str(user_data_dir),
    ]
    for sel in (wait_for or []):
        if sel:
            cmd += ["--wait-for", sel]
    if sleep_ms and sleep_ms > 0:
        cmd += ["--sleep-ms", str(sleep_ms)]
    return cmd


def run_scraper(cmd: list[str], timeout_sec: int, log_file: Path) -> subprocess.CompletedProcess[str]:
    """Запускает подпроцесс и пишет stdout+stderr в лог-файл."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as lf:
        return subprocess.run(
            cmd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_sec,
        )


# --- Доп. утилиты, которые использует /batch ---

def capture_page(
    python_exec: str,
    scraper: Path,
    url: str,
    out_png: Path,
    user_data_dir: Path,
    wait_for: Sequence[str] | None,
    sleep_ms_val: int,
    timeout_sec: int,
    log_file: Path,
) -> subprocess.CompletedProcess[str]:
    """Удобная обёртка: собрать команду и запустить."""
    cmd = build_scraper_cmd(
        python_exec=python_exec,
        scraper=scraper,
        url=url,
        out_png=out_png,
        user_data_dir=user_data_dir,
        wait_for=wait_for,
        sleep_ms=sleep_ms_val,
    )
    return run_scraper(cmd, timeout_sec, log_file)


def sleep_ms(ms: int) -> None:
    """Короткая пауза между страницами в /batch."""
    if ms and ms > 0:
        time.sleep(ms / 1000)
