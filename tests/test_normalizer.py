from scrapers.base import Holding
from normalizer import build_payload


def test_build_payload_aggregates_cross_holdings():
    scraped = {
        "0050":   [Holding("2330", "台積電", 48.5, 100_000_000),
                   Holding("2454", "聯發科", 3.8, 2_000_000)],
        "00980A": [Holding("2330", "台積電", 32.1, 5_000_000),
                   Holding("2454", "聯發科", 6.2, 200_000)],
    }
    etfs_config = {
        "0050":   {"scraper": "yuanta", "name": "元大台灣50",
                   "type": "passive", "tags": ["市值型"], "color": "#4a9eff"},
        "00980A": {"scraper": "nomura", "name": "野村臺灣智慧優選",
                   "type": "active", "tags": ["主動"], "color": "#34d399"},
    }
    stocks_config = {
        "2330": {"name": "台積電", "industry": "半導體"},
        "2454": {"name": "聯發科", "industry": "半導體"},
    }

    payload = build_payload(scraped, etfs_config, stocks_config)

    # ETF block
    assert len(payload["etfs"]) == 2
    etf_tickers = {e["ticker"] for e in payload["etfs"]}
    assert etf_tickers == {"0050", "00980A"}
    e0050 = next(e for e in payload["etfs"] if e["ticker"] == "0050")
    assert e0050["name"] == "元大台灣50"
    assert e0050["type"] == "passive"
    assert e0050["holdings_count"] == 2

    # Holdings block — cross-holding aggregation
    assert len(payload["holdings"]) == 2
    tsmc = next(h for h in payload["holdings"] if h["stock_id"] == "2330")
    assert tsmc["stock_name"] == "台積電"
    assert tsmc["industry"] == "半導體"
    assert len(tsmc["held_by"]) == 2
    held_by_etfs = {b["etf"] for b in tsmc["held_by"]}
    assert held_by_etfs == {"0050", "00980A"}


def test_build_payload_sorts_holdings_by_held_count():
    """Stocks held by more ETFs should come first."""
    scraped = {
        "0050":   [Holding("2330", "台積電", 48.5, 100),
                   Holding("2317", "鴻海", 4.0, 200)],
        "00980A": [Holding("2330", "台積電", 32.0, 50)],
    }
    etfs_config = {
        "0050":   {"scraper": "yuanta", "name": "A", "type": "passive", "tags": [], "color": "#000"},
        "00980A": {"scraper": "nomura", "name": "B", "type": "active",  "tags": [], "color": "#000"},
    }
    stocks_config = {}

    payload = build_payload(scraped, etfs_config, stocks_config)
    # 台積電 (held by 2) should come before 鴻海 (held by 1)
    assert payload["holdings"][0]["stock_id"] == "2330"
    assert payload["holdings"][1]["stock_id"] == "2317"


def test_build_payload_uses_override_when_provided():
    scraped = {"0050": [Holding("2330", "台積電", 48.5, 100)]}
    etfs_config = {"0050": {"scraper": "yuanta", "name": "A", "type": "passive", "tags": [], "color": "#000"}}
    payload = build_payload(scraped, etfs_config, {}, updated_at_override="2025-12-01T12:00:00+08:00")
    assert payload["updated_at"] == "2025-12-01T12:00:00+08:00"
