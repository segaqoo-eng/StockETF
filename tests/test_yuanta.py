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

    total = sum(h.weight_pct for h in holdings)
    assert 95 <= total <= 101, f"weight sum {total} out of range"
