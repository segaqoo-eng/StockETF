"""Base types and HTTP helpers for scrapers."""
from dataclasses import dataclass
import time
import requests

USER_AGENT = "StockETF-Bot/1.0 (+https://github.com/your-user/StockETF)"
REQUEST_TIMEOUT = 20
RETRY_BACKOFF = (2, 4, 8)  # seconds between retries


def classify_market(stock_id: str) -> str:
    """Classify a holding's market by stock_id format.

    Per spec: 4-digit numeric → "TW"; suffixed " US" → "US"; suffixed " JP" → "JP";
    everything else (futures contracts, bonds, foreign stocks on other exchanges,
    Taiwan emerging-market 5-digit codes, etc.) → "OTHER".

    The cross-holding aggregation in normalizer treats only "TW" as cross-comparable;
    "OTHER" stocks still appear in per-ETF holdings but not in the main cross-table.
    """
    s = stock_id.strip()
    if s.endswith(" US"):
        return "US"
    if s.endswith(" JP"):
        return "JP"
    if s.isdigit() and len(s) == 4:
        return "TW"
    return "OTHER"


@dataclass(frozen=True)
class Holding:
    stock_id: str
    stock_name: str
    weight_pct: float
    shares: int
    market: str  # "TW" | "US" | "JP" | "OTHER"; use classify_market(stock_id)


class BaseScraper:
    """HTTP session with retry. Subclasses implement fetch(ticker)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get(self, url: str) -> str:
        """GET with 3 retries and exponential backoff. Returns response text."""
        last_err = None
        for delay in (0, *RETRY_BACKOFF):
            if delay:
                time.sleep(delay)
            try:
                r = self.session.get(url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                return r.text
            except requests.RequestException as exc:
                last_err = exc
        raise RuntimeError(f"GET {url} failed after retries: {last_err}")

    def post(self, url: str, json: dict | None = None) -> str:
        """POST with 3 retries and exponential backoff. Returns response text."""
        last_err = None
        for delay in (0, *RETRY_BACKOFF):
            if delay:
                time.sleep(delay)
            try:
                r = self.session.post(url, json=json, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                return r.text
            except requests.RequestException as exc:
                last_err = exc
        raise RuntimeError(f"POST {url} failed after retries: {last_err}")

    def get_bytes(self, url: str) -> bytes:
        """GET with 3 retries and exponential backoff. Returns response body bytes.

        For binary payloads (xlsx, pdf, images) where decoding to text is wrong.
        """
        last_err = None
        for delay in (0, *RETRY_BACKOFF):
            if delay:
                time.sleep(delay)
            try:
                r = self.session.get(url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                return r.content
            except requests.RequestException as exc:
                last_err = exc
        raise RuntimeError(f"GET {url} failed after retries: {last_err}")

    def fetch(self, ticker: str) -> list[Holding]:
        raise NotImplementedError
