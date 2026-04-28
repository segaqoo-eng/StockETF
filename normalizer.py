"""Merge scraper outputs + config into the final JSON payload."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import yaml

from scrapers.base import Holding

TAIPEI = ZoneInfo("Asia/Taipei")


def load_config(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_payload(
    scraped: dict[str, list[Holding]],
    etfs_config: dict,
    stocks_config: dict,
    updated_at_override: str | None = None,
    fund_meta_by_ticker: dict[str, dict] | None = None,
) -> dict:
    """Combine per-ETF holdings, ETF metadata, and stock metadata into the
    shape described in the design spec §4.1.

    fund_meta_by_ticker — optional per-ETF metadata dict (NAV / units /
    p_unit / asset_breakdown / as_of_date). Empty/missing entries result in
    no fund_meta key on that ETF block, so the frontend's optional rendering
    stays tidy.
    """
    now = updated_at_override or datetime.now(TAIPEI).isoformat(timespec="seconds")
    fund_meta_by_ticker = fund_meta_by_ticker or {}

    # Per-ETF block — full holdings list (TW + foreign) so the frontend's
    # per-ETF expansion can show everything that ETF holds.
    etfs_block = []
    for ticker, holdings in scraped.items():
        meta = etfs_config.get(ticker, {})
        block = {
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "type": meta.get("type", "passive"),
            "tags": meta.get("tags", []),
            "color": meta.get("color", "#58a6ff"),
            "holdings_count": len(holdings),
            "holdings": [
                {
                    "stock_id": h.stock_id,
                    "stock_name": h.stock_name,
                    "weight_pct": h.weight_pct,
                    "shares": h.shares,
                    "market": h.market,
                }
                for h in holdings
            ],
        }
        if meta.get("url"):
            block["url"] = meta["url"]
        fm = fund_meta_by_ticker.get(ticker) or {}
        if fm:
            block["fund_meta"] = fm
        etfs_block.append(block)

    # Cross-aggregation — only TW stocks. Foreign holdings (US/JP) and
    # non-equities (futures classified as OTHER) are excluded from the main
    # cross-table because they can't be cross-counted across pure-TW peer ETFs.
    # See docs/known-issues/holdings-diff-todo.md for the rationale.
    held_by_map: dict[str, list[dict]] = defaultdict(list)
    stock_names: dict[str, str] = {}
    for ticker, holdings in scraped.items():
        for h in holdings:
            if h.market != "TW":
                continue
            held_by_map[h.stock_id].append({
                "etf": ticker,
                "weight_pct": h.weight_pct,
                "shares": h.shares,
            })
            stock_names.setdefault(h.stock_id, h.stock_name)

    holdings_block = []
    for stock_id, held_by in held_by_map.items():
        stock_meta = stocks_config.get(stock_id, {})
        holdings_block.append({
            "stock_id": stock_id,
            "stock_name": stock_meta.get("name") or stock_names.get(stock_id, stock_id),
            "industry": stock_meta.get("industry", ""),
            "held_by": sorted(held_by, key=lambda b: -b["weight_pct"]),
        })

    # Sort: most cross-held first, then by max weight
    holdings_block.sort(key=lambda h: (-len(h["held_by"]), -max(b["weight_pct"] for b in h["held_by"])))

    return {
        "updated_at": now,
        "etfs": sorted(etfs_block, key=lambda e: e["ticker"]),
        "holdings": holdings_block,
    }


def compute_diff(today: dict, yesterday: dict) -> dict:
    """Per-ETF day-over-day holdings delta keyed by ETF ticker.

    For each ETF present in BOTH payloads, partitions the TW-only holdings into:
      - added:   stock_id appears today but not yesterday
      - removed: stock_id appears yesterday but not today (carries yesterday's weight)
      - changed: stock_id in both; weight delta whose abs >= change_threshold
                 (default 0.005% — anything that wouldn't round to a visible
                 0.01% change is filtered as noise)

    ETFs present in only one payload (lineup change) are intentionally absent
    from the result — those should be communicated separately, not as a wall
    of "all stocks added" or "all stocks removed".

    Foreign holdings (market != "TW") are excluded to stay consistent with the
    cross-table convention. Frontend renders an asterisk for top-10-only ETFs
    (Capital) where false-positive added/removed are likely.
    """
    today_etfs = {e["ticker"]: e for e in today.get("etfs", [])}
    yesterday_etfs = {e["ticker"]: e for e in yesterday.get("etfs", [])}

    result: dict = {}
    for ticker in today_etfs.keys() & yesterday_etfs.keys():
        # Backward-compat: pre-v1.5 snapshots have no etfs[i].holdings field.
        # Skip rather than flagging everything as added (false 🆕 noise).
        if "holdings" not in yesterday_etfs[ticker] or "holdings" not in today_etfs[ticker]:
            continue
        today_h = {
            h["stock_id"]: h
            for h in today_etfs[ticker]["holdings"]
            if h.get("market") == "TW"
        }
        yesterday_h = {
            h["stock_id"]: h
            for h in yesterday_etfs[ticker]["holdings"]
            if h.get("market") == "TW"
        }

        added = [
            {"stock_id": h["stock_id"], "stock_name": h["stock_name"],
             "shares": h.get("shares", 0) or 0}
            for sid, h in today_h.items()
            if sid not in yesterday_h
        ]
        removed = [
            {"stock_id": h["stock_id"], "stock_name": h["stock_name"],
             "shares": h.get("shares", 0) or 0}
            for sid, h in yesterday_h.items()
            if sid not in today_h
        ]
        # Only real trades count — weight % floats daily from price moves,
        # only a change in share count means the manager actually bought/sold.
        changed = []
        for sid in today_h.keys() & yesterday_h.keys():
            t, y = today_h[sid], yesterday_h[sid]
            shares_t = t.get("shares", 0) or 0
            shares_y = y.get("shares", 0) or 0
            if shares_t == shares_y:
                continue
            changed.append({
                "stock_id": sid,
                "stock_name": t["stock_name"],
                "shares_now": shares_t,
                "shares_prev": shares_y,
                "shares_delta": shares_t - shares_y,
            })

        result[ticker] = {
            "added": sorted(added, key=lambda h: -(h["shares"] or 0)),
            "removed": sorted(removed, key=lambda h: -(h["shares"] or 0)),
            "changed": sorted(changed, key=lambda h: -abs(h["shares_delta"])),
        }
    return result


def compute_leaderboard(
    today: dict,
    baseline: dict,
    *,
    top_n: int = 5,
    move_threshold: float = 0.05,
) -> dict:
    """Top movers across all ETFs over the today-vs-baseline window.

    For each TW stock, sums per-ETF weight deltas across every ETF that holds
    it in either snapshot. Stocks fully added in today (absent in baseline)
    contribute today's weight as positive delta; fully removed stocks
    contribute baseline's weight as negative delta.

    `etf_count` counts only ETFs whose individual delta has |delta| >= move_threshold —
    that's the "above noise" tally that makes a "consensus move" badge meaningful.
    `total_delta` sums every per-ETF contribution regardless of threshold so the
    magnitude isn't lost.

    Returns:
      {
        "top_added":   [{stock_id, stock_name, etf_count, total_delta}, ... up to top_n],
        "top_removed": [{stock_id, stock_name, etf_count, total_delta}, ... up to top_n],
      }

    ETFs whose baseline entry lacks etfs[i].holdings (pre-v1.5 snapshots)
    are skipped — without this guard, every TW stock in those ETFs would
    register as freshly added.
    """
    today_etfs = {e["ticker"]: e for e in today.get("etfs", [])}
    baseline_etfs = {e["ticker"]: e for e in baseline.get("etfs", [])}

    # stock_id -> {"name": ..., "total_delta": float, "etf_count": int}
    aggregate: dict[str, dict] = {}

    for ticker in today_etfs.keys() & baseline_etfs.keys():
        today_etf = today_etfs[ticker]
        baseline_etf = baseline_etfs[ticker]
        if "holdings" not in today_etf or "holdings" not in baseline_etf:
            continue

        today_h = {h["stock_id"]: h for h in today_etf["holdings"] if h.get("market") == "TW"}
        baseline_h = {h["stock_id"]: h for h in baseline_etf["holdings"] if h.get("market") == "TW"}

        for sid in today_h.keys() | baseline_h.keys():
            t = today_h.get(sid)
            b = baseline_h.get(sid)
            if t and b:
                delta = t["weight_pct"] - b["weight_pct"]
                name = t["stock_name"]
            elif t:
                delta = t["weight_pct"]            # newly held
                name = t["stock_name"]
            else:
                delta = -b["weight_pct"]           # fully removed
                name = b["stock_name"]

            if delta == 0:
                continue
            entry = aggregate.setdefault(sid, {"name": name, "total_delta": 0.0, "etf_count": 0})
            entry["total_delta"] += delta
            if abs(delta) >= move_threshold:
                entry["etf_count"] += 1

    added = [
        {"stock_id": sid, "stock_name": v["name"],
         "etf_count": v["etf_count"], "total_delta": round(v["total_delta"], 4)}
        for sid, v in aggregate.items()
        if v["total_delta"] > 0 and v["etf_count"] > 0
    ]
    removed = [
        {"stock_id": sid, "stock_name": v["name"],
         "etf_count": v["etf_count"], "total_delta": round(v["total_delta"], 4)}
        for sid, v in aggregate.items()
        if v["total_delta"] < 0 and v["etf_count"] > 0
    ]

    added.sort(key=lambda x: (-x["total_delta"], -x["etf_count"]))
    removed.sort(key=lambda x: (x["total_delta"], -x["etf_count"]))

    return {"top_added": added[:top_n], "top_removed": removed[:top_n]}


def write_payload(payload: dict, data_dir: str | Path = "data") -> None:
    """Write latest.json and today's snapshot to data/."""
    data_dir = Path(data_dir)
    (data_dir / "snapshots").mkdir(parents=True, exist_ok=True)

    latest_path = data_dir / "latest.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    date = datetime.now(TAIPEI).date().isoformat()
    snapshot_path = data_dir / "snapshots" / f"{date}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
