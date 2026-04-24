from scrapers.nomura import parse_nomura_holdings


def test_parse_nomura_00980A(fixture_path):
    text = fixture_path("nomura_00980A.json").read_text(encoding="utf-8")
    holdings = parse_nomura_holdings(text)

    # 00980A is an active ETF with ~50 stock holdings plus 1 futures position = 51 total.
    # Widen upper bound to 80 to allow for growth over time.
    assert 40 <= len(holdings) <= 80, f"expected 40-80 holdings, got {len(holdings)}"

    # Largest weight should be on a known stock; weight range sanity
    top = holdings[0]
    assert top.stock_id
    assert top.weight_pct > 0

    for h in holdings:
        assert h.stock_id
        assert h.weight_pct >= 0
        assert h.shares >= 0

    # Weight sum in reasonable range.
    # Active ETF has stock (~94.6%) + futures (~1.9%) = ~96.5%; cash buffers bring
    # the disclosed sum below 100. Widen to 80..101 to accommodate cash buffers.
    total = sum(h.weight_pct for h in holdings)
    assert 80 <= total <= 101, f"weight sum {total} out of expected range"
