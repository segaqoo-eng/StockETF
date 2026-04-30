"""End-to-end API tests for /api/refresh/* endpoints.

啟動真實 HTTPServer 在隨機 port，用 http.client 打 request。
"""
import json
import threading
import time
import http.client
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pytest


@pytest.fixture
def server():
    """Start web_server.StockETFHandler on a random free port; yield (host, port)."""
    from http.server import HTTPServer
    import scripts.web_server as ws

    # 重置 mutex state（每個測試獨立）
    ws._reset_for_tests()

    httpd = HTTPServer(("127.0.0.1", 0), ws.StockETFHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield ("127.0.0.1", port)
    finally:
        httpd.shutdown()


def _get(server, path):
    conn = http.client.HTTPConnection(*server)
    conn.request("GET", path)
    r = conn.getresponse()
    body = r.read().decode("utf-8")
    conn.close()
    return r.status, json.loads(body) if body else None


def test_refresh_status_initial_state(server):
    """初始狀態：running=False, current_job=None"""
    status, body = _get(server, "/api/refresh/status")
    assert status == 200
    assert body["running"] is False
    assert body["current_job"] is None
    assert body["last_error"] is None
