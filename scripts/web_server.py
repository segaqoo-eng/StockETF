"""web_server.py — StockETF 本機 web server (含 my_positions API)

替代 `python -m http.server`：static files 一樣 serve，多了：
  GET  /api/positions          → 取得持倉 + 已實現 + 浮動 P&L 完整資料
  POST /api/positions/add      → body: {stock_id, stock_name, buy_price, shares, buy_date?}
  POST /api/positions/close    → body: {stock_id, sell_price, sell_date?}
  POST /api/refresh            → 重跑 main.py + backtest + status (背景)

讓網頁前端「我的部位」tab 可直接點按鈕操作，不必跑 CLI。

用法：
  python scripts/web_server.py [port]      # 預設 8000
"""
from __future__ import annotations

import json
import sys
import traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Force UTF-8 stdout/stderr so background jobs (backtest / generate_status /
# paper_trade / main) can print Unicode chars (▶ → ✓ etc.) without crashing
# on Windows cp950 default. update.bat already sets PYTHONIOENCODING=utf-8
# but we shouldn't depend on the launcher.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass  # streams not always reconfigurable (e.g. piped); silently ignore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import my_status  # noqa: E402

import threading

# ── Refresh job state（module-level mutex）──────────────────
_job_lock = threading.Lock()
_running_job: str | None = None         # "prices" | "etfs" | None
_job_started_at: str | None = None
_last_result: dict | None = None
_last_error: str | None = None


def _reset_for_tests() -> None:
    """Test-only: reset module state between tests."""
    global _running_job, _job_started_at, _last_result, _last_error
    _running_job = None
    _job_started_at = None
    _last_result = None
    _last_error = None


import json as _json   # 避免遮蔽 do_POST 內的 json 匯入


def _run_prices_job() -> None:
    """Background runner: fetch_daily_close + write prices_today.json."""
    global _running_job, _last_result, _last_error
    try:
        from scrapers.daily_close import fetch_daily_close
        from datetime import datetime
        from zoneinfo import ZoneInfo

        latest_path = ROOT / "data" / "latest.json"
        prices_path = ROOT / "data" / "prices_today.json"
        target = datetime.now(ZoneInfo("Asia/Taipei")).date()

        latest = _json.loads(latest_path.read_text(encoding="utf-8"))
        held_ids = sorted({
            h["stock_id"]
            for etf in latest.get("etfs", [])
            for h in etf.get("holdings", [])
            if h.get("market") == "TW"
        })
        result = fetch_daily_close(list(held_ids), target)

        if result["ok"]:
            payload = {
                "date":       result["date"],
                "source":     result["source"],
                "fetched_at": result["fetched_at"],
                "prices":     result["prices"],
                "missing":    result["missing"],
            }
            prices_path.write_text(_json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        _last_result = {
            "job":            "prices",
            "ok":             result["ok"],
            "source":         result["source"],
            "missing_count":  len(result["missing"]),
            "tried":          result["tried"],
            "error":          result["error"],
        }
        _last_error = None
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        _last_error = f"{type(e).__name__}: {e}"
        _last_result = None


def _run_etfs_job() -> None:
    """Background runner: re-run main.main() (full ETF pipeline + prices at end)."""
    global _last_result, _last_error
    try:
        import importlib
        import main as etf_main
        importlib.reload(etf_main)
        rc = etf_main.main()
        _last_result = {"ok": rc == 0, "exit_code": rc, "job": "etfs"}
        _last_error = None
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        _last_error = f"{type(e).__name__}: {e}"
        _last_result = None


def _run_backtest_job() -> None:
    """Background runner: backtest.py + generate_status.py + paper_trade.py.

    Spec: docs/superpowers/specs/2026-04-30-prices-source-and-refresh-design.md
    (extended in v1.6 to add the manual-trigger backtest pipeline).
    """
    global _last_result, _last_error
    try:
        import importlib

        steps = []

        # 1. backtest
        import backtest as bt_mod
        importlib.reload(bt_mod)
        rc1 = bt_mod.main() if hasattr(bt_mod, "main") else 0
        # backtest.main() returns None on success (no explicit return); treat None as 0
        if rc1 is None:
            rc1 = 0
        steps.append(("backtest", rc1))

        # 2. status report
        sys.path.insert(0, str(ROOT / "scripts"))
        import generate_status as gs_mod
        importlib.reload(gs_mod)
        rc2 = gs_mod.main() if hasattr(gs_mod, "main") else 0
        if rc2 is None:
            rc2 = 0
        steps.append(("generate_status", rc2))

        # 3. paper trade
        import paper_trade as pt_mod
        importlib.reload(pt_mod)
        rc3 = pt_mod.main() if hasattr(pt_mod, "main") else 0
        if rc3 is None:
            rc3 = 0
        steps.append(("paper_trade", rc3))

        all_ok = all(rc == 0 for _, rc in steps)
        _last_result = {
            "job":   "backtest",
            "ok":    all_ok,
            "steps": [{"name": n, "rc": rc} for n, rc in steps],
        }
        _last_error = None
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        _last_error = f"{type(e).__name__}: {e}"
        _last_result = None


def _try_start_job(job_name: str, target_fn) -> tuple[bool, str | None]:
    """嘗試取 mutex 並啟動 background thread。回 (started, error_msg)。"""
    global _running_job, _job_started_at, _last_error
    from datetime import datetime
    from zoneinfo import ZoneInfo

    with _job_lock:
        if _running_job is not None:
            return False, f"another job '{_running_job}' is running"
        _running_job = job_name
        _job_started_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
        _last_error = None

    def _runner():
        global _running_job, _job_started_at, _last_error
        try:
            target_fn()
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            _last_error = f"{type(e).__name__}: {e}"
        finally:
            with _job_lock:
                _running_job = None
                _job_started_at = None

    threading.Thread(target=_runner, daemon=True).start()
    return True, None


class StockETFHandler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    # 全部請求印一行 log
    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} "
                         f"{format % args}\n")

    # ── GET ───────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/api/refresh/status":
            return self._send_json({
                "running":     _running_job is not None,
                "current_job": _running_job,
                "started_at":  _job_started_at,
                "last_result": _last_result,
                "last_error":  _last_error,
            })
        if self.path == "/api/positions":
            return self._send_json(my_status.get_full_status())
        if self.path.startswith("/api/markdown"):
            return self._send_markdown()
        if self.path.startswith("/api/ohlcv"):
            return self._send_stock_data("ohlcv")
        if self.path.startswith("/api/institutional"):
            return self._send_stock_data("institutional")
        return super().do_GET()

    def _send_stock_data(self, dataset: str) -> None:
        """讀 SQLite cache (data_provider)，缺的 by-need 補抓。前端 ranking.js 用。"""
        from urllib.parse import urlparse, parse_qs
        import data_provider as dp
        q = parse_qs(urlparse(self.path).query)
        sid = (q.get("stock_id", [""])[0]).strip()
        start = (q.get("start_date", ["2025-04-01"])[0]).strip()
        if not sid:
            return self._send_json({"ok": False, "error": "stock_id required"}, status=400)
        if dataset == "ohlcv":
            rows = dp.get_ohlcv(sid, start)
        else:  # institutional
            rows = dp.get_institutional(sid, start)
        return self._send_json({"status": 200, "data": rows})

    def _send_markdown(self) -> None:
        """讀取根目錄的 .md (限定白名單)、回原始文字。"""
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("file", [""])[0]).strip()
        WHITELIST = {"status_today", "paper_status", "my_status"}
        if name not in WHITELIST:
            return self._send_json({"ok": False, "error": "unknown file"}, status=400)
        path = ROOT / f"{name}.md"
        if not path.exists():
            text = f"# {name}\n\n（{name}.md 不存在 — 跑 update.bat 後會產生）"
        else:
            text = path.read_text(encoding="utf-8")
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ── POST ──────────────────────────────────────────────

    def do_POST(self):
        try:
            if self.path == "/api/refresh/prices":
                ok, err = _try_start_job("prices", _run_prices_job)
                if not ok:
                    return self._send_json({"ok": False, "error": err}, status=409)
                return self._send_json({"job": "prices", "started_at": _job_started_at},
                                       status=202)

            if self.path == "/api/refresh/etfs":
                ok, err = _try_start_job("etfs", _run_etfs_job)
                if not ok:
                    return self._send_json({"ok": False, "error": err}, status=409)
                return self._send_json({"job": "etfs", "started_at": _job_started_at},
                                       status=202)

            if self.path == "/api/refresh/backtest":
                ok, err = _try_start_job("backtest", _run_backtest_job)
                if not ok:
                    return self._send_json({"ok": False, "error": err}, status=409)
                return self._send_json({"job": "backtest", "started_at": _job_started_at}, status=202)

            if self.path == "/api/positions/add":
                payload = self._read_json()
                pos = my_status.add_position(
                    stock_id   = payload["stock_id"],
                    stock_name = payload["stock_name"],
                    buy_price  = float(payload["buy_price"]),
                    shares     = int(payload["shares"]),
                    buy_date   = payload.get("buy_date"),
                    buy_reason = payload.get("buy_reason", ""),
                )
                return self._send_json({"ok": True, "position": pos})

            if self.path == "/api/positions/close":
                payload = self._read_json()
                closed = my_status.close_position(
                    stock_id   = payload["stock_id"],
                    sell_price = float(payload["sell_price"]),
                    sell_date  = payload.get("sell_date"),
                )
                if closed is None:
                    return self._send_json({"ok": False, "error": "找不到持倉中的股票"}, status=404)
                return self._send_json({"ok": True, "closed": closed})

            if self.path == "/api/positions/delete":
                payload = self._read_json()
                deleted = my_status.delete_position(stock_id=payload["stock_id"])
                if deleted is None:
                    return self._send_json({"ok": False, "error": "找不到持倉中的股票"}, status=404)
                return self._send_json({"ok": True, "deleted": deleted})

            return self._send_json({"ok": False, "error": "unknown endpoint"}, status=404)

        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return self._send_json({"ok": False, "error": str(e)}, status=500)

    # ── helpers ───────────────────────────────────────────

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    addr = ("0.0.0.0", port)
    print(f"StockETF web server: http://localhost:{port}")
    print(f"  static  : {ROOT}")
    print(f"  api     : /api/positions  /api/positions/add  /api/positions/close")
    print(f"  Ctrl+C 結束")
    try:
        HTTPServer(addr, StockETFHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n停止 server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
