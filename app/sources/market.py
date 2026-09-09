"""FX and commodity reference prints.

USD/INR comes from the FBIL reference rate republished by Frankfurter (free,
no key). Brent comes from Yahoo Finance (BZ=F) with FRED (DCOILBRENTEU) as fallback.
"""
import datetime as dt

import requests

from ..config import HTTP_TIMEOUT, USER_AGENT

FRANKFURTER = "https://api.frankfurter.dev/v1/"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
YAHOO_BRENT = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=3mo"
YAHOO_BRENT_BACKUP = "https://query2.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=3mo"


def usdinr(date=None):
    """FBIL USD/INR reference rate on or before `date`. Returns dict or None.

    Frankfurter answers a non-publishing day with the previous print, so the
    returned `as_of` can be earlier than the date asked for.
    """
    when = date or dt.date.today().isoformat()
    url = f"{FRANKFURTER}{when}?base=USD&symbols=INR"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError):
        return None
    rate = (payload.get("rates") or {}).get("INR")
    if rate is None:
        return None
    return {
        "pair": "USD/INR",
        "close": float(rate),
        "as_of": payload.get("date"),
        "source": "FBIL reference rate via Frankfurter",
        "stale": payload.get("date") != when,
    }


def _brent_yahoo(date=None):
    """Fetch Brent Crude Oil from Yahoo Finance."""
    cutoff = date or dt.date.today().isoformat()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    for url in (YAHOO_BRENT, YAHOO_BRENT_BACKUP):
        try:
            r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                continue
            data = r.json()
            res = (data.get("chart", {}).get("result") or [])[0]
            timestamps = res.get("timestamp", [])
            quotes = (res.get("indicators", {}).get("quote") or [{}])[0]
            closes = quotes.get("close", [])
            meta = res.get("meta", {})
            current_price = meta.get("regularMarketPrice")

            history = {}
            for ts, c in zip(timestamps, closes):
                if c is not None:
                    d_str = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")
                    history[d_str] = round(float(c), 2)

            # Match requested date or latest <= cutoff
            matched_date = None
            matched_price = None
            if history:
                valid_dates = sorted([d for d in history if d <= cutoff])
                if valid_dates:
                    matched_date = valid_dates[-1]
                    matched_price = history[matched_date]
            
            if matched_price is None and current_price is not None:
                matched_price = round(float(current_price), 2)
                matched_date = cutoff

            if matched_price is not None:
                return {
                    "price_usd": matched_price,
                    "as_of": matched_date or cutoff,
                    "source": "Yahoo Finance (BZ=F)",
                    "stale": matched_date != cutoff if matched_date else False,
                    "history": history,
                }
        except (requests.RequestException, ValueError, KeyError, IndexError):
            continue
    return None


def _brent_fred(date=None):
    """Latest Brent print at or before `date` from FRED. None if unreachable."""
    cutoff = date or dt.date.today().isoformat()
    try:
        r = requests.get(FRED_CSV, headers={"User-Agent": USER_AGENT},
                         timeout=5)
        r.raise_for_status()
    except requests.RequestException:
        return None

    latest = None
    history = {}
    for line in r.text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        day, value = parts[0].strip(), parts[1].strip()
        if value in ("", "."):
            continue
        try:
            val_f = round(float(value), 2)
            history[day] = val_f
            if day <= cutoff:
                latest = (day, val_f)
        except ValueError:
            continue
    if not latest:
        return None
    return {
        "price_usd": latest[1],
        "as_of": latest[0],
        "source": "FRED DCOILBRENTEU (EIA)",
        "stale": latest[0] != cutoff,
        "history": history,
    }


def brent(date=None):
    """Latest Brent print at or before `date`. Tries Yahoo Finance then FRED."""
    res = _brent_yahoo(date)
    if res:
        return res
    return _brent_fred(date)


def fetch_all(date=None):
    data, notes = {}, {}
    for name, fn in (("usdinr", usdinr), ("brent", brent)):
        value = fn(date)
        data[name] = value
        if value is None:
            notes[name] = "unavailable (source unreachable) - stays manual"
        elif value.get("stale"):
            notes[name] = f"last print {value['as_of']} (no publish for {date})"
        else:
            notes[name] = f"as of {value['as_of']}"
    return data, notes

