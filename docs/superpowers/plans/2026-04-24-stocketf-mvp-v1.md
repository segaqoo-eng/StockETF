# StockETF MVP v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manually-runnable Python scraper + static HTML frontend that shows a cross-holding table for 4 Taiwan ETFs (0050, 0056, 00980A, 00981A), deployable to GitHub Pages.

**Architecture:** Three-layer separation. Python scrapers fetch per-issuer holdings → normalizer merges them with a YAML config into `data/latest.json` → static HTML/CSS/JS frontend fetches the JSON and renders a filterable, expandable table. No backend, no database. `python main.py` runs end-to-end.

**Tech Stack:** Python 3.12, requests, beautifulsoup4, pyyaml, pytest. Frontend: vanilla HTML + CSS + ES6 JavaScript. Deployment: GitHub Pages (manual commit for v1).

---

## File Structure

```
StockETF/
├── index.html                    # Frontend entry
├── assets/
│   ├── style.css                 # Visual style (dark theme)
│   └── app.js                    # Fetch + render + filter logic
├── config/
│   ├── etfs.yml                  # ETF metadata (ticker, scraper, tags, color)
│   └── stocks.yml                # Stock industry mapping
├── scrapers/
│   ├── __init__.py
│   ├── base.py                   # BaseScraper: HTTP session, retry
│   ├── yuanta.py                 # 0050, 0056
│   ├── nomura.py                 # 00980A
│   └── capital.py                # 00981A
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixture path helper
│   ├── fixtures/                 # Saved HTML samples
│   ├── test_base.py
│   ├── test_yuanta.py
│   ├── test_nomura.py
│   ├── test_capital.py
│   └── test_normalizer.py
├── data/
│   ├── latest.json               # Generated
│   └── snapshots/.gitkeep
├── normalizer.py                 # Merge scraper outputs + config → JSON
├── main.py                       # Orchestrator
├── requirements.txt
└── README.md
```

**Boundaries:**
- `scrapers/*.py` know only how to fetch one issuer's HTML and parse to `list[Holding]`. They do not know about config, JSON layout, or other ETFs.
- `normalizer.py` knows about the config format and the output JSON shape. It does not fetch anything.
- `main.py` orchestrates: loops configured ETFs, calls the right scraper, passes results to normalizer. Handles per-ETF failure (uses previous data for failed ETFs).
- `assets/app.js` knows only about the shape of `latest.json`. It does not care how the JSON was produced.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `README.md`
- Create: `data/snapshots/.gitkeep`
- Create: `config/etfs.yml`
- Create: `config/stocks.yml`
- Create: `scrapers/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.32.3
beautifulsoup4==4.12.3
pyyaml==6.0.2
pytest==8.3.3
```

- [ ] **Step 2: Create `README.md`**

```markdown
# StockETF

台灣 ETF 交叉持股分析工具（v1 MVP）。

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

Then open `index.html` in a browser.

## Deployment

Push to GitHub; enable GitHub Pages (Settings → Pages → Source: main / root).
Data is refreshed manually by running `python main.py` and committing `data/`.

## 免責聲明

本網站資訊僅供參考，不構成投資建議。
```

- [ ] **Step 3: Create `data/snapshots/.gitkeep`** (empty file to commit empty dir)

- [ ] **Step 4: Create `config/etfs.yml`**

```yaml
"0050":
  scraper: yuanta
  name: 元大台灣50
  type: passive
  tags: [市值型]
  color: "#4a9eff"

"0056":
  scraper: yuanta
  name: 元大高股息
  type: passive
  tags: [高股息型]
  color: "#4adfb8"

"00980A":
  scraper: nomura
  name: 野村臺灣智慧優選
  type: active
  tags: [主動, 台股型]
  color: "#34d399"

"00981A":
  scraper: capital
  name: 統一台股增長
  type: active
  tags: [主動, 台股型]
  color: "#f472b6"
```

- [ ] **Step 5: Create `config/stocks.yml`** (seed set, extend as needed when scrapers return unknown stocks)

```yaml
"2330": { name: 台積電, industry: 半導體 }
"2317": { name: 鴻海,   industry: 電子 }
"2454": { name: 聯發科, industry: 半導體 }
"2382": { name: 廣達,   industry: 電腦及週邊設備 }
"2303": { name: 聯電,   industry: 半導體 }
"2308": { name: 台達電, industry: 電子零組件 }
"2881": { name: 富邦金, industry: 金融保險 }
"2882": { name: 國泰金, industry: 金融保險 }
```

- [ ] **Step 6: Create empty package markers**

`scrapers/__init__.py` — empty file
`tests/__init__.py` — empty file

- [ ] **Step 7: Commit**

```bash
git add requirements.txt README.md data/snapshots/.gitkeep config/ scrapers/__init__.py tests/__init__.py
git commit -m "scaffold: add project skeleton, config, readme"
```

---

### Task 2: Holding dataclass + BaseScraper

