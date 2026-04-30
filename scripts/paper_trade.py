"""paper_trade.py — Paper Trading 自動跟單模擬

每次跑：
  1. 讀 data/paper_portfolio.json 已有部位
  2. 抓每檔最新收盤價
  3. 觸 TP / SL → 自動平倉
  4. 從 backtest_results.csv 拿最新日期的買進訊號（取 buy_score top 5 中還沒在持倉的）
  5. 依「同時最多 5 部位、每部位等權重 NTD 200,000」自動進場
  6. 輸出 paper_status.md

用意：實盤之前先「乾跑」一兩週，驗證便當 5 在 forward-looking 的表現。

用法:
  python scripts/paper_trade.py            # 模擬今日 + 產生報告
  python scripts/paper_trade.py status     # 只產生報告，不模擬
  python scripts/paper_trade.py reset      # 清空 paper 部位（重新開始）
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import data_provider  # noqa: E402

PORTFOLIO_FILE = ROOT / "data" / "paper_portfolio.json"
OUTPUT_FILE    = ROOT / "paper_status.md"
BACKTEST_CSV   = ROOT / "backtest_results.csv"
TAIPEI         = ZoneInfo("Asia/Taipei")

INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS   = 5
POSITION_SIZE   = INITIAL_CAPITAL / MAX_POSITIONS
TP_PCT          = 5.0
SL_PCT          = -5.0
COST_BUY_PCT    = 0.1
COST_SELL_PCT   = 0.4
DEFAULT_STRATEGY = "tp5"


def empty_portfolio() -> dict:
    return {
        "_comment": "Paper trading 自動模擬。請勿手動編輯，由 paper_trade.py 維護。",
        "started_at": datetime.now(TAIPEI).strftime("%Y-%m-%d"),
        "initial_capital": INITIAL_CAPITAL,
        "max_positions":   MAX_POSITIONS,
        "position_size":   POSITION_SIZE,
        "cash":            INITIAL_CAPITAL,
        "open":   [],
        "closed": [],
    }


def load_portfolio() -> dict:
    if not PORTFOLIO_FILE.exists():
        return empty_portfolio()
    return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))


def save_portfolio(p: dict) -> None:
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def latest_close(stock_id: str) -> tuple[str, float] | None:
    rows = data_provider.get_ohlcv(stock_id, start_date="2025-04-01")
    if not rows:
        return None
    last = rows[-1]
    return last["date"], float(last["close"])


def calc_pnl_ntd(buy_price: float, sell_price: float, shares: int) -> int:
    cost = buy_price * shares * (1 + COST_BUY_PCT / 100)
    proceeds = sell_price * shares * (1 - COST_SELL_PCT / 100)
    return int(round(proceeds - cost))


# ── 模擬步驟 ───────────────────────────────────────────────

def check_exits(portfolio: dict) -> list[str]:
    """檢查每個 open 部位是否觸 TP / SL，觸發則平倉。"""
    notes = []
    still_open = []
    for pos in portfolio["open"]:
        sid = pos["stock_id"]
        result = latest_close(sid)
        if result is None:
            notes.append(f"  ⚠ {sid} {pos['stock_name']}: 抓不到價格，保留持倉")
            still_open.append(pos)
            continue
        last_date, cur_price = result
        bp = pos["buy_price"]
        unreal_pct = (cur_price - bp) / bp * 100

        if unreal_pct >= TP_PCT:
            # TP 觸發
            pnl = calc_pnl_ntd(bp, cur_price, pos["shares"])
            portfolio["cash"] += pos["shares"] * cur_price * (1 - COST_SELL_PCT / 100)
            portfolio["closed"].append({**pos, "sell_date": last_date, "sell_price": cur_price,
                                        "exit": "達標", "pnl_ntd": pnl})
            notes.append(f"  ✅ TP {sid} {pos['stock_name']} @ {cur_price:.1f} 浮 +{unreal_pct:.1f}%　已實現 {pnl:+,} 元")
        elif unreal_pct <= SL_PCT:
            # SL 觸發
            pnl = calc_pnl_ntd(bp, cur_price, pos["shares"])
            portfolio["cash"] += pos["shares"] * cur_price * (1 - COST_SELL_PCT / 100)
            portfolio["closed"].append({**pos, "sell_date": last_date, "sell_price": cur_price,
                                        "exit": "停損", "pnl_ntd": pnl})
            notes.append(f"  ⛔ SL {sid} {pos['stock_name']} @ {cur_price:.1f} 浮 {unreal_pct:.1f}%　已實現 {pnl:+,} 元")
        else:
            still_open.append(pos)
    portfolio["open"] = still_open
    return notes


def take_new_signals(portfolio: dict) -> list[str]:
    """從 backtest_results.csv 拿最新一天的 BUY 訊號 (tp5 策略)，按分數高低吃進。"""
    notes = []
    if not BACKTEST_CSV.exists():
        return ["  ⚠ backtest_results.csv 不存在，跳過進場"]

    with BACKTEST_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("strategy") == DEFAULT_STRATEGY]

    buy_dates = [r["buy_date"] for r in rows if r.get("buy_date")]
    if not buy_dates:
        return ["  （CSV 無買進記錄）"]

    latest = max(buy_dates)
    candidates = sorted(
        [r for r in rows if r["buy_date"] == latest],
        key=lambda r: -float(r["buy_score"]),
    )
    held = {p["stock_id"] for p in portfolio["open"]}

    for r in candidates:
        if len(portfolio["open"]) >= MAX_POSITIONS:
            break
        if r["stock_id"] in held:
            continue
        bp = float(r["buy_price"])
        # 整股數：以 POSITION_SIZE 為上限，floor 到整張 (1000 股)
        shares = int(POSITION_SIZE / bp / 1000) * 1000
        if shares < 1000:
            notes.append(f"  💸 {r['stock_name']} ({bp:.0f} 元/股) 1 張要 {bp*1000:,.0f}，超過部位上限 {POSITION_SIZE:,.0f}，跳過")
            continue
        actual_cost = shares * bp * (1 + COST_BUY_PCT / 100)
        if portfolio["cash"] < actual_cost:
            notes.append(f"  💸 現金 {portfolio['cash']:,.0f} 不夠買 {r['stock_name']} ({actual_cost:,.0f})，跳過")
            continue
        portfolio["cash"] -= actual_cost
        portfolio["open"].append({
            "stock_id":   r["stock_id"],
            "stock_name": r["stock_name"],
            "buy_date":   r["buy_date"],
            "buy_price":  bp,
            "buy_score":  float(r["buy_score"]),
            "shares":     shares,
        })
        held.add(r["stock_id"])
        notes.append(f"  🟢 BUY {r['stock_id']} {r['stock_name']} 分數 {r['buy_score']} @ {bp:.1f} × {shares} 股")
    return notes


def simulate_one_step(portfolio: dict) -> list[str]:
    notes = ["── 檢查 TP / SL ──"]
    notes += check_exits(portfolio)
    notes.append("")
    notes.append("── 進場新訊號 ──")
    notes += take_new_signals(portfolio)
    portfolio["last_run_at"] = datetime.now(TAIPEI).strftime("%Y-%m-%dT%H:%M:%S")
    return notes


# ── 報告 ───────────────────────────────────────────────────

def calc_unrealized(portfolio: dict) -> tuple[int, list[dict]]:
    """每個 open 部位算當前浮動 P&L。回傳 (合計, [details])。"""
    total = 0
    details = []
    for pos in portfolio["open"]:
        result = latest_close(pos["stock_id"])
        if result is None:
            continue
        last_date, cur = result
        pnl = calc_pnl_ntd(pos["buy_price"], cur, pos["shares"])
        unreal_pct = (cur - pos["buy_price"]) / pos["buy_price"] * 100
        total += pnl
        details.append({**pos, "current_price": cur, "current_date": last_date,
                        "pnl_ntd": pnl, "unreal_pct": unreal_pct})
    return total, details


def render_report(portfolio: dict, run_notes: list[str] | None = None) -> str:
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    started = portfolio.get("started_at", today)
    cash = portfolio["cash"]
    realized = sum(c.get("pnl_ntd", 0) for c in portfolio["closed"])
    unrealized, open_details = calc_unrealized(portfolio)
    total_equity = cash + sum(p["shares"] * (d["current_price"]) for p, d in zip(portfolio["open"], open_details)) \
                   if open_details else cash
    if not open_details:
        # 沒抓到價格時，用 cost basis 估
        total_equity = cash + sum(p["buy_price"] * p["shares"] for p in portfolio["open"])

    init = portfolio["initial_capital"]
    return_pct = (total_equity - init) / init * 100
    sign = "+" if return_pct >= 0 else ""

    lines = [
        f"# Paper Trading 模擬 · {today}",
        f"_乾跑帳戶：起始 {init:,} 元，從 {started} 開始模擬。實盤前驗證用。_",
        "",
        f"## 💰 帳戶總覽",
        f"- 起始資金：{init:,}",
        f"- 目前現金：{cash:,.0f}",
        f"- 持倉成本：{int(sum(p['buy_price'] * p['shares'] for p in portfolio['open'])):,}",
        f"- 浮動損益：{unrealized:+,}",
        f"- 已實現損益：{realized:+,}",
        f"- **帳戶總值（mark-to-market）：{int(total_equity):,}　淨報酬 {sign}{return_pct:.2f}%**",
        "",
    ]

    if open_details:
        lines.append("## 📦 目前持倉")
        lines.append("| 股票 | 進場日 | 進場價 | 現價 | 浮動% | 股數 | 浮動損益 |")
        lines.append("|---|---|---|---|---|---|---|")
        for d in sorted(open_details, key=lambda x: -x["unreal_pct"]):
            sign_p = "+" if d["unreal_pct"] >= 0 else ""
            sign_n = "+" if d["pnl_ntd"] >= 0 else ""
            lines.append(
                f"| {d['stock_name']}（{d['stock_id']}） | {d['buy_date']} | "
                f"{d['buy_price']:.1f} | {d['current_price']:.1f} | "
                f"{sign_p}{d['unreal_pct']:.2f}% | {d['shares']} | {sign_n}{d['pnl_ntd']:,} |"
            )
        lines.append("")
    else:
        lines.append("## 📦 目前持倉")
        lines.append("（無）")
        lines.append("")

    if portfolio["closed"]:
        wins = sum(1 for c in portfolio["closed"] if c.get("pnl_ntd", 0) > 0)
        losses = len(portfolio["closed"]) - wins
        lines.append(f"## 💰 已實現紀錄（{len(portfolio['closed'])} 筆，{wins} 勝 / {losses} 負）")
        lines.append("| 股票 | 進場 | 出場 | 進價 | 出價 | 結果 | 損益 |")
        lines.append("|---|---|---|---|---|---|---|")
        for c in sorted(portfolio["closed"], key=lambda x: x.get("sell_date", ""), reverse=True)[:20]:
            pnl = c.get("pnl_ntd", 0)
            sign_p = "+" if pnl >= 0 else ""
            lines.append(
                f"| {c['stock_name']}（{c['stock_id']}） | {c['buy_date']} | {c.get('sell_date', '')} | "
                f"{c['buy_price']:.1f} | {c.get('sell_price', 0):.1f} | {c.get('exit', '?')} | "
                f"**{sign_p}{pnl:,}** |"
            )
        if len(portfolio["closed"]) > 20:
            lines.append(f"| _...其餘 {len(portfolio['closed']) - 20} 筆略_ | | | | | | |")
        lines.append("")

    if run_notes:
        lines.append("## 📝 本次執行 log")
        lines.append("```")
        lines += run_notes
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("_用 `python scripts/paper_trade.py` 模擬下一個交易日。reset 清空：`python scripts/paper_trade.py reset`_")
    return "\n".join(lines) + "\n"


# ── CLI ───────────────────────────────────────────────────

def cmd_run() -> int:
    portfolio = load_portfolio()
    notes = simulate_one_step(portfolio)
    save_portfolio(portfolio)
    OUTPUT_FILE.write_text(render_report(portfolio, notes), encoding="utf-8")
    for n in notes:
        print(n)
    print(f"\n→ Wrote {OUTPUT_FILE.relative_to(ROOT)}")
    return 0


def cmd_status() -> int:
    portfolio = load_portfolio()
    OUTPUT_FILE.write_text(render_report(portfolio, run_notes=None), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE.relative_to(ROOT)}")
    return 0


def cmd_reset() -> int:
    if PORTFOLIO_FILE.exists():
        PORTFOLIO_FILE.unlink()
    print("Paper portfolio cleared. 下次跑 paper_trade.py 會重新初始化。")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return cmd_run()
    cmd = args[0]
    if cmd == "run":    return cmd_run()
    if cmd == "status": return cmd_status()
    if cmd == "reset":  return cmd_reset()
    print(f"未知命令: {cmd}")
    print("用法: python scripts/paper_trade.py [run|status|reset]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
