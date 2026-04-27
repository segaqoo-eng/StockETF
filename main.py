"""End-to-end: read config, invoke scrapers, write data/latest.json + snapshot.

Run: python main.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

from scrapers.base import BaseScraper, Holding, classify_market
from scrapers.yuanta import YuantaScraper
from scrapers.nomura import NomuraScraper
from scrapers.president import PresidentScraper
from scrapers.capital import CapitalScraper
from scrapers.fuhhwa import FuhhwaScraper
from normalizer import build_payload, write_payload, load_config

INTER_REQUEST_DELAY_SEC = 2  # be polite to issuer sites

SCRAPERS: dict[str, BaseScraper] = {
    "yuanta":    YuantaScraper(),
    "nomura":    NomuraScraper(),
    "president": PresidentScraper(),
    "capital":   CapitalScraper(),
    "fuhhwa":    FuhhwaScraper(),
}


def load_previous_holdings(latest_path: Path) -> dict[str, list[Holding]]:
    """Recover each ETF's last-known holdings from the previous latest.json,
    so a failed scrape can fall back to stale-but-present data.
    """
    if not latest_path.exists():
        return {}
    prev = json.loads(latest_path.read_text(encoding="utf-8"))

    # Prefer the new per-ETF holdings list (preserves foreign holdings on fallback);
    # fall back to deriving from cross-aggregation (TW-only) for older snapshots.
    recovered: dict[str, list[Holding]] = {}
    for etf in prev.get("etfs", []):
        if "holdings" in etf:
            recovered[etf["ticker"]] = [
                Holding(
                    stock_id=h["stock_id"],
                    stock_name=h["stock_name"],
                    weight_pct=h["weight_pct"],
                    shares=h["shares"],
                    market=h.get("market") or classify_market(h["stock_id"]),
                )
                for h in etf["holdings"]
            ]
    if recovered:
        return recovered

    recovered = {e["ticker"]: [] for e in prev.get("etfs", [])}
    for h in prev.get("holdings", []):
        for b in h["held_by"]:
            recovered.setdefault(b["etf"], []).append(Holding(
                stock_id=h["stock_id"],
                stock_name=h["stock_name"],
                weight_pct=b["weight_pct"],
                shares=b["shares"],
                market=classify_market(h["stock_id"]),
            ))
    return recovered


def main() -> int:
    etfs_config = load_config("config/etfs.yml")
    stocks_config = load_config("config/stocks.yml")
    previous = load_previous_holdings(Path("data/latest.json"))

    scraped: dict[str, list[Holding]] = {}
    failures: list[str] = []

    for i, (ticker, meta) in enumerate(etfs_config.items()):
        if i > 0:
            time.sleep(INTER_REQUEST_DELAY_SEC)
        scraper_name = meta["scraper"]
        scraper = SCRAPERS.get(scraper_name)
        if scraper is None:
            print(f"[SKIP] {ticker}: unknown scraper '{scraper_name}'", file=sys.stderr)
            continue
        try:
            print(f"[FETCH] {ticker} via {scraper_name}...")
            holdings = scraper.fetch(ticker)
            if not holdings:
                raise RuntimeError("empty holdings")
            scraped[ticker] = holdings
            print(f"  ok: {len(holdings)} holdings")
        except Exception as exc:
            failures.append(ticker)
            print(f"  FAIL: {exc}", file=sys.stderr)
            if ticker in previous and previous[ticker]:
                print(f"  using previous data ({len(previous[ticker])} holdings)")
                scraped[ticker] = previous[ticker]
            else:
                print(f"  no previous data — skipping {ticker}")

    if not scraped:
        print("ERROR: no ETF data at all", file=sys.stderr)
        return 1

    used_fallback = bool(failures and any(t in previous for t in failures))

    preserved_updated_at = None
    if used_fallback and Path("data/latest.json").exists():
        prev_json = json.loads(Path("data/latest.json").read_text(encoding="utf-8"))
        preserved_updated_at = prev_json.get("updated_at")

    if used_fallback:
        print(f"WARN: preserved previous updated_at due to {len(failures)} fallback(s)", file=sys.stderr)

    payload = build_payload(scraped, etfs_config, stocks_config, preserved_updated_at)
    write_payload(payload)
    print(f"\nWrote data/latest.json ({len(payload['etfs'])} ETFs, {len(payload['holdings'])} unique stocks)")
    if failures:
        print(f"Failures: {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
