"""Base types and HTTP helpers for scrapers."""
from dataclasses import dataclass
import time
import requests

USER_AGENT = "StockETF-Bot/1.0 (+https://github.com/your-user/StockETF)"
REQUEST_TIMEOUT = 20
RETRY_BACKOFF = (2, 4, 8)  # seconds between retries


@dataclass(frozen=True)
class Holding:
    stock_id: str
    stock_name: str
    weight_pct: float
    shares: int


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

    def fetch(self, ticker: str) -> list[Holding]:
        raise NotImplementedError
