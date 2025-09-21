#!/usr/bin/env python3
"""
Scrape Investing.com economic calendar (the same URL used in the iframe) with Playwright
and output a clean JSON/CSV list of events (including date & time).

Usage:
  python scrape_investing_calendar.py \
    --url "https://sslecal2.investing.com?columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous&category=_employment,_economicActivity,_inflation,_credit,_centralBanks,_confidenceIndex,_balance,_Bonds&importance=2,3&features=datepicker,timezone&countries=37,5&calType=week&timeZone=73&lang=1" \
    --json out.json --csv out.csv --screenshot page.png

Requirements:
  pip install playwright
  playwright install chromium

Note:
  Always check the target website's Terms of Service before scraping.
"""

from __future__ import annotations
import argparse
import json
import time
import csv
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

DEFAULT_URL = (
    "https://sslecal2.investing.com?"
    "columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous"
    "&category=_employment,_economicActivity,_inflation,_credit,_centralBanks,_confidenceIndex,_balance,_Bonds"
    "&importance=2,3&features=datepicker,timezone&countries=37,5&calType=week&timeZone=73&lang=1"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Investing.com economic calendar via Playwright")
    p.add_argument("--url", default=DEFAULT_URL, help="Calendar URL (the iframe src)")
    p.add_argument("--json", default="calendar.json", help="Path to save JSON output")
    p.add_argument("--csv", default=None, help="Optional path to save CSV output")
    p.add_argument("--screenshot", default=None, help="Optional page screenshot path (PNG)")
    p.add_argument("--headless", action="store_true", help="Run browser in headless mode (default: false)")
    p.add_argument("--wait", type=float, default=3.0, help="Extra seconds to wait after network idle")
    p.add_argument("--timeout", type=int, default=30000, help="Navigation timeout in ms")
    return p.parse_args()


def extract_table_data(page) -> Dict[str, Any]:
    """Try to extract calendar rows from the main table.
    The calendar markup may change; we attempt a few robust selectors.
    Returns dict with keys: headers: List[str], rows: List[List[str]]
    """
    # Try a few reasonable selectors in priority order
    table_selectors = [
        "table.genTbl",         # common investing.com class
        "table[data-test*='calendar']",
        "table",                # fallback to first table
    ]

    table = None
    for sel in table_selectors:
        try:
            table = page.locator(sel).first
            if table and table.count() > 0:
                if table.is_visible():
                    break
        except Exception:
            continue

    if not table or table.count() == 0:
        raise RuntimeError("Calendar table not found. Inspect the page to adjust selectors.")

    # headers
    headers: List[str] = []
    try:
        ths = table.locator("thead tr th")
        if ths.count() == 0:
            ths = table.locator("tr th")  # sometimes headless markup
        for i in range(ths.count()):
            headers.append(ths.nth(i).inner_text().strip())
    except Exception:
        # if no thead, we'll try to infer headers later
        headers = []

    # rows (skip potential header row if thead absent)
    body_rows = table.locator("tbody tr")
    if body_rows.count() == 0:
        # fallback: any tr but skip ones that clearly look like the header
        body_rows = table.locator("tr")

    rows: List[List[str]] = []

    # some calendars have date-separator rows; we track current date
    current_date: Optional[str] = None

    for i in range(body_rows.count()):
        tr = body_rows.nth(i)
        # Try to detect a date-separator row
        try:
            # If a row spans many columns and includes a date string
            if tr.locator("td").count() == 1:
                txt = tr.inner_text().strip()
                if txt and any(c.isdigit() for c in txt):
                    current_date = txt
                    continue
        except Exception:
            pass

        tds = tr.locator("td")
        if tds.count() == 0:
            continue

        row = []
        for j in range(tds.count()):
            cell_txt = tds.nth(j).inner_text().replace("\n", " ").strip()
            # compact whitespace
            row.append(" ".join(cell_txt.split()))

        # enrich with current_date if we have one and it's not already included
        if current_date is not None:
            row_with_date = [current_date] + row
            rows.append(row_with_date)
        else:
            rows.append(row)

    # If we have a stable column count, we can create synthesized headers
    if not headers and rows:
        # assume first row's width
        max_len = max(len(r) for r in rows)
        headers = [f"col_{k+1}" for k in range(max_len)]

    return {"headers": headers, "rows": rows}


def shape_events(records: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Try to convert raw rows into list of dict events with best-guess columns."""
    headers = records.get("headers", [])
    rows = records.get("rows", [])

    # We attempt to map columns heuristically based on common Investing calendar layout
    # Typical columns might include: Date, Time, Currency, Importance, Event, Actual, Forecast, Previous
    events: List[Dict[str, Any]] = []

    for row in rows:
        item: Dict[str, Any] = {}

        # If date was prepended by us, row[0] is date; else unknown
        idx = 0
        if len(row) >= 8:
            # Heuristic mapping for common table:
            # [Date?] Time | Currency | Importance | Event | Actual | Forecast | Previous | ...
            if any(char.isdigit() for char in row[0]):
                item["date"] = row[idx]; idx += 1
            # now attempt to assign fields
            keys = ["time", "currency", "importance", "event", "actual", "forecast", "previous"]
            for k in keys:
                if idx < len(row):
                    item[k] = row[idx]
                    idx += 1
            # append any remaining columns
            if idx < len(row):
                for extra_i, val in enumerate(row[idx:], start=1):
                    item[f"extra_{extra_i}"] = val
        else:
            # generic fallback mapping
            for j, val in enumerate(row):
                key = headers[j] if j < len(headers) and headers[j] else f"col_{j+1}"
                item[key] = val

        # Filter out lines that don't look like real events (e.g., blank rows)
        if any(v for v in item.values()):
            events.append(item)

    return events


def save_json(events: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def save_csv(events: List[Dict[str, Any]], path: str) -> None:
    # collect all keys
    keys = set()
    for e in events:
        keys.update(e.keys())
    fieldnames = sorted(keys)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for e in events:
            w.writerow(e)


def main() -> None:
    args = parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        try:
            page.goto(args.url, wait_until="networkidle", timeout=args.timeout)
        except PWTimeoutError:
            # continue anyway; sometimes networkidle never fires due to streaming/beacons
            page.wait_for_load_state("domcontentloaded")

        # Give the table a moment to render dynamic content
        if args.wait > 0:
            time.sleep(args.wait)

        if args.screenshot:
            page.screenshot(path=args.screenshot, full_page=True)

        records = extract_table_data(page)
        events = shape_events(records)

        save_json(events, args.json)
        if args.csv:
            save_csv(events, args.csv)

        print(f"✅ Extracted {len(events)} events -> {args.json}{' and ' + args.csv if args.csv else ''}")

        browser.close()


if __name__ == "__main__":
    main()
