#!/usr/bin/env bash
set -uo pipefail
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
client="$base/hyprglass/sidebar/client.sh"

want() { [ "${SWAYNC_TOGGLE_STATE:-false}" = true ]; }
emit() { if "$@"; then echo true; else echo false; fi; }

bt_on()    { bluetoothctl show 2>/dev/null | grep -q 'Powered: yes'; }
wifi_on()  { [ "$(nmcli radio wifi 2>/dev/null)" = enabled ]; }
dnd_on()   { [ "$("$client" -D 2>/dev/null)" = true ]; }
dark_on()  { [ "$(gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null)" = "'prefer-dark'" ]; }
night_on() { [ "$(gsettings get org.gnome.settings-daemon.plugins.color night-light-enabled 2>/dev/null)" = true ]; }
plane_on() { ! wifi_on && ! bt_on; }

bt_power() {
	if [ "$1" = on ]; then
		rfkill unblock bluetooth 2>/dev/null
		bluetoothctl power on
	else
		bluetoothctl power off
	fi
}

apply() {
	case $1 in
		wifi)      want && nmcli radio wifi on || nmcli radio wifi off ;;
		bluetooth) want && bt_power on || bt_power off ;;
		dnd)       want && "$client" -dn || "$client" -df ;;
		dark)      want && gsettings set org.gnome.desktop.interface color-scheme prefer-dark \
		                || gsettings set org.gnome.desktop.interface color-scheme default ;;
		night)     want && gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled true \
		                || gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled false ;;
		airplane)
			if want; then nmcli radio all off; bt_power off
			else          nmcli radio all on;  bt_power on
			fi ;;
		*) return 2 ;;
	esac
}

case "${1:-}" in
	get)
		case "${2:-}" in
			wifi)      emit wifi_on ;;
			bluetooth) emit bt_on ;;
			dnd)       emit dnd_on ;;
			dark)      emit dark_on ;;
			night)     emit night_on ;;
			airplane)  emit plane_on ;;
			*)         echo false ;;
		esac ;;
	set)
		apply "${2:-}" >/dev/null 2>&1 ;;
	*)
		printf 'usage: %s {get|set} {wifi|bluetooth|dnd|dark|night|airplane}\n' "${0##*/}" >&2
		exit 2 ;;
esac
exit 0
