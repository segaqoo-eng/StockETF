"""Capital / 群益投信 (Capital Investment Trust) holdings scraper.

Supports: 00982A (主動群益台灣強棒), 00992A (主動群益科技創新).
Data source: SSR HTML on /etf/product/detail/{internal_id}/portfolio.

Known limitation: only top-10 holdings are exposed in SSR HTML; the full list
lives behind an internal-network API. See docs/known-issues/capital-scraper.md.
"""
from __future__ import annotations
import logging

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Holding, classify_market

logger = logging.getLogger(__name__)

PORTFOLIO_URL = "https://www.capitalfund.com.tw/etf/product/detail/{id}/portfolio"

# Stable ticker → internal product detail id (extracted from main.js routes)
_TICKER_TO_ID = {
    "00982A": 399,
    "00992A": 500,
}


def parse_capital_holdings(text: str) -> list[Holding]:
    """Parse top-10 holdings from a Capital ETF portfolio page (Angular SSR).

    Each holding row is rendered as:
        <div class="tr show-for-medium">
          <div class="th"> {stock_id} </div>
          <div class="th"> {stock_name} </div>
          <div class="td"> {weight}% </div>
          <div class="td sm-full"> {shares with commas} </div>
        </div>

    Fail loudly if the structure no longer matches.
    """
    soup = BeautifulSoup(text, "html.parser")
    rows = soup.find_all(
        "div",
        class_=lambda c: c and "tr" in c.split() and "show-for-medium" in c.split(),
    )
    if not rows:
        raise ValueError(
            "Capital parser: no rows with class 'tr show-for-medium' found — "
            "page structure may have changed"
        )

    holdings: list[Holding] = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all("div", recursive=False)]
        if len(cells) != 4:
            raise ValueError(
                f"Capital parser: expected 4 cells per row, got {len(cells)}: {cells!r} — "
                "page structure may have changed"
            )
        stock_id, stock_name, weight_str, shares_str = cells
        if not stock_id or not stock_name:
            raise ValueError(
                f"Capital parser: empty stock_id or name in row {cells!r} — "
                "page structure may have changed"
            )

        try:
            weight_pct = float(weight_str.rstrip("%"))
        except ValueError as exc:
            raise ValueError(
                f"Capital parser: cannot parse weight {weight_str!r} for {stock_id} — "
                "page structure may have changed"
            ) from exc

        try:
            shares = int(shares_str.replace(",", ""))
        except ValueError as exc:
            raise ValueError(
                f"Capital parser: cannot parse shares {shares_str!r} for {stock_id} — "
                "page structure may have changed"
            ) from exc

        holdings.append(
            Holding(
                stock_id=stock_id,
                stock_name=stock_name,
                weight_pct=weight_pct,
                shares=shares,
                market=classify_market(stock_id),
            )
        )

    return holdings


class CapitalScraper(BaseScraper):
    """Scraper for 群益投信 active ETFs (00982A, 00992A).

    SSR top-10 only — see docs/known-issues/capital-scraper.md for the
    rationale and future-improvement options.
    """

    def fetch(self, ticker: str) -> list[Holding]:
        if ticker not in _TICKER_TO_ID:
            raise ValueError(
                f"CapitalScraper supports {sorted(_TICKER_TO_ID)}, got {ticker!r}"
            )
        logger.warning(
            "capital: top-10 only, see docs/known-issues/capital-scraper.md"
        )
        url = PORTFOLIO_URL.format(id=_TICKER_TO_ID[ticker])
        text = self.get(url)
        return parse_capital_holdings(text)
