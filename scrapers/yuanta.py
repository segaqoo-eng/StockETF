"""Yuanta (元大投信) holdings scraper.

Supports passive ETFs listed on yuantaetfs.com.
Currently handles: 0050, 0056.

Data source type: HTML with server-side rendered window.__NUXT__ payload.

The Yuanta ETF pages are Nuxt.js SSR applications. The full holdings data
is embedded in a compressed IIFE (immediately invoked function expression)
assigned to window.__NUXT__. The IIFE de-duplicates repeated strings by
lifting them into parameters:
    window.__NUXT__=(function(a,b,...,qc){ body })(arg0,...,argN));
so stock codes, names, and weights may appear as variable references
(e.g. code:kF, name:kG) rather than inline literals.

This parser:
1. Extracts the parameter names and argument values from the IIFE.
2. Resolves each variable reference to its actual string/number value.
3. Locates the StockWeights array in the function body and parses it.

Note: weights that happen to be shared across multiple stocks (e.g. two
stocks both at 0.56%) are also stored as variable references, so the
resolver handles both numeric literals and variable references for weights.
"""

import json
import re

from scrapers.base import BaseScraper, Holding, ScrapeResult, classify_market

HOLDINGS_URL = "https://www.yuantaetfs.com/product/detail/{ticker}/ratio"

# JS identifier: word chars + dollar sign (e.g. k$, j_, l$)
_JS_IDENT = r"[\w$]+"
# Active ETFs (e.g. 00990A) have foreign holdings whose code/name/ename are
# inline string literals like "LITE US" / "LUMENTUM HOLDINGS INC" — strings with
# spaces aren't valid JS identifiers so the build pipeline doesn't compress them.
# Accept either a quoted string or a JS identifier for these fields.
_STR_OR_IDENT = r'(?:"[^"]*"|[\w$]+)'
# A weight token is either a JS identifier (variable ref like mO, e$) or a numeric literal
# (.99, 62.09, 1.5, 0.53 — note leading dot is valid in JS)
_WEIGHT_TOK = r"(?:[0-9]*\.[0-9]+|[0-9]+|[\w$]+)"


