"""generate_status.py — 產生每日「便當 5」實戰訊號 status_today.md

策略 (便當 5)：
  分數 > 65         → 明日收盤買進
  浮動報酬 ≥ +5%    → 明日收盤賣出（達標獲利）
  浮動報酬 ≤ -5%    → 明日收盤賣出（停損）
  進場後不看分數，只看價

讀取：
  data/latest.json
  data/leaderboard_7d.json
  backtest_results.csv (含 strategy 欄位)

輸出：
  status_today.md  (UTF-8, 適合複製貼到 FB / 自己參考)

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

# 便當 5 策略參數
DEFAULT_STRATEGY = "tp5"
STRATEGY_LABEL   = "便當 5"
TP_PCT           = 5.0   # 達標獲利出場
SL_PCT           = -5.0  # 停損出場
BUY_THR          = 65    # 買進分數門檻


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
    if rows and "strategy" in rows[0]:
        rows = [r for r in rows if r.get("strategy") == DEFAULT_STRATEGY]
    return rows


def split_signals(trades: list[dict]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """切出四類：今日新買進、今日 TP 出場、今日 SL 出場、目前持倉。"""
    if not trades:
        return [], [], [], []

    buy_dates = [t["buy_date"] for t in trades if t.get("buy_date")]
    closed = [t for t in trades if t.get("exit") in ("達標獲利", "停損")]
    sell_dates = [t["sell_date"] for t in closed if t.get("sell_date")]

    latest_buy  = max(buy_dates) if buy_dates else None
    latest_sell = max(sell_dates) if sell_dates else None

    today_buys  = [t for t in trades if t["buy_date"] == latest_buy]
    today_tp    = [t for t in closed if t.get("sell_date") == latest_sell and t.get("exit") == "達標獲利"]
    today_sl    = [t for t in closed if t.get("sell_date") == latest_sell and t.get("exit") == "停損"]
    open_pos    = [t for t in trades if t.get("exit") == "期末強平"]
    return today_buys, today_tp, today_sl, open_pos


def summarise_completed(trades: list[dict]) -> dict:
    completed = [t for t in trades if t.get("exit") in ("達標獲利", "停損")]
    if not completed:
        return {"count": 0}
    rets = [float(t["return_pct"]) for t in completed]
    wins = [r for r in rets if r > 0]
    medians = sorted(rets)
    median_ret = medians[len(medians) // 2]
    return {
        "count": len(completed),
        "win_rate": len(wins) / len(rets) * 100,
        "avg_return": sum(rets) / len(rets),
        "median": median_ret,
        "tp_count": sum(1 for t in completed if t.get("exit") == "達標獲利"),
        "sl_count": sum(1 for t in completed if t.get("exit") == "停損"),
    }


def fmt_tp_sl(buy_price: float) -> tuple[float, float]:
    return buy_price * (1 + TP_PCT / 100), buy_price * (1 + SL_PCT / 100)


# ── 區段 ────────────────────────────────────────────────

def section_buys(buys: list[dict]) -> list[str]:
    if not buys:
        return ["## 🟢 最新進場訊號", "（無）", ""]
    d = buys[0]["buy_date"]
    lines = [
        f"## 🟢 最新進場訊號（{d}）",
        f"分數 > {BUY_THR} 進場。買進後設 TP +{TP_PCT}% / SL {SL_PCT}% 委託。",
        "",
    ]
    sorted_buys = sorted(buys, key=lambda t: -float(t["buy_score"]))
    for t in sorted_buys[:15]:
        bp = float(t["buy_price"])
        tp, sl = fmt_tp_sl(bp)
        lines.append(
            f"- **{t['stock_name']}（{t['stock_id']}）** 分數 {t['buy_score']}"
            f"　 進 @ {bp:.1f}　TP {tp:.1f}　SL {sl:.1f}"
        )
    if len(sorted_buys) > 15:
        lines.append(f"- ...（其餘 {len(sorted_buys) - 15} 檔略；分數越高越優先）")
    lines.append("")
    return lines


def section_exits(tp_list: list[dict], sl_list: list[dict]) -> list[str]:
    lines = []
    if tp_list:
        d = tp_list[0]["sell_date"]
        lines.append(f"## ✅ 今日達標出場（{d}）")
        for t in sorted(tp_list, key=lambda t: -float(t["return_pct"])):
            ret = float(t["return_pct"])
            lines.append(
                f"- {t['stock_name']}（{t['stock_id']}）"
                f"　@ {float(t['sell_price']):.1f}　淨 +{ret:.2f}%　持 {t['hold_days']} 天"
            )
        lines.append("")
    if sl_list:
        d = sl_list[0]["sell_date"]
        lines.append(f"## ⛔ 今日停損出場（{d}）")
        for t in sorted(sl_list, key=lambda t: float(t["return_pct"])):
            ret = float(t["return_pct"])
            lines.append(
                f"- {t['stock_name']}（{t['stock_id']}）"
                f"　@ {float(t['sell_price']):.1f}　淨 {ret:.2f}%　持 {t['hold_days']} 天"
            )
        lines.append("")
    if not tp_list and not sl_list:
        lines += ["## 今日出場", "（無達標 / 停損訊號）", ""]
    return lines


def _format_pos_row(t: dict) -> str:
    bp = float(t["buy_price"])
    tp, sl = fmt_tp_sl(bp)
    ret = float(t["return_pct"])
    sign = "+" if ret >= 0 else ""
    return (f"| {t['stock_name']}（{t['stock_id']}） | {t['buy_date']} |"
            f" {bp:.1f} | {tp:.1f} | {sl:.1f} | {sign}{ret:.1f}% |")


def section_open_positions(positions: list[dict]) -> list[str]:
    """策略目前未出場的部位。給使用者「我手上有的話該設多少價」做對照。"""
    if not positions:
        return ["## ⏳ 持倉中（待 TP / SL 觸發）", "（無）", ""]

    sorted_pos = sorted(positions, key=lambda t: -float(t["return_pct"]))
    lines = [
        f"## ⏳ 持倉中（{len(positions)} 檔，等 TP +{TP_PCT}% 或 SL {SL_PCT}%）",
        f"⚠ 此為 backtest 無資金限制下的全部部位。**實盤建議照分數最高的 5 檔**進場，",
        "  其他訊號當「想跟」的觀察名單。下表前 15 強、後 10 弱供決策：",
        "",
        "| 股票 | 進場日 | 進場價 | TP 目標 | SL 停損 | 目前浮動 |",
        "|---|---|---|---|---|---|",
    ]
    if len(sorted_pos) <= 25:
        lines += [_format_pos_row(t) for t in sorted_pos]
    else:
        lines += [_format_pos_row(t) for t in sorted_pos[:15]]
        lines.append(f"| _(中段 {len(sorted_pos) - 25} 檔略)_ | | | | | |")
        lines += [_format_pos_row(t) for t in sorted_pos[-10:]]
    lines.append("")
    return lines


def section_consensus(lb: dict | None, key: str, label: str, min_etf: int = 2) -> list[str]:
    items = (lb or {}).get(key, [])
    filtered = [x for x in items if x.get("etf_count", 0) >= min_etf]
    if not filtered:
        return [f"## {label}（≥{min_etf} 檔 ETF）", "（無）", ""]
    lines = [f"## {label}（≥{min_etf} 檔 ETF 同向，僅供參考非進出依據）"]
    for x in filtered[:6]:
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
        return ["## 📊 回測表現", "（尚無完成交易）", ""]
    avg = stats["avg_return"]
    sign = "+" if avg >= 0 else ""
    return [
        "## 📊 回測表現（便當 5，半年）",
        f"- 完成交易：{stats['count']} 筆（達標 {stats['tp_count']} / 停損 {stats['sl_count']}）",
        f"- 勝率：{stats['win_rate']:.1f}%",
        f"- 平均報酬：{sign}{avg:.2f}%（已扣 0.5% 來回成本）",
        f"- 中位數：+{stats['median']:.2f}%（一半以上交易賺得到）",
        "",
    ]


def section_disclaimer() -> list[str]:
    return [
        "---",
        "## ⚠️ 風險提醒",
        "- 過去績效**不保證**未來。回測樣本期 2025-10 ~ 2026-04（半年），含科技股大多頭。",
        "- 回測 vs 實盤有滑價、稅費、額度等差異。",
        "- 訊號越多越要分散：單檔建議 ≤ 20% 倉位。",
        "- TP/SL 用券商「條件單」自動委託；半夜 gap 開盤偏離可能被吃掉。",
        "- **跟訊號 ≠ 保證賺**，自負盈虧。",
        "",
        f"_資料來源：{', '.join(['FinMind / yfinance (股價籌碼)', 'ETF 發行商官網 (持股)'])}_",
    ]


def main() -> int:
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")

    latest = load_json("data/latest.json")
    if latest is None:
        print("ERROR: data/latest.json 不存在，請先跑 main.py", file=sys.stderr)
        return 1

    leaderboard = load_json("data/leaderboard_7d.json")
    trades = load_trades()
    today_buys, today_tp, today_sl, open_pos = split_signals(trades)
    stats = summarise_completed(trades)

    snapshot_date = (latest.get("updated_at") or today)[:10]

    lines = [
        f"# StockETF {STRATEGY_LABEL} 訊號 · {today}",
        f"資料截至：{snapshot_date}　|　ETF：{len(latest.get('etfs', []))} 檔　|　追蹤股：{len(latest.get('holdings', []))} 檔",
        "",
        f"**策略**：分數 > {BUY_THR} 進場、浮動 +{TP_PCT}% 出場、-{abs(SL_PCT)}% 停損。",
        "",
    ]
    lines += section_buys(today_buys)
    lines += section_exits(today_tp, today_sl)
    lines += section_open_positions(open_pos)
    lines += section_consensus(leaderboard, "top_added", "📈 法人共識加碼")
    lines += section_consensus(leaderboard, "top_removed", "📉 法人共識減碼")
    lines += section_backtest_summary(stats)
    lines += section_disclaimer()

    out = ROOT / "status_today.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
