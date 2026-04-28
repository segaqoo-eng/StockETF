from scrapers.twse_prices import PricesFetcher
from unittest.mock import patch
from datetime import date

TWSE_STUB = '''{
  "stat": "OK",
  "tables": [{
    "title": "每日收盤行情",
    "fields": ["證券代號","收盤價","漲跌(+/-)","漲跌價差"],
    "data": [["2330","550.00","<p style=\\"color:red\\">+</p>","19.50"]]
  }]
}'''

TPEX_STUB = '''{
  "stat": "ok",
  "tables": [{
    "title": "上櫃股票行情",
    "fields": ["代號","收盤","漲跌"],
    "data": [["3037","85.00","-1.20"]]
  }]
}'''

def test_fetch_all_tags_twse_exchange():
    fetcher = PricesFetcher()
    with patch.object(fetcher, "get", side_effect=[TWSE_STUB, TPEX_STUB]):
        result = fetcher.fetch_all(date(2026, 4, 27))
    assert result["2330"]["exchange"] == "TWSE"

def test_fetch_all_tags_tpex_exchange():
    fetcher = PricesFetcher()
    with patch.object(fetcher, "get", side_effect=[TWSE_STUB, TPEX_STUB]):
        result = fetcher.fetch_all(date(2026, 4, 27))
    assert result["3037"]["exchange"] == "TPEX"

def test_twse_takes_priority_over_tpex():
    fetcher = PricesFetcher()
    tpex_with_2330 = TPEX_STUB.replace('"3037"', '"2330"')
    with patch.object(fetcher, "get", side_effect=[TWSE_STUB, tpex_with_2330]):
        result = fetcher.fetch_all(date(2026, 4, 27))
    assert result["2330"]["exchange"] == "TWSE"
