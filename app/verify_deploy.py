"""Fail unless Vercel serves exactly the public files from this refresh."""
import argparse
import hashlib
import time
from pathlib import Path

import requests

from .config import BASE_DIR

URL = "https://debt-market-dashboard-main.vercel.app"


def verify(timeout=900):
    if timeout <= 0:
        raise ValueError("deployment timeout must be positive")
    files = ("data.js", "index.html", "cdcp.html", "cbrics.html", "report.html")
    expected = {name: hashlib.sha256((Path(BASE_DIR) / "public" / name).read_bytes()).digest()
                for name in files}
    deadline = time.monotonic() + timeout
    while True:
        pending = []
        for index, (name, digest) in enumerate(expected.items()):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pending.extend(list(expected)[index:])
                break
            try:
                response = requests.get(f"{URL}/{name}", params={"refresh": time.time_ns()},
                                        headers={"Cache-Control": "no-cache"},
                                        timeout=min(20, remaining))
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
        time.sleep(min(10, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=900)
    raise SystemExit(0 if verify(parser.parse_args().timeout) else 1)
