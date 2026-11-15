# Hypr glass

A violet, translucent Hyprland desktop with Waybar, an app launcher, Wi-Fi and
Bluetooth menus, a notification sidebar with Markdown tasks, weather, a calendar,
a wallpaper picker, screen capture, and optional local AI.

## Install

Use an Arch-based Linux system with a systemd user session. Automatic dependency
installation supports Arch and its derivatives. Other distributions need manual
dependencies. Python 3.11+ and Hyprland 0.55+ with Lua configuration are required.

```sh
sudo pacman -Syu --needed git python
git clone https://github.com/Nishant891/hyprglass.git ~/hypr-glass
cd ~/hypr-glass
./install.sh --plan
./install.sh
```

Run setup as your normal user. It offers missing dependencies through Pacman,
including a full system upgrade, builds the custom SwayNC sidebar, and backs up
replaced configuration under `~/.config/hypr-backup/`. Log out and select Hyprland.
Keep the checkout in place because installed configuration links point to it.

Use `./install.sh --terminal kitty` to choose a terminal. Only Ghostty receives
the included terminal theme. To install dependencies yourself, run
`./install.sh --check`, resolve the reported requirements, then run
`./install.sh --no-packages`.

## Controls

| Action | Control |
| --- | --- |
| Open terminal | Super+Q |
| Open applications | Super+Space |
| Close window | Super+W |
| Open Files | Super+E |
| Change workspace | Three-finger swipe left or right, or Super+1 through Super+0 |
| Move window to workspace | Super+Shift+1 through Super+Shift+0 |
| Open notifications, quick settings, and Todo | Hamburger button |
| Open calendar | Click the date |
| Lock screen | Lock button beside the date |
| Choose wallpaper | Ctrl+W |
| Take region screenshot | Super+Shift+S |
| Start or stop recording | Sidebar Record button or Super+Shift+Print |
| Open local AI | Star button or Super+B |
| Reload configuration | Super+Shift+R |

## Customize

Edit ignored `local.lua`, then reload with Super+Shift+R.

```lua
return {
	terminal = "kitty",
	internal_scale = 1,
	open_terminal_on_start = false,
	lock_on_start = false,
}
```

- Add wallpapers to `~/Pictures/Wallpaper`. Choices are saved per monitor.
- Todo saves tasks in `~/notes/daily/YYYY-MM-DD.md`.
- Screenshots go to `~/Pictures/Screenshots` and recordings to `~/Videos/Recordings`.
- Desktop settings and keybindings live in `hyprglass/desktop/config.lua`.

For local AI, install Ollama separately and download a model. No model is included.

```sh
systemctl --user start hypr-ollama.service
./bin/hypr-glass ollama pull <model-name>
```

## Troubleshoot

Run `./install.sh --check` for missing or incompatible dependencies. After a native
sidebar failure, run `./install.sh --rebuild` and log back in.

```sh
hyprctl configerrors
systemctl --user status swaync.service hypr-widgets.service
journalctl --user -u swaync.service -u hypr-widgets.service -b --no-pager
```

For Wi-Fi, Bluetooth, or audio problems, check NetworkManager, Bluetooth, and
PipeWire services. Setup does not enable system services. If two bars appear,
disable the previous bar's startup service.

## Update or restore

Keep personal settings in `local.lua`. To update, run these from the checkout,
then log back in.

```sh
git pull
./install.sh
```

To restore a previous configuration, choose an ID from the backup list.

```sh
./install.sh --list-backups
systemctl --user stop swaync.service hypr-widgets.service hypr-ollama.service
./install.sh --restore <backup-id>
```

Restore refuses to overwrite changed targets. It preserves personal data and
does not undo package installations or system upgrades.

## License

Original code and artwork use [MIT](LICENSE). The custom SwayNC sidebar uses
GPLv3. See [third-party notices](THIRD_PARTY.md).
