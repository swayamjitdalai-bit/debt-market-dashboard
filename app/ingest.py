"""One command that fills the database.

    python -m app.ingest                  # today
    python -m app.ingest --date 2026-07-31
    python -m app.ingest --days 7         # last 7 calendar days (F-TRAC's window)
    python -m app.ingest --backfill 30    # after business hours F-TRAC allows 30

Safe to re-run: each source replaces its own slice rather than appending.
"""
import argparse
import datetime as dt
import sys

from . import db, derive
from .config import BASE_DIR
from .sources import cbrics, ccil, fbil, ftrac, market


def _slices_for(records):
    """Only the (instrument, segment, date) slices we actually received rows for."""
    return {(r["instrument"], r["segment"], r["deal_date"]) for r in records}


def ingest_trades(conn, from_date, to_date, instruments=("CD", "CP", "CB"),
                  progress=None):
    """Pull F-TRAC trade reports for a date range into the trades table."""
    total, notes = 0, {}
    for inst in instruments:
        if inst not in ftrac.INSTRUMENTS:
            continue
        for seg in ftrac.INSTRUMENTS[inst][1]:
            recs, info = ftrac.fetch_range(inst, seg, from_date, to_date, progress)
            derive.enrich(recs)
            db.replace_trades(conn, recs, _slices_for(recs))
            total += len(recs)

            note = f"{len(recs)} rows ({info})"
            notes[f"{inst}/{seg}"] = note
            if "LAYOUT CHANGED" in note:
                status = "error"
            elif not recs:
                status = "empty"
            else:
                status = "ok"
            db.log(conn, f"{from_date}..{to_date}", f"ftrac:{inst}/{seg}", status, note)
    return total, notes


def ingest_ccil(conn):
    data, notes = ccil.fetch_all()
    counts = {
        "mm_rates": db.upsert_mm_rates(conn, data.get("money_market", {})),
        "curve_points": db.upsert_curve(conn, data.get("tenorwise_yields", {})),
    }
    for key, note in notes.items():
        db.log(conn, None, f"ccil:{key}",
               "error" if note.startswith("failed") else "ok", note)
    return counts, notes


def ingest_fbil(conn):
    """Fetch official MIBOR-OIS benchmark curve points from FBIL."""
    data, notes = fbil.fetch_all()
    ois_by_date = data.get("mibor_ois", {})
    count = db.upsert_curve(conn, ois_by_date)
    for key, note in notes.items():
        db.log(conn, None, f"fbil:{key}",
               "error" if note.startswith("failed") else "ok", note)
    return count, notes


def ingest_market(conn, date, from_date=None):
    """FX and commodities.

    Frankfurter and Yahoo Finance serve historical dates, so USD/INR and
    Brent Crude Oil can be backfilled.
    """
    data, notes = market.fetch_all(date)
    n = db.upsert_fx(conn, date, data.get("usdinr"))
    brent_data = data.get("brent")
    n += db.upsert_commodity(conn, date, "Brent", brent_data)
    for key, note in notes.items():
        db.log(conn, date, f"market:{key}",
               "empty" if "unavailable" in note else "ok", note)

    # Backfill commodities (Brent) from history dict if present
    if brent_data and isinstance(brent_data.get("history"), dict):
        brent_filled = 0
        for h_date, h_price in brent_data["history"].items():
            if not db.commodity(conn, h_date, "Brent"):
                db.upsert_commodity(conn, h_date, "Brent", {
                    "price_usd": h_price,
                    "as_of": h_date,
                    "source": brent_data.get("source"),
                })
                brent_filled += 1
        if brent_filled:
            notes["brent_backfill"] = f"{brent_filled} earlier date(s) filled"

    if from_date and from_date < date:
        start = dt.date.fromisoformat(str(from_date))
        end = dt.date.fromisoformat(str(date))
        filled = 0
        day = start
        while day < end:
            iso = day.isoformat()
            if day.weekday() < 5 and not db.fx(conn, iso):   # skip weekends
                rec = market.usdinr(iso)
                if rec and rec.get("as_of") == iso:
                    db.upsert_fx(conn, iso, rec)
                    filled += 1
            day += dt.timedelta(days=1)
        if filled:
            notes["usdinr_backfill"] = f"{filled} earlier date(s) filled"
            n += filled
    return n, notes


def ingest_cbrics(conn):
    """Refresh CBRICS without replacing yesterday's file if NSE is unavailable."""
    import os
    path = os.path.join(BASE_DIR, "data", "cbrics.csv")
    try:
        count = cbrics.refresh(path)
    except Exception as exc:
        note = f"{exc.__class__.__name__}: {exc}"
        db.log(conn, None, "nse:cbrics", "error", note)
        return 0, note
    note = f"{count} live listed-OTC rows refreshed"
    db.log(conn, None, "nse:cbrics", "ok", note)
    return count, note


