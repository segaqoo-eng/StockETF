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


def test_post_refresh_etfs_returns_202(server, monkeypatch):
    """ETF refresh 走獨立 endpoint。"""
    import scripts.web_server as ws
    done = threading.Event()
    monkeypatch.setattr(ws, "_run_etfs_job", lambda: done.set())

    status, body = _post(server, "/api/refresh/etfs")
    assert status == 202
    assert body["job"] == "etfs"
    assert done.wait(timeout=2)


def test_thread_crash_writes_last_error_releases_mutex(server, monkeypatch):
    """Thread 內爆 exception → last_error 有值 + mutex 釋放（不卡死）"""
    import scripts.web_server as ws

    def boom():
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(ws, "_run_prices_job", boom)

    s1, _ = _post(server, "/api/refresh/prices")
    assert s1 == 202

    deadline = time.time() + 2
    while time.time() < deadline and ws._running_job is not None:
        time.sleep(0.02)
    assert ws._running_job is None

    status, body = _get(server, "/api/refresh/status")
    assert "simulated crash" in (body["last_error"] or "")


def test_run_backtest_job_records_result(monkeypatch):
    """_run_backtest_job assembles steps list correctly when all subprocesses succeed."""
    import scripts.web_server as ws
    ws._reset_for_tests()

    # Stub out the three modules so we don't actually run them
    class _FakeMod:
        def __init__(self, rc): self._rc = rc
        def main(self): return self._rc

    fake_bt = _FakeMod(0)
    fake_gs = _FakeMod(0)
    fake_pt = _FakeMod(0)

    import sys
    monkeypatch.setitem(sys.modules, "backtest", fake_bt)
    monkeypatch.setitem(sys.modules, "generate_status", fake_gs)
    monkeypatch.setitem(sys.modules, "paper_trade", fake_pt)

    # Stub importlib.reload to a no-op (modules already in sys.modules)
    import importlib
    monkeypatch.setattr(importlib, "reload", lambda m: m)

    ws._run_backtest_job()

    assert ws._last_error is None
    assert ws._last_result["job"] == "backtest"
    assert ws._last_result["ok"] is True
    names = [s["name"] for s in ws._last_result["steps"]]
    assert names == ["backtest", "generate_status", "paper_trade"]


def test_run_backtest_job_records_error_on_crash(monkeypatch):
    """If any sub-job raises, _last_error is set, _last_result is None."""
    import scripts.web_server as ws
    ws._reset_for_tests()

    class _Boomer:
        def main(self): raise RuntimeError("simulated backtest crash")

    import sys
    monkeypatch.setitem(sys.modules, "backtest", _Boomer())
    import importlib
    monkeypatch.setattr(importlib, "reload", lambda m: m)

    ws._run_backtest_job()

    assert "simulated backtest crash" in (ws._last_error or "")
    assert ws._last_result is None


