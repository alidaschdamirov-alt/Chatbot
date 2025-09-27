import sys, subprocess
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
