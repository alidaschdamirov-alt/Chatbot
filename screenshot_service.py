import sys, subprocess
import time
from pathlib import Path
from typing import Sequence

def build_scraper_cmd(python_exec: str, scraper: Path, url: str, out_png: Path, user_data_dir: Path, wait_for: Sequence[str]):
    cmd = [python_exec, str(scraper), "--url", url, "--out", str(out_png), "--user-data-dir", str(user_data_dir)]
    for sel in wait_for:
        cmd += ["--wait-for", sel]
    return cmd

def run_scraper(cmd: list[str], timeout_sec: int, log_file: Path):
    with log_file.open("w", encoding="utf-8") as lf:
        return subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=timeout_sec)

# screenshot_service.py (добавьте функцию)


def capture_page(python_exec: str, scraper: Path, url: str, out_png: Path,
                 user_data_dir: Path, wait_for: Sequence[str], sleep_ms: int,
                 timeout_sec: int, log_file: Path):
    cmd = build_scraper_cmd(python_exec, scraper, url, out_png, user_data_dir, wait_for, sleep_ms)
    return run_scraper(cmd, timeout_sec, log_file)

def sleep_ms(ms: int):
    if ms > 0:
        time.sleep(ms / 1000)
