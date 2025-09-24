#!/usr/bin/env python3
"""
Run the live integration test against a locally started server.

- Starts uvicorn (FastAPI app)
- Waits for readiness
- Runs the integration test
- Shuts the server down

Usage examples:
- PYENV_VERSION=godadder python scripts/run_integration.py
- PYENV_VERSION=godadder python scripts/run_integration.py --ollama-url http://127.0.0.1:11434 --model qwen2.5:0.5b
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import shutil
import subprocess as sp
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run integration test with a local server")
    p.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p.add_argument("--port", default="8000", help="Server port (default: 8000)")
    p.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"), help="Ollama base URL")
    p.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b"), help="Ollama model name")
    p.add_argument("--ready-timeout", type=float, default=10.0, help="Seconds to wait for server readiness")
    return p.parse_args()


def ensure_pyenv_env():
    pyenv = shutil.which("pyenv")
    if not pyenv:
        return
    try:
        current = sp.check_output([pyenv, "version-name"], text=True).strip()
    except Exception:
        return
    if current != "godadder":
        print("[!] Detected pyenv environment:", current, file=sys.stderr)
        print("[!] Please activate 'godadder' (or prefix PYENV_VERSION=godadder).", file=sys.stderr)
        sys.exit(1)


def start_server(repo_root: Path, host: str, port: str, env: dict[str, str], log_file: Path) -> int:
    uvicorn = shutil.which("uvicorn")
    if not uvicorn:
        print("[error] uvicorn not found in PATH", file=sys.stderr)
        sys.exit(1)

    args = [
        uvicorn,
        "--app-dir",
        str(repo_root / "src"),
        "startupper.startup_namer:app",
        "--host",
        host,
        "--port",
        port,
        "--log-config",
        str((repo_root / "conf" / "logging.dev.json")),
        "--log-level",
        "debug",
    ]

    log_fh = open(log_file, "w")
    proc = sp.Popen(args, stdout=log_fh, stderr=sp.STDOUT, env=env)
    return proc.pid


def wait_ready(base_url: str, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(f"{base_url}/openapi.json", timeout=0.5)
            if r.status_code == 200:
                print("[ready] API is up")
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def run_integration(repo_root: Path, api_base_url: str, env: dict[str, str]) -> int:
    # Run via 'python -m pytest' to avoid shell/entrypoint quirks
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-s",
        "-m",
        "integration",
        str(repo_root / "tests" / "integration" / "test_live_riff_names.py::test_live_riff_names"),
    ]
    return sp.call(cmd, env=env)


def main() -> int:
    args = parse_args()
    ensure_pyenv_env()

    repo_root = Path(__file__).resolve().parents[1]
    api_base = f"http://{args.host}:{args.port}"

    env = os.environ.copy()
    env["API_BASE_URL"] = api_base
    env["OLLAMA_URL"] = args.ollama_url
    env["OLLAMA_MODEL"] = args.model

    print(f"[run] Using Python: {shutil.which('python')}")
    print(f"[run] API: {api_base} | OLLAMA_URL={env['OLLAMA_URL']} | OLLAMA_MODEL={env['OLLAMA_MODEL']}")

    log_file = Path("/tmp/godadder_uvicorn.log")
    pid = start_server(repo_root, args.host, args.port, env, log_file)

    try:
        if not wait_ready(api_base, args.ready_timeout):
            print("[error] API did not become ready in time", file=sys.stderr)
            try:
                print("[logs] tail:")
                with open(log_file, "r") as fh:
                    lines = fh.readlines()[-120:]
                    sys.stdout.write("".join(lines))
            except Exception:
                pass
            return 1

        print("[run] Running integration test...")
        rc = run_integration(repo_root, api_base, env)
        if rc != 0:
            print("[error] Integration test failed. Showing server logs:", file=sys.stderr)
            try:
                with open(log_file, "r") as fh:
                    lines = fh.readlines()[-200:]
                    sys.stdout.write("".join(lines))
            except Exception:
                pass
            return rc
        print("[ok] Integration test passed.")
        return 0
    finally:
        try:
            os.kill(pid, 15)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
