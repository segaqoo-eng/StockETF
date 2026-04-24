"""Capital / 統一投信 (Uni-President Asset Management) holdings scraper.

Supports: 00981A (統一台股增長 active ETF).
Data source: HTML page with holdings embedded in a `data-content` attribute
             on a <div id="DataAsset"> element as a JSON array. The stock
             holdings entry has AssetCode="ST" and a Details list; each entry
             has fields DetailCode, DetailName, Share, NavRate.
Source URL: https://www.ezmoney.com.tw/ETF/Fund/Info?FundCode=49YTW
"""

import html as html_module
import json
import re

from scrapers.base import BaseScraper, Holding

# The ezmoney.com.tw server sets a session cookie on first hit and redirects
# to the same URL; the second request (with cookie) returns the full page.
HOLDINGS_URL = "https://www.ezmoney.com.tw/ETF/Fund/Info?FundCode=49YTW"

# Regex to locate the DataAsset embedded JSON block
_DATA_ASSET_RE = re.compile(r'id="DataAsset"\s+data-content="([^"]+)"')

# AssetCode for stock holdings
_STOCK_ASSET_CODE = "ST"


def parse_capital_holdings(text: str) -> list[Holding]:
    """Parse 統一投信 holdings data embedded in the ezmoney.com.tw fund page.

    The page embeds holdings as a JSON array in the data-content attribute of
    <div id="DataAsset">. The entry with AssetCode="ST" contains a Details list
    of individual stock holdings.

    Fail loudly on structure changes.
    """
    m = _DATA_ASSET_RE.search(text)
    if not m:
        raise ValueError(
            "Capital parser: <div id='DataAsset'> not found — "
            "page structure may have changed"
        )

    try:
        raw_json = html_module.unescape(m.group(1))
        asset_array = json.loads(raw_json)
    except (json.JSONDecodeError, Exception) as exc:
        raise ValueError(
            "Capital parser: DataAsset content is not valid JSON — "
            "page structure may have changed"
        ) from exc

    if not isinstance(asset_array, list):
        raise ValueError(
            "Capital parser: DataAsset JSON is not a list — "
            "page structure may have changed"
        )

    # Find the stock holdings entry
    stock_entry = None
    for entry in asset_array:
        if entry.get("AssetCode") == _STOCK_ASSET_CODE:
            stock_entry = entry
            break

    if stock_entry is None:
        raise ValueError(
            f"Capital parser: no entry with AssetCode='{_STOCK_ASSET_CODE}' found — "
            "page structure may have changed"
        )

    details = stock_entry.get("Details")
    if not isinstance(details, list):
        raise ValueError(
            "Capital parser: stock entry has no Details list — "
            "page structure may have changed"
        )

    holdings: list[Holding] = []
    for row in details:
        stock_id = str(row.get("DetailCode", "")).strip()
        stock_name = str(row.get("DetailName", "")).strip()

        if not stock_id or not stock_name:
            raise ValueError(
                f"Capital parser: missing DetailCode or DetailName in row {row!r} — "
                "page structure may have changed"
            )

        raw_shares = row.get("Share")
        try:
            shares = int(float(str(raw_shares).replace(",", "")))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Capital parser: cannot parse Share '{raw_shares}' "
                f"for {stock_id} — page structure may have changed"
            ) from exc

        raw_weight = row.get("NavRate")
        try:
            weight_pct = float(str(raw_weight).replace(",", ""))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Capital parser: cannot parse NavRate '{raw_weight}' "
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
            "Capital parser: no stock holdings extracted — "
            "page structure may have changed or no entries in Details"
        )

    return holdings


class CapitalScraper(BaseScraper):
    """Scraper for 統一投信 ETF holdings (00981A).

    The ezmoney.com.tw server requires a valid session cookie; BaseScraper's
    requests.Session() naturally persists cookies across calls, so the first
    GET sets the cookie and the retry loop's next attempt returns the full page.
    However, since the server returns HTTP 302 on the first cookieless request
    and then 200 on the cookie-bearing one, we use allow_redirects=True (the
    default in requests) and let the session handle it.
    """

    def fetch(self, ticker: str) -> list[Holding]:
        # URL is fixed for 00981A; ticker param kept for interface consistency
        text = self.get(HOLDINGS_URL)
        return parse_capital_holdings(text)
