"""
backtest.py — 買進評分策略回測（本機執行）

策略：
  今日分數 > 65 且未持倉 → 明日收盤買進
  今日分數 < 60 且持倉中 → 明日收盤賣出

用法：
  .venv\\Scripts\\python.exe backtest.py
"""

import json, os, time, sys
from pathlib import Path
import requests
import pandas as pd
import numpy as np
from datetime import date

# 可選：FinMind API token (https://finmindtrade.com 免費註冊就有，配額 600→6000/小時)
# 設定方式：在 shell 或 update.bat 裡 set FINMIND_TOKEN=eyJ...
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()

# ── 設定 ────────────────────────────────────────────────
BACKTEST_START = "2025-10-01"   # 回測起點（半年）
DATA_START     = "2025-04-01"   # 抓取起點（需足夠計算指標）
SLEEP_SEC      = 0.8            # 每次 API 請求間隔
FINMIND_URL    = "https://api.finmindtrade.com/api/v4/data"

# 交易成本（單筆來回，台股實際）
#   買進手續費 0.1% + 賣出手續費 0.1% + 證交稅 0.3% ≈ 0.5%
COST_PER_ROUND_TRIP_PCT = 0.5

# 基準對照
BENCHMARK_TICKER = "0050"

# 策略變體：一次跑多組參數 (資料只抓一次，CPU 計算便宜)
#   buy:      score > buy 才買進
#   sell:     score < sell 才賣出 (None = 不看分數，只看價)
#   stop_pct: 浮動虧損低於此 % 強制下個交易日賣出 (None 表示不停損)
#   tp_pct:   浮動獲利超過此 % 強制下個交易日賣出 (None 表示不停利)
STRATEGIES = [
    {"name": "baseline",    "label": "原 65/60/無/無",        "buy": 65, "sell": 60,   "stop_pct": None,  "tp_pct": None},
    {"name": "combined",    "label": "強組合 75/50/-8%/無",   "buy": 75, "sell": 50,   "stop_pct": -8.0,  "tp_pct": None},
    {"name": "tp3",         "label": "便當3 65/無/-5%/+3%",   "buy": 65, "sell": None, "stop_pct": -5.0,  "tp_pct": 3.0},
    {"name": "tp5",         "label": "便當5 65/無/-5%/+5%",   "buy": 65, "sell": None, "stop_pct": -5.0,  "tp_pct": 5.0},
    {"name": "tight_tp5",   "label": "嚴便當 75/無/-5%/+5%",  "buy": 75, "sell": None, "stop_pct": -5.0,  "tp_pct": 5.0},
]
# ────────────────────────────────────────────────────────


def get_stocks():
    with open("data/latest.json", encoding="utf-8") as f:
        d = json.load(f)
    return [(h["stock_id"], h["stock_name"]) for h in d["holdings"]]


CACHE_DIR = Path("data/finmind_cache")
CACHE_TTL_SEC = 24 * 3600   # 一天內 cache 有效


def fetch_finmind(dataset, stock_id):
    """先看 cache (24h 內視為新鮮)，沒命中再打 API。

    用意：一天內反覆調策略不會耗 API 配額。FinMind 免費版每 IP 每小時有 limit。
    """
    cache_file = CACHE_DIR / f"{dataset}_{stock_id}.json"
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL_SEC:
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass  # cache 壞了就重抓

    params = {"dataset": dataset, "data_id": stock_id, "start_date": DATA_START}
    if FINMIND_TOKEN:
        params["token"] = FINMIND_TOKEN
    try:
        r = requests.get(FINMIND_URL, params=params, timeout=30)
        d = r.json()
        if d.get("status") == 200 and d.get("data"):
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(d["data"], ensure_ascii=False), encoding="utf-8")
            return d["data"]
        # rate limit / 配額用完時印明顯訊息一次
        if d.get("status") == 402:
            global _RATE_LIMIT_WARNED
            if not _RATE_LIMIT_WARNED:
                _RATE_LIMIT_WARNED = True
                print(f"\n[FINMIND RATE LIMIT] {d.get('msg','')}\n"
                      f"  → 註冊免費帳號取得 token 可提升到 6000/hr：https://finmindtrade.com\n"
                      f"  → 取得後執行：set FINMIND_TOKEN=eyJ... 再跑 update.bat\n",
                      file=sys.stderr)
    except Exception as e:
        print(f"[WARN] {stock_id} {dataset}: {e}", file=sys.stderr)
    return []


