#!/usr/bin/env python3
"""
Quick sanity-check for the /check-domains endpoint.

Usage examples:
  python scripts/try_check_domains.py -d acme.ai -d falafel.com
  python scripts/try_check_domains.py acme.ai falafel.com --server http://127.0.0.1:8000
  API_URL=http://127.0.0.1:8000 python scripts/try_check_domains.py -d acme.ai -d acme.com -v

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the /check-domains endpoint")
    parser.add_argument("domains", nargs="*", help="Domains to check (e.g., acme.ai falafel.com)")
    parser.add_argument("-d", "--domain", action="append", default=None, help="Add a domain (repeatable)")
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

    collected: list[str] = []
    if args.domains:
        collected.extend(args.domains)
    if args.domain:
        collected.extend(args.domain)
    # Dedup while preserving order
    seen = set()
    domains: list[str] = []
    for d in collected:
        dd = str(d).strip().lower()
        if dd and dd not in seen:
            seen.add(dd)
            domains.append(dd)

    if not domains:
        print("No domains provided. Use positional args or -d.", file=sys.stderr)
        return 2

    url = args.server.rstrip("/") + "/check-domains"
    payload: dict[str, Any] = {"domains": domains}
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

    results = data.get("results")
    if not isinstance(results, list):
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    print(f"Checked {len(results)} domain(s):")
    for r in results:
        dom = r.get("domain")
        avail = r.get("available")
        price = r.get("price")
        curr = r.get("currency")
        err = r.get("error") or r.get("price_error")
        extra = f" price={price} {curr}" if price else ""
        suffix = f" (error: {err})" if err else ""
        print(f"- {dom:30s} available={avail}{extra}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

