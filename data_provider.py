"""SQLite-backed multi-source stock data cache.

設計目標：
  1. 在地累積：抓過的歷史資料寫進 SQLite，未來不用重抓
  2. 多資料源 fallback：FinMind 撞限額時自動切 yfinance / TWSE
  3. 增量更新：每次 query 只抓「DB 缺的那段」
  4. 對 backtest.py 透明：API 維持回傳 list[dict]，欄位與 FinMind 相容

用法：
    from data_provider import get_ohlcv, get_institutional, get_benchmark_close

    ohlcv = get_ohlcv("2330", start_date="2025-04-01")
    inst  = get_institutional("2330", start_date="2025-04-01")

DB 位置：data/stock_data.db （.gitignore 已排除）
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

DB_PATH = Path("data/stock_data.db")
TAIPEI = ZoneInfo("Asia/Taipei")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    stock_id TEXT NOT NULL,
    date     TEXT NOT NULL,
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   INTEGER,
    source   TEXT,
    PRIMARY KEY (stock_id, date)
);

CREATE TABLE IF NOT EXISTS institutional (
    stock_id TEXT NOT NULL,
    date     TEXT NOT NULL,
    name     TEXT NOT NULL,
    buy      INTEGER,
    sell     INTEGER,
    source   TEXT,
    PRIMARY KEY (stock_id, date, name)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_date         ON ohlcv(date);
CREATE INDEX IF NOT EXISTS idx_institutional_date ON institutional(date);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.executescript(_SCHEMA)
    return c


# ── DB 讀寫 ─────────────────────────────────────────────────

def _read_ohlcv(stock_id: str, start_date: str) -> list[dict]:
    """欄位名稱與 FinMind 相容 (max/min/Trading_Volume)。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT date, open, high, low, close, volume "
            "FROM ohlcv WHERE stock_id = ? AND date >= ? "
            "ORDER BY date",
            (stock_id, start_date),
        ).fetchall()
    return [
        {"date": r[0], "open": r[1], "max": r[2], "min": r[3],
         "close": r[4], "Trading_Volume": r[5]}
        for r in rows
    ]


def _save_ohlcv(stock_id: str, rows: list[dict], source: str) -> int:
    if not rows:
        return 0
    payload = []
    for r in rows:
        # 兼容 FinMind 命名 (max/min/Trading_Volume) 和標準命名 (high/low/volume)
        payload.append((
            stock_id,
            r["date"],
            r.get("open"),
            r.get("max", r.get("high")),
            r.get("min", r.get("low")),
            r.get("close"),
            r.get("Trading_Volume", r.get("volume")),
            source,
        ))
    with _conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO ohlcv "
            "(stock_id, date, open, high, low, close, volume, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
    return len(payload)


def _read_institutional(stock_id: str, start_date: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT date, name, buy, sell "
            "FROM institutional WHERE stock_id = ? AND date >= ? "
            "ORDER BY date, name",
            (stock_id, start_date),
        ).fetchall()
    return [{"date": r[0], "name": r[1], "buy": r[2], "sell": r[3]} for r in rows]


def _save_institutional(stock_id: str, rows: list[dict], source: str) -> int:
    if not rows:
        return 0
    payload = [
        (stock_id, r["date"], r["name"], r.get("buy", 0), r.get("sell", 0), source)
        for r in rows
    ]
    with _conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO institutional "
            "(stock_id, date, name, buy, sell, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            payload,
        )
    return len(payload)


def _last_date(stock_id: str, table: str) -> str | None:
    with _conn() as c:
        r = c.execute(f"SELECT MAX(date) FROM {table} WHERE stock_id = ?",
                      (stock_id,)).fetchone()
    return r[0] if r and r[0] else None


# ── Provider 抽象 ───────────────────────────────────────────

class DataProvider:
    name = "abstract"

    def fetch_ohlcv(self, stock_id: str, start_date: str) -> list[dict]:
        raise NotImplementedError

    def fetch_institutional(self, stock_id: str, start_date: str) -> list[dict]:
        raise NotImplementedError


