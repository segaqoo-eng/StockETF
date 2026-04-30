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


def _post(server, path, body=None):
    conn = http.client.HTTPConnection(*server)
    body_bytes = json.dumps(body).encode("utf-8") if body else b""
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body_bytes))}
    conn.request("POST", path, body=body_bytes, headers=headers)
    r = conn.getresponse()
    text = r.read().decode("utf-8")
    conn.close()
    return r.status, json.loads(text) if text else None


def test_post_refresh_prices_returns_202_and_starts_thread(server, monkeypatch):
    """正常情況：return 202 並啟動背景 thread"""
    import scripts.web_server as ws

    fake_done = threading.Event()
    def fake_run_prices_job():
        time.sleep(0.05)
        fake_done.set()

    monkeypatch.setattr(ws, "_run_prices_job", fake_run_prices_job)

    status, body = _post(server, "/api/refresh/prices")
    assert status == 202
    assert body["job"] == "prices"
    assert "started_at" in body

    assert fake_done.wait(timeout=2)
    deadline = time.time() + 1
    while time.time() < deadline and ws._running_job is not None:
        time.sleep(0.01)
    assert ws._running_job is None


def test_concurrent_refresh_returns_409(server, monkeypatch):
    """第二個 request 撞 mutex → 409 Conflict"""
    import scripts.web_server as ws
    blocking = threading.Event()

    def slow_run():
        blocking.wait(timeout=2)

    monkeypatch.setattr(ws, "_run_prices_job", slow_run)

    s1, b1 = _post(server, "/api/refresh/prices")
    assert s1 == 202

    s2, b2 = _post(server, "/api/refresh/prices")
    assert s2 == 409
    assert "running" in b2["error"].lower()

    blocking.set()
