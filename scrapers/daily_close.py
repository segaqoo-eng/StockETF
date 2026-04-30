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


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")


def fetch_daily_close(
    stock_ids: list[str],
    target_date: date,
    providers: list[PriceProvider] | None = None,
) -> dict:
    """Walk providers in order; first one returning ≥ SUCCESS_THRESHOLD wins.

    See spec §3 + §4 for full behavior.

    Returns:
      {
        "ok":         bool,
        "date":       "YYYY-MM-DD",
        "source":     "finmind" | "yfinance" | "twse_tpex" | "cache" | None,
        "fetched_at": ISO8601 with Asia/Taipei tz,
        "prices":     {stock_id: {close, change, change_pct, exchange}},
        "missing":    [stock_id, ...],
        "tried":      [provider_name, ...],
        "error":      str | None,
      }
    """
    if providers is None:
        providers = [
            FinMindDailyClose(),
            YFinanceDailyClose(),
            TwseTpexDailyClose(),
            CacheDailyClose(),
        ]

    tried: list[str] = []
    for p in providers:
        tried.append(p.name)
        try:
            partial = p.fetch(stock_ids, target_date)
        except ProviderUnavailable as e:
            logger.warning("[%s] unavailable: %s", p.name, e)
            continue
        except Exception as e:
            logger.warning("[%s] unexpected error: %s", p.name, e)
            continue

        if not partial:
            continue
        ratio = len(partial) / max(1, len(stock_ids))
        if ratio < SUCCESS_THRESHOLD:
            logger.info("[%s] returned %d/%d (<%.0f%%), trying next",
                        p.name, len(partial), len(stock_ids), SUCCESS_THRESHOLD * 100)
            continue

        missing = [sid for sid in stock_ids if sid not in partial]
        return {
            "ok":         True,
            "date":       target_date.isoformat(),
            "source":     p.name,
            "fetched_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
            "prices":     partial,
            "missing":    missing,
            "tried":      tried,
            "error":      None,
        }

    return {
        "ok":         False,
        "date":       target_date.isoformat(),
        "source":     None,
        "fetched_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "prices":     {},
        "missing":    list(stock_ids),
        "tried":      tried,
        "error":      "all providers failed",
    }


class YFinanceDailyClose(PriceProvider):
    """yfinance batch download for multiple tickers.

    Tries .TW (TWSE) suffix only; per spec we don't iterate .TWO since the
    universe comes from latest.json which already classifies. If a stock
    is on TPEx, this provider will miss it — TWSE+TPEx fallback covers.
    """
    name = "yfinance"

    def fetch(self, stock_ids: list[str], target_date: date) -> dict[str, dict]:
        try:
            import yfinance as yf
        except ImportError:
            raise ProviderUnavailable("yfinance not installed")

        if not stock_ids:
            return {}

        tickers = [f"{sid}.TW" for sid in stock_ids]
        start = target_date - timedelta(days=5)
        end = target_date + timedelta(days=1)

        # Suppress yfinance's chatty stdout/stderr (per-ticker 404s, "possibly
        # delisted" lines, "N Failed downloads" summary). TPEx stocks always fail
        # the .TW lookup; TWSE+TPEx provider covers them in the next fallback.
        import contextlib, io
        yf_logger = logging.getLogger("yfinance")
        yf_old_level = yf_logger.level
        yf_logger.setLevel(logging.CRITICAL)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    df = yf.download(
                        tickers,
                        start=start.isoformat(),
                        end=end.isoformat(),
                        progress=False,
                        threads=True,
                        group_by="ticker",
                        auto_adjust=False,
                    )
                except Exception as e:
                    raise ProviderUnavailable(f"yfinance download failed: {e}")
        finally:
            yf_logger.setLevel(yf_old_level)

        if df is None or df.empty:
            raise ProviderUnavailable("yfinance returned empty DataFrame")

        result: dict[str, dict] = {}
        for sid in stock_ids:
            ticker = f"{sid}.TW"
            try:
                if ticker not in df.columns.get_level_values(0):
                    continue
                sub = df[ticker].dropna(subset=["Close"])
                if len(sub) < 1:
                    continue
                close = float(sub["Close"].iloc[-1])
                prev = float(sub["Close"].iloc[-2]) if len(sub) >= 2 else close
                change = close - prev
                change_pct = round(change / prev * 100, 2) if prev > 0 else 0.0
                result[sid] = {
                    "close": round(close, 2),
                    "change": round(change, 2),
                    "change_pct": change_pct,
                    "exchange": "TWSE",
                }
            except Exception as e:
                logger.warning("[yfinance] %s: %s", sid, e)
                continue

        missing = len(stock_ids) - len(result)
        if missing > 0:
            logger.info("[yfinance] %d/%d unavailable (likely TPEx), fallthrough may apply",
                        missing, len(stock_ids))
        return result
