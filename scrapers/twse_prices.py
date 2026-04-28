"""Daily-close price fetcher for Taiwan stocks.

Single market-wide pull (not per-ETF) — feeds the 收盤/漲跌% column on the
cross-holdings table. TWSE (上市) and TPEx (上櫃) have separate endpoints
with different response shapes; both are queried and merged.

Output shape (data/prices_today.json):
  {"date": "2026-04-27", "prices": {stock_id: {close, change, change_pct}, ...}}

Soft-fails on any endpoint problem: logs a warning and returns whatever it
got. Empty prices on failure is preferable to taking down the whole pipeline
(prices are an enrichment, not core data).
"""
from __future__ import annotations
import json
import logging
import re
from datetime import date

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

TWSE_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date}&type=ALL"
TPEX_URL = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={date}&se=AL&s=0,asc,0"

# TWSE 漲跌(+/-) cell is HTML-wrapped: <p style= color:red>+</p> or color:green for −
_TWSE_SIGN_POS = re.compile(r"color:\s*red", re.IGNORECASE)
_TWSE_SIGN_NEG = re.compile(r"color:\s*green", re.IGNORECASE)


def parse_twse_prices(text: str) -> dict[str, dict]:
    """Extract per-stock close + signed change from a TWSE MI_INDEX response."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if data.get("stat") != "OK":
        return {}

    table = next((t for t in data.get("tables", []) if "每日收盤行情" in t.get("title", "")), None)
    if not table:
        return {}

    fields = table.get("fields", [])
    try:
        i_id    = fields.index("證券代號")
        i_close = fields.index("收盤價")
        i_sign  = fields.index("漲跌(+/-)")
        i_chg   = fields.index("漲跌價差")
    except ValueError:
        return {}

    out: dict[str, dict] = {}
    for row in table.get("data", []):
        try:
            sid = row[i_id]
            close = _safe_float(row[i_close])
            chg_abs = _safe_float(row[i_chg])
            if close is None or chg_abs is None:
                continue
            sign_html = str(row[i_sign])
            sign = +1 if _TWSE_SIGN_POS.search(sign_html) else (-1 if _TWSE_SIGN_NEG.search(sign_html) else 0)
            chg = sign * chg_abs
            prev_close = close - chg
            chg_pct = round(chg / prev_close * 100, 2) if prev_close > 0 else 0.0
            out[sid] = {"close": round(close, 2), "change": round(chg, 2), "change_pct": chg_pct}
        except Exception:
            continue
    return out


def parse_tpex_prices(text: str) -> dict[str, dict]:
    """Extract per-stock close + signed change from a TPEx daily-close response."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if data.get("stat") != "ok":
        return {}

    table = next((t for t in data.get("tables", []) if "上櫃股票行情" in t.get("title", "")), None)
    if not table:
        return {}

    fields = table.get("fields", [])
    try:
        i_id    = fields.index("代號")
        i_close = fields.index("收盤")
        i_chg   = fields.index("漲跌")
    except ValueError:
        return {}

    out: dict[str, dict] = {}
    for row in table.get("data", []):
        try:
            sid = row[i_id]
            close = _safe_float(row[i_close])
            chg = _safe_float(row[i_chg])  # already signed in TPEx
            if close is None or chg is None:
                continue
            prev_close = close - chg
            chg_pct = round(chg / prev_close * 100, 2) if prev_close > 0 else 0.0
            out[sid] = {"close": round(close, 2), "change": round(chg, 2), "change_pct": chg_pct}
        except Exception:
            continue
    return out


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


class PricesFetcher(BaseScraper):
    """Hits TWSE + TPEx daily-close endpoints and merges into a single dict."""

    def fetch_all(self, target_date: date) -> dict[str, dict]:
        twse_date = target_date.strftime("%Y%m%d")
        tpex_date = f"{target_date.year - 1911}/{target_date.month:02d}/{target_date.day:02d}"

        prices: dict[str, dict] = {}
        try:
            twse_text = self.get(TWSE_URL.format(date=twse_date))
            twse = parse_twse_prices(twse_text)
            for sid, data in twse.items():
                prices[sid] = {**data, "exchange": "TWSE"}
            logger.info("prices: TWSE %d stocks", len(twse))
        except Exception as exc:
            logger.warning("prices: TWSE fetch failed: %s", exc)

        try:
            tpex_text = self.get(TPEX_URL.format(date=tpex_date))
            tpex = parse_tpex_prices(tpex_text)
            for sid, data in tpex.items():
                if sid not in prices:
                    prices[sid] = {**data, "exchange": "TPEX"}
            logger.info("prices: TPEx %d stocks", len(tpex))
        except Exception as exc:
            logger.warning("prices: TPEx fetch failed: %s", exc)

        return prices
