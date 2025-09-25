#!/usr/bin/env python3
"""
Sanity checks for the API using Python requests (no pytest).

Subcommands:
  - health
  - riff-names
  - check-domains (supports --persist)
  - riff-and-check (supports --persist)
  - list-domains

Examples:
  python scripts/sanity_checks.py health
  python scripts/sanity_checks.py riff-names -b acme -n 3
  python scripts/sanity_checks.py check-domains -d acme.ai -d acme.com --persist
  python scripts/sanity_checks.py riff-and-check -b ashbaba -n 6 --tld .ai --tld .com --persist
  python scripts/sanity_checks.py list-domains --limit 10 --order-by conceived --desc

Env:
  API_URL (default http://127.0.0.1:8000)
  TIMEOUT or RIFF_TIMEOUT (seconds; default 30)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


def _default_timeout() -> float | None:
    raw = os.getenv("RIFF_TIMEOUT", os.getenv("TIMEOUT", "30")).strip()
    try:
        t = float(raw)
        return None if t <= 0 else t
    except Exception:
        return 30.0


def cmd_health(base: str, timeout: float | None) -> int:
    r = requests.get(f"{base}/health", timeout=timeout)
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0


def cmd_riff_names(base: str, timeout: float | None, args: argparse.Namespace) -> int:
    body: dict[str, Any] = {"base": args.base, "count": args.count}
    if args.model:
        body["model"] = args.model
    r = requests.post(f"{base}/riff-names", json=body, timeout=timeout)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0


def cmd_check_domains(base: str, timeout: float | None, args: argparse.Namespace) -> int:
    body: dict[str, Any] = {"domains": args.domain, "persist": bool(args.persist)}
    r = requests.post(f"{base}/check-domains", json=body, timeout=timeout)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0


def cmd_riff_and_check(base: str, timeout: float | None, args: argparse.Namespace) -> int:
    body: dict[str, Any] = {"base": args.base, "count": args.count, "persist": bool(args.persist)}
    if args.model:
        body["model"] = args.model
    if args.tld:
        body["tlds"] = args.tld
    r = requests.post(f"{base}/riff-and-check", json=body, timeout=timeout)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0


def cmd_list_domains(base: str, timeout: float | None, args: argparse.Namespace) -> int:
    params = {}
    if args.limit is not None:
        params["limit"] = args.limit
    if args.order_by:
        params["order_by"] = args.order_by
    if args.desc:
        params["desc"] = True
    r = requests.get(f"{base}/domains", params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if args.flat:
        for rec in data:
            name = rec.get("name") or rec.get("domain")
            available = rec.get("available")
            print(f"{name}: {available}")
    elif args.table:
        try:
            import pandas as pd  # type: ignore

            df = pd.DataFrame.from_records(data)
            # Reorder columns if present
            cols = [
                c
                for c in [
                    "domain",
                    "name",
                    "available",
                    "price",
                    "currency",
                    "price_error",
                    "error",
                    "definitive",
                    "conceived",
                ]
                if c in df.columns
            ]
            if cols:
                df = df[cols]
            print(df.to_string(index=False))
        except Exception as e:
            print(f"Failed to render table ({e}); falling back to JSON")
            print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sanity checks for the API")
    p.add_argument(
        "--server",
        default=os.getenv("API_URL", "http://127.0.0.1:8000"),
        help="Server base URL (default: %(default)s or API_URL env)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")

    pr = sub.add_parser("riff-names")
    pr.add_argument("-b", "--base", required=True)
    pr.add_argument("-n", "--count", type=int, default=3)
    pr.add_argument("-m", "--model")

    pc = sub.add_parser("check-domains")
    pc.add_argument("-d", "--domain", action="append", required=True)
    pc.add_argument("--persist", action="store_true")

    prc = sub.add_parser("riff-and-check")
    prc.add_argument("-b", "--base", required=True)
    prc.add_argument("-n", "--count", type=int, default=5)
    prc.add_argument("-m", "--model")
    prc.add_argument("--tld", action="append")
    prc.add_argument("--persist", action="store_true")

    pl = sub.add_parser("list-domains")
    pl.add_argument("--limit", type=int)
    pl.add_argument("--order-by")
    pl.add_argument("--desc", action="store_true")
    pl.add_argument("--flat", action="store_true", help="Print 'name: available' lines instead of JSON")
    pl.add_argument("--table", action="store_true", help="Pretty-print as a table using pandas")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = args.server.rstrip("/")
    timeout = _default_timeout()

    try:
        if args.cmd == "health":
            return cmd_health(base, timeout)
        if args.cmd == "riff-names":
            return cmd_riff_names(base, timeout, args)
        if args.cmd == "check-domains":
            return cmd_check_domains(base, timeout, args)
        if args.cmd == "riff-and-check":
            return cmd_riff_and_check(base, timeout, args)
        if args.cmd == "list-domains":
            return cmd_list_domains(base, timeout, args)
        print(f"Unknown command: {args.cmd}", file=sys.stderr)
        return 2
    except requests.HTTPError as e:
        detail = None
        try:
            detail = e.response.json()
        except Exception:
            detail = getattr(e.response, "text", "")
        print(f"HTTP error: {e}\n{detail}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"Request error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
