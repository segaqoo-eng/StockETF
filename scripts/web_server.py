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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import my_status  # noqa: E402


class StockETFHandler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    # 全部請求印一行 log
    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} "
                         f"{format % args}\n")

    # ── GET ───────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/api/positions":
            return self._send_json(my_status.get_full_status())
        return super().do_GET()

    # ── POST ──────────────────────────────────────────────

    def do_POST(self):
        try:
            if self.path == "/api/positions/add":
                payload = self._read_json()
                pos = my_status.add_position(
                    stock_id   = payload["stock_id"],
                    stock_name = payload["stock_name"],
                    buy_price  = float(payload["buy_price"]),
                    shares     = int(payload["shares"]),
                    buy_date   = payload.get("buy_date"),
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