def run(date=None, days=1, instruments=("CD", "CP", "CB"), verbose=True):
    target = date or db.today()
    to_date = dt.date.fromisoformat(target)
    from_date = to_date - dt.timedelta(days=max(days, 1) - 1)

    conn = db.init()
    moved = db.migrate_legacy(conn)

    def say(*a):
        if verbose:
            print(*a)

    db.log(conn, target, "run", "started", f"{from_date}..{to_date}")

    windows = ftrac.date_chunks(from_date.isoformat(), to_date.isoformat())
    say(f"Ingest for {from_date} .. {to_date}"
        + (f"  ({len(windows)} export windows)" if len(windows) > 1 else ""))
    if moved:
        say(f"  migrated {moved} saved report(s) from the legacy reports.db")

    say("\n[1/5] F-TRAC trade reports")

    def progress(inst, seg, start, stop, n):
        if verbose and len(windows) > 1:
            print(f"      {inst}/{seg:3} {start}..{stop}  {n:>4} rows")

    count, notes = ingest_trades(conn, from_date.isoformat(), to_date.isoformat(),
                                 instruments, progress)
    if len(windows) > 1:
        say("      ---")
    for key, note in sorted(notes.items()):
        say(f"      {key:8} {note.split(' (')[0]}")
    say(f"      -> {count} trade rows stored")

    say("\n[2/5] CCIL money market + indicative yields")
    counts, ccil_notes = ingest_ccil(conn)
    for key, note in sorted(ccil_notes.items()):
        say(f"      {key:18} {note}")
    say(f"      -> {counts['mm_rates']} rate rows, {counts['curve_points']} curve points")

    say("\n[3/5] FBIL MIBOR-OIS benchmark curve")
    ois_count, fbil_notes = ingest_fbil(conn)
    for key, note in sorted(fbil_notes.items()):
        say(f"      {key:18} {note}")
    say(f"      -> {ois_count} OIS curve points stored")

    say("\n[4/5] FX and commodities (Brent Crude Oil)")
    _, market_notes = ingest_market(conn, target, from_date.isoformat())
    for key, note in sorted(market_notes.items()):
        say(f"      {key:16} {note}")

    say("\n[5/5] NSE CBRICS corporate-bond market watch")
    _, cbrics_note = ingest_cbrics(conn)
    say(f"      -> {cbrics_note}")

    db.log(conn, target, "run", "completed", f"{count} trade rows")

    problems = health(conn, target)
    if problems:
        say("\n!! ATTENTION")
        for p in problems:
            say(f"      {p}")

    say(f"\nDone. Database: {db.DB_PATH}")
    conn.close()
    return count


def health(conn, target=None):
    """Things a human should look at. Empty list means all good.

    Separates 'a source broke' from 'the market was shut', which the raw
    row counts cannot tell apart on their own.
    """
    target = target or db.today()
    out = []

    recent = db.ingest_history(conn, 60)
    broken = [r for r in recent if r["status"] == "error"]
    for r in broken:
        out.append(f"SOURCE BROKEN  {r['source']}: {r['detail'][:120]}")

    # A run that started and never reported completion was killed part-way.
    # run() logs 'completed' *before* calling this, so when the newest run row
    # is still 'started' it belongs to an earlier, dead run.
    runs = [r for r in recent if r["source"] == "run"]
    if runs and runs[0]["status"] == "started":
        out.append(f"RUN DIED       the run started {runs[0]['run_at']} never finished "
                   "- machine slept, logged off, or the window was closed")

    dates = db.trade_dates(conn)
    if not dates:
        out.append("NO TRADE DATA at all - run: python -m app.ingest --backfill 30")
        return out

    latest = dt.date.fromisoformat(dates[0])
    today = dt.date.fromisoformat(target)
    weekdays_since = sum(1 for i in range(1, (today - latest).days + 1)
                         if (latest + dt.timedelta(days=i)).weekday() < 5)
    if weekdays_since >= 3:
        out.append(f"STALE TRADES   newest deal date is {dates[0]}, "
                   f"{weekdays_since} business days ago - is the scheduled task running?")

    mm = db.latest_mm_date(conn, target)
    if mm:
        gap = sum(1 for i in range(1, (today - dt.date.fromisoformat(mm)).days + 1)
                  if (dt.date.fromisoformat(mm) + dt.timedelta(days=i)).weekday() < 5)
        if gap >= 3:
            out.append(f"STALE RATES    newest CCIL money market date is {mm}")
    else:
        out.append("NO CCIL RATES  money market table is empty")

    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch debt market data into the local database.")
    p.add_argument("--date", help="target date, YYYY-MM-DD (default: today)")
    p.add_argument("--days", type=int, default=1,
                   help="number of days ending at --date (default 1)")
    p.add_argument("--backfill", type=int,
                   help="shorthand for --days N; F-TRAC allows 7 during "
                        "business hours, 30 after")
    p.add_argument("--instruments", default="CD,CP,CB",
                   help="comma-separated subset of CD,CP,CB,NC")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    days = args.backfill or args.days
    instruments = tuple(x.strip().upper() for x in args.instruments.split(",") if x.strip())
    try:
        run(args.date, days, instruments, verbose=not args.quiet)
    except Exception as e:                                       # noqa: BLE001
        print(f"Ingest failed: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
