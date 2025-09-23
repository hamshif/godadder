#!/usr/bin/env python3
"""
Quick sanity-check for the riff endpoint.

Usage examples:
  python scripts/try_riff.py --base acme --count 5
  python scripts/try_riff.py acme -n 8 --server http://127.0.0.1:8000
  API_URL=http://127.0.0.1:8000 python scripts/try_riff.py -n 5  # uses default base
  python scripts/try_riff.py -b falafel -n 8 --timeout 90
  python scripts/try_riff.py --interactive y  # prompt, default shown

Defaults:
  - Base defaults to hardcoded 'acme' (override with `-b/--base`).
  - Server defaults from env `API_URL`, else http://127.0.0.1:8000.
  - Timeout defaults from env `RIFF_TIMEOUT` (then `TIMEOUT`), else 30s; 0 disables.

Requires: requests
"""

import argparse
import os
import sys
import json
from typing import Any

import requests


DEFAULT_BASE = "acme"


def _parse_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    v = str(val).strip().lower()
    if v in {"y", "yes", "true", "1", "on"}:
        return True
    if v in {"n", "no", "false", "0", "off"}:
        return False
    return default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the /riff-names endpoint")
    # Optional positional base (kept for convenience)
    parser.add_argument("pos_base", nargs="?", help="Base word or phrase for riffing (e.g., 'acme')")
    # Flagged base with default
    parser.add_argument("-b", "--base", default=None, help=f"Base to riff (default: '{DEFAULT_BASE}')")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of names to generate (1-50)")
    parser.add_argument("-m", "--model", default=None, help="Optional override model name")
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
    parser.add_argument("--interactive", default="n", help="Prompt for base? (y/n). Default: n")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging (headers, timings)")
    parser.add_argument("--stream", action="store_true", help="Use streaming response (debug headers early)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=default_timeout,
        help="HTTP timeout seconds (0 disables). Default from RIFF_TIMEOUT/TIMEOUT or 30.",
    )
    args = parser.parse_args(argv)

    interactive = _parse_bool(args.interactive, default=False)
    base = args.pos_base or args.base or DEFAULT_BASE
    if interactive:
        # Interactive prompt; Enter keeps current default
        try:
            entered = input(f"Base to riff [{base}]: ").strip()
        except KeyboardInterrupt:
            print()
            return 130
        if entered:
            base = entered

    url = args.server.rstrip("/") + "/riff-names"
    payload: dict[str, Any] = {"base": base, "count": int(args.count)}
    if args.model:
        payload["model"] = args.model

    timeout = None if args.timeout is not None and args.timeout <= 0 else float(args.timeout)
    if args.verbose:
        print(f"POST {url} timeout={timeout} stream={args.stream}")
        try:
            print(f"Payload: {json.dumps(payload)}")
        except Exception:
            pass
    try:
        resp = requests.post(url, json=payload, timeout=timeout, stream=bool(args.stream))
        resp.raise_for_status()
        if args.verbose:
            try:
                print(f"Status: {resp.status_code}; Content-Length: {resp.headers.get('Content-Length')}")
            except Exception:
                pass
    except requests.HTTPError as e:
        # Try to include server-provided error detail for faster debugging
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
