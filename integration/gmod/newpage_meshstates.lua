-- Finite topology playback using ordinary Source bodygroups. Client-side.
local M = {}
local function finite(value)
    return type(value) == "number" and value == value and math.abs(value) < math.huge
end
local function valid(clip)
    if type(clip) ~= "table" or clip.schema ~= 1 or clip.type ~= "newpage_mesh_states" then return false end
    if type(clip.model) ~= "string" or type(clip.group) ~= "string" or type(clip.loop) ~= "boolean" then return false end
    if type(clip.states) ~= "table" or #clip.states == 0 then return false end
    if type(clip.times) ~= "table" or type(clip.sequence) ~= "table" or #clip.times == 0 or #clip.times ~= #clip.sequence then return false end
    if not finite(clip.duration) or clip.duration <= 0 or clip.times[1] ~= 0 then return false end
    for index, time in ipairs(clip.times) do
        local state = clip.sequence[index]
        if not finite(time) or (index > 1 and time <= clip.times[index - 1]) then return false end
        if not finite(state) or state ~= math.floor(state) or state < 0 or state >= #clip.states then return false end
    end
    return clip.duration > clip.times[#clip.times]
end

function M.Load(model)
    if type(model) ~= "string" or not model:match("^models/.+%.mdl$") or model:find("..", 1, true) then
        return nil, "expected a model path under models/"
    end
    local path = model:gsub("%.mdl$", ".meshstates.json")
    local text = file.Read(path, "GAME")
    if not text then return nil, "missing mesh state metadata: " .. path end
    local clip = util.JSONToTable(text)
    if not valid(clip) or clip.model:lower() ~= model:lower() then return nil, "invalid mesh state metadata" end
    return clip
end

function M.Sample(entity, clip, seconds)
    if not IsValid(entity) or not valid(clip) or not finite(seconds) then return false, "invalid entity, clip or time" end
    if (entity:GetModel() or ""):lower() ~= clip.model:lower() then return false, "clip model does not match entity" end
    local groupID
    for _, group in ipairs(entity:GetBodyGroups()) do
        if group.name == clip.group then
            if group.num ~= #clip.states then return false, "bodygroup state count does not match clip" end
            groupID = group.id
            break
        end
    end
    if groupID == nil then return false, "missing bodygroup: " .. clip.group end
    seconds = math.max(0, seconds)
    seconds = clip.loop and (seconds % clip.duration) or math.min(seconds, clip.duration)
    local index = 1
    while index < #clip.times and clip.times[index + 1] <= seconds do index = index + 1 end
    entity:SetBodygroup(groupID, clip.sequence[index])
    return true, clip.sequence[index]
end

return M
