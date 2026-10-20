-- Client-side playback of BakeSceneAnimation output.
local M = {}
local function finite(v) return type(v)=="number" and v==v and math.abs(v)<math.huge end
local function modelpath(v) return type(v)=="string" and v:match("^models/.+%.mdl$") and not v:find("..",1,true) end
local function validclip(clip)
    if type(clip)~="table" or type(clip.controller)~="string" or clip.controller=="" or
       type(clip.position_controller)~="string" or clip.position_controller=="" or
       (clip.model~=nil and not modelpath(clip.model)) or
       type(clip.times)~="table" or #clip.times==0 then return false end
    for i,time in pairs(clip.times) do
        if not finite(i) or i~=math.floor(i) or i<1 or i>#clip.times or not finite(time) or
           (i>1 and (not finite(clip.times[i-1]) or time<=clip.times[i-1])) then return false end
    end
    return true
end
function M.Load(model)
    if not modelpath(model) then return nil,"expected a model path under models/" end
    local path = model:gsub("%.mdl$", ".vertexanim.json")
    local text = file.Read(path, "GAME")
    if not text then return nil, "missing vertex animation metadata: " .. path end
    local data = util.JSONToTable(text)
    if type(data)~="table" or data.schema~=1 or type(data.clips)~="table" or #data.clips==0 then
        return nil,"invalid vertex animation metadata"
    end
    for i,clip in pairs(data.clips) do
        if not finite(i) or i~=math.floor(i) or i<1 or i>#data.clips or not validclip(clip) then
            return nil,"invalid vertex animation clip"
        end
        clip.model=model
    end
    for i=1,#data.clips do
        if not validclip(data.clips[i]) then return nil,"invalid vertex animation clip" end
    end
    return data
end
function M.Sample(entity, clip, seconds)
    if not IsValid(entity) or not validclip(clip) or not finite(seconds) then return false,"invalid entity, clip or time" end
    if clip.model and (not entity.GetModel or (entity:GetModel() or ""):lower()~=clip.model:lower()) then
        return false,"clip model does not match entity"
    end
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
