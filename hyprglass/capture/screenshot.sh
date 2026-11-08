#!/usr/bin/env bash
set -eu

image=${1:-}
[[ -f "$image" && -s "$image" ]] || exit 0
[[ $(file --brief --mime-type -- "$image") == image/png ]] || exit 0

(
    action=$(notify-send --app-name=Hyprshot --icon="$image" \
        --expire-time=8000 --action=copy=Copy \
        'Screenshot saved' 'Saved and copied to clipboard.') || exit 0
    if [[ "$action" == copy && -r "$image" ]]; then
        wl-copy --type image/png < "$image"
    fi
) </dev/null >/dev/null 2>&1 &
