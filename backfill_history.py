"""Backfill historical snapshots for issuers whose APIs accept a date.

Produces partial daily snapshots in data/snapshots/YYYY-MM-DD.json containing
only the ETFs we can fetch retrospectively. The other issuers' ETFs are
intentionally absent — compute_diff / compute_leaderboard already skip ETFs
missing from one side of the comparison, so this just narrows the scope of
historical analysis to what's actually attestable.

Currently supports:
  fuhhwa  (00991A)  — /api/assetsExcel/ETF23/{YYYYMMDD}; weekends 404-equivalent
  nomura  (00980A)  — POST /api/Fund/GetFundAssets with {SearchDate: YYYY-MM-DD}

Usage:
  python backfill_history.py 2026-04-20 2026-04-24
  python backfill_history.py 2026-04-20             # single day

Re-run python main.py afterwards so write_diff / write_leaderboard recompute
against the newly-available baselines.
"""
from __future__ import annotations
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from scrapers.fuhhwa import EXCEL_URL as FUHHWA_EXCEL_URL, parse_fuhhwa_xlsx, parse_fuhhwa_meta, _TICKER_TO_ID as FUHHWA_IDS
from scrapers.nomura import HOLDINGS_URL as NOMURA_URL, parse_nomura_holdings, parse_nomura_meta
from scrapers.base import BaseScraper, ScrapeResult
from normalizer import build_payload, load_config


def _fuhhwa_historical(scraper: BaseScraper, ticker: str, day: date) -> ScrapeResult | None:
    """Returns None if the issuer has no data for that day (weekend / holiday)."""
    internal_id = FUHHWA_IDS[ticker]
    url = FUHHWA_EXCEL_URL.format(id=internal_id, date=day.strftime("%Y%m%d"))
    body = scraper.get_bytes(url)
    if not body.startswith(b"PK\x03\x04"):
        return None
    return ScrapeResult(
        holdings=parse_fuhhwa_xlsx(body),
        fund_meta=parse_fuhhwa_meta(body),
    )


def _nomura_historical(scraper: BaseScraper, ticker: str, day: date) -> ScrapeResult | None:
    """Returns None on StatusCode != 0 (fund unavailable that day)."""
    text = scraper.post(NOMURA_URL, json={"FundID": ticker, "SearchDate": day.strftime("%Y-%m-%d")})
    try:
        if json.loads(text).get("StatusCode") != 0:
            return None
    except Exception:
        return None
    return ScrapeResult(
        holdings=parse_nomura_holdings(text),
        fund_meta=parse_nomura_meta(text),
    )


# (ticker, fetcher) pairs — ordered by issuer for log readability
HISTORICAL_FETCHERS = [
    ("00991A", _fuhhwa_historical),
    ("00980A", _nomura_historical),
]


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def backfill_one_day(day: date, etfs_config: dict, stocks_config: dict, snapshots_dir: Path) -> None:
    scraper = BaseScraper()  # shared session — we're hitting <10 endpoints total
    print(f"\n=== {day.isoformat()} ===")

    scraped: dict[str, list] = {}
    fund_meta: dict[str, dict] = {}

    for ticker, fetch in HISTORICAL_FETCHERS:
        try:
            result = fetch(scraper, ticker, day)
        except Exception as exc:
            print(f"  [FAIL]  {ticker}: {exc}")
            continue
        if result is None:
            print(f"  [SKIP]  {ticker}: no data for this date (weekend / holiday)")
            continue
        scraped[ticker] = result.holdings
        if result.fund_meta:
            fund_meta[ticker] = result.fund_meta
        print(f"  [OK]    {ticker}: {len(result.holdings)} holdings"
              + (f" (+ fund_meta {sorted(result.fund_meta)})" if result.fund_meta else ""))

    if not scraped:
        print(f"  → no data for any issuer on {day}; snapshot not written")
        return

    # The payload's updated_at gets a fixed timestamp on the date itself so
    # downstream tools see a consistent "as of EOD" rather than the moment
    # this script ran.
    pretend_updated_at = datetime.combine(day, datetime.min.time()).isoformat() + "+08:00"
    payload = build_payload(
        scraped, etfs_config, stocks_config,
        updated_at_override=pretend_updated_at,
        fund_meta_by_ticker=fund_meta,
    )

    snapshot_path = snapshots_dir / f"{day.isoformat()}.json"
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  → wrote {snapshot_path.name} ({len(payload['etfs'])} ETFs)")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or len(argv) > 3:
        print(__doc__, file=sys.stderr)
        return 2

    start = date.fromisoformat(argv[1])
    end = date.fromisoformat(argv[2]) if len(argv) == 3 else start

    etfs_config = load_config("config/etfs.yml")
    stocks_config = load_config("config/stocks.yml")
    snapshots_dir = Path("data/snapshots")
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Don't overwrite today's snapshot — main.py owns it and produces a
    # 7-ETF full snapshot, not the 2-ETF partial one this script makes.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()

    for day in daterange(start, end):
        if day == today:
            print(f"\n=== {day.isoformat()} ===\n  → skipping (today's snapshot is owned by main.py; run that for the full 7-ETF version)")
            continue
        backfill_one_day(day, etfs_config, stocks_config, snapshots_dir)

    print("\nDone. Re-run `python main.py` so diff / leaderboard pick up the new baselines.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
