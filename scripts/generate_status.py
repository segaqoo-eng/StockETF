"""generate_status.py — 產生每日貼文摘要 status_today.md

讀取：
  data/latest.json
  data/leaderboard_7d.json
  backtest_results.csv

輸出：
  status_today.md  (UTF-8, 適合複製貼到 FB)

用法：
  python scripts/generate_status.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TAIPEI = ZoneInfo("Asia/Taipei")

# 多策略 CSV 預設只看哪一個策略
DEFAULT_STRATEGY = "baseline"


def load_json(rel_path: str) -> dict | None:
    p = ROOT / rel_path
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_trades() -> list[dict]:
    p = ROOT / "backtest_results.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # 多策略 CSV: 只取 DEFAULT_STRATEGY；舊 CSV 沒這欄就全收
    if rows and "strategy" in rows[0]:
        rows = [r for r in rows if r.get("strategy") == DEFAULT_STRATEGY]
    return rows


def split_signals(trades: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """切出三類：今日新買進、今日新賣出、目前持倉。

    今日買進 = buy_date 最大的那天（不論 exit 狀態）
    今日賣出 = sell_date 最大、且 exit != 期末強平 的那天
    目前持倉 = exit == 期末強平 的所有筆
    """
    if not trades:
        return [], [], []

    buy_dates = [t["buy_date"] for t in trades if t.get("buy_date")]
    sell_dates = [t["sell_date"] for t in trades
                  if t.get("sell_date") and t.get("exit") != "期末強平"]

    latest_buy = max(buy_dates) if buy_dates else None
    latest_sell = max(sell_dates) if sell_dates else None

    today_buys = [t for t in trades if t["buy_date"] == latest_buy]
    today_sells = [t for t in trades
                   if t.get("sell_date") == latest_sell
                   and t.get("exit") != "期末強平"]
    open_positions = [t for t in trades if t.get("exit") == "期末強平"]
    return today_buys, today_sells, open_positions


def summarise_completed(trades: list[dict]) -> dict:
    completed = [t for t in trades if t.get("exit") and t["exit"] != "期末強平"]
    if not completed:
        return {"count": 0}
    rets = [float(t["return_pct"]) for t in completed]
    wins = [r for r in rets if r > 0]
    return {
        "count": len(completed),
        "win_rate": len(wins) / len(rets) * 100,
        "avg_return": sum(rets) / len(rets),
        "max_win": max(rets),
        "max_loss": min(rets),
        "max_win_name": max(completed, key=lambda t: float(t["return_pct"]))["stock_name"],
        "max_loss_name": min(completed, key=lambda t: float(t["return_pct"]))["stock_name"],
    }


def section_etf_overview(latest: dict) -> list[str]:
    return [
        "## 追蹤",
        f"- ETF：{len(latest.get('etfs', []))} 檔",
        f"- 不重複持股：{len(latest.get('holdings', []))} 檔",
        "",
    ]


def section_buys(buys: list[dict]) -> list[str]:
    if not buys:
        return ["## 今日新買進訊號", "（無）", ""]
    d = buys[0]["buy_date"]
    lines = [f"## 今日新買進訊號（{d}）"]
    sorted_buys = sorted(buys, key=lambda t: -float(t["buy_score"]))
    for t in sorted_buys[:10]:
        lines.append(
            f"- {t['stock_name']}（{t['stock_id']}） "
            f"@ {float(t['buy_price']):.1f}　分數 {t['buy_score']}"
        )
    if len(sorted_buys) > 10:
        lines.append(f"- ...（其餘 {len(sorted_buys) - 10} 筆略）")
    lines.append("")
    return lines


def section_sells(sells: list[dict]) -> list[str]:
    if not sells:
        return ["## 今日新賣出訊號", "（無）", ""]
    d = sells[0]["sell_date"]
    lines = [f"## 今日新賣出訊號（{d}）"]
    sorted_sells = sorted(sells, key=lambda t: float(t["return_pct"]), reverse=True)
    for t in sorted_sells[:10]:
        ret = float(t["return_pct"])
        sign = "+" if ret >= 0 else ""
        lines.append(
            f"- {t['stock_name']}（{t['stock_id']}） "
            f"@ {float(t['sell_price']):.1f}　{sign}{ret:.1f}%"
        )
    if len(sorted_sells) > 10:
        lines.append(f"- ...（其餘 {len(sorted_sells) - 10} 筆略）")
    lines.append("")
    return lines


def section_open_positions(positions: list[dict]) -> list[str]:
    if not positions:
        return ["## 策略目前持倉", "（無）", ""]
    rets = [float(t["return_pct"]) for t in positions]
    avg = sum(rets) / len(rets)
    sign_avg = "+" if avg >= 0 else ""
    lines = [
        f"## 策略目前持倉（{len(positions)} 檔，平均浮動 {sign_avg}{avg:.1f}%）",
    ]
    for t in sorted(positions, key=lambda t: float(t["return_pct"]), reverse=True)[:10]:
        ret = float(t["return_pct"])
        sign = "+" if ret >= 0 else ""
        lines.append(
            f"- {t['stock_name']}（{t['stock_id']}）"
            f"　{sign}{ret:.1f}%　持有 {t['hold_days']} 天"
        )
    if len(positions) > 10:
        lines.append(f"- ...（其餘 {len(positions) - 10} 筆略）")
    lines.append("")
    return lines


def section_consensus(lb: dict | None, key: str, label: str, min_etf: int = 2) -> list[str]:
    items = (lb or {}).get(key, [])
    filtered = [x for x in items if x.get("etf_count", 0) >= min_etf]
    if not filtered:
        return [f"## {label}（≥{min_etf} 檔 ETF）", "（無）", ""]
    lines = [f"## {label}（≥{min_etf} 檔 ETF 同向）"]
    for x in filtered[:8]:
        delta = x["total_delta"]
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"- {x['stock_name']}（{x['stock_id']}） "
            f"{sign}{delta:.2f}%　{x['etf_count']} 檔 ETF"
        )
    lines.append("")
    return lines


def section_backtest_summary(stats: dict) -> list[str]:
    if stats.get("count", 0) == 0:
        return ["## 回測累計表現", "（尚無完成交易）", ""]
    avg = stats["avg_return"]
    sign = "+" if avg >= 0 else ""
    return [
        "## 回測累計表現",
        f"- 完成交易：{stats['count']} 筆",
        f"- 勝率：{stats['win_rate']:.1f}%",
        f"- 平均報酬：{sign}{avg:.2f}%（已扣 0.5% 來回成本）",
        f"- 最大獲利：+{stats['max_win']:.1f}% ({stats['max_win_name']})",
        f"- 最大虧損：{stats['max_loss']:.1f}% ({stats['max_loss_name']})",
        "",
    ]


def main() -> int:
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")

    latest = load_json("data/latest.json")
    if latest is None:
        print("ERROR: data/latest.json 不存在，請先跑 main.py", file=sys.stderr)
        return 1

    leaderboard = load_json("data/leaderboard_7d.json")
    trades = load_trades()
    today_buys, today_sells, open_positions = split_signals(trades)
    stats = summarise_completed(trades)

    snapshot_date = (latest.get("updated_at") or today)[:10]

    lines = [
        f"# StockETF 觀察筆記 · {today}",
        f"資料截至：{snapshot_date}",
        "",
    ]
    lines += section_etf_overview(latest)
    lines += section_buys(today_buys)
    lines += section_sells(today_sells)
    lines += section_open_positions(open_positions)
    lines += section_consensus(leaderboard, "top_added", "共識加碼")
    lines += section_consensus(leaderboard, "top_removed", "共識減碼")
    lines += section_backtest_summary(stats)
    lines += [
        "---",
        "_策略：分數 > 65 買進、< 60 賣出。回測已扣 0.5% 來回成本（手續費 + 證交稅）。_",
    ]

    out = ROOT / "status_today.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
