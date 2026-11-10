hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

local hyprDir = os.getenv("HOME") .. "/.config/hypr"

hypr_settings = { terminal = "ghostty", internal_scale = 1, open_terminal_on_start = false, lock_on_start = false }
local overrides = io.open(hyprDir .. "/local.lua", "r")
if overrides then
    overrides:close()
    for key, value in pairs(dofile(hyprDir .. "/local.lua")) do hypr_settings[key] = value end
end
local function quote(value) return "'" .. value:gsub("'", "'\\''") .. "'" end
local terminal = hypr_settings.terminal
local menu = quote(hyprDir .. "/bin/hypr-glass") .. " launcher"
hl.env("HYPR_TERMINAL", terminal)

hl.on("hyprland.start", function()
    if hypr_settings.open_terminal_on_start then hl.exec_cmd(terminal) end
    hl.exec_cmd("waybar -c " .. hyprDir .. "/hyprglass/waybar/config -s " .. hyprDir .. "/hyprglass/waybar/style.css")
    hl.exec_cmd(hyprDir .. "/bin/hypr-glass desktop")
    hl.exec_cmd("hyprpaper -c " .. quote(hyprDir .. "/hyprglass/wallpapers/hyprpaper.conf"))
    hl.exec_cmd("python3 -B " .. hyprDir .. "/bin/hypr-glass restore-wallpapers")
    if hypr_settings.lock_on_start then hl.exec_cmd("hyprlock") end
end)

hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")
hl.env("HYPRSHOT_DIR", os.getenv("HOME") .. "/Pictures/Screenshots")

