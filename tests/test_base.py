from scrapers.base import Holding, classify_market


def test_holding_stores_fields():
    h = Holding(stock_id="2330", stock_name="台積電", weight_pct=48.5, shares=100_000_000, market="TW")
    assert h.stock_id == "2330"
    assert h.stock_name == "台積電"
    assert h.weight_pct == 48.5
    assert h.shares == 100_000_000
    assert h.market == "TW"


def test_holding_equality():
    a = Holding(stock_id="2330", stock_name="台積電", weight_pct=48.5, shares=100, market="TW")
    b = Holding(stock_id="2330", stock_name="台積電", weight_pct=48.5, shares=100, market="TW")
    assert a == b


def test_classify_market():
    # 4-digit pure number → TW
    assert classify_market("2330") == "TW"
    assert classify_market("0050") == "TW"
    # " US" / " JP" suffix → foreign exchange
    assert classify_market("LITE US") == "US"
    assert classify_market("MU US") == "US"
    assert classify_market("285A JP") == "JP"
    assert classify_market("5706 JP") == "JP"
    # ETF tickers, futures contracts, anything non-conforming → OTHER
    assert classify_market("00981A") == "OTHER"
    assert classify_market("TXFD6") == "OTHER"
    assert classify_market("") == "OTHER"
