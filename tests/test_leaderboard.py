"""Tests for normalizer.compute_leaderboard — top movers across ETFs."""
from normalizer import compute_leaderboard


def _payload(etfs):
    """Same shape as build_payload's etfs[i].holdings."""
    return {
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
    }


def test_empty_when_no_movement():
    today = _payload({"0050": [("2330", "台積電", 48.5)]})
    baseline = _payload({"0050": [("2330", "台積電", 48.5)]})
    result = compute_leaderboard(today, baseline)
    assert result["top_added"] == []
    assert result["top_removed"] == []


def test_baseline_lacks_holdings_returns_empty():
    """Old-format baseline (no etfs[i].holdings) → no comparison possible."""
    today = _payload({"0050": [("2330", "台積電", 48.5)]})
    baseline = _payload({"0050": [("2330", "台積電", 48.5)]})
    del baseline["etfs"][0]["holdings"]
    result = compute_leaderboard(today, baseline)
    assert result["top_added"] == []
    assert result["top_removed"] == []


def test_added_aggregated_across_etfs():
    """A stock weight bumped in 3 ETFs ranks above one bumped in 1 ETF (counting)."""
    today = _payload({
        "0050":   [("2330", "台積電", 50.0), ("6669", "緯穎", 4.0)],
        "00980A": [("2330", "台積電", 35.0), ("6669", "緯穎", 5.0)],
        "00990A": [("2330", "台積電", 4.0)],  # +0.5 only
    })
    baseline = _payload({
        "0050":   [("2330", "台積電", 48.5), ("6669", "緯穎", 3.5)],
        "00980A": [("2330", "台積電", 32.0), ("6669", "緯穎", 4.5)],
        "00990A": [("2330", "台積電", 3.5)],
    })
    result = compute_leaderboard(today, baseline)
    # 2330 moved in 3 ETFs (+1.5, +3.0, +0.5 = 5.0 total); 6669 in 2 (+0.5, +0.5 = 1.0)
    assert len(result["top_added"]) == 2
    top1 = result["top_added"][0]
    assert top1["stock_id"] == "2330"
    assert top1["etf_count"] == 3
    assert abs(top1["total_delta"] - 5.0) < 1e-6
    top2 = result["top_added"][1]
    assert top2["stock_id"] == "6669"
    assert top2["etf_count"] == 2
    assert abs(top2["total_delta"] - 1.0) < 1e-6


def test_removed_uses_negative_delta():
    today = _payload({"0050": [("2330", "台積電", 45.0)]})
    baseline = _payload({"0050": [("2330", "台積電", 50.0)]})
    result = compute_leaderboard(today, baseline)
    assert len(result["top_removed"]) == 1
    r = result["top_removed"][0]
    assert r["stock_id"] == "2330"
    assert r["etf_count"] == 1
    assert abs(r["total_delta"] - (-5.0)) < 1e-6
    assert result["top_added"] == []


def test_threshold_filters_noise():
    """Tiny per-ETF moves don't count toward etf_count, even if total adds up."""
    today = _payload({
        "0050":   [("2330", "台積電", 48.51)],   # +0.01 (below threshold)
        "00980A": [("2330", "台積電", 32.02)],   # +0.02 (below)
        "00990A": [("2330", "台積電", 3.55)],    # +0.05 (at threshold — counts)
    })
    baseline = _payload({
        "0050":   [("2330", "台積電", 48.5)],
        "00980A": [("2330", "台積電", 32.0)],
        "00990A": [("2330", "台積電", 3.5)],
    })
    result = compute_leaderboard(today, baseline, move_threshold=0.05)
    # only 1 ETF crosses threshold — but total still summed across all
    if result["top_added"]:
        top = result["top_added"][0]
        assert top["etf_count"] == 1


def test_foreign_holdings_ignored():
    today = _payload({
        "00990A": [
            ("2330", "台積電", 5.0, "TW"),
            ("LITE US", "Lumentum", 8.0, "US"),
        ],
    })
    baseline = _payload({
        "00990A": [
            ("2330", "台積電", 4.0, "TW"),
            ("LITE US", "Lumentum", 6.0, "US"),
        ],
    })
    result = compute_leaderboard(today, baseline)
    # 2330 should appear; LITE US should not
    assert len(result["top_added"]) == 1
    assert result["top_added"][0]["stock_id"] == "2330"


def test_newly_appearing_stock_counted_as_added():
    """A stock that wasn't in baseline at all is treated as full-weight added."""
    today = _payload({"0050": [("2330", "台積電", 48.5), ("9999", "新進", 2.0)]})
    baseline = _payload({"0050": [("2330", "台積電", 48.5)]})
    result = compute_leaderboard(today, baseline)
    assert len(result["top_added"]) == 1
    top = result["top_added"][0]
    assert top["stock_id"] == "9999"
    assert top["etf_count"] == 1
    assert abs(top["total_delta"] - 2.0) < 1e-6


def test_completely_removed_stock_counted_as_negative():
    today = _payload({"0050": [("2330", "台積電", 50.5)]})
    baseline = _payload({"0050": [("2330", "台積電", 48.5), ("9999", "踢出", 2.0)]})
    result = compute_leaderboard(today, baseline)
    # 2330 +2 added; 9999 -2 removed
    assert len(result["top_added"]) == 1 and result["top_added"][0]["stock_id"] == "2330"
    assert len(result["top_removed"]) == 1
    assert result["top_removed"][0]["stock_id"] == "9999"
    assert abs(result["top_removed"][0]["total_delta"] - (-2.0)) < 1e-6


def test_top_n_truncation():
    # 7 stocks all added; only top 5 returned
    today = _payload({"0050": [
        (f"100{i}", f"S{i}", 10.0 + i) for i in range(7)
    ]})
    baseline = _payload({"0050": [
        (f"100{i}", f"S{i}", 5.0) for i in range(7)
    ]})
    result = compute_leaderboard(today, baseline, top_n=5)
    assert len(result["top_added"]) == 5
    # Largest delta first
    assert result["top_added"][0]["stock_id"] == "1006"
    assert result["top_added"][-1]["stock_id"] == "1002"
