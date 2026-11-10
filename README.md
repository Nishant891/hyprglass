# Hypr glass

A violet, translucent Hyprland desktop with Waybar, an app launcher, Wi-Fi and
Bluetooth menus, a notification sidebar with Markdown tasks, a calendar, a
wallpaper carousel, screenshots, recording, and optional local AI.

This repository contains the desktop configuration **and** the small applications
that make it work. The sidebar uses a custom SwayNC build for its Todo widget.

[Install](#install) · [Use](#use-and-customize) ·
[Troubleshooting](#services-and-troubleshooting) ·
[Restore](#update-restore-or-remove) ·
[Development](#repository-layout-and-development)

## Install

Automatic dependency installation supports **Arch Linux and Arch derivatives**
that identify themselves with `ID_LIKE=arch`. Other distributions can use the
manual dependency route below. A systemd user session is required.

Install Git and Python 3.11 or newer first. On Arch:

```sh
sudo pacman -Syu --needed git python
```

Clone this GitHub repository using its **Code → HTTPS** URL into a permanent
folder, for example `~/hypr-glass`. Open that folder and run as your normal user:

```sh
./install.sh --plan
./install.sh
```

`--plan` changes nothing. It shows the selected terminal, prerequisite failures,
configuration targets, and backup location. The installer then:

1. Checks commands, Python modules, GTK introspection, and supported minimum versions.
2. On Arch, offers to install missing dependencies through
   `sudo pacman -Syu --needed ...`. Pacman asks for confirmation. This includes a
   **full system upgrade**, not a partial upgrade. Existing packages that provide
   a dependency, such as a compatible `hyprland-git`, are accepted.
3. Asks the installed Hyprland to validate the actual Lua configuration, then
   builds the pinned SwayNC sidebar. A source or
   native-library change causes a rebuild. A failed build retains the previous
   built sidebar.
4. Backs up affected configuration entries under `~/.config/hypr-backup/`, then
   installs links and personal settings. It does not merge two desktops.
5. Creates `~/Pictures/Wallpaper` if needed and supplies a default image when empty.
6. Reloads systemd user unit definitions. Log out and select Hyprland to start
   the new desktop.

Keep the checkout where it is. The installed configuration links point to it.
Setup uses `~/.config/hypr`; a different `XDG_CONFIG_HOME` is rejected with an
explanation. NetworkManager, Bluetooth, and audio system services are not changed
by setup. Their setup instructions are below.

### What happens to existing configuration?

| Target | Action |
| --- | --- |
| `~/.config/hypr` | Back up the existing entry and link this checkout. If it already is this checkout, leave it in place. |
| `~/.config/ghostty` | Back up and link the included preset only when Ghostty is selected. |
| `~/.config/systemd/user/swaync.service` | Back up and link the sidebar user unit. |
| `~/.config/systemd/user/hypr-widgets.service` | Back up and link the widget user unit. |
| `~/.config/systemd/user/hypr-ollama.service` | Back up and link the optional AI user unit. |
| Checkout `local.lua` | Create it, or back it up before changing only its terminal field when needed. |

Other terminals keep their own configuration. Existing standalone Waybar, Rofi,
and Wofi configuration directories stay in place; this desktop passes its own
configuration paths to those applications.

Waybar is required and installed when missing, even if another bar is installed.
The new Hyprland startup uses Waybar. Setup does not uninstall other bars or
silently disable independently enabled user services. If a previous bar still
starts from its own service, disable that service as described in troubleshooting.

### Terminal selection

The default `--terminal auto` preserves an available terminal already selected in
this checkout's `local.lua`. Otherwise it uses the first installed terminal in
this order: Ghostty, Kitty, Foot, Alacritty, WezTerm, Konsole, XTerm. If none is
available, Arch setup installs Ghostty.

To choose explicitly:

```sh
./install.sh --terminal kitty
```

A supported missing terminal can be installed by the package manager. A custom
executable must already exist on `PATH`. Use an executable name without arguments.
Only Ghostty receives the included Ghostty preset. Kitty and other terminals use
**their own settings and appearance**. When a previously selected terminal is
missing, setup backs up `local.lua` and changes its terminal field to the chosen
fallback, preserving the other settings.

### Manual prerequisites and compatibility

To prevent package installation:

```sh
./install.sh --check
./install.sh --no-packages
```

`--check` is read-only and exits unsuccessfully when prerequisites are missing.
On unsupported distributions, install the reported requirements with your package
manager, then use `--no-packages`. Package names and development packages vary;
automatic package installation is only supported on Arch-based systems.

| Requirement | Minimum checked |
| --- | --- |
| Python | 3.11 |
| Hyprland with Lua configuration | 0.55 |
| GTK | 4.16.13 |
| GLib | 2.82 |
| gtk4-layer-shell | 1.0.4 |
| libadwaita | 1.6.1 |
| Granite 7 | 7.5.0 |
| libgee | 0.20.6 |
| JSON-GLib | 1.6 |
| Wayland | 1.23 |

The native library minimums are checked when building. Required commands include
Waybar, Wofi, Wayland Rofi, Hyprpaper, Hyprlock, NetworkManager, BlueZ tools,
PipeWire and WirePlumber, brightnessctl, libnotify, curl, Nautilus, playerctl,
wf-recorder, Hyprshot, grim, slurp, wl-clipboard, and `file`. Python needs
PyGObject and python-dbus. Fonts are Adwaita Sans and JetBrainsMono Nerd Font,
including its Propo variant.

Building also needs a C compiler, Git, Meson, Ninja, Vala, Blueprint Compiler,
sassc, pkg-config, GLib resource/schema tools, Wayland protocols, and development
files for the libraries above and libpulse. The authoritative command/package
mapping is in [`hyprglass/install/dependencies.py`](hyprglass/install/dependencies.py).

Too-old or unreadable checked versions stop installation with the detected
problem. Arch setup updates through Pacman and checks again; it never downgrades
packages or builds replacement system libraries. Other tools are checked for
presence rather than promising compatibility with every release. If a custom
package still supplies an old incompatible version after updating, upgrade that
provider yourself before retrying.

Setup also runs `Hyprland --verify-config` against this configuration with a
temporary home and runtime directory. A rejected configuration stops installation
before links change, including when a newer Hyprland changes its Lua API.

SwayNC is built from upstream **0.12.6**, commit
`1043ef98ec97a27e24192a726576fce807d2ee49`. A separately installed SwayNC package
cannot supply the custom Todo widget. The original desktop was tested with
Hyprland 0.56.2. Minimum versions are not a claim that every future release has
been tested.

## Use and customize

| Action | Control |
| --- | --- |
| Open the selected terminal | Super+Q |
| Close a window | Super+W |
| Open applications | Super+Space |
| Open local AI | Star button or Super+B |
| Open notifications, settings, and Todo | Hamburger button |
| Open the calendar | Click the date |
| Open Files | Super+E |
| Lock | Lock button beside the date |
| Change workspace | Super+1 through Super+0 |
| Move a window to a workspace | Super+Shift+1 through Super+Shift+0 |
| Choose a wallpaper | Ctrl+W |
| Start or stop recording | Sidebar Record button or Super+Shift+Print |
| Take a region screenshot | Super+Shift+S |

Personal settings live in ignored `local.lua`. Keep one literal return table,
for example:

```lua
return {
    terminal = "kitty",
    internal_scale = 1,
    open_terminal_on_start = false,
    lock_on_start = false,
}
```

Setup preserves the other fields when changing the terminal. If it cannot safely
read a dynamic terminal expression, it stops and asks for a literal executable
name. Edit settings and use Super+Shift+R to reload Hyprland.

### App appearance, notifications, and weather

Windows use 90% opacity when focused and 50% when unfocused, including newly
installed apps. An app's own transparent surfaces can make it appear more
transparent. Ghostty's preset uses an opaque background before the compositor
applies these values. Firefox and other apps keep their own internal styling.

Files uses the violet libadwaita theme through Super+E and a separate 97% focused,
92% unfocused opacity rule. Its sidebar and content toolbars share native
libadwaita spacing.

Notification popups appear at the top right below Waybar for three seconds.
Hovering pauses their timer. Normal notifications remain in the sidebar after
their popup expires. DND suppresses popups until switched off in quick settings.

The weather card below Waybar shows Kolkata, Celsius temperature, feels-like
temperature, humidity, wind speed, coordinates, and a condition icon using
[Open-Meteo](https://open-meteo.com/en/docs). It sits above the wallpaper and behind
app windows. It refreshes every ten minutes. Failed refreshes retain the last
reading marked stale; an initial failure shows Unavailable. The card measures the
gap between the workspace tabs and resource indicators once per monitor layout,
then keeps that position when Waybar labels change. Proportional positioning is
used until accessibility bounds are available.

### Todo

The sidebar `+` button opens task input. Enter saves a task. Each row has a
checkbox and a delete button. Deleting removes that checkbox line from today's
Markdown note while preserving unrelated text. Caps Lock and other typing keys
keep the input open; Escape closes the sidebar.

Notes are stored in `~/notes/daily/YYYY-MM-DD.md`. Set `HYPR_NOTES_DIR` before
starting the sidebar to select another notebook root. Up to ten recent recovery
copies are kept in `daily/.hypr-history`, with an 8 MiB budget except when the
newest copy alone is larger. To recover a deleted task, copy its line from a
recent history file back into today's note. Stale edits are refused so external
editor changes are not overwritten.

### Wallpapers and capture

Add images to `~/Pictures/Wallpaper`. The carousel supports JPG, PNG, WebP, AVIF,
JXL, and BMP; previews depend on installed image loaders. Scroll or use arrow
keys, then click the center image or press Enter. Escape cancels. Choices are
saved per monitor and the lock screen uses matching blurred backgrounds.

Screenshots are saved to `~/Pictures/Screenshots`. Recordings are saved to
`~/Videos/Recordings`. Press Record again to finish and save the recording.

### Optional local AI

Install Ollama separately if wanted. No model is downloaded automatically.
Start the server and download a model of your choice:

```sh
systemctl --user start hypr-ollama.service
./bin/hypr-glass ollama pull <model-name>
```

The dropdown lists local models and chat uses the selected model. The panel has
no web-search feature. Conversations stay in application memory and are not
saved by this project. Selection is preserved when refreshing the open panel;
it is not persisted across application restarts.

The wrapper reuses a running server at `127.0.0.1:11434`. That existing server
keeps its own storage and settings. When the wrapper starts a server, it uses
`data/ollama/models`, binds localhost, and disables Ollama cloud access. It
prefers `ollama` on `PATH`; an already unpacked `tools/ollama` is a supported local
fallback, but setup does not populate that directory.

## Services and troubleshooting

| User service | Purpose |
| --- | --- |
| `swaync.service` | Custom notification sidebar and Todo. |
| `hypr-widgets.service` | Local AI, calendar, and wallpaper picker UI. |
| `hypr-ollama.service` | Optional local AI server. |

Hyprland starts these at login; Ollama starts only when its executable exists.
They use the graphical session and do not need `systemctl --user enable`.
Failures are recorded in the user journal, rather than discarded:

```sh
systemctl --user status swaync.service hypr-widgets.service hypr-ollama.service
journalctl --user -u swaync.service -u hypr-widgets.service -b --no-pager
```

| Problem | What to check or do |
| --- | --- |
| Missing or old dependency | Run `./install.sh --check`. On Arch rerun setup to offer package updates; otherwise install the listed requirements manually. |
| A custom package is installed | Compatible packages that provide required dependencies are accepted. Upgrade an incompatible provider yourself if the configured repositories cannot update it. |
| Native sidebar fails after an upgrade | Run `./install.sh --rebuild`, then log back in. Inspect the build error and `journalctl --user -u swaync.service -b`. |
| No Wi-Fi or Bluetooth | Check `systemctl status NetworkManager bluetooth` and hardware availability. If you intend to use these backends, enable them with `sudo systemctl enable --now NetworkManager bluetooth`. Do not run competing network managers on the same interface. |
| Wi-Fi says “Connection error.” | Check the password and signal. Run `nmcli device status` and `journalctl -u NetworkManager -b` for system diagnostics. Failed attempts try to restore the previous connection. |
| No audio | Check `wpctl status` and `systemctl --user status pipewire pipewire-pulse wireplumber`. Start the installed audio services if needed. |
| Two bars appear | Hypr Glass starts Waybar. Inspect `systemctl --user list-unit-files --state=enabled`; stop and disable the old bar's own unit if it is independently enabled. |
| Wrong terminal | Run `./install.sh --terminal kitty`, substituting an installed executable. Other terminals retain their own theme. |
| Local AI is offline or empty | Install/start Ollama, download a model, and reopen the panel. Existing system Ollama retains its own model location. |
| Restore reports changed configuration | Move the changed target to a safe location yourself, then retry. Restore refuses to overwrite it. |
| Another setup or restore is running | Wait for it to finish, then retry. The operation lock is released automatically when its process exits. |

## Update, restore, or remove

Keep your changes in `local.lua`, then update from the checkout:

```sh
git pull
./install.sh
```

Setup reuses unchanged links and does not create redundant backups. It rebuilds
when source fingerprints or linked library versions change. `--rebuild` forces
that step. Log back in after installing an update.

Each configuration-changing install creates a private directory such as
`~/.config/hypr-backup/20261108T090000Z-a1b2c3d4/`. Its `manifest.json` describes
the affected paths and original entries. Original files, directories, and even
broken symlinks are preserved there. Backups are not automatically deleted.
Existing old `.before-hypr` backups from earlier versions are left alone.

List backups, then restore a listed ID from the same checkout:

```sh
./install.sh --list-backups
./install.sh --restore <backup-id>
```

Stop this desktop's user processes before removing it:

```sh
systemctl --user stop swaync.service hypr-widgets.service hypr-ollama.service
./install.sh --restore <backup-id>
```

Restore removes only recorded project links/settings and returns the saved
original entries. It checks all targets before changing them, refuses changed
targets, and can be repeated after an interrupted restore. The manifest stays as
a record. Restore older installs in reverse order when their targets overlap.
Package additions and system upgrades are **not** undone. Notes, wallpaper
libraries, models, and recordings remain untouched.

If installation fails during configuration changes, setup attempts rollback and
prints the retained backup path. If you cannot open the desktop, switch to a TTY,
log in, enter the retained checkout, and run the restore command there. A package
or build failure happens before configuration links change. When installing from
inside an already active checkout, source-code changes are managed by Git;
configuration backup does not copy the checkout's entire source history.

## Repository layout and development

Code, configuration, and owned assets live together:

```text
bin/hypr-glass              Stable command entry point
hyprland.lua               Thin Hyprland entry point
hyprlock.conf              Thin lock-screen entry point
local.example.lua          Example personal settings
hyprglass/
  assistant/               Local AI, calendar, CSS, Ollama wrapper, user units
  bluetooth/               Bluetooth menu and pairing
  wifi/                    Wi-Fi menu and connection worker
  radio/                   Shared Rofi UI, theme, and toggle icons
  sidebar/                 SwayNC config, styling, icons, service, native source
  notes/                   Markdown storage and JSON command interface
  wallpapers/              Carousel, wallpaper state, lock config, default images
  waybar/                  Bar configuration, styling, and date label
  launcher/                Wofi configuration, styling, and launch command
  terminal/ghostty/        Ghostty-specific preset
  files/                   Nautilus launcher and GTK theme
  capture/                 Recording and screenshot helpers
  desktop/                 Hyprland settings, monitors, session startup
  install/                 Dependencies, terminal settings, backups, restore
  paths.py                 Shared checkout and runtime paths
  verify.py                Optional live desktop checks
tests/                     Automated behavior checks
```

Generated local directories are intentionally separate from component source:

- `data/` contains wallpaper choices, generated sidebar/lock configuration, GTK
  compatibility CSS, private assets, and project-owned Ollama models. This is
  persistent local data, not all disposable cache.
- `tools/swaync/` contains the built sidebar, matching client, stylesheet, schema,
  upstream license, and source/library fingerprint. `tools/ollama/` is only an
  optional preexisting local executable fallback.
- `local.lua`, `data/`, `tools/`, bytecode, logs, and local audit files are ignored
  by Git. Keep personal wallpapers in `~/Pictures/Wallpaper`.

No Python package installation or `PYTHONPATH` setup is needed. All external
callers use `bin/hypr-glass`; component imports use the `hyprglass` package. To
run checks without touching your notebook or requiring a desktop:

```sh
XDG_RUNTIME_DIR=/tmp python3 -B -m unittest discover -s tests
lua tests/test-monitor-layout.lua
./install.sh --check
```

The Lua check requires a Lua interpreter. `--check` also checks live system
prerequisites, so missing optional build tools can make it fail before a first
build. The unit suite itself uses temporary homes and mocked package/service
operations.

After changing `hyprglass/sidebar/native/todo.vala` or `swaync.patch`, rebuild:

```sh
./bin/hypr-glass build-sidebar
systemctl --user restart swaync.service
```

The build validates the pinned source commit, applies the patch, compiles both
binaries, stages all runtime files, then replaces the previous build. Temporary
source/build trees are removed. Updating the pinned version requires reviewing
the patch against that upstream version. Live accessibility checks require AT-SPI
and a running desktop; see `./bin/hypr-glass verify --notes-only` for Todo checks.

## License

Original configuration, helpers, contributions, and bundled original artwork use
[MIT](LICENSE). The customized sidebar includes GPLv3 SwayNC code; root MIT does
not relicense that dependency. Its license is retained in
[`hyprglass/sidebar/native/COPYING`](hyprglass/sidebar/native/COPYING) and beside
the built binary. See [third-party notices](THIRD_PARTY.md) for the source and
license details.