_RATE_LIMIT_WARNED = False


# ── 技術指標（pandas 版） ────────────────────────────────

def calc_rsi(closes: pd.Series, period=14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calc_macd(closes: pd.Series, fast=12, slow=26, sig=9):
    ema_f = closes.ewm(span=fast, adjust=False).mean()
    ema_s = closes.ewm(span=slow, adjust=False).mean()
    macd  = ema_f - ema_s
    signal = macd.ewm(span=sig, adjust=False).mean()
    return macd, signal, macd - signal   # macd, signal, hist


def calc_kd(df: pd.DataFrame, period=9, sm=3):
    hi = df["high"].rolling(period).max()
    lo = df["low"].rolling(period).min()
    rsv = ((df["close"] - lo) / (hi - lo).replace(0, np.nan) * 100).fillna(50)
    k = rsv.ewm(com=sm - 1, adjust=False).mean()
    d = k.ewm(com=sm - 1, adjust=False).mean()
    return k, d


# ── 籌碼解析 ─────────────────────────────────────────────

def parse_inst(raw):
    """raw list → dict[date_str] = {foreign, trust, dealer}（單位：張）"""
    bydate = {}
    for r in raw:
        dt = r["date"]
        if dt not in bydate:
            bydate[dt] = {"foreign": 0.0, "trust": 0.0, "dealer": 0.0}
        net = ((r.get("buy") or 0) - (r.get("sell") or 0)) / 1000
        n = r.get("name", "")
        if n in ("Foreign_Investor", "Foreign_Dealer_Self"):
            bydate[dt]["foreign"] += net
        elif n == "Investment_Trust":
            bydate[dt]["trust"] += net
        elif n in ("Dealer_self", "Dealer_Hedging"):
            bydate[dt]["dealer"] += net
    return bydate


# ── 單日評分 ─────────────────────────────────────────────

def score_on_day(df: pd.DataFrame, inst: dict, as_of: str) -> float | None:
    """計算 as_of 當日的買進分數（只用 as_of 以前的資料）。"""
    sub = df[df["date"] <= as_of].copy()
    if len(sub) < 30:
        return None
    closes = sub["close"]

    # ── 技術分數 ──
    tech = 0

    rsi = calc_rsi(closes)
    if not pd.isna(rsi.iloc[-1]):
        v = rsi.iloc[-1]
        if v < 30:      tech += 6
        elif v < 50:    tech += 3
        elif v < 70:    tech += 2
        elif v < 80:    tech -= 2
        else:           tech -= 5

    macd, _, hist = calc_macd(closes)
    if len(hist) >= 2 and not pd.isna(hist.iloc[-1]):
        if   hist.iloc[-2] <= 0 and hist.iloc[-1] > 0: tech += 6
        elif hist.iloc[-2] >= 0 and hist.iloc[-1] < 0: tech -= 6
        elif macd.iloc[-1] > 0:                          tech += 3

    k, d = calc_kd(sub)
    if len(k) >= 2 and not pd.isna(k.iloc[-1]):
        k1, d1 = k.iloc[-2], d.iloc[-2]
        k2, d2 = k.iloc[-1], d.iloc[-1]
        if   k1 <= d1 and k2 > d2:              tech += 5
        elif k2 < 20:                            tech += 4
        elif k1 >= d1 and k2 < d2 and k2 >= 20: tech -= 3
        elif k2 > 80:                            tech -= 3

    if len(closes) >= 60:
        ma5, ma20, ma60 = closes.iloc[-5:].mean(), closes.iloc[-20:].mean(), closes.iloc[-60:].mean()
        if   ma5 > ma20 > ma60: tech += 8
        elif ma5 < ma20 < ma60: tech -= 8

    tech = max(-30, min(30, tech))

    # ── 籌碼分數 ──
    chip = 0
    recent = sorted([dt for dt in inst if dt <= as_of], reverse=True)[:10]
    if recent:
        near5 = recent[:5]
        fT = sum(inst[dt]["foreign"] for dt in near5)
        tT = sum(inst[dt]["trust"]   for dt in near5)
        dT = sum(inst[dt]["dealer"]  for dt in near5)
        if fT > 0: chip += 5
        elif fT < 0: chip -= 5
        if tT > 0: chip += 4
        elif tT < 0: chip -= 4
        if dT > 0: chip += 2
        elif dT < 0: chip -= 2
        # 外資連續性
        sign = 1 if inst[recent[0]]["foreign"] >= 0 else -1
        streak = sum(1 for dt in recent if (1 if inst[dt]["foreign"] >= 0 else -1) == sign)
        fdays = sign * streak
        if fdays >= 5:   chip += 5
        elif fdays <= -5: chip -= 5
        if fT > 0 and tT > 0 and dT > 0: chip += 6
        elif fT < 0 and tT < 0 and dT < 0: chip -= 6
    chip = max(-30, min(30, chip))

    # ── 量價分數 ──
    vol = 0
    if len(sub) >= 6:
        last, prev = sub.iloc[-1], sub.iloc[-2]
        avg_vol = sub.iloc[-6:-1]["volume"].mean()
        if avg_vol > 0:
            if   last["volume"] > avg_vol * 1.5 and last["close"] > prev["close"]: vol += 6
            elif last["volume"] > avg_vol * 1.5 and last["close"] < prev["close"]: vol -= 6
            elif last["volume"] < avg_vol * 0.7 and last["close"] > prev["close"]: vol -= 2
            elif last["volume"] < avg_vol * 0.7 and last["close"] < prev["close"]: vol += 2
    vol = max(-20, min(20, vol))

    # ── 趨勢分數 ──
    trend = 0
    if len(sub) >= 2:
        last, prev = sub.iloc[-1], sub.iloc[-2]
        s60 = sub.iloc[-60:]
        h60, l60 = s60["high"].max(), s60["low"].min()
        if   last["close"] >= h60: trend += 8
        elif last["close"] <= l60: trend -= 8
        if len(closes) >= 21:
            ma20_now  = closes.iloc[-20:].mean()
            ma20_prev = closes.iloc[-21:-1].mean()
            if   last["close"] > ma20_now and prev["close"] <= ma20_prev: trend += 4
            elif last["close"] < ma20_now and prev["close"] >= ma20_prev: trend -= 4
        chg = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0
        if chg > 7:   trend -= 3
        elif chg < -7: trend -= 5
    trend = max(-20, min(20, trend))

    return max(0, min(100, tech + chip + vol + trend + 50))


# ── 單股回測 ─────────────────────────────────────────────

def _close_position(position, sell_date, sell_price, exit_reason):
    """產生 trade dict (扣費後的 net + gross 都記)。"""
    bp = position["buy_price"]
    ret_gross = (sell_price - bp) / bp * 100
    return {**position,
        "sell_date": sell_date, "sell_price": sell_price,
        "return_pct_gross": ret_gross,
        "return_pct": ret_gross - COST_PER_ROUND_TRIP_PCT,
        "hold_days": (pd.to_datetime(sell_date) - pd.to_datetime(position["buy_date"])).days,
        "exit": exit_reason,
    }


def prep_stock(ohlcv_raw, inst_raw):
    """事先算好 bt_df + 每日 score (策略共用，避免重複計算)。

    回傳 None 表示資料不足、跳過。
    """
    df = pd.DataFrame(ohlcv_raw).rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
    df = df.sort_values("date").reset_index(drop=True)
    inst = parse_inst(inst_raw)

    bt_df = df[df["date"] >= BACKTEST_START].reset_index(drop=True)
    if bt_df.empty:
        return None
    scores = {as_of: score_on_day(df, inst, as_of) for as_of in bt_df["date"]}
    return {"bt_df": bt_df, "scores": scores}


def run_strategy(stock_id, stock_name, prep, strategy):
    """跑單一策略 (buy/sell/stop_pct 由 strategy 參數決定)。共用 prep。"""
    bt_df = prep["bt_df"]
    scores = prep["scores"]

    buy_thr  = strategy["buy"]
    sell_thr = strategy.get("sell")     # 可能為 None (不看分數)
    stop_pct = strategy.get("stop_pct") # 可能為 None
    tp_pct   = strategy.get("tp_pct")   # 可能為 None

    trades = []
    position = None

    for i in range(len(bt_df)):
        row = bt_df.iloc[i]
        as_of = row["date"]
        sc = scores.get(as_of)
        if sc is None:
            continue

        # 期末強平
        if i + 1 >= len(bt_df):
            if position:
                trades.append(_close_position(position, as_of, row["close"], "期末強平"))
            break

        nxt = bt_df.iloc[i + 1]

        if position is None:
            if sc > buy_thr:
                position = {"stock_id": stock_id, "stock_name": stock_name,
                            "buy_date": nxt["date"], "buy_price": nxt["close"],
                            "buy_score": sc}
        else:
            # 出場優先順序：停損 > 達標獲利 > 分數低於門檻
            unrealized_pct = (row["close"] - position["buy_price"]) / position["buy_price"] * 100
            exit_reason = None
            if stop_pct is not None and unrealized_pct < stop_pct:
                exit_reason = "停損"
            elif tp_pct is not None and unrealized_pct > tp_pct:
                exit_reason = "達標獲利"
            elif sell_thr is not None and sc < sell_thr:
                exit_reason = "分數低於門檻"

            if exit_reason:
                trades.append(_close_position(position, nxt["date"], nxt["close"], exit_reason))
                position = None

    return trades


# ── 基準對照 ────────────────────────────────────────────

def fetch_benchmark_return():
    """抓 BENCHMARK_TICKER (預設 0050) 同期 buy-and-hold 報酬。

    回傳 dict 或 None（抓不到資料時）：
      {
        "ticker", "start_date", "end_date",
        "start_price", "end_price",
        "return_pct_gross",  # 毛報酬
        "return_pct_net",    # 扣 0.5% 來回成本
      }
    """
    raw = fetch_finmind("TaiwanStockPrice", BENCHMARK_TICKER)
    if not raw:
        return None

    df = pd.DataFrame(raw).sort_values("date").reset_index(drop=True)
    in_window = df[df["date"] >= BACKTEST_START]
    if in_window.empty:
        return None

    start_row = in_window.iloc[0]
    end_row = df.iloc[-1]
    start_p, end_p = float(start_row["close"]), float(end_row["close"])
    gross = (end_p - start_p) / start_p * 100
    return {
        "ticker": BENCHMARK_TICKER,
        "start_date": start_row["date"],
        "end_date":   end_row["date"],
        "start_price": start_p,
        "end_price":   end_p,
        "return_pct_gross": gross,
        "return_pct_net":   gross - COST_PER_ROUND_TRIP_PCT,
    }


# ── 主程式 ───────────────────────────────────────────────

def main():
    stocks = get_stocks()
    print(f"▶ 回測 {len(stocks)} 支股票 × {len(STRATEGIES)} 策略變體")
    print(f"▶ 期間：{BACKTEST_START} ~ 今日")
    print("▶ 變體：")
    for s in STRATEGIES:
        print(f"     {s['label']}")
    print()

    all_trades = []

    for i, (sid, name) in enumerate(stocks):
        print(f"[{i+1:3d}/{len(stocks)}] {sid} {name}... ", end="", flush=True)
        ohlcv = fetch_finmind("TaiwanStockPrice", sid)
        time.sleep(SLEEP_SEC)
        inst  = fetch_finmind("TaiwanStockInstitutionalInvestorsBuySell", sid)
        time.sleep(SLEEP_SEC)

        if not ohlcv:
            print("無資料")
            continue

        prep = prep_stock(ohlcv, inst)
        if prep is None:
            print("資料不足")
            continue

        counts = []
        for strat in STRATEGIES:
            trades = run_strategy(sid, name, prep, strat)
            for t in trades:
                t["strategy"] = strat["name"]
            all_trades.extend(trades)
            counts.append(len(trades))
        print(f"共 {sum(counts)} 筆  每策略 {counts}")

    if not all_trades:
        print("\n回測期間內無任何買賣訊號")
        return

    df_all = pd.DataFrame(all_trades)

    # ── 基準對照 ──
    print("\n" + "═" * 70)
    bench = fetch_benchmark_return()
    if bench is None:
        print("基準：無法取得 0050 資料")
        bench_net = None
    else:
        bench_net = bench["return_pct_net"]
        print(f"基準對照：{BENCHMARK_TICKER} 同期 buy-and-hold")
        print(f"  期間：{bench['start_date']} @ {bench['start_price']:.2f}"
              f" → {bench['end_date']} @ {bench['end_price']:.2f}")
        print(f"  持有報酬（淨）：{bench_net:+.2f}%  (扣 {COST_PER_ROUND_TRIP_PCT}% 來回成本)")
    print("═" * 70)

    # ── 各策略對比表 ──
    print(f"\n{'策略':<22} {'交易':>5} {'勝率':>7} {'平均淨%':>9} {'中位淨%':>9}"
          f" {'最大虧%':>9} {'累計淨%':>10}")
    print("─" * 75)
    for strat in STRATEGIES:
        sdf = df_all[df_all["strategy"] == strat["name"]]
        if sdf.empty:
            print(f"{strat['label']:<22} (無交易)")
            continue
        n = len(sdf)
        win_rate = (sdf["return_pct"] > 0).sum() / n * 100
        avg = sdf["return_pct"].mean()
        med = sdf["return_pct"].median()
        worst = sdf["return_pct"].min()
        cum = sdf["return_pct"].sum()
        print(f"{strat['label']:<22} {n:>5} {win_rate:>6.1f}%"
              f" {avg:>+8.2f}% {med:>+8.2f}% {worst:>+8.1f}% {cum:>+9.1f}%")

    # ── vs 0050 ──
    if bench_net is not None:
        print("\nvs 0050 (持有 +{:.1f}%)：".format(bench_net))
        for strat in STRATEGIES:
            sdf = df_all[df_all["strategy"] == strat["name"]]
            if sdf.empty:
                continue
            avg = sdf["return_pct"].mean()
            mark = "✅勝" if avg > bench_net else "❌輸"
            print(f"  {strat['label']:<22} 平均單筆 {avg:+.2f}%  →  vs 0050 {avg - bench_net:+.2f}% {mark}")

    # ── 各策略出場原因分布 ──
    print("\n各策略出場原因分布：")
    for strat in STRATEGIES:
        sdf = df_all[df_all["strategy"] == strat["name"]]
        if sdf.empty:
            continue
        counts = sdf["exit"].value_counts()
        parts = [f"{k} {v}" for k, v in counts.items()]
        print(f"  {strat['label']:<22} {' / '.join(parts)}")

    print()
    print("⚠ 提醒：")
    print("  - '平均%' vs 0050 是粗比較，未考慮資金管理")
    print("  - '累計%' 假設每筆獨立 1 單位資金，不等於資金倍增")
    print("  - 真實資金曲線模擬留 Phase 3.5")

    out = "backtest_results.csv"
    df_all.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n詳細結果已存至 {out} ({len(df_all)} 筆，含 strategy 欄位)")


if __name__ == "__main__":
    main()
