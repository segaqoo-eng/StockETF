from scrapers.president import parse_president_holdings, parse_president_meta


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


def test_parse_president_meta(fixture_path):
    """ezmoney's DataAsset JSON exposes 9 AssetCode entries — confirm we lift
    the canonical meta fields out cleanly."""
    text = fixture_path("capital_00981A.html").read_text(encoding="utf-8")
    meta = parse_president_meta(text)

    # Canonical fields — all expected to be present for 統一's source
    assert "as_of_date" in meta and meta["as_of_date"], "EditDate should be captured"
    assert isinstance(meta.get("nav_total"), float) and meta["nav_total"] > 0
    assert isinstance(meta.get("units_outstanding"), float) and meta["units_outstanding"] > 0
    assert isinstance(meta.get("p_unit"), float) and 0 < meta["p_unit"] < 100

    # asset_breakdown should include 股票 (always present) but NOT NAV/OUT_UNIT/P_UNIT
    bd = meta.get("asset_breakdown") or {}
    assert "股票" in bd
    assert bd["股票"]["value"] > 0
    assert "pct" in bd["股票"]
    # ETF totals should not appear as breakdown categories
    assert all(name not in bd for name in ("淨資產", "流通在外單位數", "每單位淨值"))


def test_parse_president_meta_missing_dataasset_returns_empty():
    """No DataAsset block → graceful empty meta (don't break the holdings parse)."""
    assert parse_president_meta("<html><body>nothing here</body></html>") == {}
