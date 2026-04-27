from scrapers.nomura import parse_nomura_holdings, parse_nomura_meta


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
        assert h.stock_name
        assert h.weight_pct >= 0
        assert h.shares >= 0

    # Weight sum in reasonable range.
    # Active ETF has stock (~94.6%) + futures (~1.9%) = ~96.5%; cash buffers bring
    # the disclosed sum below 100. Widen to 80..101 to accommodate cash buffers.
    total = sum(h.weight_pct for h in holdings)
    assert 80 <= total <= 101, f"weight sum {total} out of expected range"


def test_parse_nomura_meta(fixture_path):
    """Entries.Data.FundAsset has the canonical 4-field metadata block."""
    text = fixture_path("nomura_00980A.json").read_text(encoding="utf-8")
    meta = parse_nomura_meta(text)
    assert meta.get("as_of_date") == "2026-04-24"   # NavDate slash-to-dash
    assert isinstance(meta.get("nav_total"), float) and meta["nav_total"] > 0
    assert isinstance(meta.get("units_outstanding"), float) and meta["units_outstanding"] > 0
    assert isinstance(meta.get("p_unit"), float) and 0 < meta["p_unit"] < 1000


def test_parse_nomura_meta_invalid_returns_empty():
    assert parse_nomura_meta("not json") == {}
    assert parse_nomura_meta('{"Entries": {}}') == {}
