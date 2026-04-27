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
) -> dict:
    """Combine per-ETF holdings, ETF metadata, and stock metadata into the
    shape described in the design spec §4.1.
    """
    now = updated_at_override or datetime.now(TAIPEI).isoformat(timespec="seconds")

    # Per-ETF block — full holdings list (TW + foreign) so the frontend's
    # per-ETF expansion can show everything that ETF holds.
    etfs_block = []
    for ticker, holdings in scraped.items():
        meta = etfs_config.get(ticker, {})
        etfs_block.append({
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
        })

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


def write_payload(payload: dict, data_dir: str | Path = "data") -> None:
    """Write latest.json and today's snapshot to data/."""
    data_dir = Path(data_dir)
    (data_dir / "snapshots").mkdir(parents=True, exist_ok=True)

    latest_path = data_dir / "latest.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    date = datetime.now(TAIPEI).date().isoformat()
    snapshot_path = data_dir / "snapshots" / f"{date}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
