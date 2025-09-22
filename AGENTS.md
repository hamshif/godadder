Agent Working Agreement
=======================

Scope: applies to the entire repository.

Goals
- Provide one clean API for name riffing using PydanticAI + Ollama via HTTP.
- Keep the app easy to debug, test, and swap backends (agent implementations).

Endpoints
- POST `/riff-names`
  - Body: `{ base: str, count: int>=1<=50, model?: str }`
  - Returns: `{ names: string[] }`
  - Implementation: PydanticAI `Agent` + `FunctionModel` that calls Ollama HTTP.
- GET `/health`
  - Returns `{ ok, ollama: { reachable, model, model_present|null } }`.

Agent Pattern
- Interface: `NameRiffAgent.riff(base, count, model?) -> List[str]`.
- Default agent: uses PydanticAI `Agent` + `FunctionModel` (no provider import) and `requests` to hit Ollama’s `api/generate`.
- Dependency Injection: `get_riff_agent()` wired via FastAPI `Depends` in routes.
- Optional warm‑up on startup: set `OLLAMA_WARMUP=1`; `OLLAMA_URL` and `OLLAMA_MODEL` respected.

Dependencies
- Add dependencies in `setup.py` → `install_requires`.
- Install via `./package_py.sh` (preferably with `PYENV_VERSION=godadder`).
- Recommended pins for stability (do not change unless needed):
  - `pydantic-ai==1.0.10`
  - Optionally pin `ollama==0.5.4` if using the Python client (not required for HTTP path).

Env & Running
- Python: pyenv env `godadder` (3.11). Activate then run `./package_py.sh`.
- Start server for development/debug:
  - VS Code launch: “API (uvicorn)” in `.vscode/launch.json` (no `--reload`).
  - Equivalent CLI: `uvicorn --app-dir src godadder.gpoc:app --host 127.0.0.1 --port 8000`.
- Prefer `--app-dir src` (or set `PYTHONPATH=src`) to avoid import path issues.

Debugging
- Use VS Code “API (uvicorn)” config. Avoid `--reload` while debugging.
- Breakpoints should bind in `src/godadder/gpoc.py` (verify via Debug Console if needed).

Testing
- Unit/API tests (in‑process): `pytest -q`. Use FastAPI `TestClient` with dependency overrides.
  - Example: `tests/api/test_riff_names.py` overrides `get_riff_agent` with a fake.
- Integration test (live server): `tests/integration/test_live_riff_names.py` (marked `integration`).
  - Start server first, then: `pytest -q -s -m integration tests/integration/test_live_riff_names.py::test_live_riff_names`.
- Policy: no external network calls in unit tests; integration test talks to localhost only.

Operational Notes
- Ollama must be running for real calls: `ollama serve` and ensure model (e.g., `llama3.3:latest`) is available.
- `/health` provides quick reachability and model presence signal.

Branching & Commits
- Branch naming: `feature/<topic>`; use conventional commit messages (e.g., `feat(api): ...`, `chore: ...`).
- Squash‑merge allowed to keep history tidy — do it only after explicit confirmation/prompting.

Out of Scope Patterns
- Do not import provider‑specific modules like `pydantic_ai.llms.*` at module import time (fragile across versions). Prefer the FunctionModel + HTTP call.
- Avoid adding long‑running or blocking startup tasks in lifespan; warm‑up is best‑effort and non‑blocking.
