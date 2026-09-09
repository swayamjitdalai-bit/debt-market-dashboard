"""FBIL (fbil.org.in) benchmark data scraper.

Fetches official benchmark rates:
  - MIBOR-OIS curve points (6M, 1Y, 5Y, etc.)
  - MIFOR / Modified MIFOR benchmark rates
"""
import re
import requests

from ..config import HTTP_TIMEOUT, USER_AGENT

BASE = "https://www.fbil.org.in/wasdm"
OIS_GRAPH_URL = f"{BASE}/miborois/fetchcommongraph"

OIS_TENORS = {
    "1M": ("1 Month", "1M"),
    "2M": ("2 Months", "2M"),
    "3M": ("3 Months", "3M"),
    "6M": ("6 Months", "6M"),
    "9M": ("9 Months", "9M"),
    "1Y": ("1 Year", "1Y"),
    "2Y": ("2 Years", "2Y"),
    "3Y": ("3 Years", "3Y"),
    "4Y": ("4 Years", "4Y"),
    "5Y": ("5 Years", "5Y"),
}


def _clean_tenor(name):
    """Normalize 'MIBOR-OIS - 6M' or '6M' into standard label and bucket."""
    m = re.search(r"(\d+\s*[MYDmyd])", name or "")
    if m:
        raw = m.group(1).upper().replace(" ", "")
        if raw in OIS_TENORS:
            return OIS_TENORS[raw]
        return f"{raw}", raw
    return name, name


def mibor_ois(span="6M"):
    """Fetch MIBOR-OIS benchmark rate history from FBIL.

    Returns {date: {'ois': [{'tenor_label': ..., 'bucket': ..., 'security': ..., 'ytm': ...}]}}
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
    }
    url = f"{OIS_GRAPH_URL}/{span}"
    try:
        r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        # Fallback to 1M if 6M fails
        if span != "1M":
            return mibor_ois(span="1M")
        return {}

    products = payload.get("benchMarkTrendData") or []
    by_date = {}

    for prod in products:
        prod_name = prod.get("productName", "")
        label, bucket = _clean_tenor(prod_name)
        trends = prod.get("benchMarkTrend") or []
        for item in trends:
            pub_date = item.get("publishDate")
            rate = item.get("rate")
            if not pub_date or rate is None:
                continue
            # Format YYYY-MM-DD
            d_str = str(pub_date)[:10]
            try:
                rate_f = round(float(rate), 4)
            except (ValueError, TypeError):
                continue
            
            day_map = by_date.setdefault(d_str, {"ois": []})
            day_map["ois"].append({
                "tenor_label": label,
                "bucket": bucket,
                "security": prod_name or f"MIBOR-OIS {bucket}",
                "ytm": rate_f,
            })

    return by_date


def fetch_all():
    """Fetch all FBIL benchmarks with per-source isolation."""
    data, notes = {}, {}
    try:
        ois_data = mibor_ois()
        data["mibor_ois"] = ois_data
        notes["mibor_ois"] = f"{len(ois_data)} date(s)" if ois_data else "empty"
    except Exception as e:
        data["mibor_ois"] = {}
        notes["mibor_ois"] = f"failed: {e.__class__.__name__}: {e}"

    return data, notes
