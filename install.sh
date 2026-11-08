#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null; then
    echo 'Python 3 is required. Install python with your distribution package manager, then run ./install.sh again.' >&2
    exit 1
fi
exec python3 -B "$base/bin/hypr-glass" setup "$@"
