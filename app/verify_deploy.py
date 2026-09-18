"""Fail unless Vercel serves exactly the public files from this refresh."""
import argparse
import hashlib
import time
from pathlib import Path

import requests

from .config import BASE_DIR

URL = "https://debt-market-dashboard-main.vercel.app"


def verify(timeout=240):
    files = ("data.js", "index.html", "cdcp.html", "cbrics.html", "report.html")
    expected = {name: hashlib.sha256((Path(BASE_DIR) / "public" / name).read_bytes()).digest()
                for name in files}
    deadline = time.monotonic() + timeout
    while True:
        pending = []
        for name, digest in expected.items():
            try:
                response = requests.get(f"{URL}/{name}", params={"refresh": time.time_ns()},
                                        headers={"Cache-Control": "no-cache"}, timeout=20)
                response.raise_for_status()
                if hashlib.sha256(response.content).digest() != digest:
                    pending.append(name)
            except requests.RequestException:
                pending.append(name)
        if not pending:
            print(f"VERIFIED: all five production files match this refresh: {URL}", flush=True)
            return True
        if time.monotonic() >= deadline:
            print("DEPLOYMENT NOT VERIFIED: " + ", ".join(pending), flush=True)
            return False
        print("Waiting for Vercel: " + ", ".join(pending), flush=True)
        time.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=240)
    raise SystemExit(0 if verify(parser.parse_args().timeout) else 1)
