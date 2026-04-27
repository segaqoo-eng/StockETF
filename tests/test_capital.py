import pytest

from scrapers.capital import parse_capital_holdings


@pytest.mark.parametrize("ticker, top_id, top_name", [
    ("00982A", "2330", "台積電"),
    ("00992A", "2330", "台積電"),
])
def test_parse_capital(ticker, top_id, top_name, fixture_path):
    text = fixture_path(f"capital_{ticker}.html").read_text(encoding="utf-8")
    holdings = parse_capital_holdings(text)

    # SSR exposes only top-10 — see docs/known-issues/capital-scraper.md
    assert 1 <= len(holdings) <= 10, f"expected 1-10 holdings, got {len(holdings)}"

    top = holdings[0]
    assert top.stock_id == top_id
    assert top.stock_name == top_name
    assert top.weight_pct > 0

    for h in holdings:
        assert h.stock_id
        assert h.stock_name
        assert h.weight_pct > 0
        assert h.shares > 0
