local topology
local internalScale = (hypr_settings and hypr_settings.internal_scale) or 1
local function arrangeMonitors()
    local monitors = hl.get_monitors()
    table.sort(monitors, function(a, b) return a.id < b.id end)
    local names = {}
    local internal
    for _, monitor in ipairs(monitors) do
        table.insert(names, monitor.name)
        if monitor.name:match("^eDP") or monitor.name:match("^LVDS") then internal = monitor end
    end
    local key = table.concat(names, ",")
    if key == topology then return end
    topology = key
    if #monitors == 0 then return end
    hl.exec_cmd("python3 -B " .. os.getenv("HOME") .. "/.config/hypr/bin/hypr-glass restore-wallpapers")
    if internal then
        hl.monitor({ output = internal.name, mode = "preferred", position = "0x0", scale = internalScale })
    end
    local externalCount = 0
    local nextX = internal and math.floor(internal.width / internalScale) or 0
    for _, monitor in ipairs(monitors) do
        if not internal or monitor.id ~= internal.id then
            externalCount = externalCount + 1
            local position
            if internal and externalCount == 1 then
                position = "0x" .. tostring(-monitor.height)
            else
                position = tostring(nextX) .. "x0"
                nextX = nextX + monitor.width
            end
            hl.monitor({ output = monitor.name, mode = "preferred", position = position, scale = 1 })
        end
    end
end
arrangeMonitors()
hl.on("monitor.added", arrangeMonitors)
hl.on("monitor.removed", arrangeMonitors)

local lastAxis
local function updateWorkspaceMotion()
    local focused = hl.get_active_monitor()
    if not focused then return end
    local vertical = false
    for _, other in ipairs(hl.get_monitors()) do
        if other.id ~= focused.id and focused.y < other.y then
            vertical = true
        end
    end
    local axis = vertical and "vertical" or "horizontal"
    if axis == lastAxis then return end
    if lastAxis then
        hl.gesture({ fingers = 3, direction = lastAxis, action = "unset" })
    end
    lastAxis = axis
    hl.gesture({ fingers = 3, direction = axis, action = "workspace" })
    for _, leaf in ipairs({ "workspaces", "workspacesIn", "workspacesOut" }) do
        hl.animation({ leaf = leaf, enabled = true, speed = 3.5,
            bezier = "easeOutQuint", style = vertical and "slidevert" or "slide" })
    end
end
for _, event in ipairs({ "monitor.focused", "monitor.layout_changed", "monitor.added", "monitor.removed" }) do
    hl.on(event, updateWorkspaceMotion)
end
updateWorkspaceMotion()
