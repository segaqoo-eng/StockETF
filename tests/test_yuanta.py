from scrapers.yuanta import parse_yuanta_holdings


def test_parse_yuanta_0050(fixture_path):
    # The page embeds holdings in a server-rendered window.__NUXT__ payload (HTML)
    text = fixture_path("yuanta_0050.html").read_text(encoding="utf-8")
    holdings = parse_yuanta_holdings(text)

    assert len(holdings) == 50, f"expected 50 holdings in 0050, got {len(holdings)}"

    # First holding should be 2330 台積電 with highest weight
    first = holdings[0]
    assert first.stock_id == "2330"
    assert "台積" in first.stock_name
    assert first.weight_pct > 40  # 0050's TSMC weight historically > 40%

    # All weights should be positive and sum < 101 (allow rounding)
    total = sum(h.weight_pct for h in holdings)
    assert 95 <= total <= 101, f"weight sum {total} out of range"


def test_parse_yuanta_0056(fixture_path):
    text = fixture_path("yuanta_0056.html").read_text(encoding="utf-8")
    holdings = parse_yuanta_holdings(text)

    assert len(holdings) >= 30  # 0056 has ~50 holdings
    for h in holdings:
        assert h.stock_id and h.stock_name
        assert h.weight_pct > 0
        # 0056 is a pure-TW dividend ETF — every holding must classify as TW
        assert h.market == "TW", f"unexpected market for {h.stock_id}: {h.market}"

    total = sum(h.weight_pct for h in holdings)
    assert 95 <= total <= 101, f"weight sum {total} out of range"


def test_parse_yuanta_00990A_mixed_markets(fixture_path):
    """Active ETF with foreign holdings — code/name/ename are inline string
    literals (not compressed VARs) and tickers like 'LITE US' / '285A JP' must
    classify into US/JP markets, not TW."""
    text = fixture_path("yuanta_00990A.html").read_text(encoding="utf-8")
    holdings = parse_yuanta_holdings(text)

    assert len(holdings) >= 20, f"expected ≥20 holdings, got {len(holdings)}"

    by_market = {}
    for h in holdings:
        by_market.setdefault(h.market, []).append(h)

    # Mixed AI ETF must contain at least TW + US holdings
    assert "TW" in by_market, "expected TW holdings"
    assert "US" in by_market, "expected US holdings (e.g. LITE US, MU US)"
    # JP optional but presence in current snapshot — assert if found
    if "JP" in by_market:
        assert any("JP" in h.stock_id for h in by_market["JP"])

    # Spot-check a TW holding (台積電 always present in this AI ETF snapshot)
    tw = by_market["TW"]
    assert any(h.stock_id == "2330" for h in tw), "台積電 should be in TW slice"

    # Spot-check a US holding has English name (no Chinese name expected)
    us = by_market["US"]
    sample_us = us[0]
    assert sample_us.stock_id.endswith(" US")
    assert sample_us.stock_name  # name is the English company name

    # Weight sum across all markets ≈ 100
    total = sum(h.weight_pct for h in holdings)
    assert 80 <= total <= 101, f"weight sum {total} out of range"
