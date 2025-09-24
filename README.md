
Setup Instructions
=
1) Create and activate the pyenv environment (once):
   `pyenv virtualenv 3.11 godadder`
   `pyenv activate godadder`

2) Install package + dependencies into that env:
   `./package_py.sh`

3) Run tools (with the env active):
   - `python scripts/sanity_checks.py health` to check reachability.
   - `python scripts/sanity_checks.py riff-names -b acme -n 5` to riff names.
   - `python scripts/sanity_checks.py check-domains -d acme.ai -d acme.com --persist` to check and store.
   - `python scripts/sanity_checks.py list-domains --limit 10 --flat` to view stored rows.

Notes
- The installer script verifies you’re in `pyenv` env `godadder` before installing.
- Ensure Ollama is running locally; set `OLLAMA_URL` if non-default.
