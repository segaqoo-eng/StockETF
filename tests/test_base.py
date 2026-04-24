from scrapers.base import Holding

def test_holding_stores_fields():
    h = Holding(stock_id="2330", stock_name="台積電", weight_pct=48.5, shares=100_000_000)
    assert h.stock_id == "2330"
    assert h.stock_name == "台積電"
    assert h.weight_pct == 48.5
    assert h.shares == 100_000_000

def test_holding_equality():
    a = Holding(stock_id="2330", stock_name="台積電", weight_pct=48.5, shares=100)
    b = Holding(stock_id="2330", stock_name="台積電", weight_pct=48.5, shares=100)
    assert a == b
