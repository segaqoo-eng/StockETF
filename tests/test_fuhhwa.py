from scrapers.fuhhwa import extract_date_from_detail, parse_fuhhwa_xlsx


def test_extract_date_from_detail(fixture_path):
    html = fixture_path("fuhhwa_00991A_detail.html").read_text(encoding="utf-8")
    assert extract_date_from_detail(html, "ETF23") == "20260424"


def test_parse_fuhhwa_xlsx(fixture_path):
    content = fixture_path("fuhhwa_00991A.xlsx").read_bytes()
    holdings = parse_fuhhwa_xlsx(content)

    assert len(holdings) == 50, f"expected 50 holdings, got {len(holdings)}"

    # 00991A's largest position is 台積電 (2330) per fund prospectus
    top = holdings[0]
    assert top.stock_id == "2330"
    assert top.weight_pct > 10  # 14.929% in this snapshot

    # All holdings are pure-TW 4-digit tickers
    for h in holdings:
        assert h.stock_id
        assert h.stock_name
        assert h.weight_pct >= 0
        assert h.shares >= 0
        assert h.market == "TW", f"unexpected market for {h.stock_id}: {h.market}"

    # Stock weights should sum near 100% (cash/derivatives make up the rest)
    total = sum(h.weight_pct for h in holdings)
    assert 95 <= total <= 101, f"weight sum {total} out of expected range"
