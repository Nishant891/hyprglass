#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
exec wofi --conf "$base/hyprglass/launcher/config" --style "$base/hyprglass/launcher/style.css" \
    --term "${HYPR_TERMINAL:-ghostty}" --show drun
