"""Tests for normalizer.compute_diff — per-ETF day-over-day holdings delta.

Diff is shares-based: only a change in share count counts as a real trade.
Weight-only drift (same shares, different %) is ignored.
"""
from normalizer import compute_diff


def _payload(etfs):
    """Build a minimal payload matching build_payload's etfs[i].holdings shape.
    Tuple format: (stock_id, stock_name, weight_pct, market='TW', shares=0)
    """
    return {
        "updated_at": "2026-04-27T17:00:00+08:00",
        "etfs": [
            {
                "ticker": ticker,
                "name": ticker,
                "type": "active",
                "tags": [],
                "color": "#000",
                "holdings_count": len(holdings),
                "holdings": [
                    {
                        "stock_id": h[0],
                        "stock_name": h[1],
                        "weight_pct": h[2],
                        "shares": h[4] if len(h) > 4 else 0,
                        "market": h[3] if len(h) > 3 else "TW",
                    }
                    for h in holdings
                ],
            }
            for ticker, holdings in etfs.items()
        ],
        "holdings": [],
    }


def test_no_share_change_produces_empty_changed():
    """Same shares → not a trade, even if weight % drifted."""
    today     = _payload({"0050": [("2330", "台積電", 49.5, "TW", 1000)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5, "TW", 1000)]})
    diff = compute_diff(today, yesterday)
    assert "0050" in diff
    assert diff["0050"]["changed"] == []


def test_share_change_detected():
    """Different share count → shows up in changed with shares_delta."""
    today     = _payload({"0050": [("2330", "台積電", 49.5, "TW", 1200)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5, "TW", 1000)]})
    diff = compute_diff(today, yesterday)
    assert len(diff["0050"]["changed"]) == 1
    ch = diff["0050"]["changed"][0]
    assert ch["stock_id"] == "2330"
    assert ch["shares_now"] == 1200
    assert ch["shares_prev"] == 1000
    assert ch["shares_delta"] == 200


def test_added_stock():
    today     = _payload({"0050": [("2330", "台積電", 48.5), ("6669", "緯穎", 4.2, "TW", 5000)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5)]})
    diff = compute_diff(today, yesterday)
    assert len(diff["0050"]["added"]) == 1
    added = diff["0050"]["added"][0]
    assert added["stock_id"] == "6669"
    assert added["stock_name"] == "緯穎"
    assert added["shares"] == 5000
    assert diff["0050"]["changed"] == []


def test_removed_stock_carries_shares():
    today     = _payload({"0050": [("2330", "台積電", 49.5)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5), ("9999", "某檔", 1.0, "TW", 3000)]})
    diff = compute_diff(today, yesterday)
    removed = diff["0050"]["removed"][0]
    assert removed["stock_id"] == "9999"
    assert removed["shares"] == 3000


def test_changed_sorted_by_absolute_shares_delta_desc():
    today = _payload({"0050": [
        ("2330", "台積電", 48.5, "TW", 1000),  # unchanged
        ("2454", "聯發科", 3.0,  "TW", 900),   # -100
        ("2317", "鴻海",   6.0,  "TW", 1500),  # +500
    ]})
    yesterday = _payload({"0050": [
        ("2330", "台積電", 48.5, "TW", 1000),
        ("2454", "聯發科", 4.0,  "TW", 1000),
        ("2317", "鴻海",   3.5,  "TW", 1000),
    ]})
    diff = compute_diff(today, yesterday)
    deltas = [c["shares_delta"] for c in diff["0050"]["changed"]]
    assert deltas[0] == 500   # 鴻海 biggest absolute
    assert deltas[1] == -100


def test_foreign_holdings_ignored():
    today = _payload({
        "00990A": [
            ("2330",    "台積電",            3.5, "TW", 1000),
            ("LITE US", "LUMENTUM HOLDINGS", 7.2, "US", 500),
        ],
    })
    yesterday = _payload({
        "00990A": [
            ("2330",    "台積電",            3.5, "TW", 1000),
            ("LITE US", "LUMENTUM HOLDINGS", 8.0, "US", 500),
        ],
    })
    diff = compute_diff(today, yesterday)
    assert diff["00990A"] == {"added": [], "removed": [], "changed": []}


def test_etf_only_in_one_side_skipped():
    today     = _payload({"0050": [("2330", "台積電", 48.5)], "00991A": [("2330", "台積電", 14.9)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5)]})
    diff = compute_diff(today, yesterday)
    assert "00991A" not in diff


def test_old_format_yesterday_skipped():
    today     = _payload({"0050": [("2330", "台積電", 48.5)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5)]})
    del yesterday["etfs"][0]["holdings"]
    assert compute_diff(today, yesterday) == {}
