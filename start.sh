#!/bin/sh
# Group16 one-click start (macOS / Linux). Needs Python 3.11+.
# Options are passed through, e.g.:  ./start.sh --port 9000   ./start.sh --minimal   ./start.sh --reset
set -e
cd "$(dirname "$0")"

PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$c"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "[group16] Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/"
    exit 1
fi

venv_python() {
    # Git Bash / MSYS on Windows creates .venv/Scripts instead of .venv/bin
    if [ -x .venv/bin/python ]; then echo .venv/bin/python; elif [ -x .venv/Scripts/python.exe ]; then echo .venv/Scripts/python.exe; fi
}

VPY="$(venv_python)"
if [ -n "$VPY" ] && ! "$VPY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    echo "[group16] The existing .venv is broken or too old, recreating it..."
    rm -rf .venv
    VPY=""
fi
if [ -z "$VPY" ]; then
    echo "[group16] Creating virtual environment with $PY ..."
    "$PY" -m venv .venv
    VPY="$(venv_python)"
fi

exec "$VPY" scripts/dev.py "$@"
