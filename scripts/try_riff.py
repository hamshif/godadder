#!/usr/bin/env python3
"""
Quick sanity-check for the riff endpoint.

Usage examples:
  python scripts/try_riff.py --base acme --count 5
  python scripts/try_riff.py acme -n 8 --server http://127.0.0.1:8000
  API_URL=http://127.0.0.1:8000 python scripts/try_riff.py acme -n 5

Requires: requests
"""

import argparse
import os
import sys
import json
from typing import Any

import requests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the /riff-names endpoint")
    parser.add_argument("base", nargs="?", help="Base word or phrase for riffing (e.g., 'acme')")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of names to generate (1-50)")
    parser.add_argument("-m", "--model", default=None, help="Optional override model name")
    parser.add_argument(
        "--server",
        default=os.getenv("API_URL", "http://127.0.0.1:8000"),
        help="Server base URL (default: %(default)s or API_URL env)",
    )
    parser.add_argument("-r", "--raw", action="store_true", help="Print raw JSON response")
    args = parser.parse_args(argv)

    base = args.base
    if not base:
        try:
            base = input("Base to riff: ").strip()
        except KeyboardInterrupt:
            print()
            return 130
    if not base:
        print("Base is required", file=sys.stderr)
        return 2

    url = args.server.rstrip("/") + "/riff-names"
    payload: dict[str, Any] = {"base": base, "count": int(args.count)}
    if args.model:
        payload["model"] = args.model

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Request error: {e}", file=sys.stderr)
        return 1

    try:
        data = resp.json()
    except Exception as e:
        print(f"Invalid JSON response: {e}\nBody: {resp.text[:500]}", file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    names = data.get("names")
    if not isinstance(names, list):
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    print(f"Riffed {len(names)} names for base '{base}':")
    for i, name in enumerate(names, 1):
        print(f"{i:2d}. {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

