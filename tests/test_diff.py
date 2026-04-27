"""Tests for normalizer.compute_diff — per-ETF day-over-day holdings delta."""
from normalizer import compute_diff


def _payload(etfs):
    """Build a minimal payload matching build_payload's etfs[i].holdings shape."""
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
                        "shares": 0,
                        "market": h[3] if len(h) > 3 else "TW",
                    }
                    for h in holdings
                ],
            }
            for ticker, holdings in etfs.items()
        ],
        "holdings": [],
    }


def test_no_change_omits_etf():
    """When today and yesterday are identical, the ETF doesn't appear in the diff."""
    today = _payload({"0050": [("2330", "台積電", 48.5), ("2454", "聯發科", 3.8)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5), ("2454", "聯發科", 3.8)]})
    assert compute_diff(today, yesterday) == {}


def test_added_stock():
    today = _payload({"0050": [("2330", "台積電", 48.5), ("6669", "緯穎", 4.2)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5)]})
    diff = compute_diff(today, yesterday)
    assert "0050" in diff
    assert len(diff["0050"]["added"]) == 1
    assert diff["0050"]["added"][0] == {"stock_id": "6669", "stock_name": "緯穎", "weight_pct": 4.2}
    assert diff["0050"]["removed"] == []
    assert diff["0050"]["changed"] == []


def test_removed_stock_carries_yesterday_weight():
    """Removed entries report the weight from yesterday (today's is 0 by definition)."""
    today = _payload({"0050": [("2330", "台積電", 49.5)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5), ("9999", "某檔", 1.0)]})
    diff = compute_diff(today, yesterday)
    assert diff["0050"]["removed"] == [{"stock_id": "9999", "stock_name": "某檔", "weight_pct": 1.0}]


def test_weight_change_above_threshold():
    today = _payload({"0050": [("2330", "台積電", 49.20)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.50)]})
    diff = compute_diff(today, yesterday)
    assert len(diff["0050"]["changed"]) == 1
    ch = diff["0050"]["changed"][0]
    assert ch["stock_id"] == "2330"
    assert ch["weight_now"] == 49.20
    assert ch["weight_prev"] == 48.50
    assert abs(ch["delta"] - 0.70) < 1e-9


def test_weight_change_below_threshold_filtered():
    """Sub-threshold drift (< 0.005%) is noise — don't pollute the changed list."""
    today = _payload({"0050": [("2330", "台積電", 48.503)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.500)]})
    diff = compute_diff(today, yesterday)
    assert diff == {}, "0.003% drift should be below threshold and produce no diff"


def test_foreign_holdings_ignored():
    """LITE US / 285A JP are TW-cross-incomparable; ignore them in diffs to match
    the cross-table TW-only convention. See known-issues/holdings-diff-todo.md."""
    today = _payload({
        "00990A": [
            ("2330", "台積電", 3.5, "TW"),
            ("LITE US", "LUMENTUM HOLDINGS INC", 7.2, "US"),  # changed weight 7.2 → 8.0
            ("AMD US", "ADVANCED MICRO DEVICES", 2.6, "US"),  # newly added foreign
        ],
    })
    yesterday = _payload({
        "00990A": [
            ("2330", "台積電", 3.5, "TW"),
            ("LITE US", "LUMENTUM HOLDINGS INC", 8.0, "US"),
        ],
    })
    diff = compute_diff(today, yesterday)
    # 2330 unchanged, foreign holdings ignored entirely → no diff for 00990A
    assert diff == {}


def test_etf_only_in_one_side_skipped():
    """Lineup changes (ETF added/removed) aren't a holdings diff — skip those ETFs."""
    today = _payload({"0050": [("2330", "台積電", 48.5)], "00991A": [("2330", "台積電", 14.9)]})
    yesterday = _payload({"0050": [("2330", "台積電", 48.5)]})
    diff = compute_diff(today, yesterday)
    assert "00991A" not in diff, "ETF only in today should be skipped, not flagged as all-added"


def test_old_format_yesterday_skipped():
    """Pre-v1.5 snapshots had no etfs[i].holdings field. Treat as no-comparison-
    data for that ETF rather than flagging today's whole list as new."""
    today = _payload({"0050": [("2330", "台積電", 48.5)]})
    # Strip the holdings field to simulate an old-format snapshot
    yesterday = _payload({"0050": [("2330", "台積電", 48.5)]})
    del yesterday["etfs"][0]["holdings"]
    assert compute_diff(today, yesterday) == {}


def test_changed_sorted_by_absolute_delta_desc():
    """The biggest mover should be first (positive or negative)."""
    today = _payload({"0050": [
        ("2330", "台積電", 48.5),  # delta 0
        ("2454", "聯發科", 3.0),   # delta -1.0
        ("2317", "鴻海", 6.0),     # delta +2.5
    ]})
    yesterday = _payload({"0050": [
        ("2330", "台積電", 48.5),
        ("2454", "聯發科", 4.0),
        ("2317", "鴻海", 3.5),
    ]})
    diff = compute_diff(today, yesterday)
    deltas = [c["delta"] for c in diff["0050"]["changed"]]
    assert deltas[0] == 2.5  # 鴻海 (biggest absolute change first)
    assert deltas[1] == -1.0
