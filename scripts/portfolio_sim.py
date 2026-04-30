"""portfolio_sim.py — 資金管理模擬 (Phase 3.5)

把 backtest_results.csv 的單筆獨立交易，改用「真實資金 + 部位數限制」模擬：

  起始資金: 100 萬
  同時最多: 5 部位（每部位 20 萬，固定）
  訊號太多: 取 buy_score 最高的 N 個（其餘記為 missed）
  訊號優先: 同日先處理 SELL 釋放資金、再處理 BUY

輸出：
  資金成長曲線（每天 cash + open positions）
  最大回撤
  每月報酬
  vs 0050 同期 buy-and-hold

用法:
  python scripts/portfolio_sim.py                  # 預設 tp5 / 5 部位 / 100 萬
  python scripts/portfolio_sim.py --strategy combined --max-positions 3
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

# 讓子目錄 import 得到 data_provider
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import data_provider  # noqa: E402

DEFAULT_INITIAL_CAPITAL = 1_000_000
DEFAULT_MAX_POSITIONS   = 5
DEFAULT_STRATEGY        = "tp5"
COST_PER_ROUND_TRIP_PCT = 0.5   # 與 backtest.py 一致


def load_trades(strategy: str) -> list[dict]:
    p = ROOT / "backtest_results.csv"
    if not p.exists():
        sys.exit(f"backtest_results.csv 不存在 — 請先跑 backtest.py")
    with p.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("strategy") == strategy]


def simulate(trades: list[dict], initial_capital: float, max_positions: int) -> dict:
    position_size = initial_capital / max_positions

    buys_by_date  = defaultdict(list)  # date -> [(score, trade_idx, trade)]
    sells_by_date = defaultdict(list)  # date -> [(trade_idx, return_pct)]

    for idx, t in enumerate(trades):
        score = float(t["buy_score"])
        ret_pct = float(t["return_pct"])  # 已扣 0.5% 來回成本
        buys_by_date[t["buy_date"]].append((score, idx, t))
        sells_by_date[t["sell_date"]].append((idx, ret_pct))

    all_dates = sorted(set(buys_by_date) | set(sells_by_date))
    open_positions: dict[int, float] = {}  # trade_idx -> cost basis
    cash = initial_capital
    equity_curve: list[dict] = []
    trades_taken: list[dict] = []
    trades_missed: list[dict] = []
    peak_equity = initial_capital
    max_drawdown_pct = 0.0

    for d in all_dates:
        # 1. SELL 先 — 釋放資金
        for trade_idx, ret_pct in sells_by_date[d]:
            if trade_idx in open_positions:
                cost = open_positions.pop(trade_idx)
                proceeds = cost * (1 + ret_pct / 100)
                cash += proceeds
                trades_taken.append({**trades[trade_idx], "pnl": proceeds - cost})

        # 2. BUY — 分數高的優先
        for score, trade_idx, trade in sorted(buys_by_date[d], reverse=True):
            if len(open_positions) < max_positions and cash >= position_size:
                cash -= position_size
                open_positions[trade_idx] = position_size
            else:
                trades_missed.append(trade)

        # 3. 紀錄當日權益（cash + 持倉成本基礎；沒有 mark-to-market）
        equity = cash + sum(open_positions.values())
        peak_equity = max(peak_equity, equity)
        drawdown = (equity - peak_equity) / peak_equity * 100
        max_drawdown_pct = min(max_drawdown_pct, drawdown)

        equity_curve.append({
            "date": d, "cash": cash, "open_count": len(open_positions),
            "equity": equity, "drawdown_pct": drawdown,
        })

    # 收尾：理論上所有訊號都有對應 sell 事件 (期末強平 也是 sell)
    # 但若 SELL 在 trades 之外的日期觸發（不應該），這裡處理保險
    final_cash = cash + sum(open_positions.values())

    return {
        "initial_capital": initial_capital,
        "max_positions":   max_positions,
        "position_size":   position_size,
        "final_equity":    final_cash,
        "total_return_pct": (final_cash - initial_capital) / initial_capital * 100,
        "trades_taken":    len(trades_taken),
        "trades_missed":   len(trades_missed),
        "equity_curve":    equity_curve,
        "max_drawdown_pct": max_drawdown_pct,
        "wins":  sum(1 for t in trades_taken if t["pnl"] > 0),
        "losses": sum(1 for t in trades_taken if t["pnl"] <= 0),
        "best_trade":  max(trades_taken, key=lambda t: t["pnl"], default=None),
        "worst_trade": min(trades_taken, key=lambda t: t["pnl"], default=None),
    }


def fetch_benchmark(start_date: str, end_date: str) -> dict | None:
    """0050 同期 buy-and-hold。"""
    rows = data_provider.get_ohlcv("0050", start_date)
    if not rows:
        return None
    in_window = [r for r in rows if start_date <= r["date"] <= end_date]
    if not in_window:
        return None
    start_p = float(in_window[0]["close"])
    end_p = float(in_window[-1]["close"])
    gross = (end_p - start_p) / start_p * 100
    return {
        "start_date": in_window[0]["date"],  "start_price": start_p,
        "end_date":   in_window[-1]["date"], "end_price":   end_p,
        "return_pct_gross": gross,
        "return_pct_net":   gross - COST_PER_ROUND_TRIP_PCT,
    }


def print_report(result: dict, bench: dict | None, strategy: str) -> None:
    init = result["initial_capital"]
    final = result["final_equity"]
    ret_pct = result["total_return_pct"]
    sign = "+" if ret_pct >= 0 else ""

    print("═" * 70)
    print(f"資金管理模擬 · 策略 {strategy}")
    print("═" * 70)
    print(f"起始資金       ：{init:>12,.0f}")
    print(f"同時部位數上限 ：{result['max_positions']}")
    print(f"每部位資金     ：{result['position_size']:>12,.0f}")
    print()
    print(f"期末資金       ：{final:>12,.0f}")
    print(f"總報酬         ：{sign}{ret_pct:.2f}%")
    print(f"最大回撤       ：{result['max_drawdown_pct']:.2f}%")
    print()
    n_taken = result["trades_taken"]
    n_missed = result["trades_missed"]
    if n_taken:
        win_rate = result["wins"] / n_taken * 100
        print(f"實際成交       ：{n_taken} 筆")
        print(f"  勝率          ：{win_rate:.1f}% ({result['wins']} 勝 / {result['losses']} 負)")
        if result["best_trade"]:
            t = result["best_trade"]
            print(f"  最大獲利      ：{t['stock_name']} {t['pnl']:+,.0f} 元 ({float(t['return_pct']):+.1f}%)")
        if result["worst_trade"]:
            t = result["worst_trade"]
            print(f"  最大虧損      ：{t['stock_name']} {t['pnl']:+,.0f} 元 ({float(t['return_pct']):+.1f}%)")
    print(f"錯失訊號       ：{n_missed} 筆 (5 部位額滿時)")
    print()

    if bench:
        bench_pct = bench["return_pct_net"]
        delta = ret_pct - bench_pct
        verdict = "✅ 策略勝" if delta > 0 else "❌ 輸 0050"
        verdict_strong = "✅ 策略明顯勝" if delta > 5 else verdict if delta > 0 else verdict
        print(f"基準 0050 持有 ：{bench_pct:+.2f}% ({bench['start_date']} @ {bench['start_price']:.2f}"
              f" → {bench['end_date']} @ {bench['end_price']:.2f})")
        print(f"  超額報酬      ：{delta:+.2f}%  {verdict_strong}")
        if abs(delta) < 5:
            print(f"  ⚠ 超額 < 5%：策略努力換來的微小優勢，誤差範圍內，可能直接買 0050 比較省事")
    else:
        print("基準 0050        ：無法取得資料")
    print()

    # 等權益曲線採樣（每月一個點）
    curve = result["equity_curve"]
    if curve:
        print("資金曲線（月底採樣）：")
        prev_month = None
        samples = []
        for pt in curve:
            month = pt["date"][:7]
            if month != prev_month:
                samples.append(pt)
                prev_month = month
        samples.append(curve[-1])  # 最後一天
        for pt in samples:
            bar_len = int((pt["equity"] / init - 0.5) * 30) if pt["equity"] > 0 else 0
            bar = "▌" * max(0, min(40, bar_len))
            pct = (pt["equity"] / init - 1) * 100
            print(f"  {pt['date']}  {pt['equity']:>10,.0f}  ({pct:+6.1f}%)  {bar}")


def main() -> int:
    parser = argparse.ArgumentParser(description="便當 5 資金管理模擬")
    parser.add_argument("--strategy",      default=DEFAULT_STRATEGY,
                        help=f"策略名稱（CSV 的 strategy 欄；預設 {DEFAULT_STRATEGY}）")
    parser.add_argument("--initial",       type=float, default=DEFAULT_INITIAL_CAPITAL,
                        help=f"起始資金，預設 {DEFAULT_INITIAL_CAPITAL:,}")
    parser.add_argument("--max-positions", type=int,   default=DEFAULT_MAX_POSITIONS,
                        help=f"同時最多部位數，預設 {DEFAULT_MAX_POSITIONS}")
    args = parser.parse_args()

    trades = load_trades(args.strategy)
    if not trades:
        print(f"backtest_results.csv 找不到 strategy='{args.strategy}' 的交易")
        return 1
    print(f"載入 {len(trades)} 筆 {args.strategy} 策略交易\n")

    result = simulate(trades, args.initial, args.max_positions)

    start_date = min(t["buy_date"] for t in trades)
    end_date = max(t["sell_date"] for t in trades)
    bench = fetch_benchmark(start_date, end_date)

    print_report(result, bench, args.strategy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