**Files:**
- Create: `scrapers/base.py`
- Create: `tests/test_base.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixture_path():
    def _resolve(name: str) -> Path:
        return FIXTURES / name
    return _resolve
```

- [ ] **Step 2: Write failing test for `Holding` dataclass**

Create `tests/test_base.py`:

```python
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
```

- [ ] **Step 3: Run test, confirm it fails**

```bash
pytest tests/test_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'scrapers.base'`

- [ ] **Step 4: Create `scrapers/base.py` with `Holding` dataclass**

```python
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

    def fetch(self, ticker: str) -> list[Holding]:
        raise NotImplementedError
```

- [ ] **Step 5: Run test, confirm it passes**

```bash
pytest tests/test_base.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add scrapers/base.py tests/conftest.py tests/test_base.py
git commit -m "feat(scrapers): add Holding dataclass and BaseScraper"
```

---

### Task 3: Yuanta scraper (0050, 0056)

**Files:**
- Create: `tests/fixtures/yuanta_0050.html`
- Create: `tests/fixtures/yuanta_0056.html`
- Create: `scrapers/yuanta.py`
- Create: `tests/test_yuanta.py`

**Note:** The HTML structure on the issuer site can change at any time. This task captures real HTML as a fixture first, then writes the parser against that fixture. If the live site's structure differs from what the sample selectors below expect, adjust the CSS selectors in the parser — the test will tell you if parsing is correct.

- [ ] **Step 1: Capture live HTML fixture for 0050**

The Yuanta holdings page URL pattern is `https://www.yuantaetfs.com/product/detail/<ticker>/ratio`. Verify in a browser first, then:

```bash
curl -A "StockETF-Bot/1.0" -L "https://www.yuantaetfs.com/product/detail/0050/ratio" -o tests/fixtures/yuanta_0050.html
curl -A "StockETF-Bot/1.0" -L "https://www.yuantaetfs.com/product/detail/0056/ratio" -o tests/fixtures/yuanta_0056.html
```

Open `tests/fixtures/yuanta_0050.html` in a browser or editor. Find the holdings table. Note:
- The CSS selector path (e.g., `table.ratio-table tbody tr`)
- Column order (stock code, name, weight, shares)
- Total row count (should match 50 for 0050)

If the page loads data via JavaScript (empty HTML), the site needs a different approach — check for a JSON API endpoint in browser DevTools Network tab, capture that URL instead, and store the JSON as fixture. Document which approach applies in a comment at the top of `scrapers/yuanta.py`.

- [ ] **Step 2: Write failing test**

Create `tests/test_yuanta.py`:

```python
from scrapers.yuanta import parse_yuanta_holdings


def test_parse_yuanta_0050(fixture_path):
    html = fixture_path("yuanta_0050.html").read_text(encoding="utf-8")
    holdings = parse_yuanta_holdings(html)

    assert len(holdings) == 50, f"expected 50 holdings in 0050, got {len(holdings)}"

    # First holding should be 2330 台積電 with highest weight
    first = holdings[0]
    assert first.stock_id == "2330"
    assert "台積" in first.stock_name
    assert first.weight_pct > 40  # 0050's TSMC weight historically > 40%

    # All weights should be positive and sum < 101 (allow rounding)
    total = sum(h.weight_pct for h in holdings)
    assert 95 <= total <= 101, f"weight sum {total} out of range"


def test_parse_yuanta_0056(fixture_path):
    html = fixture_path("yuanta_0056.html").read_text(encoding="utf-8")
    holdings = parse_yuanta_holdings(html)

    assert len(holdings) >= 30  # 0056 has ~50 holdings
    # Each holding must have non-empty fields
    for h in holdings:
        assert h.stock_id and h.stock_name
        assert h.weight_pct > 0
```

- [ ] **Step 3: Run test, confirm it fails**

```bash
pytest tests/test_yuanta.py -v
```

Expected: `ModuleNotFoundError: No module named 'scrapers.yuanta'`

- [ ] **Step 4: Implement `scrapers/yuanta.py`**

Adjust the selectors below to match what you see in the fixture. The structure here is a template — if the site uses a JSON endpoint, change `parse_yuanta_holdings` to parse JSON instead.

```python
"""Yuanta (元大投信) holdings scraper.

Supports passive ETFs listed on yuantaetfs.com.
Currently handles: 0050, 0056.
"""
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, Holding

HOLDINGS_URL = "https://www.yuantaetfs.com/product/detail/{ticker}/ratio"


def parse_yuanta_holdings(html: str) -> list[Holding]:
    """Parse Yuanta holdings table from HTML into a list of Holdings.

    Adjust selectors below to match the real page structure.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tbody tr")  # ADJUST: real selector from fixture

    holdings = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 4:
            continue
        # ADJUST column indices to real layout: [code, name, weight, shares, ...]
        stock_id = cols[0]
        name = cols[1]
        try:
            weight_pct = float(cols[2].replace("%", "").replace(",", ""))
            shares = int(cols[3].replace(",", ""))
        except ValueError:
            continue
        holdings.append(Holding(stock_id, name, weight_pct, shares))
    return holdings


class YuantaScraper(BaseScraper):
    def fetch(self, ticker: str) -> list[Holding]:
        html = self.get(HOLDINGS_URL.format(ticker=ticker))
        return parse_yuanta_holdings(html)
```

