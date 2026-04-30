"""End-to-end: read config, invoke scrapers, write data/latest.json + snapshot.

Run: python main.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

from scrapers.base import BaseScraper, Holding, ScrapeResult, classify_market
from scrapers.yuanta import YuantaScraper
from scrapers.nomura import NomuraScraper
from scrapers.president import PresidentScraper
from scrapers.capital import CapitalScraper
from scrapers.fuhhwa import FuhhwaScraper
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from normalizer import build_payload, write_payload, load_config, compute_diff, compute_leaderboard

LEADERBOARD_WINDOW_DAYS = 7

TAIPEI = ZoneInfo("Asia/Taipei")

INTER_REQUEST_DELAY_SEC = 2  # be polite to issuer sites

SCRAPERS: dict[str, BaseScraper] = {
    "yuanta":    YuantaScraper(),
    "nomura":    NomuraScraper(),
    "president": PresidentScraper(),
    "capital":   CapitalScraper(),
    "fuhhwa":    FuhhwaScraper(),
}


def load_previous_payload(latest_path: Path) -> tuple[dict[str, list[Holding]], dict[str, dict]]:
    """Recover per-ETF holdings AND fund_meta from the previous latest.json,
    so a failed scrape can fall back to stale-but-present data + meta.

    Returns (holdings_by_ticker, meta_by_ticker). Both empty when no
    previous payload exists.
    """
    if not latest_path.exists():
        return {}, {}
    prev = json.loads(latest_path.read_text(encoding="utf-8"))

    # Prefer the new per-ETF holdings list (preserves foreign holdings on fallback);
    # fall back to deriving from cross-aggregation (TW-only) for older snapshots.
    recovered: dict[str, list[Holding]] = {}
    meta_by_ticker: dict[str, dict] = {}
    for etf in prev.get("etfs", []):
        ticker = etf["ticker"]
        if "fund_meta" in etf:
            meta_by_ticker[ticker] = etf["fund_meta"]
        if "holdings" in etf:
            recovered[ticker] = [
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
        return recovered, meta_by_ticker

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
    return recovered, meta_by_ticker


def main() -> int:
    etfs_config = load_config("config/etfs.yml")
    stocks_config = load_config("config/stocks.yml")
    previous, previous_meta = load_previous_payload(Path("data/latest.json"))

    scraped: dict[str, list[Holding]] = {}
    fund_meta_by_ticker: dict[str, dict] = {}
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
            result = scraper.fetch(ticker)
            if not result.holdings:
                raise RuntimeError("empty holdings")
            scraped[ticker] = result.holdings
            if result.fund_meta:
                fund_meta_by_ticker[ticker] = result.fund_meta
            print(f"  ok: {len(result.holdings)} holdings"
                  + (f" (+ fund_meta {sorted(result.fund_meta)})" if result.fund_meta else ""))
        except Exception as exc:
            failures.append(ticker)
            print(f"  FAIL: {exc}", file=sys.stderr)
            if ticker in previous and previous[ticker]:
                print(f"  using previous data ({len(previous[ticker])} holdings)")
                scraped[ticker] = previous[ticker]
                # Carry forward previous fund_meta on fallback so the modal still
                # shows the issuer's last-known stats (the data hasn't moved).
                if ticker in previous_meta:
                    fund_meta_by_ticker[ticker] = previous_meta[ticker]
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

    payload = build_payload(scraped, etfs_config, stocks_config, preserved_updated_at,
                            fund_meta_by_ticker=fund_meta_by_ticker)
    write_payload(payload)
    print(f"\nWrote data/latest.json ({len(payload['etfs'])} ETFs, {len(payload['holdings'])} unique stocks)")

    write_diff(payload, Path("data"))
    write_leaderboard(payload, Path("data"))
    write_per_stock_history(Path("data"))
    write_prices(payload, Path("data"))

    if failures:
        print(f"Failures: {failures}")
    return 0


def write_leaderboard(today_payload: dict, data_dir: Path, window_days: int = LEADERBOARD_WINDOW_DAYS) -> None:
    """Compute the today-vs-N-days-ago top-movers leaderboard.

    Picks the snapshot whose date is closest to (today - window_days) but
    still within the window — if the user only has 3 days of snapshots,
    we use the oldest one rather than skipping.
    """
    today_iso = datetime.now(TAIPEI).date().isoformat()
    cutoff_iso = (datetime.now(TAIPEI).date() - timedelta(days=window_days)).isoformat()
    snapshots_dir = data_dir / "snapshots"
    baseline = _find_baseline_snapshot(snapshots_dir, today_iso, cutoff_iso)

    if baseline is None:
        result = {"window_days": window_days, "as_of_today": today_iso, "as_of_baseline": None,
                  "top_added": [], "top_removed": []}
        print(f"Leaderboard: no baseline snapshot in past {window_days} days; writing empty")
    else:
        baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
        lb = compute_leaderboard(today_payload, baseline_payload)
        result = {"window_days": window_days, "as_of_today": today_iso,
                  "as_of_baseline": baseline.stem, **lb}
        print(f"Leaderboard: {baseline.stem} → today "
              f"({len(lb['top_added'])} added, {len(lb['top_removed'])} removed)")

    (data_dir / "leaderboard_7d.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_baseline_snapshot(snapshots_dir: Path, today_iso: str, cutoff_iso: str) -> Path | None:
    """Snapshot whose date is closest to cutoff_iso but strictly before today.

    Preference order: an exact-cutoff match, else the oldest dated > cutoff,
    else the oldest available before today.
    """
    if not snapshots_dir.exists():
        return None
    candidates = sorted(p for p in snapshots_dir.glob("*.json") if p.stem < today_iso)
    if not candidates:
        return None
    in_window = [p for p in candidates if p.stem >= cutoff_iso]
    if in_window:
        return in_window[0]  # oldest within window = closest to cutoff
    return candidates[-1]    # all candidates older than window — use the most recent of those


def write_diff(today_payload: dict, data_dir: Path) -> None:
    """Diff the two most recent snapshots and write latest_diff.json.

    Always compares the last two snapshots (not latest.json vs snapshot),
    so the diff is meaningful even when today's scrape produced no new data.
    Sets is_stale=True when the newest snapshot is older than today, so the
    frontend can show a "今日無最新資料" notice.

    Output shape:
      { "as_of_today": "YYYY-MM-DD",       -- newest snapshot date
        "as_of_baseline": "YYYY-MM-DD",     -- second-newest snapshot date
        "is_stale": bool,                   -- true when newest < real today
        "by_etf": { ticker: {added, removed, changed}, ... } }
    """
    today_iso = datetime.now(TAIPEI).date().isoformat()
    snapshots_dir = data_dir / "snapshots"
    snaps = sorted(snapshots_dir.glob("*.json")) if snapshots_dir.exists() else []

    if len(snaps) < 2:
        result = {"as_of_today": snaps[0].stem if snaps else today_iso,
                  "as_of_baseline": None, "is_stale": True, "by_etf": {}}
        print("Diff: fewer than 2 snapshots; writing empty diff")
    else:
        newest, prev = snaps[-1], snaps[-2]
        is_stale = newest.stem < today_iso
        newest_payload = json.loads(newest.read_text(encoding="utf-8"))
        prev_payload   = json.loads(prev.read_text(encoding="utf-8"))
        by_etf = compute_diff(newest_payload, prev_payload)
        changed_etfs = sum(1 for d in by_etf.values() if d["added"] or d["removed"] or d["changed"])
        stale_tag = " [STALE]" if is_stale else ""
        print(f"Diff: {prev.stem} → {newest.stem} ({changed_etfs}/{len(by_etf)} ETFs with changes){stale_tag}")
        result = {"as_of_today": newest.stem, "as_of_baseline": prev.stem,
                  "is_stale": is_stale, "by_etf": by_etf}

    diff_path = data_dir / "latest_diff.json"
    diff_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def write_prices(today_payload: dict, data_dir: Path) -> None:
    """Fetch today's close prices via 4-tier provider chain.

    Spec: docs/superpowers/specs/2026-04-30-prices-source-and-refresh-design.md

    Universe = unique stock_ids in today_payload's TW holdings (~150).
    Walks FinMind → yfinance → TWSE+TPEx → cache; first ≥80% wins.
    On total failure, keeps existing prices_today.json unchanged.
    """
    from scrapers.daily_close import fetch_daily_close

    target = datetime.now(TAIPEI).date()
    held_ids = sorted({
        h["stock_id"]
        for etf in today_payload.get("etfs", [])
        for h in etf.get("holdings", [])
        if h.get("market") == "TW"
    })
    prices_path = data_dir / "prices_today.json"

    result = fetch_daily_close(list(held_ids), target)

    if not result["ok"]:
        if prices_path.exists():
            prev_date = json.loads(prices_path.read_text(encoding="utf-8")).get("date", "?")
            print(f"Prices: all providers failed for {target} — keeping previous ({prev_date})")
        else:
            prices_path.write_text(
                json.dumps({"date": target.isoformat(), "source": None,
                            "fetched_at": result["fetched_at"], "prices": {},
                            "missing": list(held_ids)}, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Prices: no data for {target}, wrote empty placeholder")
        return

    payload = {
        "date":       result["date"],
        "source":     result["source"],
        "fetched_at": result["fetched_at"],
        "prices":     result["prices"],
        "missing":    result["missing"],
    }
    prices_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Prices: wrote {len(result['prices'])} stocks from {result['source']} "
          f"(missing {len(result['missing'])})")


def write_per_stock_history(data_dir: Path) -> None:
    """Materialise a per-stock weight time series across every snapshot.

    Output shape:
      { stock_id: {
          ticker: [{date: "YYYY-MM-DD", weight: float}, ...],
          ...
      }, ... }

    Front-end fetches this once and renders inline trend sparklines from it.
    Cheaper than 11+ HTTP requests for every snapshot file. TW only — foreign
    holdings excluded for the same reason as the cross-table.
    """
    snapshots_dir = data_dir / "snapshots"
    if not snapshots_dir.exists():
        return

    history: dict[str, dict[str, list]] = {}
    snap_count = 0

    for snap_path in sorted(snapshots_dir.glob("*.json")):
        date_str = snap_path.stem
        try:
            payload = json.loads(snap_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        snap_count += 1
        for etf in payload.get("etfs", []):
            ticker = etf["ticker"]
            for h in etf.get("holdings", []):
                if h.get("market") != "TW":
                    continue
                sid = h["stock_id"]
                history.setdefault(sid, {}).setdefault(ticker, []).append({
                    "date": date_str,
                    "weight": h["weight_pct"],
                })

    # Sort each ticker's series by date for deterministic plotting order.
    for sid in history:
        for ticker in history[sid]:
            history[sid][ticker].sort(key=lambda x: x["date"])

    out_path = data_dir / "history_per_stock.json"
    out_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"History: {snap_count} snapshots → {len(history)} unique stocks tracked")


if __name__ == "__main__":
    sys.exit(main())
