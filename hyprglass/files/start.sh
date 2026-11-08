#!/usr/bin/env bash
set -e
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
export XDG_DATA_DIRS="$base/data:$base/hyprglass/files:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export GTK_THEME=HyprViolet:dark
exec nautilus --new-window "$@"