class FinMindProvider(DataProvider):
    name = "finmind"
    URL = "https://api.finmindtrade.com/api/v4/data"

    def __init__(self):
        self.token = os.environ.get("FINMIND_TOKEN", "").strip()
        self._exhausted = False  # 一旦撞 limit 同個 process 不再嘗試

    def _fetch(self, dataset: str, stock_id: str, start_date: str) -> list[dict]:
        if self._exhausted:
            return []
        params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date}
        if self.token:
            params["token"] = self.token
        try:
            r = requests.get(self.URL, params=params, timeout=30)
            d = r.json()
            if d.get("status") == 200:
                return d.get("data", [])
            if d.get("status") == 402:
                self._exhausted = True
                print(f"[FinMind] 配額用完：{d.get('msg', '')}\n"
                      f"  → 註冊 finmindtrade.com 取 token 可提升 600→6000/hr",
                      file=sys.stderr)
        except Exception as e:
            print(f"[FinMind] {stock_id} {dataset}: {e}", file=sys.stderr)
        return []

    def fetch_ohlcv(self, stock_id, start_date):
        return self._fetch("TaiwanStockPrice", stock_id, start_date)

    def fetch_institutional(self, stock_id, start_date):
        return self._fetch("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date)


class YFinanceProvider(DataProvider):
    """Yahoo Finance fallback (僅 OHLCV，TW 三大法人不提供)。

    Symbol 格式：上市 `NNNN.TW`、上櫃 `NNNN.TWO`。
    """
    name = "yfinance"

    def __init__(self):
        self._yf = None  # lazy import (yfinance 是 optional dep)

    def _import_yf(self):
        if self._yf is None:
            try:
                import yfinance as yf  # type: ignore[import-untyped]
                self._yf = yf
            except ImportError:
                print("[yfinance] 未安裝，pip install yfinance 後可用", file=sys.stderr)
                self._yf = False  # 標記為不可用
        return self._yf

    def fetch_ohlcv(self, stock_id, start_date):
        yf = self._import_yf()
        if not yf:
            return []
        # 試上市 .TW 再試上櫃 .TWO
        for suffix in (".TW", ".TWO"):
            symbol = f"{stock_id}{suffix}"
            try:
                df = yf.download(symbol, start=start_date, progress=False,
                                 auto_adjust=False, threads=False)
                if df is None or df.empty:
                    continue
                # MultiIndex 拆出第一層
                if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                    df.columns = df.columns.get_level_values(0)
                rows = []
                for d, row in df.iterrows():
                    rows.append({
                        "date": d.strftime("%Y-%m-%d"),
                        "open":  float(row.get("Open"))   if "Open"   in row else None,
                        "max":   float(row.get("High"))   if "High"   in row else None,
                        "min":   float(row.get("Low"))    if "Low"    in row else None,
                        "close": float(row.get("Close"))  if "Close"  in row else None,
                        "Trading_Volume": int(row.get("Volume", 0))
                            if "Volume" in row else None,
                    })
                return rows
            except Exception as e:
                print(f"[yfinance] {symbol}: {e}", file=sys.stderr)
        return []

    def fetch_institutional(self, stock_id, start_date):
        return []  # 不支援


_DEFAULT_PROVIDERS: list[DataProvider] | None = None


def default_providers() -> list[DataProvider]:
    global _DEFAULT_PROVIDERS
    if _DEFAULT_PROVIDERS is None:
        _DEFAULT_PROVIDERS = [FinMindProvider(), YFinanceProvider()]
    return _DEFAULT_PROVIDERS


# ── 對外 API ────────────────────────────────────────────────

def _today_iso() -> str:
    return datetime.now(TAIPEI).date().isoformat()


def get_ohlcv(stock_id: str, start_date: str,
              providers: list[DataProvider] | None = None) -> list[dict]:
    """從 DB 拿 OHLCV，缺的部分依序問 providers。永遠回傳合併後完整資料。"""
    last = _last_date(stock_id, "ohlcv")
    today = _today_iso()
    needs_fetch = (last is None) or (last < today)

    if needs_fetch:
        # DB 已有資料就只抓「下一天起」，沒就從 start_date 起
        fetch_from = start_date if last is None else (
            (datetime.fromisoformat(last) + timedelta(days=1)).date().isoformat()
        )
        for p in providers or default_providers():
            new_rows = p.fetch_ohlcv(stock_id, fetch_from)
            if new_rows:
                _save_ohlcv(stock_id, new_rows, source=p.name)
                break
    return _read_ohlcv(stock_id, start_date)


def get_institutional(stock_id: str, start_date: str,
                       providers: list[DataProvider] | None = None) -> list[dict]:
    """從 DB 拿三大法人，缺的部分依序問 providers。"""
    last = _last_date(stock_id, "institutional")
    today = _today_iso()
    needs_fetch = (last is None) or (last < today)

    if needs_fetch:
        fetch_from = start_date if last is None else (
            (datetime.fromisoformat(last) + timedelta(days=1)).date().isoformat()
        )
        for p in providers or default_providers():
            new_rows = p.fetch_institutional(stock_id, fetch_from)
            if new_rows:
                _save_institutional(stock_id, new_rows, source=p.name)
                break
    return _read_institutional(stock_id, start_date)


def db_stats() -> dict:
    """方便 debug：DB 裡有多少資料。"""
    with _conn() as c:
        ohlcv_n  = c.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        ohlcv_s  = c.execute("SELECT COUNT(DISTINCT stock_id) FROM ohlcv").fetchone()[0]
        ohlcv_d  = c.execute("SELECT MIN(date), MAX(date) FROM ohlcv").fetchone()
        inst_n   = c.execute("SELECT COUNT(*) FROM institutional").fetchone()[0]
        inst_s   = c.execute("SELECT COUNT(DISTINCT stock_id) FROM institutional").fetchone()[0]
        sources  = c.execute("SELECT source, COUNT(*) FROM ohlcv GROUP BY source").fetchall()
    return {
        "ohlcv_rows": ohlcv_n,
        "ohlcv_stocks": ohlcv_s,
        "ohlcv_date_range": ohlcv_d,
        "institutional_rows": inst_n,
        "institutional_stocks": inst_s,
        "sources": dict(sources),
    }


if __name__ == "__main__":
    # CLI: python data_provider.py 顯示 DB 統計
    import json
    print(json.dumps(db_stats(), ensure_ascii=False, indent=2, default=str))
