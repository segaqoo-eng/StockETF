"""
backtest.py — 買進評分策略回測（本機執行）

策略：
  今日分數 > 65 且未持倉 → 明日收盤買進
  今日分數 < 60 且持倉中 → 明日收盤賣出

用法：
  .venv\\Scripts\\python.exe backtest.py
"""

import json, time, sys
import requests
import pandas as pd
import numpy as np
from datetime import date

# ── 設定 ────────────────────────────────────────────────
BACKTEST_START = "2026-04-02"   # 回測起點
DATA_START     = "2025-04-01"   # 抓取起點（需足夠計算指標）
BUY_THRESHOLD  = 65
SELL_THRESHOLD = 60
SLEEP_SEC      = 0.8            # 每次 API 請求間隔
FINMIND_URL    = "https://api.finmindtrade.com/api/v4/data"
# ────────────────────────────────────────────────────────


def get_stocks():
    with open("data/latest.json", encoding="utf-8") as f:
        d = json.load(f)
    return [(h["stock_id"], h["stock_name"]) for h in d["holdings"]]


def fetch_finmind(dataset, stock_id):
    try:
        r = requests.get(FINMIND_URL, params={
            "dataset": dataset, "data_id": stock_id, "start_date": DATA_START,
        }, timeout=30)
        d = r.json()
        if d.get("status") == 200 and d.get("data"):
            return d["data"]
    except Exception as e:
        print(f"[WARN] {stock_id} {dataset}: {e}", file=sys.stderr)
    return []


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

def backtest_stock(stock_id, stock_name, ohlcv_raw, inst_raw):
    df = pd.DataFrame(ohlcv_raw).rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
    df = df.sort_values("date").reset_index(drop=True)
    inst = parse_inst(inst_raw)

    bt_df = df[df["date"] >= BACKTEST_START].reset_index(drop=True)
    if bt_df.empty:
        return []

    trades = []
    position = None   # None 或 {"buy_date", "buy_price", "buy_score"}

    for i, row in bt_df.iterrows():
        as_of = row["date"]
        sc = score_on_day(df, inst, as_of)
        if sc is None:
            continue

        # 取下一個交易日
        if i + 1 >= len(bt_df):
            # 最後一天：強制平倉
            if position:
                ret = (row["close"] - position["buy_price"]) / position["buy_price"] * 100
                trades.append({**position,
                    "sell_date": as_of, "sell_price": row["close"],
                    "return_pct": ret,
                    "hold_days": (pd.to_datetime(as_of) - pd.to_datetime(position["buy_date"])).days,
                    "exit": "期末強平",
                })
            break

        nxt = bt_df.iloc[i + 1]

        if position is None:
            if sc > BUY_THRESHOLD:
                position = {"stock_id": stock_id, "stock_name": stock_name,
                            "buy_date": nxt["date"], "buy_price": nxt["close"], "buy_score": sc}
        else:
            if sc < SELL_THRESHOLD:
                ret = (nxt["close"] - position["buy_price"]) / position["buy_price"] * 100
                trades.append({**position,
                    "sell_date": nxt["date"], "sell_price": nxt["close"],
                    "return_pct": ret,
                    "hold_days": (pd.to_datetime(nxt["date"]) - pd.to_datetime(position["buy_date"])).days,
                    "exit": "分數低於60",
                })
                position = None

    return trades


# ── 主程式 ───────────────────────────────────────────────

def main():
    stocks = get_stocks()
    print(f"▶ 回測 {len(stocks)} 支股票")
    print(f"▶ 期間：{BACKTEST_START} ~ 今日")
    print(f"▶ 策略：分數 > {BUY_THRESHOLD} 買進 / 分數 < {SELL_THRESHOLD} 賣出\n")

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

        trades = backtest_stock(sid, name, ohlcv, inst)
        all_trades.extend(trades)

        if trades:
            avg = sum(t["return_pct"] for t in trades) / len(trades)
            print(f"{len(trades)} 筆  平均 {avg:+.1f}%")
        else:
            print("無交易")

    # ── 結果摘要 ──
    print("\n" + "═" * 55)
    print("回測結果摘要")
    print("═" * 55)

    if not all_trades:
        print("回測期間內無任何買賣訊號")
        return

    df = pd.DataFrame(all_trades)
    w = df[df["return_pct"] > 0]
    l = df[df["return_pct"] <= 0]

    print(f"總交易次數  ：{len(df)}")
    print(f"勝率        ：{len(w)/len(df)*100:.1f}%（{len(w)} 勝 / {len(l)} 負）")
    print(f"平均報酬    ：{df['return_pct'].mean():+.2f}%")
    print(f"中位數報酬  ：{df['return_pct'].median():+.2f}%")
    print(f"平均持倉天數：{df['hold_days'].mean():.1f} 天")
    print(f"最大獲利    ：{df['return_pct'].max():+.2f}%  ({df.loc[df['return_pct'].idxmax(), 'stock_name']})")
    print(f"最大虧損    ：{df['return_pct'].min():+.2f}%  ({df.loc[df['return_pct'].idxmin(), 'stock_name']})")

    print(f"\n前 10 筆最佳交易：")
    top = df.nlargest(10, "return_pct")[
        ["stock_id", "stock_name", "buy_date", "sell_date", "return_pct", "hold_days"]
    ]
    print(top.to_string(index=False))

    out = "backtest_results.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n詳細結果已存至 {out}")


if __name__ == "__main__":
    main()
