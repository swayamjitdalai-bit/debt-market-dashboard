"""Verified desk closing reports supplied by the ICMS investment-banking desk.

Public feeds are useful during the session but can differ from the desk's final
cut-off, consolidation rules, or corrections.  These records are an explicit
end-of-day overlay: ``report.full_report`` keeps them intact when the automated
refresh runs later.

Run ``python -m app.desk_close --apply`` after adding a verified desk close.
The command is idempotent and is safe for the scheduled publisher to run.
"""
import argparse

from . import db


SOURCE = "ICMS investment-banking desk close (manual verified)"


def _gsecs(rows):
    return [{"name": name, "yield_today": today, "yield_prev": previous}
            for name, today, previous in rows]


def _curve(rows):
    return [{"tenor_label": tenor, "security_name": security,
             "yield_today": today, "yield_prev": previous}
            for tenor, security, today, previous in rows]


def _ranges(rows):
    return [{"tenor_label": tenor, "low": low, "high": high}
            for tenor, low, high in rows]


def _sdl_ranges(rows):
    return [{"tenor_label": tenor, "low": low, "high": high,
             "range_text": f"{low:.2f}% - {high:.2f}%"}
            for tenor, low, high in rows]


DESK_CLOSES = {
    "2026-09-18": {
        "source_note": SOURCE,
        "call": {"label": "CALL", "ltr": 5.05, "weighted_avg": 5.09},
        "trep": {"label": "TREP", "ltr": 5.30, "weighted_avg": 5.07},
        "mm_volume": {"total_crores": 714306.01, "weighted_avg": 5.00},
        "top_traded_gsecs": _gsecs([
            ("06.94 GS 2036", 7.0686, 7.0463), ("07.06 GS 2041", 7.2243, 7.2115),
            ("06.36 GS 2031", 6.7708, 6.7837), ("06.68 GS 2040", 7.2007, 7.1827),
            ("07.24 GS 2055", 7.5975, 7.5886), ("07.63 GS 2056", 7.5962, 7.6001),
            ("06.48 GS 2035", 7.0363, 7.0405), ("07.33 GS 2026", 5.2400, 5.0182),
            ("06.10 GS 2031", 6.8396, 6.8613), ("06.90 GS 2065", 7.6792, 7.6756),
        ]),
        "benchmark_curve": _curve([
            ("3 Years", "6.79 GS 2029", 6.6814, 6.6644),
            ("5 Years", "6.36 GS 2031", 6.7708, 6.7837),
            ("10 Years", "06.48 GS 2035", 7.0363, 7.0359),
            ("10 Years", "06.94 GS 2036", 7.0686, 7.0463),
        ]),
        "sdl_range": _sdl_ranges([("3 Years", 7.17, 7.22), ("5 Years", 7.32, 7.38),
                                  ("10 Years", 7.70, 7.75), ("15 Years", 7.87, 7.94)]),
        "brent": {"price_usd": 103.27, "as_of": "5:00 pm IST", "source": SOURCE},
        "ois_curve": [
            {"tenor_label": tenor, "rate_today": today, "rate_prev": previous}
            for tenor, today, previous in [("1 Year", 6.0640, 6.0390),
                                            ("3 Years", 6.4000, 6.3710),
                                            ("5 Years", 6.5850, 6.5670),
                                            ("10 Years", 6.7120, 6.7340)]
        ],
        "tbill_range": [
            {"tenor_label": tenor, "rate_today": today, "rate_prev": previous}
            for tenor, today, previous in [("91 Days", 5.3400, 5.3400),
                                            ("182 Days", 5.6200, 5.6200),
                                            ("364 Days", 5.8900, 5.8900)]
        ],
        "aaa_psu_corp": _ranges([("3 Years", 7.7000, 7.7700), ("5 Years", 7.7500, 7.8000),
                                  ("10 Years", 7.7500, 7.8500)]),
        "cd_money_market": _ranges([("3 Months", 6.10, 6.15), ("6 Months", 6.75, 6.80),
                                     ("12 Months", 7.30, 7.35)]),
        "fx": {"pair": "USD/INR", "close": 95.9100, "open": 95.7500,
               "day_low": 95.7100, "day_high": 95.9300, "source": SOURCE},
    },
    "2026-09-21": {
        "source_note": SOURCE,
        "call": {"label": "CALL", "ltr": 4.90, "weighted_avg": 5.25},
        "trep": {"label": "TREP", "ltr": 5.04, "weighted_avg": 5.16},
        "mm_volume": {"total_crores": 731615.55, "weighted_avg": 5.13},
        "top_traded_gsecs": _gsecs([
            ("06.94 GS 2036", 7.0497, 7.0686), ("07.06 GS 2041", 7.2006, 7.2243),
            ("06.36 GS 2031", 6.7307, 6.7708), ("06.10 GS 2031", 6.8047, 6.8396),
            ("07.63 GS 2056", 7.5664, 7.5962), ("07.24 GS 2055", 7.5744, 7.5975),
            ("06.90 GS 2065", 7.6571, 7.6792), ("07.34 GS 2064", 7.6651, 7.6952),
            ("06.68 GS 2040", 7.2007, 7.2007), ("07.71 GS 2066", 7.6443, 7.6764),
        ]),
        "benchmark_curve": _curve([
            ("3 Years", "6.79 GS 2029", 6.6814, 6.6814),
            ("5 Years", "6.36 GS 2031", 6.7307, 6.7708),
            ("10 Years", "06.48 GS 2035", 7.0319, 7.0363),
            ("10 Years", "06.94 GS 2036", 7.0497, 7.0686),
        ]),
        "sdl_range": _sdl_ranges([("3 Years", 7.17, 7.22), ("5 Years", 7.32, 7.38),
                                  ("10 Years", 7.70, 7.75), ("15 Years", 7.87, 7.94)]),
        "brent": {"price_usd": 101.32, "as_of": "5:00 pm IST", "source": SOURCE},
        "ois_curve": [
            {"tenor_label": tenor, "rate_today": today, "rate_prev": previous}
            for tenor, today, previous in [("1 Year", 6.0700, 6.0640),
                                            ("3 Years", 6.3700, 6.4000),
                                            ("5 Years", 6.5480, 6.5850),
                                            ("10 Years", 6.6890, 6.7120)]
        ],
        "tbill_range": [
            {"tenor_label": tenor, "rate_today": today, "rate_prev": previous}
            for tenor, today, previous in [("91 Days", 5.2700, 5.2800),
                                            ("182 Days", 5.7351, 5.7500),
                                            ("364 Days", 6.0250, 6.0400)]
        ],
        "aaa_psu_corp": _ranges([("3 Years", 7.6500, 7.7200), ("5 Years", 7.7000, 7.7500),
                                  ("10 Years", 7.7000, 7.8000)]),
        "cd_money_market": _ranges([("3 Months", 6.05, 6.10), ("6 Months", 6.72, 6.77),
                                     ("12 Months", 7.25, 7.30)]),
        "fx": {"pair": "USD/INR", "close": 95.7800, "open": 95.8600,
               "day_low": 95.7200, "day_high": 95.8600, "source": SOURCE},
    },
}


def apply():
    conn = db.connect()
    try:
        for date, payload in DESK_CLOSES.items():
            db.save_report(conn, date, dict(payload, report_date=date))
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save verified ICMS desk close overlays")
    parser.add_argument("--apply", action="store_true", help="write the bundled verified closes")
    args = parser.parse_args()
    if args.apply:
        apply()
        print(f"Saved {len(DESK_CLOSES)} verified ICMS desk closes.")
    else:
        parser.print_help()
