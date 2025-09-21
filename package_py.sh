#!/bin/bash
# package_py.sh - Install the package into the active Python (pyenv 'godadder' recommended)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure we are inside the expected pyenv environment if pyenv is available
if command -v pyenv >/dev/null 2>&1; then
  current_env="$(pyenv version-name)"
  if [[ "${current_env}" != "godadder" ]]; then
    echo "[!] Detected pyenv environment: ${current_env}"
    echo "[!] Please activate the 'godadder' env first:"
    echo "    pyenv virtualenv 3.11 godadder   # once"
    echo "    pyenv activate godadder"
    echo "Or rerun with PYENV_VERSION=godadder prefixed."
    exit 1
  fi
fi

echo "Using Python: $(command -v python)"
python -m pip install -e "${SCRIPT_DIR}"
echo "Install complete."
