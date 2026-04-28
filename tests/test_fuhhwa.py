from scrapers.fuhhwa import extract_date_from_detail, parse_fuhhwa_xlsx, parse_fuhhwa_meta, parse_fuhhwa_api


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


def test_parse_fuhhwa_meta(fixture_path):
    """Top rows of the xlsx carry as_of_date / nav_total / units_outstanding / p_unit."""
    content = fixture_path("fuhhwa_00991A.xlsx").read_bytes()
    meta = parse_fuhhwa_meta(content)

    # The fixture is dated 2026/04/24 per the user's earlier spec
    assert meta.get("as_of_date") == "2026-04-24"
    assert meta.get("nav_total") == 33_662_750_937.0
    assert meta.get("units_outstanding") == 2_072_916_000.0
    assert meta.get("p_unit") == 16.24


def test_parse_fuhhwa_meta_corrupt_returns_empty():
    """Garbage bytes → empty meta, not exception."""
    assert parse_fuhhwa_meta(b"not an xlsx") == {}


def test_parse_fuhhwa_api(fixture_path):
    text = fixture_path("fuhhwa_api_00991A.json").read_text(encoding="utf-8")
    holdings, meta = parse_fuhhwa_api(text)

    assert len(holdings) == 2          # 2 股票; 現金 excluded
    assert holdings[0].stock_id == "2330"
    assert holdings[0].stock_name == "台灣積體"
    assert holdings[0].shares == 3_600_000
    assert abs(holdings[0].weight_pct - 21.406) < 0.001
    assert holdings[0].market == "TW"

    assert meta["as_of_date"] == "2026-04-28"
    assert meta["nav_total"] == 37_251_262_686.0
    assert meta["units_outstanding"] == 2_243_416_000.0
    assert meta["p_unit"] == 16.6


def test_parse_fuhhwa_api_empty_on_bad_status():
    holdings, meta = parse_fuhhwa_api('{"status": 1, "result": []}')
    assert holdings == []
    assert meta == {}
