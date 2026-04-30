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


from scrapers.twse_prices import PricesFetcher


class TwseTpexDailyClose(PriceProvider):
    """TWSE + TPEx bulk daily-close — wraps existing PricesFetcher."""
    name = "twse_tpex"

    def __init__(self):
        self._fetcher = PricesFetcher()

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        raw = self._fetcher.fetch_all(target_date)
        if not raw:
            raise ProviderUnavailable("TWSE+TPEx returned empty")
        wanted = set(stock_ids)
        return {sid: raw[sid] for sid in wanted if sid in raw}


import os
import logging
import requests

logger = logging.getLogger(__name__)

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindDailyClose(PriceProvider):
    """FinMind per-stock loop. Free tier blocks bulk-by-date so we loop.

    Uses FINMIND_TOKEN env var if set (raises 600/hr → 6000/hr quota).
    """
    name = "finmind"

    def __init__(self):
        self.token = os.environ.get("FINMIND_TOKEN", "").strip()
        self._exhausted = False    # 同 process 內配額爆就停試

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        if self._exhausted:
            raise ProviderUnavailable("FinMind quota exhausted earlier in this process")

        date_str = target_date.isoformat()
        result: dict[str, dict] = {}
        for sid in stock_ids:
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": sid,
                "start_date": date_str,
                "end_date": date_str,
            }
            if self.token:
                params["token"] = self.token
            try:
                r = requests.get(FINMIND_URL, params=params, timeout=20)
                d = r.json()
            except Exception as e:
                logger.warning("[finmind] %s: %s", sid, e)
                continue

            status = d.get("status")
            if status == 402:
                self._exhausted = True
                raise ProviderUnavailable(f"FinMind quota: {d.get('msg')}")
            if status == 400 and "level" in (d.get("msg") or "").lower():
                raise ProviderUnavailable(f"FinMind level too low: {d.get('msg')}")
            if status != 200:
                logger.warning("[finmind] %s status=%s msg=%s", sid, status, d.get("msg"))
                continue

            rows = d.get("data") or []
            if not rows:
                continue
            row = rows[-1]
            close = float(row["close"])
            change = float(row.get("spread") or 0.0)
            prev = close - change
            change_pct = round(change / prev * 100, 2) if prev > 0 else 0.0
            result[sid] = {
                "close": round(close, 2),
                "change": round(change, 2),
                "change_pct": change_pct,
                "exchange": "TWSE",
            }
        return result
