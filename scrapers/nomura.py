"""Nomura (野村投信) holdings scraper.

Supports: 00980A (野村臺灣智慧優選, first Taiwan active ETF, daily disclosure).
Data source: JSON endpoint — POST /API/ETFAPI/api/Fund/GetFundAssets
             with body {"FundID": "00980A", "SearchDate": "YYYY-MM-DD"}.

The response contains a Table array with (at least) two entries:
  - "股票" (stocks): columns [stock_id, stock_name, shares, weight_pct]
  - "期貨" (futures): columns [contract_id, contract_name, contracts, weight_pct]

Both are included in the returned holdings list. The third table (無標題/unnamed)
contains cash/liability line items and is intentionally excluded.
"""

import json
from datetime import date

from scrapers.base import BaseScraper, Holding

HOLDINGS_URL = "https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets"

# Column indices for the stock table (TableTitle == "股票")
_STOCK_ID_COL = 0
_STOCK_NAME_COL = 1
_STOCK_SHARES_COL = 2
_STOCK_WEIGHT_COL = 3

# Column indices for the futures table (TableTitle == "期貨")
_FUT_ID_COL = 0
_FUT_NAME_COL = 1
_FUT_CONTRACTS_COL = 2
_FUT_WEIGHT_COL = 3

# Tables to include (match on TableTitle)
_INCLUDED_TABLES = {"股票", "期貨"}


def parse_nomura_holdings(text: str) -> list[Holding]:
    """Parse Nomura ETF holdings from the raw JSON API response.

    Accepts the JSON text returned by POST /API/ETFAPI/api/Fund/GetFundAssets.
    Returns a list of Holding objects: stocks first (sorted by weight desc,
    as returned by the API), then futures.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Nomura parser: response is not valid JSON — "
            "page structure may have changed"
        ) from exc

    status = data.get("StatusCode")
    if status != 0:
        raise ValueError(
            f"Nomura API returned StatusCode={status} (expected 0) — "
            "fund may be unavailable or page structure may have changed"
        )

    try:
        tables = data["Entries"]["Data"]["Table"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "Nomura parser: expected path Entries.Data.Table not found — "
            "page structure may have changed"
        ) from exc

    if not isinstance(tables, list):
        raise ValueError(
            "Nomura parser: Table is not a list — page structure may have changed"
        )

    holdings: list[Holding] = []

    for table in tables:
        title = table.get("TableTitle", "")
        if title not in _INCLUDED_TABLES:
            # Skip the unnamed cash/liability summary table
            continue

        rows = table.get("Rows", [])
        for row in rows:
            if len(row) < 4:
                raise ValueError(
                    f"Nomura parser: row in table '{title}' has {len(row)} columns, "
                    "expected at least 4 — page structure may have changed"
                )
            stock_id = str(row[_STOCK_ID_COL]).strip()
            stock_name = str(row[_STOCK_NAME_COL]).strip()

            try:
                shares = int(str(row[_STOCK_SHARES_COL]).replace(",", ""))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Nomura parser: cannot parse shares '{row[_STOCK_SHARES_COL]}' "
                    f"for {stock_id} — page structure may have changed"
                ) from exc

            try:
                weight_pct = float(str(row[_STOCK_WEIGHT_COL]).replace(",", ""))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Nomura parser: cannot parse weight '{row[_STOCK_WEIGHT_COL]}' "
                    f"for {stock_id} — page structure may have changed"
                ) from exc

            holdings.append(
                Holding(
                    stock_id=stock_id,
                    stock_name=stock_name,
                    weight_pct=weight_pct,
                    shares=shares,
                )
            )

    if not holdings:
        raise ValueError(
            "Nomura parser: no holdings extracted from response — "
            "page structure may have changed"
        )

    return holdings


class NomuraScraper(BaseScraper):
    """Scraper for Nomura ETF holdings (00980A)."""

    def fetch(self, ticker: str) -> list[Holding]:
        today = date.today().strftime("%Y-%m-%d")
        payload = {"FundID": ticker, "SearchDate": today}
        text = self.post(HOLDINGS_URL, json=payload)
        return parse_nomura_holdings(text)
