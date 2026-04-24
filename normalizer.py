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
) -> dict:
    """Combine per-ETF holdings, ETF metadata, and stock metadata into the
    shape described in the design spec §4.1.
    """
    now = datetime.now(TAIPEI).isoformat(timespec="seconds")

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
        })

    # held_by_map[stock_id] = list of {"etf": ticker, "weight_pct", "shares"}
    held_by_map: dict[str, list[dict]] = defaultdict(list)
    stock_names: dict[str, str] = {}
    for ticker, holdings in scraped.items():
        for h in holdings:
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
