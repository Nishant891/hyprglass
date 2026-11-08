# Third-party code

The sidebar builds [SwayNotificationCenter](https://github.com/ErikReider/SwayNotificationCenter)
0.12.6 with the local patch in `hyprglass/sidebar/native/swaync.patch`.
SwayNotificationCenter is licensed under GNU GPL version 3. Its license is
included in `hyprglass/sidebar/native/COPYING`
and copied beside the built binary. The native Todo widget is part of that
patched build. Compiled binaries and downloaded source trees are not published
with this configuration.

The root [MIT license](LICENSE) covers original configuration, helpers, artwork,
and contributions in this repository. It does not replace SwayNC's license.
The customized SwayNC executable includes GPL code and is distributed under
SwayNC's GPL terms. Its build copies `COPYING` beside the executable. The source,
patch, and build instructions for that executable are retained in this project.

The bundled default wallpaper and avatar were drawn for this configuration.
Fonts and system icon themes come from packages installed by the user. Personal
wallpapers and lock-screen images are excluded from the repository.
