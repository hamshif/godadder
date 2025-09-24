Scripts for local testing
=========================

All scripts default to `API_URL=http://127.0.0.1:8000` unless overridden.
Timeout defaults from `RIFF_TIMEOUT` (then `TIMEOUT`) or 30 seconds.

Prereqs
- Run the API server (fails fast if Ollama is down):
  - `uvicorn --app-dir src godadder.startup_namer:app --host 127.0.0.1 --port 8000`
- Ensure Ollama is running and the model configured by `OLLAMA_MODEL` is present.

run_integration.py
------------------
- Starts the server, waits for readiness, runs the integration test, and stops the server.

Usage
- `PYENV_VERSION=godadder python scripts/run_integration.py`
- Options:
  - `--host 127.0.0.1` (default)
  - `--port 8000` (default)
  - `--ollama-url http://127.0.0.1:11434`
  - `--model qwen2.5:0.5b`

try_riff.py
-----------
- Riff names via `/riff-names`.

Examples
- `python scripts/try_riff.py -b acme -n 5`
- `python scripts/try_riff.py aurora -n 8 --server http://127.0.0.1:8000`
- `API_URL=http://127.0.0.1:8000 python scripts/try_riff.py -n 5 -v`

try_check_domains.py
--------------------
- Check availability/price via `/check-domains`.

Examples
- `python scripts/try_check_domains.py -d acme.ai -d falafel.com`
- `python scripts/try_check_domains.py acme.ai falafel.com --server http://127.0.0.1:8000`
- `API_URL=http://127.0.0.1:8000 python scripts/try_check_domains.py -d acme.ai -d acme.com -v`

try_riff_and_check.py
---------------------
- Riff names and check domains via `/riff-and-check`.

Examples
- `python scripts/try_riff_and_check.py -b aurora -n 5`
- `python scripts/try_riff_and_check.py aurora -n 6 --tld .ai --tld .com --server http://127.0.0.1:8000`
- `API_URL=http://127.0.0.1:8000 python scripts/try_riff_and_check.py -b acme -n 5 -v`

Notes
- Use `-r/--raw` to print raw JSON responses.
- Use `-v/--verbose` for request/response details.
- Increase `--timeout` if needed.
