Scripts for local testing
=========================

All scripts default to `API_URL=http://127.0.0.1:8000` unless overridden.
Timeout defaults from `RIFF_TIMEOUT` (then `TIMEOUT`) or 30 seconds.

Prereqs
- Run the API server (fails fast if Ollama is down):
  - `uvicorn --app-dir src startupper.startup_namer:app --host 127.0.0.1 --port 8000`
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

Sanity checks
-------------
Use a Python helper to sanity‑check endpoints (persist options supported):

Examples

```
PYENV_VERSION=godadder python scripts/sanity_checks.py health
PYENV_VERSION=godadder python scripts/sanity_checks.py riff-names -b acme -n 3
PYENV_VERSION=godadder python scripts/sanity_checks.py check-domains -d acme.ai -d acme.com --persist
PYENV_VERSION=godadder python scripts/sanity_checks.py riff-and-check -b ashbaba -n 6 --tld .ai --tld .com --persist
PYENV_VERSION=godadder python scripts/sanity_checks.py list-domains --limit 10 --order-by conceived --desc
PYENV_VERSION=godadder python scripts/sanity_checks.py list-domains --limit 10 --flat
```

Curl alternatives (for quick copy/paste)
----------------------------------------
Quick curl calls to verify the API locally (assumes server is running at 127.0.0.1:8000):

Start server (example):

```
PYENV_VERSION=godadder OLLAMA_URL=http://127.0.0.1:11434 \
  uvicorn --app-dir src startupper.startup_namer:app --host 127.0.0.1 --port 8000
```

Health:

```
curl -s http://127.0.0.1:8000/health | jq
```

Riff names:

```
curl -s -X POST http://127.0.0.1:8000/riff-names \
  -H 'content-type: application/json' \
  -d '{"base":"acme","count":3}' | jq
```

Check domains (persist results):

```
curl -s -X POST http://127.0.0.1:8000/check-domains \
  -H 'content-type: application/json' \
  -d '{"domains":["acme.ai","acme.com"],"persist":true}' | jq
```

Riff and check (with TLDs, persist results):

```
curl -s -X POST http://127.0.0.1:8000/riff-and-check \
  -H 'content-type: application/json' \
  -d '{"base":"ashbaba","count":6,"tlds":[".ai",".com",".ai"],"persist":true}' | jq
```

List stored domains:

```
curl -s 'http://127.0.0.1:8000/domains?limit=10&order_by=conceived&desc=true' | jq
```

Docs (OpenAPI/Swagger UI):

- Interactive docs: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Raw schema: http://127.0.0.1:8000/openapi.json
