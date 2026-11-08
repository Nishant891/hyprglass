#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
session_vars=()
for name in WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE; do
    if [[ -v $name ]]; then session_vars+=("$name"); fi
done
if ((${#session_vars[@]})); then systemctl --user import-environment "${session_vars[@]}"; fi
systemctl --user start swaync.service hypr-widgets.service
if command -v ollama >/dev/null || [[ -x "$base/tools/ollama/usr/bin/ollama" ]]; then
    systemctl --user start hypr-ollama.service
fi
