Quick Resume
============

- pyenv activate: `pyenv activate godadder`
- install deps: `./package_py.sh`
- run tests: `pytest -q`
- start server (debug): use VS Code "API (uvicorn)" launch
- call API:
  - Health: `curl -s http://127.0.0.1:8000/health | jq .`
  - Riff: `curl -s -X POST http://127.0.0.1:8000/riff-names -H 'Content-Type: application/json' -d '{"base":"Aurorify","count":3}' | jq .`