hl.env("GDK_SCALE", "1")
hl.env("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
hl.env("QT_SCALE_FACTOR", "1")
hl.env("ELECTRON_OZONE_PLATFORM_HINT", "wayland")
hl.env("MOZ_ENABLE_WAYLAND", "1")
local dataDirs = { hyprDir .. "/data", hyprDir .. "/hyprglass/files" }
for path in (os.getenv("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"):gmatch("[^:]+") do
    if path ~= dataDirs[1] and path ~= dataDirs[2] then table.insert(dataDirs, path) end
end
hl.env("XDG_DATA_DIRS", table.concat(dataDirs, ":"))

hl.config({
    general = {
        gaps_in  = 3,
        gaps_out = 6,

        border_size = 2,

        col = {
            active_border   = { colors = { "rgba(d0bcffff)", "rgba(4f378bff)" }, angle = 45 },
            inactive_border = "rgba(2b2930ff)",
        },

        resize_on_border = true,

        allow_tearing = false,

        layout = "dwindle",
    },

    decoration = {
        rounding       = 16,
        rounding_power = 2,

        active_opacity   = 0.90,
        inactive_opacity = 0.50,
        dim_inactive = false,
        border_part_of_window = true,

        shadow = {
            enabled      = true,
            range        = 4,
            render_power = 3,
            color        = 0xee1a1a1a,
        },

        blur = {
            enabled           = true,
            size              = 10,
            passes            = 3,
            new_optimizations = true,
            ignore_opacity    = true,
            noise             = 0,
            contrast          = 1.0,
            brightness        = 0.70,
            vibrancy          = 0,
            popups            = true,
        },
    },

    animations = {
        enabled = true,
    },
})

hl.curve("easeOutQuint",   { type = "bezier", points = { {0.23, 1},    {0.32, 1} } })
hl.curve("easeInOutCubic", { type = "bezier", points = { {0.65, 0.05}, {0.36, 1} } })
hl.curve("linear",         { type = "bezier", points = { {0, 0},       {1, 1} } })
hl.curve("almostLinear",   { type = "bezier", points = { {0.5, 0.5},   {0.75, 1.0} } })
hl.curve("quick",          { type = "bezier", points = { {0.15, 0},    {0.1, 1} } })

hl.animation({ leaf = "global",        enabled = true, speed = 10,   bezier = "default" })
hl.animation({ leaf = "border",        enabled = true, speed = 5.39, bezier = "easeOutQuint" })
hl.animation({ leaf = "windows",       enabled = true, speed = 4.79, bezier = "easeOutQuint" })
hl.animation({ leaf = "windowsIn",     enabled = true, speed = 4.1,  bezier = "easeOutQuint",  style = "popin 87%" })
hl.animation({ leaf = "windowsOut",    enabled = true, speed = 1.49, bezier = "linear",        style = "popin 87%" })
hl.animation({ leaf = "fadeIn",        enabled = true, speed = 1.73, bezier = "almostLinear" })
hl.animation({ leaf = "fadeOut",       enabled = true, speed = 1.46, bezier = "almostLinear" })
hl.animation({ leaf = "fade",          enabled = true, speed = 3.03, bezier = "quick" })
hl.animation({ leaf = "layers",        enabled = true, speed = 3.81, bezier = "easeOutQuint" })
hl.animation({ leaf = "layersIn",      enabled = true, speed = 4,    bezier = "easeOutQuint",  style = "fade" })
hl.animation({ leaf = "layersOut",     enabled = true, speed = 1.5,  bezier = "linear",        style = "fade" })
hl.animation({ leaf = "fadeLayersIn",  enabled = true, speed = 1.79, bezier = "almostLinear" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1.39, bezier = "almostLinear" })
hl.animation({ leaf = "workspaces",    enabled = true, speed = 1.94, bezier = "almostLinear",  style = "fade" })
hl.animation({ leaf = "workspacesIn",  enabled = true, speed = 1.21, bezier = "almostLinear",  style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear",  style = "fade" })

hl.layer_rule({
    name = "waybar-glass",
    match = { namespace = "^waybar$" },
    blur = true,
    ignore_alpha = 0.05,
    xray = false,
})
hl.layer_rule({
    name = "sidebar-glass-slide",
    match = { namespace = "^swaync-control-center$" },
    blur = true,
    ignore_alpha = 0.05,
    xray = false,
    animation = "slide right",
})

for i = 1, 10 do
    hl.workspace_rule({ workspace = tostring(i), layout = "dwindle" })
end

dofile(hyprDir .. "/hyprglass/desktop/monitors.lua")

hl.config({
    dwindle = {

        preserve_split = true,
    },
})

hl.config({
    master = {
        new_status = "master",
    },
})

hl.config({
    misc = {
        force_default_wallpaper = 0,
        disable_hyprland_logo   = true,
        disable_splash_rendering = true,
    },
})

hl.config({
    ecosystem = {
        no_update_news  = true,
        no_donation_nag = true,
    },
})

hl.config({
    input = {
        kb_layout  = "us",
        kb_variant = "",
        kb_model   = "",
        kb_options = "",
        kb_rules   = "",

        follow_mouse = 1,

        sensitivity = 0,

        touchpad = {
            natural_scroll = true,
        },
    },
})

hl.config({
    gestures = {
        workspace_swipe_create_new = true,
    },
})


local mainMod = "SUPER"

hl.bind(mainMod .. " + Q",     hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + M",     hl.dsp.exit())
hl.bind(mainMod .. " + E",     hl.dsp.exec_cmd(hyprDir .. "/bin/hypr-glass files"))

hl.bind(mainMod .. " + W",         hl.dsp.window.close())
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd(menu))

hl.bind(mainMod .. " + SHIFT + R", hl.dsp.exec_cmd("hyprctl reload"))

hl.bind(mainMod .. " + Tab",       hl.dsp.focus({ workspace = "previous" }))

local screenshotNotify = " -- " .. hyprDir .. "/hyprglass/capture/screenshot.sh"

hl.bind("Print",                hl.dsp.exec_cmd("hyprshot -s -m output -m active" .. screenshotNotify))
hl.bind("SHIFT + Print",        hl.dsp.exec_cmd("hyprshot -s -m region" .. screenshotNotify))
hl.bind(mainMod .. " + Print",  hl.dsp.exec_cmd("hyprshot -s -m window -m active" .. screenshotNotify))

hl.bind(mainMod .. " + SHIFT + S", hl.dsp.exec_cmd("hyprshot -s -m region" .. screenshotNotify))

hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))

hl.bind(mainMod .. " + CTRL + left",  hl.dsp.focus({ monitor = "l" }))
hl.bind(mainMod .. " + CTRL + right", hl.dsp.focus({ monitor = "r" }))

hl.bind(mainMod .. " + SHIFT + CTRL + left",  hl.dsp.window.move({ monitor = "l" }))
hl.bind(mainMod .. " + SHIFT + CTRL + right", hl.dsp.window.move({ monitor = "r" }))

for i = 1, 10 do
    local key = i % 10
    hl.bind(mainMod .. " + " .. key,         hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

hl.bind(mainMod .. " + A",         hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + A", hl.dsp.window.move({ workspace = "special:magic" }))

hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

hl.bind("XF86AudioRaiseVolume",  hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume",  hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
hl.bind("XF86AudioMute",         hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true, repeating = true })
hl.bind("XF86AudioMicMute",      hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true, repeating = true })
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("brightnessctl s 10%+"),                           { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl s 10%-"),                           { locked = true, repeating = true })

hl.bind("XF86AudioNext",  hl.dsp.exec_cmd("playerctl next"),       { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay",  hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev",  hl.dsp.exec_cmd("playerctl previous"),   { locked = true })

hl.window_rule({
    name  = "zoom-fixes",
    match = { class = "(zoom)" },

    no_blur    = true,
    no_shadow  = true,
    opaque     = true,
    force_rgbx = true,
    immediate  = true,
})

hl.window_rule({
    name = "files-readable-glass",
    match = { class = "^org[.]gnome[.]Nautilus$" },
    opacity = "0.97 override 0.92 override",
})

hl.config({
    xwayland = {
        force_zero_scaling = true,
    },
})

hl.window_rule({

    name  = "suppress-maximize",
    match = { class = ".*" },

    suppress_event = "maximize",
})

hl.window_rule({

    name  = "xwayland-drag-fix",
    match = {
        class      = "^$",
        title      = "^$",
        xwayland   = true,
        float      = true,
        fullscreen = false,
        pin        = false,
    },

    no_focus = true,
})

for _, namespace in ipairs({ "wofi", "rofi", "hypr-assistant", "hypr-calendar", "hypr-todo", "hypr-wallpapers", "hypr-weather", "swaync-notification-window" }) do
    hl.layer_rule({ name = namespace .. "-glass", match = { namespace = "^" .. namespace .. "$" },
        blur = true, ignore_alpha = 0.05, xray = false })
end
hl.bind(mainMod .. " + B", hl.dsp.exec_cmd("python3 -B " .. hyprDir .. "/bin/hypr-glass assistant"))
hl.bind("CTRL + W", hl.dsp.exec_cmd("python3 -B " .. hyprDir .. "/bin/hypr-glass wallpapers"))
hl.bind(mainMod .. " + SHIFT + Print", hl.dsp.exec_cmd(hyprDir .. "/bin/hypr-glass record toggle"))

hl.bind(mainMod .. " + CTRL + up", hl.dsp.focus({ monitor = "u" }))
hl.bind(mainMod .. " + CTRL + down", hl.dsp.focus({ monitor = "d" }))
hl.bind(mainMod .. " + SHIFT + CTRL + up", hl.dsp.window.move({ monitor = "u" }))
hl.bind(mainMod .. " + SHIFT + CTRL + down", hl.dsp.window.move({ monitor = "d" }))
