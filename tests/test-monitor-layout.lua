local callbacks, gestures, animations, arranged = {}, {}, {}, {}
local executions = 0
local screens, focused
hypr_settings = { internal_scale = 1.2 }
hl = {
    get_monitors = function() return screens end,
    get_active_monitor = function() return focused end,
    on = function(event, fn)
        callbacks[event] = callbacks[event] or {}
        table.insert(callbacks[event], fn)
    end,
    exec_cmd = function() executions = executions + 1 end,
    monitor = function(spec) arranged[spec.output] = spec end,
    gesture = function(spec)
        if spec.action == "unset" then
            assert(gestures[spec.direction], "removed an unregistered gesture")
            gestures[spec.direction] = nil
        else gestures[spec.direction] = spec.action end
    end,
    animation = function(spec) animations[spec.leaf] = spec.style end,
}
local function emit(event)
    for _, fn in ipairs(callbacks[event] or {}) do fn() end
end
local function assertHorizontal(scenario)
    assert(gestures.horizontal == "workspace" and not gestures.vertical,
        scenario .. ": expected horizontal workspace gesture, got horizontal=" ..
        tostring(gestures.horizontal) .. ", vertical=" .. tostring(gestures.vertical))
    for _, leaf in ipairs({ "workspaces", "workspacesIn", "workspacesOut" }) do
        assert(animations[leaf] == "slide",
            scenario .. ": expected " .. leaf .. " slide, got " .. tostring(animations[leaf]))
    end
end
local laptop = {id=0, name="eDP-7", width=1920, height=1080, x=0, y=0}
screens, focused = {laptop}, laptop
dofile("hyprglass/desktop/monitors.lua")
assertHorizontal("laptop startup")
assert(arranged["eDP-7"].scale == 1.2)
local above = {id=1, name="DP-9", width=2560, height=1440, x=0, y=-1440}
screens = {laptop, above}
emit("monitor.added")
assert(arranged["DP-9"].position == "0x-1440")
focused = above
emit("monitor.focused")
assertHorizontal("upper display focused")
focused = laptop
emit("monitor.focused")
assertHorizontal("laptop focused with upper display attached")
emit("monitor.layout_changed")
assertHorizontal("layout changed")
local side = {id=2, name="HDMI-A-9", width=1920, height=1080, x=1600, y=0}
screens = {laptop, above, side}
emit("monitor.added")
assert(arranged["HDMI-A-9"].position == "1600x0")
focused = side
emit("monitor.focused")
assertHorizontal("side display focused")
focused, screens = laptop, {laptop}
emit("monitor.removed")
assertHorizontal("undocked")
local before = executions
screens, focused = {}, nil
emit("monitor.removed")
assert(executions == before, "empty configuration verification must not start wallpaper jobs")
screens, focused = {laptop}, laptop
emit("monitor.added")
assert(executions == before + 1, "reconnecting the same monitor must restore its wallpaper")
assertHorizontal("laptop reconnected")
callbacks, gestures, animations, arranged = {}, {}, {}, {}
screens, focused = {laptop, above}, above
dofile("hyprglass/desktop/monitors.lua")
assertHorizontal("startup with upper display focused")
assert(arranged["DP-9"].position == "0x-1440")
print("PASS: horizontal workspace motion on laptop, upper display, side display, undocking, and reconnect")
