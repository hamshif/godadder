#!/usr/bin/env python3
"""
Quick sanity-check for the /riff-and-check endpoint.

Usage examples:
  python scripts/try_riff_and_check.py -b aurora -n 5
  python scripts/try_riff_and_check.py aurora -n 6 --tld .ai --tld .com --server http://127.0.0.1:8000
  API_URL=http://127.0.0.1:8000 python scripts/try_riff_and_check.py -b acme -n 5 -v

Defaults:
  - Server defaults from env `API_URL`, else http://127.0.0.1:8000.
  - Timeout defaults from env `RIFF_TIMEOUT` (then `TIMEOUT`), else 30s; 0 disables.

Requires: requests
"""

from __future__ import annotations

import argparse
import os
import sys
import json
from typing import Any

import requests


DEFAULT_BASE = "acme"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the /riff-and-check endpoint")
    parser.add_argument("pos_base", nargs="?", help="Base word or phrase (e.g., 'acme')")
    parser.add_argument("-b", "--base", default=None, help=f"Base to riff (default: '{DEFAULT_BASE}')")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of names to generate (1-50)")
    parser.add_argument("-m", "--model", default=None, help="Optional override model name")
    parser.add_argument("--tld", action="append", default=None, help="TLD to combine (repeatable), include '.' e.g., .ai")
    parser.add_argument(
        "--server",
        default=os.getenv("API_URL", "http://127.0.0.1:8000"),
        help="Server base URL (default: %(default)s or API_URL env)",
    )
    timeout_env = os.getenv("RIFF_TIMEOUT", os.getenv("TIMEOUT", "30")).strip()
    try:
        default_timeout = float(timeout_env)
    except Exception:
        default_timeout = 30.0

    parser.add_argument("-r", "--raw", action="store_true", help="Print raw JSON response")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--timeout",
        type=float,
        default=default_timeout,
        help="HTTP timeout seconds (0 disables). Default from RIFF_TIMEOUT/TIMEOUT or 30.",
    )
    args = parser.parse_args(argv)

    base = args.pos_base or args.base or DEFAULT_BASE
    tlds = [t for t in (args.tld or []) if t]
    url = args.server.rstrip("/") + "/riff-and-check"
    payload: dict[str, Any] = {"base": base, "count": int(args.count)}
    if args.model:
        payload["model"] = args.model
    if tlds:
        payload["tlds"] = tlds

    timeout = None if args.timeout is not None and args.timeout <= 0 else float(args.timeout)
    if args.verbose:
        print(f"POST {url} timeout={timeout}")
        print(f"Payload: {json.dumps(payload)}")

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        if args.verbose:
            print(f"Status: {resp.status_code}")
    except requests.HTTPError as e:
        detail = None
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        print(f"Request error: {e}\nServer response: {str(detail)[:500]}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"Request error: {e}. Try increasing --timeout.", file=sys.stderr)
        return 1

    try:
        data = resp.json()
    except Exception as e:
        print(f"Invalid JSON response: {e}\nBody: {resp.text[:500]}", file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    names = data.get("names") or []
    items = data.get("items") or []
    print(f"Riffed {len(names)} names for base '{base}':")
    for i, name in enumerate(names, 1):
        print(f"{i:2d}. {name}")

    print(f"\nChecked {len(items)} candidate domain(s):")
    for it in items:
        dom = it.get("domain")
        nm = it.get("name")
        avail = it.get("available")
        price = it.get("price")
        curr = it.get("currency")
        err = it.get("error") or it.get("price_error")
        extra = f" price={price} {curr}" if price else ""
        suffix = f" (error: {err})" if err else ""
        print(f"- {nm:22s} -> {dom:30s} available={avail}{extra}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

