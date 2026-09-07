#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
command -v python3 >/dev/null 2>&1 || {
    echo "error: required command not found: python3" >&2
    exit 2
}
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "error: Python 3.10 or later is required" >&2
    exit 2
}
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$ROOT/tools/pipeline.py" "$@"
