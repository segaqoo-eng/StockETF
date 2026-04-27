from scrapers.president import parse_president_holdings


def test_parse_president_00981A(fixture_path):
    text = fixture_path("capital_00981A.html").read_text(encoding="utf-8")
    holdings = parse_president_holdings(text)

    # 00981A is an active ETF; active ETFs typically hold 30-100 stocks
    assert 30 <= len(holdings) <= 100, f"expected 30-100 holdings, got {len(holdings)}"

    # First holding: should have valid fields
    top = holdings[0]
    assert top.stock_id
    assert top.stock_name
    assert top.weight_pct > 0

    for h in holdings:
        assert h.stock_id
        assert h.stock_name
        assert h.weight_pct >= 0
        assert h.shares >= 0

    # Weight sum: active ETFs may have cash buffer, use wider range
    total = sum(h.weight_pct for h in holdings)
    assert 80 <= total <= 101, f"weight sum {total} out of expected range"
