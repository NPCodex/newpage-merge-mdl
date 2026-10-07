-- Explicitly invoked by game_validation_server.lua in an isolated listen server.
local report = {schema=1, cases={}, errors={}}
local pending = {
    {name="face_neutral", model="models/newpage_validation_v124/face.mdl", lod=0, weight=0},
    {name="face_neutral_repeat", model="models/newpage_validation_v124/face.mdl", lod=0, weight=0},
    {name="face_expression", model="models/newpage_validation_v124/face.mdl", lod=0, weight=1},
    {name="face_lod1", model="models/newpage_validation_v124/face.mdl", lod=1, weight=1},
    {name="ragdoll_lod0", model="models/newpage_validation_v124/ragdoll.mdl", lod=0},
    {name="ragdoll_lod1", model="models/newpage_validation_v124/ragdoll.mdl", lod=1},
    {name="bake_start", model="models/newpage_validation_v124/baked.mdl", time=0},
    {name="bake_middle", model="models/newpage_validation_v124/baked.mdl", time=.5},
    {name="bake_end", model="models/newpage_validation_v124/baked.mdl", time=1}
}
local playback = include("newpage_validation_v124/newpage_vertexanim.lua")
file.CreateDir("newpage_validation_v124")
local model, current, ready, camera, target
local function finish()
    if IsValid(model) then model:Remove() end
    hook.Remove("RenderScene", "newpage_validation_v124")
    hook.Remove("PostRender", "newpage_validation_v124")
    file.Write("newpage_validation_v124/client.json", util.TableToJSON(report, true))
    RunConsoleCommand("newpage_validation_done")
end
local function nextCase()
    if IsValid(model) then model:Remove() end
    current=table.remove(pending,1)
    if not current then finish() return end
    model=ClientsideModel(current.model,RENDERGROUP_OPAQUE)
    if not IsValid(model) then table.insert(report.errors,current.name..": invalid model") nextCase() return end
    model:SetNoDraw(true);model:SetPos(Vector(0,0,0));model:SetAngles(Angle(0,0,0))
    model:SetMaterial("models/debug/debugwhite");model:SetSequence(0);model:SetCycle(0)
    model:SetFlexScale(1)
    if current.lod then model:SetLOD(current.lod) end
    for i=0,model:GetFlexNum()-1 do
        local name=model:GetFlexName(i):lower()
        if name:find("blink") or name:find("close") or name:find("smile") then model:SetFlexWeight(i,current.weight or 0) end
    end
    if current.time then
        local meta,err=playback.Load(current.model)
        if not meta or not playback.Sample(model,meta.clips[1],current.time) then table.insert(report.errors,current.name..": "..(err or "playback failed")) end
    end
    model:SetupBones()
    local lo,hi=model:GetModelBounds();target=(lo+hi)*.5
    local radius=math.max((hi-lo):Length(),4)
    camera=target+Vector(0,-radius*1.4,radius*.8)
    if current.name:find("face") then
        local bone=model:LookupBone("ValveBiped.Bip01_Head1")
        if bone then target=model:GetBonePosition(bone);camera=target+Vector(25,-5,2) end
    end
    current.bones=model:GetBoneCount();current.flexes=model:GetFlexNum()
    ready=RealTime()+.3
end
hook.Add("RenderScene","newpage_validation_v124",function()
    if not IsValid(model) then return end
    if current and current.time then
        local meta=playback.Load(current.model)
        playback.Sample(model,meta.clips[1],current.time)
        current.weights={model:GetFlexWeight(0),model:GetFlexWeight(1)}
    end
    render.Clear(24,36,56,255,true,true)
    cam.Start3D(camera,(target-camera):Angle(),45,0,0,ScrW(),ScrH(),.1,10000)
    render.SuppressEngineLighting(true);render.ResetModelLighting(.8,.8,.8)
    render.SetModelLighting(0,1,1,1);render.SetModelLighting(4,.4,.4,.4)
    model:SetupBones();model:DrawModel()
    render.SuppressEngineLighting(false);cam.End3D()
    return true
end)
hook.Add("PostRender","newpage_validation_v124",function()
    if not current or RealTime()<ready then return end
    local data=render.Capture({format="png",x=0,y=0,w=ScrW(),h=ScrH(),alpha=false})
    if data then file.Write("newpage_validation_v124/"..current.name..".png",data);current.image_crc=util.CRC(data)
    else table.insert(report.errors,current.name..": capture failed") end
    table.insert(report.cases,current);current=nil
    timer.Simple(.1,nextCase)
end)
timer.Simple(2,nextCase)
