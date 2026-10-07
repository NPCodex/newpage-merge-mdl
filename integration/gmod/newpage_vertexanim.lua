-- Client-side playback of BakeSceneAnimation output.
local M = {}
function M.Load(model)
    local path = model:gsub("%.mdl$", ".vertexanim.json")
    local text = file.Read(path, "GAME")
    if not text then return nil, "missing vertex animation metadata: " .. path end
    local data = util.JSONToTable(text)
    if not data or data.schema ~= 1 then return nil, "invalid vertex animation metadata" end
    return data
end
function M.Sample(entity, clip, seconds)
    if not IsValid(entity) or not clip or not clip.times or #clip.times == 0 then return false end
    local times = clip.times
    seconds = math.Clamp(seconds, times[1], times[#times])
    local index = 1
    while index < #times and times[index + 1] <= seconds do index = index + 1 end
    local frame = index - 1
    if index < #times then
        local span = times[index + 1] - times[index]
        if span > 0 then frame = frame + (seconds - times[index]) / span end
    end
    local strength = entity:GetFlexIDByName(clip.controller)
    local position = entity:GetFlexIDByName(clip.position_controller)
    if strength == nil or position == nil or strength < 0 or position < 0 then return false end
    entity:SetFlexWeight(strength, 1)
    local normalized = #times > 1 and frame / (#times - 1) or 0
    -- Networked flex manipulators use normalized values; native C_BaseFlex
    -- clients use the controller's authored input range (here [-1,1]).
    local manipulated = entity.HasFlexManipulatior and entity:HasFlexManipulatior()
    entity:SetFlexWeight(position, manipulated and normalized or normalized * 2 - 1)
    return true
end
return M
