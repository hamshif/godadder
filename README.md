
Setup Instructions
=
1) Create and activate the pyenv environment (once):
   `pyenv virtualenv 3.11 godadder`
   `pyenv activate godadder`

2) Install package + dependencies into that env:
   `./package_py.sh`

3) Run tools (with the env active):
   - `src/godadder/check_godadder.py` to check a sample list and store results.
   - `src/godadder/check_nameriffer.py` or `src/godadder/riff_names.py` to generate name riffs via Ollama.
   - `src/godadder/show_domains.py` to print current DB contents.

Notes
- The installer script verifies you’re in `pyenv` env `godadder` before installing.
- Ensure Ollama is running locally; `riff_names.py` can auto-start it when needed.
