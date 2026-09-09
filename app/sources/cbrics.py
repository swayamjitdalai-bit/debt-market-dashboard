"""NSE CBRICS corporate-bond market-watch downloader and parser."""
import csv
import datetime as dt
import io
import os
import re

import requests

from ..config import HTTP_TIMEOUT, USER_AGENT

PAGE_URL = "https://www.nseindia.com/market-data/debt-market-reporting-corporate-bonds-traded-on-exchange"
CSV_URL = ("https://www.nseindia.com/api/liveCorp-bonds?index=otctrades_listed"
           "&marketType=CBM&csv=true&selectValFormat=crores")

MONTH_MAP = {
    "JA": "01", "JAN": "01", "FB": "02", "FEB": "02", "MR": "03", "MAR": "03",
    "AP": "04", "APR": "04", "MY": "05", "MAY": "05", "JN": "06", "JUN": "06",
    "JU": "06", "JUL": "07", "JL": "07", "AG": "08", "AUG": "08", "AU": "08",
    "SP": "09", "SEP": "09", "SE": "09", "OT": "10", "OCT": "10", "OC": "10",
    "NV": "11", "NOV": "11", "NO": "11", "DC": "12", "DEC": "12", "DE": "12",
}


class CbricsError(RuntimeError):
    pass


def _number(value):
    try:
        return float(str(value or "").replace(",", "").strip())
    except ValueError:
        return None


def _clean_header(value):
    return re.sub(r"\s+", " ", (value or "").replace("\ufeff", "")).strip()


def parse_descriptor(desc):
    """Extract (issuer, coupon, maturity_date) from NSE CBRICS descriptor."""
    if not desc:
        return "", None, "–"
    s = str(desc).strip()

    # 1. Maturity date (e.g. 28FB29, 10OT29, 18MY29, 31DC29, 25MR28, 28MR2029)
    mat_match = re.search(r'\b(\d{1,2})([A-Za-z]{2,3})(\d{2,4})\b', s)
    mat_date = "–"
    if mat_match:
        d = mat_match.group(1).zfill(2)
        mon_str = mat_match.group(2).upper()
        y = mat_match.group(3)
        if len(y) == 2:
            yr = int(y)
            y = f"20{yr}" if yr < 80 else f"19{yr}"
        m = MONTH_MAP.get(mon_str) or MONTH_MAP.get(mon_str[:2])
        if m:
            mat_date = f"{d}-{m}-{y}"

    # 2. Coupon (e.g. 7.38, 7.7, 7.83, 9.35, 8.94)
    coupon = None
    c_match = re.search(r'\b(\d{1,2}(?:\.\d{1,4})?)\s*(?:BD|NCD|BOND|LOA|%)\b', s, re.I)
    if not c_match:
        c_match = re.search(r'\b(\d{1,2}\.\d{2,4})\b', s)
    if c_match:
        try:
            coupon = float(c_match.group(1))
        except ValueError:
            coupon = None

    # 3. Clean Issuer Name
    split_pat = re.search(r'\s+(?:SR|SERIES|TR|TR\.?|TRANCHE|OPTION|OPT|LOA|\d{1,2}(?:\.\d{1,4})?\s*(?:BD|NCD|BOND|%|STRPP|ETF))\b', s, re.I)
    if split_pat:
        issuer = s[:split_pat.start()].strip()
    else:
        issuer = re.sub(r'FVRS.*', '', s, flags=re.I).strip()
        issuer = re.sub(r'\b\d{1,2}[A-Za-z]{2,3}\d{2,4}\b.*', '', issuer).strip()

    return issuer or s, coupon, mat_date


def fetch_csv():
    """Download the listed-OTC CBRICS CSV after establishing NSE cookies."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    page = session.get(PAGE_URL, timeout=HTTP_TIMEOUT)
    if page.status_code != 200:
        raise CbricsError(f"landing page returned HTTP {page.status_code}")
    response = session.get(CSV_URL, headers={"Referer": PAGE_URL}, timeout=HTTP_TIMEOUT)
    if response.status_code != 200:
        raise CbricsError(f"CSV download returned HTTP {response.status_code}")
    if not response.content.lstrip(b"\xef\xbb\xbf \t\r\n").startswith((b'"', b"ISIN")):
        raise CbricsError("NSE returned a non-CSV response")
    return response.content


def parse_current_csv(content, deal_date_fallback=None):
    """Convert NSE's CSV (live summary or deal log) into the standard deal-log row shape."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    rows = []
    default_date = deal_date_fallback or dt.date.today().strftime("%d-%m-%Y")
    for raw in reader:
        row = {_clean_header(k): (v or "").strip() for k, v in raw.items()}
        isin = row.get("ISIN", "")
        if not isin:
            continue

        desc = row.get("DESCRIPTOR", "") or row.get("Issuer Name", "") or row.get("Security Description", "")
        parsed_issuer, parsed_coupon, parsed_mat = parse_descriptor(desc)

        # Handle various column representations of value in crores vs lakhs
        value = None
        for k in ("VALUE (₹ Crores)", "Trade Value in Rs. Crores", "VALUE (Rs. Crores)", "Trade Value (Cr.)", "Trade Value (Cr)"):
            if k in row and row[k]:
                value = _number(row[k])
                break
        if value is None:
            for k in ("Trade Value in Rs. Lacs", "Trade Value (Lacs)", "VALUE (₹ Lacs)", "VALUE (Rs. Lakhs)"):
                if k in row and row[k]:
                    lacs = _number(row[k])
                    if lacs is not None:
                        value = round(lacs / 100.0, 2)
                    break

        if value is None:
            continue

        # Coupon
        coupon = None
        for k in ("Coupon", "Coupon (%)", "COUPON"):
            if k in row and row[k]:
                coupon = _number(row[k])
                break
        if coupon is None:
            coupon = parsed_coupon

        # Yield
        yield_val = None
        for k in ("WEIGHTED AVERAGE YIELD (YTM) (%)", "Yield", "WEIGHTED AVERAGE YIELD", "YTM", "Yield (%)"):
            if k in row and row[k]:
                yield_val = _number(row[k])
                break

        # Maturity Date
        maturity_date = "–"
        for k in ("Put/Call Date", "Maturity Date", "MATURITY DATE", "Expiry Date"):
            if k in row and row[k]:
                maturity_date = row[k]
                break
        if maturity_date in ("–", ""):
            maturity_date = parsed_mat

        # Deal Date
        deal_date = default_date
        for k in ("Trade Date & Time", "Deal Date", "Trade Date", "DEAL DATE"):
            if k in row and row[k]:
                deal_date = row[k].split()[0]
                break

        issuer_name = row.get("Issuer Name") or parsed_issuer

        rows.append({
            "deal_date": deal_date,
            "isin": isin,
            "coupon": coupon,
            "issuer": issuer_name,
            "maturity_date": maturity_date,
            "yield": yield_val,
            "trade_value_cr": value,
            "price": _number(row.get("WEIGHTED AVERAGE PRICE") or row.get("Price")),
            "security": "Listed",
            "deal_type": "OTC listed",
        })
    if not rows:
        raise CbricsError("CSV contained no recognised CBRICS rows")
    return rows


def refresh(destination):
    """Fetch and atomically replace the file used by the static publisher."""
    content = fetch_csv()
    rows = parse_current_csv(content)
    tmp = destination + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(content)
    os.replace(tmp, destination)
    return len(rows)