- [ ] **Step 5: Run test, iterate on selectors until it passes**

```bash
pytest tests/test_yuanta.py -v
```

If failing: open `tests/fixtures/yuanta_0050.html`, confirm the real table structure, and adjust `parse_yuanta_holdings`. The test assertions (50 rows, 2330 first, weight sum ~100) encode the ground truth — don't weaken them to pass.

- [ ] **Step 6: Commit**

```bash
git add scrapers/yuanta.py tests/test_yuanta.py tests/fixtures/yuanta_0050.html tests/fixtures/yuanta_0056.html
git commit -m "feat(scrapers): add Yuanta scraper for 0050/0056"
```

---

### Task 4: Nomura scraper (00980A)

**Files:**
- Create: `tests/fixtures/nomura_00980A.html`
- Create: `scrapers/nomura.py`
- Create: `tests/test_nomura.py`

**Note:** 00980A is Taiwan's first active ETF and discloses holdings daily. The issuer page is `https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A&tab=Shareholding`. Same caveats as Task 3 — capture fixture first, adjust selectors if needed.

- [ ] **Step 1: Capture fixture**

```bash
curl -A "StockETF-Bot/1.0" -L "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A&tab=Shareholding" -o tests/fixtures/nomura_00980A.html
```

Inspect the HTML. If holdings are loaded via JS/Ajax, find the XHR URL in DevTools and capture that instead (save as `nomura_00980A.json`).

- [ ] **Step 2: Write failing test**

Create `tests/test_nomura.py`:

```python
from scrapers.nomura import parse_nomura_holdings


def test_parse_nomura_00980A(fixture_path):
    html = fixture_path("nomura_00980A.html").read_text(encoding="utf-8")
    holdings = parse_nomura_holdings(html)

    assert 40 <= len(holdings) <= 80, f"expected 40-80 holdings, got {len(holdings)}"

    # Largest weight should be on a well-known semiconductor stock
    top = holdings[0]
    assert top.stock_id
    assert top.weight_pct > 0

    for h in holdings:
        assert h.stock_id.isdigit() or h.stock_id.isalnum()
        assert h.weight_pct >= 0
        assert h.shares >= 0
```

- [ ] **Step 3: Run test, confirm it fails**

```bash
pytest tests/test_nomura.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement `scrapers/nomura.py`**

```python
"""Nomura (野村投信) holdings scraper.

Supports: 00980A (first Taiwan active ETF, daily disclosure).
"""
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, Holding

HOLDINGS_URL = "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo={ticker}&tab=Shareholding"


def parse_nomura_holdings(html: str) -> list[Holding]:
    """Parse Nomura shareholding table. Adjust selectors to match real HTML."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.shareholding tbody tr")  # ADJUST to real selector

    holdings = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 4:
            continue
        # ADJUST column indices: likely [序號, 代號, 名稱, 股數, 權重]
        stock_id = cols[1]
        name = cols[2]
        try:
            shares = int(cols[3].replace(",", ""))
            weight_pct = float(cols[4].replace("%", "").replace(",", ""))
        except (ValueError, IndexError):
            continue
        holdings.append(Holding(stock_id, name, weight_pct, shares))
    return holdings


class NomuraScraper(BaseScraper):
    def fetch(self, ticker: str) -> list[Holding]:
        html = self.get(HOLDINGS_URL.format(ticker=ticker))
        return parse_nomura_holdings(html)
```

- [ ] **Step 5: Run test, iterate until passing**

```bash
pytest tests/test_nomura.py -v
```

- [ ] **Step 6: Commit**

```bash
git add scrapers/nomura.py tests/test_nomura.py tests/fixtures/nomura_00980A.html
git commit -m "feat(scrapers): add Nomura scraper for 00980A"
```

---

### Task 5: Capital scraper (00981A)

**Files:**
- Create: `tests/fixtures/capital_00981A.html`
- Create: `scrapers/capital.py`
- Create: `tests/test_capital.py`

**Note:** 統一投信 / Capital Investment Trust. Site URL to discover — search for "統一台股增長 00981A 持股". Capture fixture first. Apply the same test-first pattern.

- [ ] **Step 1: Discover and capture fixture**

Find the correct holdings URL by browsing https://www.capitalfund.com.tw/ (or the issuer's current domain) and navigating to 00981A's page.

```bash
# Replace URL below with the real one found via browser
curl -A "StockETF-Bot/1.0" -L "<REAL_URL>" -o tests/fixtures/capital_00981A.html
```

- [ ] **Step 2: Write failing test**

Create `tests/test_capital.py`:

```python
from scrapers.capital import parse_capital_holdings


def test_parse_capital_00981A(fixture_path):
    html = fixture_path("capital_00981A.html").read_text(encoding="utf-8")
    holdings = parse_capital_holdings(html)

    assert 30 <= len(holdings) <= 100
    for h in holdings:
        assert h.stock_id
        assert h.stock_name
        assert h.weight_pct >= 0
```

- [ ] **Step 3: Run test, confirm it fails**

```bash
pytest tests/test_capital.py -v
```

- [ ] **Step 4: Implement `scrapers/capital.py`**

```python
"""Capital (統一投信) holdings scraper.

