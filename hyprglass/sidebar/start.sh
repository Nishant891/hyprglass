#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
binary="$base/tools/swaync/bin/swaync"
if [[ ! -x "$binary" ]]; then
    echo 'Run ./install.sh to build the sidebar.' >&2
    exit 1
fi
export GSK_RENDERER=gl
export GSETTINGS_SCHEMA_DIR="$base/tools/swaync/schemas"
style=$("$base/bin/hypr-glass" sidebar-style hyprglass/sidebar/style.css)
config=$("$base/bin/hypr-glass" sidebar-config)
exec "$binary" --custom-system-css "$base/tools/swaync/style.css" -c "$config" -s "$style"
