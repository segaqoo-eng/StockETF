"""4 層 PriceProvider chain for fetching today's close prices.

Spec: docs/superpowers/specs/2026-04-30-prices-source-and-refresh-design.md
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


SUCCESS_THRESHOLD = 0.80   # 回傳 ≥ 80% stock_ids 視為該 provider 成功


class ProviderUnavailable(Exception):
    """Provider 整體不可用 — dispatch 應跳下一家。"""


class PriceProvider:
    """Abstract daily-close fetcher.

    fetch() 部分失敗（149/150 成功）：仍 return 那 149 檔 dict
    fetch() 整體失敗（HTTP error / 配額爆 / 等級不足 / 空回傳）：raise ProviderUnavailable
    """
    name: str = "abstract"

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        raise NotImplementedError


class CacheDailyClose(PriceProvider):
    """Read existing data/prices_today.json — last-resort fallback."""
    name = "cache"

    def __init__(self, cache_path: Path | str = Path("data/prices_today.json")):
        self.cache_path = Path(cache_path)

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        if not self.cache_path.exists():
            raise ProviderUnavailable(f"cache file missing: {self.cache_path}")
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise ProviderUnavailable(f"cache read failed: {e}")
        prices = payload.get("prices") or {}
        if not prices:
            raise ProviderUnavailable("cache prices empty")
        # filter to only requested stock_ids
        return {sid: prices[sid] for sid in stock_ids if sid in prices}
