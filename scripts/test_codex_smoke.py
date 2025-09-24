#!/usr/bin/env python3
"""
Codex sandbox-safe smoke test for core name riffing logic (no pytest, no ASGI).

- Validates the riff handler logic with a fake agent
- Checks Pydantic validation behavior
- Prints key versions for traceability
"""

from __future__ import annotations

import sys
import json


def print_versions():
    pyver = sys.version.split()[0]
    print(f"Python: {pyver}")

    try:
        import fastapi  # type: ignore

        print(f"fastapi: {getattr(fastapi, '__version__', 'unknown')}")
    except Exception:
        print("fastapi: not available")

    try:
        import starlette  # type: ignore

        print(f"starlette: {getattr(starlette, '__version__', 'unknown')}")
    except Exception:
        print("starlette: not available")

    try:
        import anyio  # type: ignore

        print(f"anyio: {getattr(anyio, '__version__', 'unknown')}")
    except Exception:
        print("anyio: not available")

    try:
        import httpx  # type: ignore

        print(f"httpx: {getattr(httpx, '__version__', 'unknown')}")
    except Exception:
        print("httpx: not available")


def run_smoke():
    from fastapi import Response
    from pydantic import ValidationError
    import godadder.gpoc as gpoc

    print(f"App version: {getattr(gpoc.app, 'version', 'unknown')}")

    # 1) Success path via direct handler call with a fake agent
    class FakeAgent(gpoc.NameRiffAgent):
        def riff(self, base: str, count: int, model: str | None = None):
            return [f"{base}-{i+1}.ai" for i in range(count)]

    req = gpoc.RiffRequest(base="Acme", count=3)
    out = gpoc.riff_names(req, Response(), agent=FakeAgent())
    print("success:", json.dumps(out.model_dump(), ensure_ascii=False))

    # 2) Validation errors
    try:
        gpoc.RiffRequest()  # type: ignore[call-arg]
        print("validation-missing: UNEXPECTED PASS")
    except ValidationError:
        print("validation-missing: OK")

    try:
        gpoc.RiffRequest(base="Acme", count=0)
        print("validation-count: UNEXPECTED PASS")
    except ValidationError:
        print("validation-count: OK")

    # 3) Model override tracked via fake agent
    class FakeAgent2(gpoc.NameRiffAgent):
        def riff(self, base: str, count: int, model: str | None = None):
            assert model == "llamaX"
            return [f"{base}-{i+1}.ai" for i in range(count)]

    out2 = gpoc.riff_names(gpoc.RiffRequest(base="Acme", count=2, model="llamaX"), Response(), agent=FakeAgent2())
    print("model-override:", json.dumps(out2.model_dump(), ensure_ascii=False))


if __name__ == "__main__":
    print_versions()
    run_smoke()