def _build_param_map(nuxt_script: str) -> dict:
    """Parse the NUXT IIFE and return a mapping of param-name -> decoded value."""
    # Extract parameter names from function signature
    param_match = re.match(r"window\.__NUXT__=\(function\(([^)]+)\)\{", nuxt_script)
    if not param_match:
        raise ValueError("Cannot parse NUXT function signature")
    params = param_match.group(1).split(",")

    # Locate the function body end by brace-counting
    last_param = params[-1]
    body_marker = last_param + "){"
    body_open = nuxt_script.index(body_marker) + len(body_marker) - 1
    depth = 0
    func_body_end = -1
    for i in range(body_open, len(nuxt_script)):
        c = nuxt_script[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                func_body_end = i
                break
    if func_body_end == -1:
        raise ValueError("Cannot find NUXT function body end")

    # Extract the raw args string and tokenize it
    args_raw = nuxt_script[func_body_end + 1 :].strip()
    if args_raw.startswith("("):
        args_raw = args_raw[1:]
    if args_raw.endswith("));"):
        args_raw = args_raw[:-2]
    elif args_raw.endswith(")"):
        args_raw = args_raw[:-1]

    args_values = _tokenize_js_args(args_raw)

    if len(args_values) != len(params):
        raise ValueError(
            f"Yuanta parser: parameter count mismatch ({len(params)} params vs "
            f"{len(args_values)} args) — page structure may have changed"
        )

    # Build param -> decoded value mapping
    param_map: dict = {}
    for idx, p in enumerate(params):
        if idx < len(args_values):
            param_map[p] = _decode_js_value(args_values[idx])
    return param_map


def _tokenize_js_args(args_raw: str) -> list[str]:
    """Split a comma-separated JS argument list, respecting strings and parens."""
    result = []
    current: list[str] = []
    paren_depth = 0
    in_string = False
    escape_next = False
    string_char = None

    for c in args_raw:
        if escape_next:
            current.append(c)
            escape_next = False
        elif in_string and c == "\\":
            current.append(c)
            escape_next = True
        elif in_string:
            if c == string_char:
                in_string = False
            current.append(c)
        elif c in ('"', "'"):
            in_string = True
            string_char = c
            current.append(c)
        elif c == "(":
            paren_depth += 1
            current.append(c)
        elif c == ")":
            paren_depth -= 1
            current.append(c)
        elif c == "," and paren_depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(c)

    if current:
        result.append("".join(current).strip())
    return result


def _decode_js_value(val: str):
    """Convert a JS literal token to a Python value."""
    if val.startswith('"') and val.endswith('"'):
        try:
            return json.loads(val)
        except Exception:
            return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    if val == "null":
        return None
    if val == "true":
        return True
    if val == "false":
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val  # leave as raw string (e.g. Array(7) — not needed for holdings)


def _extract_stock_weights_text(nuxt_script: str) -> str:
    """Return the raw text inside StockWeights:[...] from the NUXT body."""
    marker = "StockWeights:["
    try:
        sw_start = nuxt_script.index(marker) + len(marker)
    except ValueError as e:
        raise ValueError(
            "Yuanta parser: StockWeights block not found in NUXT body — "
            "page structure may have changed"
        ) from e
    sw_depth = 1
    sw_end = sw_start
    for i in range(sw_start, len(nuxt_script)):
        c = nuxt_script[i]
        if c == "[":
            sw_depth += 1
        elif c == "]":
            sw_depth -= 1
            if sw_depth == 0:
                sw_end = i
                break
    return nuxt_script[sw_start:sw_end]


# Each entry: {code:VAR_OR_STR,ym:VAR,name:VAR_OR_STR,ename:VAR_OR_STR,weights:NUMVAR,qty:NUM}
# Passive ETFs (0050/0056) compress everything to JS identifiers; active ETFs
# with foreign holdings (00990A) inline strings for code/name/ename.
# weights may be a numeric literal (.53, 62.09, 1.5) or a variable ref (mO, e$).
_ENTRY_RE = re.compile(
    r"\{code:(" + _STR_OR_IDENT + r"),ym:(" + _JS_IDENT + r"),name:(" + _STR_OR_IDENT
    + r"),ename:(" + _STR_OR_IDENT + r"),weights:(" + _WEIGHT_TOK + r"),qty:(\d+)\}"
)


def _resolve_str_or_var(token: str, param_map: dict) -> str:
    """A code/name/ename token may be a quoted string literal or a JS identifier.

    Strings come back wrapped in double quotes; identifiers go through the param
    map. Falls through to the raw token if neither (so a missing variable shows
    up loudly downstream rather than silently coercing to an empty string)."""
    if token.startswith('"') and token.endswith('"'):
        try:
            return json.loads(token)
        except Exception:
            return token[1:-1]
    val = param_map.get(token, token)
    return str(val)


def parse_yuanta_holdings(text: str) -> list[Holding]:
    """Parse Yuanta ETF holdings from the raw HTML of a ratio page.

    Extracts data from the server-rendered window.__NUXT__ payload embedded
    in the page, resolving all compressed variable references.

    Returns a list of Holding objects sorted by weight_pct descending
    (the order they appear in the NUXT payload).
    """
    # Locate the NUXT script
    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", text)
    nuxt_script = None
    for s in scripts:
        if "window.__NUXT__" in s:
            nuxt_script = s.strip()
            break
    if not nuxt_script:
        raise ValueError("window.__NUXT__ not found — page structure may have changed")

    param_map = _build_param_map(nuxt_script)
    sw_text = _extract_stock_weights_text(nuxt_script)

    def resolve(var: str):
        """Resolve a JS variable reference to its Python value via the param map."""
        return param_map.get(var, var)

    holdings = []
    for m in _ENTRY_RE.finditer(sw_text):
        code_tok, _ym_var, name_tok, _ename_tok, weight_var, qty_str = m.groups()

        stock_id = _resolve_str_or_var(code_tok, param_map)
        stock_name = _resolve_str_or_var(name_tok, param_map)

        # weight_var may be a numeric literal or a variable reference
        weight_raw = resolve(weight_var)
        try:
            weight_pct = float(weight_raw)
        except (TypeError, ValueError):
            # skip entries where weight can't be resolved to a number
            continue

        shares = int(qty_str)
        holdings.append(Holding(
            stock_id=stock_id,
            stock_name=stock_name,
            weight_pct=weight_pct,
            shares=shares,
            market=classify_market(stock_id),
        ))

    if not holdings:
        raise ValueError(
            "Yuanta parser: StockWeights block found but no entries matched — "
            "field order or format may have changed"
        )
    return holdings


_PCF_BLOCK_RE = re.compile(r"PCF:\{([^}]*)\}")
# Each field's value can be a quoted string, a numeric literal, or a JS identifier.
_PCF_FIELD_RE = re.compile(r'(\w+):("(?:\\.|[^"])*"|\d+\.?\d*|[\w$]+)')


def parse_yuanta_meta(text: str) -> dict:
    """Extract fund-level metadata from the same NUXT payload the holdings parser uses.

    The PCF block (Portfolio Composition File) on every yuanta ETF detail
    page has these fields that map to our standard schema:
      upddate  → as_of_date         (e.g. "2026-04-24 15:58:15" → "2026-04-24T15:58:15")
      totalav  → nav_total          (基金總資產 — sometimes a JS variable ref)
      osunit   → units_outstanding  (流通在外受益權單位數)
      nav      → p_unit             (每受益權單位淨值 — sometimes a variable ref)

    Variable refs are resolved via the same NUXT param map the holdings parser
    builds. Returns {} on any structural failure — silent fallback.
    """
    try:
        scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", text)
        nuxt = next((s for s in scripts if "window.__NUXT__" in s), None)
        if not nuxt:
            return {}
        try:
            pmap = _build_param_map(nuxt)
        except Exception:
            pmap = {}

        pcf_m = _PCF_BLOCK_RE.search(nuxt)
        if not pcf_m:
            return {}
        fields = dict(_PCF_FIELD_RE.findall(pcf_m.group(1)))
    except Exception:
        return {}

    def resolve(tok):
        """Resolve a PCF field token to a Python value (str / int / float / None)."""
        if tok is None:
            return None
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1]
        if re.fullmatch(r"\d+\.?\d*", tok):
            return float(tok) if "." in tok else int(tok)
        return pmap.get(tok)  # VAR ref

    meta: dict = {}
    upddate = resolve(fields.get("upddate"))
    if isinstance(upddate, str) and upddate:
        meta["as_of_date"] = upddate.replace(" ", "T")  # ISO-ish

    totalav = resolve(fields.get("totalav"))
    if isinstance(totalav, (int, float)):
        meta["nav_total"] = float(totalav)

    osunit = resolve(fields.get("osunit"))
    if isinstance(osunit, (int, float)):
        meta["units_outstanding"] = float(osunit)

    nav = resolve(fields.get("nav"))
    if isinstance(nav, (int, float)):
        meta["p_unit"] = float(nav)

    return meta


class YuantaScraper(BaseScraper):
    """Scraper for Yuanta ETF holdings (0050, 0056, 00990A)."""

    def fetch(self, ticker: str) -> ScrapeResult:
        url = HOLDINGS_URL.format(ticker=ticker)
        text = self.get(url)
        return ScrapeResult(
            holdings=parse_yuanta_holdings(text),
            fund_meta=parse_yuanta_meta(text),
        )
