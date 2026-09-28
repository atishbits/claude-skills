#!/usr/bin/env python3
"""NSE index-constituent fetcher.

NSE's /api/equity-stockIndices endpoint returns the constituents of a named
index (e.g. "NIFTY MIDCAP 150", "NIFTY 500"). The endpoint blocks direct calls
without a primed session cookie, so the fetch path primes the session first,
then calls the API and parses the result.
"""

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def parse_constituents(payload: dict) -> list[str]:
    """Pure function. `payload` is the already-parsed JSON dict from NSE's
    /api/equity-stockIndices response: {"data": [ {...row...}, ... ], ...}.
    Each row is a dict with at least a "symbol" key; the index's own
    summary row (not a real constituent) has "priority": 1 -- every real
    constituent row has "priority": 0 or no "priority" key at all. Returns
    the sorted, deduplicated list of constituent ticker symbols (strings,
    already upper-cased, whitespace-stripped), excluding the priority==1
    row and any row with a missing/blank symbol. Never raises on a
    malformed payload: a payload that is None or not a dict, or whose
    "data" is missing or not a list, returns []; a row that is not a dict,
    or whose symbol is missing, blank or not a string, is skipped."""
    if not isinstance(payload, dict):
        return []

    rows = payload.get("data")
    if not isinstance(rows, list):
        return []

    symbols = set()
    for row in rows:
        if not isinstance(row, dict):
            continue

        # Skip the summary row (priority == 1)
        if row.get("priority") == 1:
            continue

        # Skip rows with missing, blank or non-string symbols
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            continue
        symbol = symbol.strip()

        symbols.add(symbol.upper())

    return sorted(symbols)


def fetch_constituents(index_name: str, session=None) -> list[str]:
    """Live network call. `index_name` is NSE's own index name string, e.g.
    "NIFTY MIDCAP 150" or "NIFTY 500" -- passed through unchanged into the
    request's `index` query parameter (URL-encoded).

    NSE's /api/equity-stockIndices endpoint (unlike the three endpoints in
    nse_disclosures.py) blocks a direct call without a primed session
    cookie. Before calling the API: GET "https://www.nseindia.com/" with
    the session (timeout=25), discard the body, then GET
    "https://www.nseindia.com/api/equity-stockIndices" with
    params={"index": index_name} and header {"Accept": "*/*"} (reuse the
    session so its cookies carry over), timeout=25.

    Raises RuntimeError with a clear, specific message (which endpoint,
    what HTTP status or exception) on ANY failure: non-200 response,
    request exception, or a response body that fails to parse as JSON.
    This function does not fail soft the way nse_disclosures.fetch does --
    its caller (Task 4's run_scan) is responsible for catching the
    RuntimeError and turning it into a clear CLI message, because there is
    no sensible empty-list fallback for "the whole scan's input is
    missing" the way there is for one ticker's pledge data.

    On success, returns parse_constituents(response.json())."""
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", UA)

    try:
        # Prime the session with a request to the home page
        r = session.get("https://www.nseindia.com/", timeout=25)
        if r.status_code != 200:
            raise RuntimeError(f"GET https://www.nseindia.com/: HTTP {r.status_code}")

        # Call the API endpoint
        r = session.get(
            "https://www.nseindia.com/api/equity-stockIndices",
            params={"index": index_name},
            headers={"Accept": "*/*"},
            timeout=25
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"GET https://www.nseindia.com/api/equity-stockIndices: HTTP {r.status_code}"
            )
    except requests.RequestException as e:
        raise RuntimeError(f"Request failed: {e}") from e

    # Parse outside the network try: requests.JSONDecodeError subclasses
    # RequestException (requests >= 2.27), so catching it above would
    # misreport a bad body as a failed request. It (and the older
    # json/simplejson decode errors) is always a ValueError.
    try:
        payload = r.json()
    except ValueError as e:
        raise RuntimeError(
            f"GET https://www.nseindia.com/api/equity-stockIndices: "
            f"failed to parse JSON response: {e}"
        ) from e
    return parse_constituents(payload)