Supports: 00981A (統一台股增長 active ETF).
"""
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, Holding

HOLDINGS_URL = "<REAL_URL_FROM_FIXTURE_STEP>"  # replace with URL used in fixture


def parse_capital_holdings(html: str) -> list[Holding]:
    """Parse Capital shareholding page. Adjust selectors to match real HTML."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tbody tr")  # ADJUST

    holdings = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 4:
            continue
        stock_id = cols[0]
        name = cols[1]
        try:
            weight_pct = float(cols[2].replace("%", "").replace(",", ""))
            shares = int(cols[3].replace(",", ""))
        except ValueError:
            continue
        holdings.append(Holding(stock_id, name, weight_pct, shares))
    return holdings


class CapitalScraper(BaseScraper):
    def fetch(self, ticker: str) -> list[Holding]:
        html = self.get(HOLDINGS_URL.format(ticker=ticker) if "{ticker}" in HOLDINGS_URL else HOLDINGS_URL)
        return parse_capital_holdings(html)
```

- [ ] **Step 5: Iterate until test passes**

```bash
pytest tests/test_capital.py -v
```

- [ ] **Step 6: Commit**

```bash
git add scrapers/capital.py tests/test_capital.py tests/fixtures/capital_00981A.html
git commit -m "feat(scrapers): add Capital scraper for 00981A"
```

---

### Task 6: Normalizer

**Files:**
- Create: `normalizer.py`
- Create: `tests/test_normalizer.py`

Responsibility: given a dict of `{ticker: list[Holding]}` plus the ETF config YAML plus the stocks config YAML, produce the final `data/latest.json` and a snapshot file.

- [ ] **Step 1: Write failing test for `build_payload`**

Create `tests/test_normalizer.py`:

```python
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
        "00980A": {"scraper": "nomura", "name": "野村智慧優選",
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
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/test_normalizer.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `normalizer.py`**

```python
"""Merge scraper outputs + config into the final JSON payload."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import yaml

from scrapers.base import Holding

TAIPEI = ZoneInfo("Asia/Taipei")


def load_config(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_payload(
    scraped: dict[str, list[Holding]],
    etfs_config: dict,
    stocks_config: dict,
) -> dict:
    """Combine per-ETF holdings, ETF metadata, and stock metadata into the
    shape described in the design spec §4.1.
    """
    now = datetime.now(TAIPEI).isoformat(timespec="seconds")

    etfs_block = []
    for ticker, holdings in scraped.items():
        meta = etfs_config.get(ticker, {})
        etfs_block.append({
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "type": meta.get("type", "passive"),
            "tags": meta.get("tags", []),
            "color": meta.get("color", "#58a6ff"),
            "holdings_count": len(holdings),
        })

    # held_by_map[stock_id] = list of {"etf": ticker, "weight_pct", "shares"}
    held_by_map: dict[str, list[dict]] = defaultdict(list)
    stock_names: dict[str, str] = {}
    for ticker, holdings in scraped.items():
        for h in holdings:
            held_by_map[h.stock_id].append({
                "etf": ticker,
                "weight_pct": h.weight_pct,
                "shares": h.shares,
            })
            stock_names.setdefault(h.stock_id, h.stock_name)

    holdings_block = []
    for stock_id, held_by in held_by_map.items():
        stock_meta = stocks_config.get(stock_id, {})
        holdings_block.append({
            "stock_id": stock_id,
            "stock_name": stock_meta.get("name") or stock_names.get(stock_id, stock_id),
            "industry": stock_meta.get("industry", ""),
            "held_by": sorted(held_by, key=lambda b: -b["weight_pct"]),
        })

    # Sort: most cross-held first, then by max weight
    holdings_block.sort(key=lambda h: (-len(h["held_by"]), -max(b["weight_pct"] for b in h["held_by"])))

    return {
        "updated_at": now,
        "etfs": sorted(etfs_block, key=lambda e: e["ticker"]),
        "holdings": holdings_block,
    }


def write_payload(payload: dict, data_dir: str | Path = "data") -> None:
    """Write latest.json and today's snapshot to data/."""
    data_dir = Path(data_dir)
    (data_dir / "snapshots").mkdir(parents=True, exist_ok=True)

    latest_path = data_dir / "latest.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    date = datetime.now(TAIPEI).date().isoformat()
    snapshot_path = data_dir / "snapshots" / f"{date}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/test_normalizer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add normalizer.py tests/test_normalizer.py
git commit -m "feat: add normalizer merging scraper outputs with config"
```

---

### Task 7: main.py orchestrator

**Files:**
- Create: `main.py`

Responsibility: wire scrapers + normalizer + config together. Must keep running if one scraper fails (per spec §5.4).

- [ ] **Step 1: Implement `main.py`**

```python
"""End-to-end: read config, invoke scrapers, write data/latest.json + snapshot.

Run: python main.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

from scrapers.base import BaseScraper, Holding
from scrapers.yuanta import YuantaScraper
from scrapers.nomura import NomuraScraper
from scrapers.capital import CapitalScraper
from normalizer import build_payload, write_payload, load_config

INTER_REQUEST_DELAY_SEC = 2  # be polite to issuer sites

SCRAPERS: dict[str, BaseScraper] = {
    "yuanta":  YuantaScraper(),
    "nomura":  NomuraScraper(),
    "capital": CapitalScraper(),
}


def load_previous_holdings(latest_path: Path) -> dict[str, list[Holding]]:
    """Recover each ETF's last-known holdings from the previous latest.json,
    so a failed scrape can fall back to stale-but-present data.
    """
    if not latest_path.exists():
        return {}
    prev = json.loads(latest_path.read_text(encoding="utf-8"))
    recovered: dict[str, list[Holding]] = {e["ticker"]: [] for e in prev.get("etfs", [])}
    for h in prev.get("holdings", []):
        for b in h["held_by"]:
            recovered.setdefault(b["etf"], []).append(Holding(
                stock_id=h["stock_id"],
                stock_name=h["stock_name"],
                weight_pct=b["weight_pct"],
                shares=b["shares"],
            ))
    return recovered


def main() -> int:
    etfs_config = load_config("config/etfs.yml")
    stocks_config = load_config("config/stocks.yml")
    previous = load_previous_holdings(Path("data/latest.json"))

    scraped: dict[str, list[Holding]] = {}
    failures: list[str] = []

    for i, (ticker, meta) in enumerate(etfs_config.items()):
        if i > 0:
            time.sleep(INTER_REQUEST_DELAY_SEC)
        scraper_name = meta["scraper"]
        scraper = SCRAPERS.get(scraper_name)
        if scraper is None:
            print(f"[SKIP] {ticker}: unknown scraper '{scraper_name}'", file=sys.stderr)
            continue
        try:
            print(f"[FETCH] {ticker} via {scraper_name}...")
            holdings = scraper.fetch(ticker)
            if not holdings:
                raise RuntimeError("empty holdings")
            scraped[ticker] = holdings
            print(f"  ok: {len(holdings)} holdings")
        except Exception as exc:
            failures.append(ticker)
            print(f"  FAIL: {exc}", file=sys.stderr)
            if ticker in previous and previous[ticker]:
                print(f"  using previous data ({len(previous[ticker])} holdings)")
                scraped[ticker] = previous[ticker]
            else:
                print(f"  no previous data — skipping {ticker}")

    if not scraped:
        print("ERROR: no ETF data at all", file=sys.stderr)
        return 1

    payload = build_payload(scraped, etfs_config, stocks_config)
    write_payload(payload)
    print(f"\nWrote data/latest.json ({len(payload['etfs'])} ETFs, {len(payload['holdings'])} unique stocks)")
    if failures:
        print(f"Failures: {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run end-to-end smoke test**

```bash
python main.py
```

Expected: terminal shows `[FETCH] 0050 via yuanta... ok: 50 holdings` (and similar for others), ends with `Wrote data/latest.json ...`.

If a scraper fails (e.g., site temporarily down), it should print `FAIL:` then continue to the next. The first run with no previous data will skip failing ETFs — that's expected behavior.

- [ ] **Step 3: Inspect generated `data/latest.json`**

Verify in a text editor:
- `updated_at` has today's date and +08:00 timezone
- `etfs` array has 4 entries (0050, 0056, 00980A, 00981A)
- `holdings` array is sorted with most cross-held stocks first
- Top holding's `held_by` array lists multiple ETFs with `weight_pct` values

- [ ] **Step 4: Commit**

```bash
git add main.py data/latest.json data/snapshots/
git commit -m "feat: add main orchestrator and initial data snapshot"
```

---

### Task 8: Frontend skeleton (HTML + CSS + fetch)

**Files:**
- Create: `index.html`
- Create: `assets/style.css`
- Create: `assets/app.js`

- [ ] **Step 1: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>StockETF — 台灣 ETF 交叉持股分析</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <header class="header">
    <h1>📊 Stock<span>ETF</span></h1>
    <div class="header-sub">台灣 ETF 交叉持股分析 · 更新於 <b id="updated-at">—</b></div>
  </header>

  <nav class="tab-nav">
    <button class="tab-btn active" data-tab="cross">交叉持股</button>
    <button class="tab-btn" data-tab="etfs" disabled title="v2 規劃中">ETF 總覽</button>
    <button class="tab-btn" data-tab="changes" disabled title="v3 規劃中">持股變動</button>
  </nav>

  <main class="container">
    <section id="tab-cross" class="tab-panel active">
      <div class="filters">
        <label>最少被持有 <select id="filter-min-etfs">
          <option value="1">1 檔以上</option>
          <option value="2" selected>2 檔以上</option>
          <option value="3">3 檔以上</option>
          <option value="4">4 檔以上</option>
        </select></label>
        <label>產業 <select id="filter-industry"><option value="">全部</option></select></label>
        <input type="search" id="filter-search" placeholder="搜尋股票代號或名稱…">
      </div>

      <div id="cross-holdings-table" class="table-wrap">
        <p class="loading">載入中…</p>
      </div>
    </section>
  </main>

  <footer class="footer">
    <p>資訊僅供參考，不構成投資建議。資料來源：各 ETF 發行商官網。</p>
    <p><a href="https://github.com/your-user/StockETF" target="_blank" rel="noopener">GitHub 原始碼</a></p>
  </footer>

  <script src="assets/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `assets/style.css`**

```css
:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #1f2937;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --text3: #6e7681;
  --accent: #58a6ff;
  --green: #3fb950;
  --gold: #d29922;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'Noto Sans TC', sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--sans); background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh; }

.header { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border-bottom: 1px solid var(--border); padding: 28px 24px 20px; text-align: center; }
.header h1 { font-size: clamp(22px, 4vw, 36px); font-weight: 700; letter-spacing: -0.5px; }
.header h1 span { color: var(--accent); }
.header-sub { margin-top: 8px; font-size: 13px; color: var(--text2); }
.header-sub b { color: var(--text); font-family: var(--mono); }

.tab-nav { display: flex; background: var(--bg2); border-bottom: 1px solid var(--border); padding: 0 24px; position: sticky; top: 0; z-index: 10; gap: 4px; }
.tab-btn { background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; color: var(--text2); padding: 13px 20px; font-size: 14px; font-family: var(--sans); cursor: pointer; }
.tab-btn:hover:not(:disabled) { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.container { max-width: 1400px; margin: 0 auto; padding: 24px 20px; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

.filters { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-bottom: 20px; padding: 16px; background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; }
.filters label { font-size: 13px; color: var(--text2); display: flex; align-items: center; gap: 8px; }
.filters select, .filters input { background: var(--bg3); border: 1px solid var(--border); color: var(--text); padding: 6px 10px; border-radius: 6px; font-family: var(--sans); font-size: 13px; }
.filters input { min-width: 220px; }

.table-wrap { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.loading { padding: 40px; text-align: center; color: var(--text2); }

table.cross { width: 100%; border-collapse: collapse; font-size: 14px; }
table.cross thead { background: var(--bg3); color: var(--text2); font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
table.cross th, table.cross td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }
table.cross th.num, table.cross td.num { text-align: right; font-family: var(--mono); }
table.cross th.center, table.cross td.center { text-align: center; }
table.cross tbody tr { cursor: pointer; }
table.cross tbody tr:hover { background: var(--bg3); }
.count-badge { display: inline-block; min-width: 28px; padding: 2px 8px; background: rgba(63, 185, 80, 0.15); color: var(--green); border-radius: 12px; font-family: var(--mono); font-weight: 600; }
.weight { color: var(--gold); font-weight: 600; }

tr.detail td { background: var(--bg); padding: 16px 24px; }
tr.detail ul { list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px 20px; }
tr.detail li { display: flex; justify-content: space-between; font-size: 13px; padding: 4px 0; }
tr.detail li .etf-name { color: var(--accent); font-family: var(--mono); }

.footer { border-top: 1px solid var(--border); padding: 24px; text-align: center; color: var(--text3); font-size: 12px; }
.footer a { color: var(--accent); text-decoration: none; }
.footer a:hover { text-decoration: underline; }
```

- [ ] **Step 3: Create `assets/app.js` with fetch + loading state only**

```javascript
// StockETF frontend — v1: cross-holdings table with filters.

const DATA_URL = "data/latest.json";
const state = {
  payload: null,
  minEtfs: 2,
  industry: "",
  search: "",
  expandedStockId: null,
};

async function load() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.payload = await res.json();
    document.getElementById("updated-at").textContent = formatDate(state.payload.updated_at);
    populateIndustryFilter();
    render();
  } catch (err) {
    document.getElementById("cross-holdings-table").innerHTML =
      `<p class="loading">載入資料失敗：${err.message}</p>`;
  }
}

function formatDate(iso) {
  // "2026-04-24T16:00:00+08:00" → "2026-04-24 16:00"
  return iso.replace("T", " ").slice(0, 16);
}

function populateIndustryFilter() {
  const sel = document.getElementById("filter-industry");
  const industries = new Set(state.payload.holdings.map(h => h.industry).filter(Boolean));
  [...industries].sort().forEach(ind => {
    const o = document.createElement("option");
    o.value = ind;
    o.textContent = ind;
    sel.appendChild(o);
  });
}

function render() {
  // Stub — filled in next task.
  document.getElementById("cross-holdings-table").innerHTML =
    `<p class="loading">已載入 ${state.payload.holdings.length} 筆股票資料 · 渲染邏輯待實作</p>`;
}

// Wire filter controls
document.getElementById("filter-min-etfs").addEventListener("change", e => {
  state.minEtfs = Number(e.target.value);
  render();
});
document.getElementById("filter-industry").addEventListener("change", e => {
  state.industry = e.target.value;
  render();
});
document.getElementById("filter-search").addEventListener("input", e => {
  state.search = e.target.value.trim();
  render();
});

load();
```

- [ ] **Step 4: Manual smoke test**

Open `index.html` in a browser (double-click the file, or drag into browser). Expected:
- Dark theme loads
- Header shows "更新於 2026-04-24 16:00" (or whatever timestamp is in your JSON)
- Filter dropdowns work (don't error)
- Main area shows "已載入 N 筆股票資料 · 渲染邏輯待實作"

**Note:** Opening via `file://` protocol may block `fetch()` in some browsers. If so, run `python -m http.server 8000` in project root and open `http://localhost:8000/`.

- [ ] **Step 5: Commit**

```bash
git add index.html assets/
git commit -m "feat(frontend): skeleton with fetch, header, tabs, filters"
```

---

### Task 9: Frontend cross-holding table (F1)

**Files:**
- Modify: `assets/app.js` (replace the `render()` function)

- [ ] **Step 1: Replace the `render()` stub in `assets/app.js`**

```javascript
function render() {
  const container = document.getElementById("cross-holdings-table");
  const rows = filteredHoldings();

  if (rows.length === 0) {
    container.innerHTML = `<p class="loading">沒有符合條件的股票</p>`;
    return;
  }

  const html = `
    <table class="cross">
      <thead>
        <tr>
          <th>股票</th>
          <th>產業</th>
          <th class="center">被幾檔 ETF 持有</th>
          <th class="num">最高權重</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(renderRow).join("")}
      </tbody>
    </table>
  `;
  container.innerHTML = html;
  wireRowClicks();
}

function filteredHoldings() {
  const { holdings } = state.payload;
  const q = state.search.toLowerCase();
  return holdings.filter(h => {
    if (h.held_by.length < state.minEtfs) return false;
    if (state.industry && h.industry !== state.industry) return false;
    if (q) {
      const hay = `${h.stock_id} ${h.stock_name}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderRow(h) {
  const maxWeight = Math.max(...h.held_by.map(b => b.weight_pct));
  return `
    <tr data-stock-id="${h.stock_id}">
      <td><b>${h.stock_id}</b> ${escapeHtml(h.stock_name)}</td>
      <td>${escapeHtml(h.industry || "—")}</td>
      <td class="center"><span class="count-badge">${h.held_by.length}</span></td>
      <td class="num weight">${maxWeight.toFixed(2)}%</td>
    </tr>
  `;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function wireRowClicks() {
  // Filled in Task 11.
}
```

- [ ] **Step 2: Manual smoke test**

Refresh the browser. Expected:
- Table renders with 4 columns
- First row should be 台積電 (被 4 檔 ETF 持有) with highest weight ~48%
- Rows sorted by held-count desc, then by max weight desc (already done by normalizer)
- Filter "最少被持有 3 檔以上" hides stocks held by fewer than 3 ETFs
- Search "2330" narrows to only 台積電

- [ ] **Step 3: Commit**

```bash
git add assets/app.js
git commit -m "feat(frontend): render cross-holdings table with filtering"
```

---

### Task 10: Expand row to show ETF detail (F3)

**Files:**
- Modify: `assets/app.js` (implement `wireRowClicks` + insert-detail logic)

- [ ] **Step 1: Replace the `wireRowClicks` stub**

```javascript
function wireRowClicks() {
  document.querySelectorAll("table.cross tbody tr[data-stock-id]").forEach(row => {
    row.addEventListener("click", () => toggleDetail(row));
  });
}

function toggleDetail(row) {
  const stockId = row.dataset.stockId;
  const existing = row.nextElementSibling;

  // If the detail row for *this* stock is already open, close it
  if (existing && existing.classList.contains("detail") && existing.dataset.for === stockId) {
    existing.remove();
    state.expandedStockId = null;
    return;
  }
  // Close any other open detail row first
  document.querySelectorAll("tr.detail").forEach(r => r.remove());

  const holding = state.payload.holdings.find(h => h.stock_id === stockId);
  if (!holding) return;

  const etfMeta = Object.fromEntries(state.payload.etfs.map(e => [e.ticker, e]));
  const items = [...holding.held_by]
    .sort((a, b) => b.weight_pct - a.weight_pct)
    .map(b => {
      const meta = etfMeta[b.etf] || {};
      const name = meta.name ? ` ${escapeHtml(meta.name)}` : "";
      return `<li>
        <span class="etf-name">${b.etf}${name}</span>
        <span class="weight">${b.weight_pct.toFixed(2)}%</span>
      </li>`;
    }).join("");

  const detailRow = document.createElement("tr");
  detailRow.className = "detail";
  detailRow.dataset.for = stockId;
  detailRow.innerHTML = `<td colspan="4"><ul>${items}</ul></td>`;
  row.after(detailRow);
  state.expandedStockId = stockId;
}
```

- [ ] **Step 2: Manual smoke test**

Refresh browser. Expected:
- Click a row → expands below, showing each ETF holding that stock and the weight
- Click the same row again → collapses
- Click a different row → previous expansion closes, new one opens
- Change a filter while expanded → the expanded detail is cleared (because the table re-renders)

- [ ] **Step 3: Commit**

```bash
git add assets/app.js
git commit -m "feat(frontend): expand stock row to show per-ETF weights"
```

---

### Task 11: End-to-end verification + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Full end-to-end run**

```bash
python main.py
```

Expected: all 4 ETFs fetch successfully, `data/latest.json` updated, a snapshot file appears in `data/snapshots/`.

- [ ] **Step 2: Run all tests**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Open `index.html` via local server**

```bash
python -m http.server 8000
```

Visit `http://localhost:8000/` in a browser. Verify:
- Header timestamp matches `data/latest.json`'s `updated_at`
- Table shows data from all 4 ETFs
- 台積電 appears at top with `held_by` count = 4
- Filter "最少被持有 4 檔以上" shows only stocks held by all 4 ETFs
- Industry filter populated with actual industries from data
- Search "聯發科" narrows to that row; click expands to show 4 ETFs' weights

- [ ] **Step 4: Expand `README.md` with deployment section**

Append to `README.md`:

```markdown
## Deploying to GitHub Pages

1. Push this repo to GitHub (public recommended — free Pages hosting).
2. On GitHub: Settings → Pages → Source: `main` branch, `/` (root) → Save.
3. Wait ~1 minute; site appears at `https://<your-user>.github.io/StockETF/`.

To refresh data (v1 is manual):

```bash
python main.py
git add data/
git commit -m "data: update $(date +%Y-%m-%d)"
git push
```

v2 will automate this with GitHub Actions.

## Project layout

- `scrapers/` — per-issuer HTML parsers (Yuanta, Nomura, Capital)
- `normalizer.py` — merges scraped data + config into `data/latest.json`
- `main.py` — orchestrator, handles per-ETF failures by reusing previous data
- `config/etfs.yml` — which ETFs to track; tags and color per ETF
- `config/stocks.yml` — industry mapping (optional enrichment)
- `index.html` + `assets/` — static frontend

## Tests

```bash
pytest -v
```

Scraper tests use saved HTML fixtures in `tests/fixtures/` so they don't hit the live sites.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: extend README with deployment and project layout"
```

---

### Task 12: Push-ready checkpoint

By now `main` contains a working MVP. This task is a review / cleanup checkpoint, not new features.

- [ ] **Step 1: Final tree check**

```bash
git ls-files
```

Expected tree matches the structure in the File Structure section at the top. No stray files.

- [ ] **Step 2: Manual sanity pass**

Open `index.html` via local server one more time. Click through every filter combination at least once. Expand 3 different rows. Confirm no console errors (F12 → Console).

- [ ] **Step 3: Review git log**

```bash
git log --oneline
```

Expected: ~11-12 commits, each describing a concrete feature/doc step.

- [ ] **Step 4: Tag v1**

```bash
git tag -a v1.0.0-mvp -m "MVP v1: 4 ETFs, manual run, cross-holding table"
```

- [ ] **Step 5 (optional, user-initiated): push to GitHub**

Only do this when the user explicitly asks. Push creates a public repo.

```bash
# User runs these themselves after creating the GitHub repo:
# git remote add origin https://github.com/<user>/StockETF.git
# git push -u origin main --tags
```

---

## Out of scope for v1 (defer to v2/v3)

These appear in the design spec but are explicitly **not** part of this plan:

- GitHub Actions daily scheduler (→ v2)
- F4 ETF overview tab (→ v2)
- F9 mobile RWD (→ v2)
- F5 holdings change history (→ v3)
- F7 CSV export (→ v3)
- F8 FB share-image generator (→ v3)
- Google Analytics / AdSense (→ v3)
- `data/etfs/{ticker}.json` per-ETF rollup (defer until perf demands it)
