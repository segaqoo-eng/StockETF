"""my_status.py — 實際持倉追蹤 + 回本進度

讀 data/my_positions.json，抓當前價，產生 my_status.md：
  - 持倉中的部位 + 浮動 P&L + TP/SL 距離 + 動作建議
  - 已實現損益（每筆 + 累計）
  - 「回本 USD 100」進度條

用法:
  python scripts/my_status.py           # 產生 my_status.md
  python scripts/my_status.py add 7769 鴻勁 5220 1000     # 加新部位
  python scripts/my_status.py close 7769 5481            # 平倉 (價格)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import data_provider  # noqa: E402

POSITIONS_FILE = ROOT / "data" / "my_positions.json"
OUTPUT_FILE    = ROOT / "my_status.md"
TAIPEI         = ZoneInfo("Asia/Taipei")

# 台股費率：買 0.1% + 賣 0.1% + 證交稅 0.3% ≈ 0.5% 來回
COST_BUY_PCT  = 0.1
COST_SELL_PCT = 0.4   # 0.1% 手續費 + 0.3% 證交稅


def load_positions() -> dict:
    if not POSITIONS_FILE.exists():
        return {"open": [], "closed": [], "_target_usd": 100, "_usd_twd_rate": 33.0,
                "_strategy_default_tp_pct": 5.0, "_strategy_default_sl_pct": -5.0}
    return json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))


def save_positions(cfg: dict) -> None:
    # 保留註解與 meta 欄位
    POSITIONS_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def fetch_latest_close(stock_id: str) -> float | None:
    """從 data_provider 拿最新收盤。"""
    rows = data_provider.get_ohlcv(stock_id, start_date="2025-04-01")
    if not rows:
        return None
    return float(rows[-1]["close"])


def calc_pnl_pct_net(buy_price: float, current_price: float) -> float:
    """淨報酬 % (扣手續費 + 證交稅)。"""
    return (current_price - buy_price) / buy_price * 100 - (COST_BUY_PCT + COST_SELL_PCT)


def calc_pnl_ntd(buy_price: float, current_price: float, shares: int) -> int:
    cost = buy_price * shares * (1 + COST_BUY_PCT / 100)
    proceeds = current_price * shares * (1 - COST_SELL_PCT / 100)
    return int(round(proceeds - cost))


# ── 純邏輯函式（CLI / Web API 共用） ────────────────────────

def add_position(stock_id: str, stock_name: str, buy_price: float, shares: int,
                  buy_date: str | None = None) -> dict:
    """加入新部位。回傳新增的 position dict。"""
    if buy_date is None:
        buy_date = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    pos = {
        "stock_id": str(stock_id),
        "stock_name": str(stock_name),
        "buy_date": buy_date,
        "buy_price": float(buy_price),
        "shares": int(shares),
    }
    cfg = load_positions()
    cfg.setdefault("open", []).append(pos)
    save_positions(cfg)
    return pos


def close_position(stock_id: str, sell_price: float,
                    sell_date: str | None = None) -> dict | None:
    """平倉 (FIFO 第一筆持有)。回傳 closed dict；找不到回 None。"""
    if sell_date is None:
        sell_date = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    cfg = load_positions()
    open_list = cfg.get("open", [])
    matched = next((p for p in open_list if p["stock_id"] == str(stock_id)), None)
    if matched is None:
        return None
    open_list.remove(matched)
    pnl = calc_pnl_ntd(matched["buy_price"], float(sell_price), matched["shares"])
    closed = {**matched, "sell_date": sell_date,
              "sell_price": float(sell_price), "pnl_ntd": pnl}
    cfg.setdefault("closed", []).append(closed)
    save_positions(cfg)
    return closed


def get_full_status() -> dict:
    """完整狀態 (持倉 + 已實現 + 即時 P&L) — 給 Web API 用。"""
    cfg = load_positions()
    open_list = cfg.get("open", [])
    closed_list = cfg.get("closed", [])
    target_usd = cfg.get("_target_usd", 100)
    fx = cfg.get("_usd_twd_rate", 33.0)
    default_tp = cfg.get("_strategy_default_tp_pct", 5.0)
    default_sl = cfg.get("_strategy_default_sl_pct", -5.0)

    open_with_pnl = []
    unrealized = 0
    for p in open_list:
        bp = float(p["buy_price"])
        shares = int(p["shares"])
        tp_pct = float(p.get("tp_pct", default_tp))
        sl_pct = float(p.get("sl_pct", default_sl))
        cur = fetch_latest_close(p["stock_id"])
        entry = {
            **p,
            "tp_price":  bp * (1 + tp_pct / 100),
            "sl_price":  bp * (1 + sl_pct / 100),
            "current_price": cur,
        }
        if cur is not None:
            entry["pnl_pct_net"] = calc_pnl_pct_net(bp, cur)
            entry["pnl_ntd"]     = calc_pnl_ntd(bp, cur, shares)
            unrealized += entry["pnl_ntd"]
        open_with_pnl.append(entry)

    realized = sum(c.get("pnl_ntd", 0) for c in closed_list)
    target_ntd = int(target_usd * fx)
    return {
        "open":      open_with_pnl,
        "closed":    sorted(closed_list, key=lambda c: c.get("sell_date", ""), reverse=True),
        "summary": {
            "realized":     realized,
            "unrealized":   unrealized,
            "total":        realized + unrealized,
            "target_usd":   target_usd,
            "target_ntd":   target_ntd,
            "fx":           fx,
            "progress_pct": (realized + unrealized) / target_ntd * 100 if target_ntd > 0 else 0,
            "wins":   sum(1 for c in closed_list if c.get("pnl_ntd", 0) > 0),
            "losses": sum(1 for c in closed_list if c.get("pnl_ntd", 0) <= 0),
        },
    }


# ── CLI 子命令 ─────────────────────────────────────────────

def cmd_add(args: list[str]) -> int:
    if len(args) < 4:
        print("用法: python scripts/my_status.py add <stock_id> <stock_name> <buy_price> <shares> [buy_date]")
        return 1
    sid, name, price, shares = args[:4]
    buy_date = args[4] if len(args) >= 5 else None
    pos = add_position(sid, name, float(price), int(shares), buy_date)
    print(f"已加入：{pos['stock_name']}（{pos['stock_id']}） {pos['shares']} 股 @ {pos['buy_price']} ({pos['buy_date']})")
    return 0


def cmd_close(args: list[str]) -> int:
    if len(args) < 2:
        print("用法: python scripts/my_status.py close <stock_id> <sell_price> [sell_date]")
        return 1
    sid, price = args[:2]
    sell_date = args[2] if len(args) >= 3 else None
    closed = close_position(sid, float(price), sell_date)
    if closed is None:
        print(f"找不到持倉中的 {sid}")
        return 1
    print(f"已平倉：{closed['stock_name']}（{closed['stock_id']}） @ {closed['sell_price']}"
          f"　已實現損益 {closed['pnl_ntd']:+,} 元")
    return 0


# ── 報告產生 ───────────────────────────────────────────────

def section_open_positions(open_list: list[dict], default_tp: float, default_sl: float) -> tuple[list[str], int]:
    if not open_list:
        return ["## 📦 目前持倉", "（無）", ""], 0

    lines = [f"## 📦 目前持倉（{len(open_list)} 檔）"]
    lines.append("| 股票 | 進場日 | 進場價 | 現價 | 浮動% | 股數 | 浮動損益 | TP | SL | 動作 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    total_unrealized = 0
    for p in open_list:
        sid = p["stock_id"]
        name = p["stock_name"]
        bp = float(p["buy_price"])
        shares = int(p["shares"])
        tp_pct = float(p.get("tp_pct", default_tp))
        sl_pct = float(p.get("sl_pct", default_sl))
        tp_price = bp * (1 + tp_pct / 100)
        sl_price = bp * (1 + sl_pct / 100)

        cur = fetch_latest_close(sid)
        if cur is None:
            lines.append(f"| {name}（{sid}） | {p['buy_date']} | {bp:.1f} | _抓不到_ | — | {shares} | — | {tp_price:.1f} | {sl_price:.1f} | — |")
            continue
        pnl_pct = calc_pnl_pct_net(bp, cur)
        pnl_ntd = calc_pnl_ntd(bp, cur, shares)
        total_unrealized += pnl_ntd

        # 動作判斷
        if cur >= tp_price:
            action = "🟢 **賣出（達標）**"
        elif cur <= sl_price:
            action = "🔴 **賣出（停損）**"
        elif pnl_pct >= tp_pct - 1:
            action = "🟡 接近 TP"
        elif pnl_pct <= sl_pct + 1:
            action = "🟡 接近 SL"
        else:
            action = "持有"

        sign = "+" if pnl_pct >= 0 else ""
        sign_n = "+" if pnl_ntd >= 0 else ""
        lines.append(
            f"| {name}（{sid}） | {p['buy_date']} | {bp:.1f} | {cur:.1f} | "
            f"{sign}{pnl_pct:.2f}% | {shares} | {sign_n}{pnl_ntd:,} | "
            f"{tp_price:.1f} | {sl_price:.1f} | {action} |"
        )
    lines.append("")
    return lines, total_unrealized


def section_realized(closed_list: list[dict]) -> tuple[list[str], int]:
    if not closed_list:
        return ["## 💰 已實現損益", "（無平倉紀錄）", ""], 0

    total = 0
    wins = sum(1 for c in closed_list if c.get("pnl_ntd", 0) > 0)
    losses = sum(1 for c in closed_list if c.get("pnl_ntd", 0) <= 0)
    lines = [
        f"## 💰 已實現損益（{len(closed_list)} 筆，{wins} 勝 / {losses} 負）",
        "| 股票 | 進場 | 出場 | 進價 | 出價 | 股數 | 損益 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in sorted(closed_list, key=lambda x: x.get("sell_date", ""), reverse=True):
        pnl = c.get("pnl_ntd", 0)
        total += pnl
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"| {c['stock_name']}（{c['stock_id']}） | {c['buy_date']} | {c['sell_date']} | "
            f"{float(c['buy_price']):.1f} | {float(c['sell_price']):.1f} | {c['shares']} | "
            f"**{sign}{pnl:,}** |"
        )
    sign_total = "+" if total >= 0 else ""
    lines.append(f"\n**累計已實現：{sign_total}{total:,} 元**\n")
    return lines, total


def section_progress(realized: int, unrealized: int, target_usd: float, fx: float) -> list[str]:
    target_ntd = int(target_usd * fx)
    total = realized + unrealized
    pct = total / target_ntd * 100 if target_ntd > 0 else 0
    bar_len = max(0, min(40, int(pct / 100 * 40)))
    bar = "█" * bar_len + "░" * (40 - bar_len)
    sign = "+" if total >= 0 else ""

    return [
        f"## 🎯 回本進度（目標：賺回 USD {target_usd:.0f} ≈ NTD {target_ntd:,}）",
        f"```",
        f"已實現   {realized:>+10,} 元",
        f"未實現   {unrealized:>+10,} 元",
        f"─────────────────────",
        f"合計     {total:>+10,} 元   ({sign}{pct:.1f}% of 目標)",
        f"",
        f"[{bar}]",
        f"```",
        "",
        f"_目標金額按匯率 1 USD = {fx:.1f} TWD 換算。修改 data/my_positions.json 的 `_target_usd` / `_usd_twd_rate` 可調整。_",
        "",
    ]


# ── 主程式 ─────────────────────────────────────────────────

def cmd_report(args: list[str]) -> int:
    cfg = load_positions()
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")

    open_list   = cfg.get("open", [])
    closed_list = cfg.get("closed", [])
    target_usd  = cfg.get("_target_usd", 100)
    fx          = cfg.get("_usd_twd_rate", 33.0)
    default_tp  = cfg.get("_strategy_default_tp_pct", 5.0)
    default_sl  = cfg.get("_strategy_default_sl_pct", -5.0)

    lines = [
        f"# 我的部位 · {today}",
        f"_資料來源：FinMind / yfinance（最新收盤）。手續費 +證交稅 ~0.5% 來回。_",
        "",
    ]

    open_section, unrealized = section_open_positions(open_list, default_tp, default_sl)
    realized_section, realized = section_realized(closed_list)

    lines += open_section
    lines += realized_section
    lines += section_progress(realized, unrealized, target_usd, fx)

    if not open_list and not closed_list:
        lines += [
            "---",
            "## 🚀 還沒開始？",
            "1. 看 `status_today.md` 找今日進場訊號",
            "2. 在券商下單後，記錄到本機：",
            "   ```",
            "   python scripts/my_status.py add 7769 鴻勁 5220 1000",
            "   ```",
            "3. 平倉後：`python scripts/my_status.py close 7769 5481`",
            "4. 之後每次 `update.bat` 跑完，這份報告會自動更新",
            "",
        ]

    OUTPUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE.relative_to(ROOT)}")
    if open_list or closed_list:
        sign = "+" if (realized + unrealized) >= 0 else ""
        print(f"  累計（已+未）：{sign}{realized + unrealized:,} 元")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return cmd_report([])
    cmd = args[0]
    if cmd == "add":   return cmd_add(args[1:])
    if cmd == "close": return cmd_close(args[1:])
    if cmd == "status" or cmd == "report": return cmd_report(args[1:])
    print(f"未知命令: {cmd}")
    print("用法:")
    print("  python scripts/my_status.py                              # 產生報告")
    print("  python scripts/my_status.py add <id> <name> <price> <shares> [date]")
    print("  python scripts/my_status.py close <id> <sell_price> [date]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
