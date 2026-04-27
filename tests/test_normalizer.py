from scrapers.base import Holding
from normalizer import build_payload


def test_build_payload_aggregates_cross_holdings():
    scraped = {
        "0050":   [Holding("2330", "台積電", 48.5, 100_000_000, "TW"),
                   Holding("2454", "聯發科", 3.8, 2_000_000, "TW")],
        "00980A": [Holding("2330", "台積電", 32.1, 5_000_000, "TW"),
                   Holding("2454", "聯發科", 6.2, 200_000, "TW")],
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

    # ETF block — full per-ETF holdings list now embedded for frontend expansion
    assert len(payload["etfs"]) == 2
    etf_tickers = {e["ticker"] for e in payload["etfs"]}
    assert etf_tickers == {"0050", "00980A"}
    e0050 = next(e for e in payload["etfs"] if e["ticker"] == "0050")
    assert e0050["name"] == "元大台灣50"
    assert e0050["type"] == "passive"
    assert e0050["holdings_count"] == 2
    assert len(e0050["holdings"]) == 2
    assert e0050["holdings"][0]["market"] == "TW"

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
        "0050":   [Holding("2330", "台積電", 48.5, 100, "TW"),
                   Holding("2317", "鴻海", 4.0, 200, "TW")],
        "00980A": [Holding("2330", "台積電", 32.0, 50, "TW")],
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
    scraped = {"0050": [Holding("2330", "台積電", 48.5, 100, "TW")]}
    etfs_config = {"0050": {"scraper": "yuanta", "name": "A", "type": "passive", "tags": [], "color": "#000"}}
    payload = build_payload(scraped, etfs_config, {}, updated_at_override="2025-12-01T12:00:00+08:00")
    assert payload["updated_at"] == "2025-12-01T12:00:00+08:00"


def test_build_payload_includes_fund_meta_when_present():
    """fund_meta_by_ticker entries flow into etfs[i].fund_meta; missing/empty → no key."""
    scraped = {
        "0050":   [Holding("2330", "台積電", 48.5, 100, "TW")],
        "00981A": [Holding("2330", "台積電", 32.0, 50, "TW")],
    }
    etfs_config = {
        "0050":   {"scraper": "yuanta", "name": "A", "type": "passive", "tags": [], "color": "#000"},
        "00981A": {"scraper": "president", "name": "B", "type": "active", "tags": [], "color": "#000"},
    }
    fund_meta = {
        "00981A": {"as_of_date": "2026-04-27T15:33:01", "nav_total": 232148514804.0, "p_unit": 27.74},
        # 0050 has no entry → expect no fund_meta key on its etf block
    }

    payload = build_payload(scraped, etfs_config, {}, fund_meta_by_ticker=fund_meta)

    e981 = next(e for e in payload["etfs"] if e["ticker"] == "00981A")
    assert "fund_meta" in e981
    assert e981["fund_meta"]["nav_total"] == 232148514804.0
    assert e981["fund_meta"]["p_unit"] == 27.74

    e0050 = next(e for e in payload["etfs"] if e["ticker"] == "0050")
    assert "fund_meta" not in e0050, "missing entry should leave fund_meta off entirely"


def test_build_payload_excludes_foreign_from_cross_table():
    """Foreign stocks (US/JP) and OTHER must not appear in payload.holdings,
    but should remain in per-ETF holdings."""
    scraped = {
        "0050":   [Holding("2330", "台積電", 48.5, 100, "TW")],
        "00990A": [
            Holding("2330", "台積電", 3.42, 433_000, "TW"),         # cross-counted
            Holding("LITE US", "LUMENTUM HOLDINGS INC", 7.21, 70_985, "US"),   # excluded from cross-table
            Holding("285A JP", "KIOXIA HOLDINGS CORP", 2.73, 102_900, "JP"),   # excluded
        ],
    }
    etfs_config = {
        "0050":   {"scraper": "yuanta", "name": "A", "type": "passive", "tags": [], "color": "#000"},
        "00990A": {"scraper": "yuanta", "name": "B", "type": "active",  "tags": [], "color": "#000"},
    }

    payload = build_payload(scraped, etfs_config, {})

    # Cross-table: 台積電 only (the one TW stock held by both)
    cross_ids = {h["stock_id"] for h in payload["holdings"]}
    assert cross_ids == {"2330"}, f"foreign stocks leaked into cross-table: {cross_ids}"
    tsmc = payload["holdings"][0]
    assert {b["etf"] for b in tsmc["held_by"]} == {"0050", "00990A"}

    # Per-ETF holdings: 00990A still has all 3 (TW + US + JP)
    e990 = next(e for e in payload["etfs"] if e["ticker"] == "00990A")
    assert e990["holdings_count"] == 3
    markets = {h["market"] for h in e990["holdings"]}
    assert markets == {"TW", "US", "JP"}
