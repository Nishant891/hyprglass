#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
if [[ " $* " == *' -rs '* || " $* " == *' --reload-css '* ]]; then
    "$base/bin/hypr-glass" sidebar-style hyprglass/sidebar/style.css >/dev/null
fi
if [[ " $* " == *' -R '* || " $* " == *' --reload-config '* ]]; then
    "$base/bin/hypr-glass" sidebar-config >/dev/null
fi
exec "$base/tools/swaync/bin/swaync-client" "$@"
