"""Run in the dedicated background checkout; never reset a user's worktree."""
import argparse
import datetime as dt
import fcntl
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import BASE_DIR


def run(*args, cwd=BASE_DIR):
    subprocess.run(args, cwd=cwd, check=True)


def run_git(*args, cwd=BASE_DIR, attempts=3):
    """Retry transient GitHub SSH transport failures before giving up.

    The cloud workflow remains the primary scheduler, but this runner is a
    useful independent backup.  A short network drop must not lose the entire
    refresh window.
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return run("git", *args, cwd=cwd)
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = attempt * 10
            print(f"Git command failed (attempt {attempt}/{attempts}); retrying in {delay}s", flush=True)
            time.sleep(delay)
    raise last_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    now = dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    minutes = now.hour * 60 + now.minute
    weekday = now.weekday()
    print(f"Scheduler invoked: {now.isoformat()} (weekday={weekday}, minute={minutes})", flush=True)
    in_window = weekday < 5 and 840 <= minutes <= 1040
    if not args.force and not in_window:
        print("Outside weekday 14:00–17:20 IST window", flush=True)
        return 0
    with open(Path(BASE_DIR) / "data" / "refresh.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another refresh is still running", flush=True)
            return 0
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=BASE_DIR).strip():
            raise RuntimeError("Background checkout has uncommitted changes; preserve them and inspect the log")
        run_git("pull", "--ff-only", "origin", "main")
        # Each run gets a fresh checkout so a failed fetch/push cannot poison
        # tomorrow's run. Failed checkouts remain available for diagnosis.
        runs = Path(BASE_DIR) / "data" / "runs"
        runs.mkdir(exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="refresh-", dir=runs)
        remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=BASE_DIR, text=True).strip()
        run("git", "clone", "--quiet", BASE_DIR, checkout)
        run("git", "remote", "set-url", "origin", remote, cwd=checkout)
        for key in ("user.name", "user.email"):
            value = subprocess.check_output(["git", "config", key], cwd=BASE_DIR, text=True).strip()
            run("git", "config", key, value, cwd=checkout)
        run(sys.executable, "-u", "-m", "app.ingest", "--days", "7", cwd=checkout)
        run(sys.executable, "-u", "-m", "app.publish", cwd=checkout)
        run("git", "add", "data/market.db", "data/cbrics.csv", "public", "vercel.json", cwd=checkout)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=checkout).returncode:
            run("git", "commit", "-m", f"Market refresh {now:%Y-%m-%d %H:%M} IST", cwd=checkout)
        # Fail visibly on a competing remote update; never discard either database.
        run_git("push", "origin", "HEAD:main", cwd=checkout)
        run(sys.executable, "-u", "-m", "app.verify_deploy", cwd=checkout)
        shutil.rmtree(checkout)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"REFRESH FAILED: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
