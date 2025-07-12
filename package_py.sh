#!/bin/bash
# package.sh - Install the package from anywhere

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pip install -e "$SCRIPT_DIR"
