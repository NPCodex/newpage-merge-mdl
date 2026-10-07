local config = include("newpage_production_validation/config.lua")
local report = {schema=1, cases={}, errors={}, materials={}}
file.CreateDir("newpage_production_validation")
local pending = {}
for _, path in ipairs(config.models) do
    local probe=ClientsideModel(path)
    if not IsValid(probe) then table.insert(report.errors,"invalid model: "..path)
    else
        probe:SetNoDraw(true)
        local missing={}
        for _,name in ipairs(probe:GetMaterials()) do
            if Material(name):IsError() then table.insert(missing,name) end
        end
        table.insert(report.materials,{model=path,missing=missing})
        table.insert(pending,{model=path,name="neutral",skin=0})
        table.insert(pending,{model=path,name="expression",skin=0,expression=true})
        table.insert(pending,{model=path,name="face_neutral",skin=0,face=true})
        table.insert(pending,{model=path,name="face_repeat",skin=0,face=true})
        table.insert(pending,{model=path,name="face_expression",skin=0,face=true,expression=true})
        if probe:SkinCount()>1 then table.insert(pending,{model=path,name="last_skin",skin=probe:SkinCount()-1}) end
        for _,group in ipairs(probe:GetBodyGroups()) do
            if group.num>1 then
                table.insert(pending,{model=path,name="body_"..group.id,group=group.id,choice=group.num-1})
            end
        end
        table.insert(pending,{model=path,name="lod1",lod=1})
        probe:Remove()
    end
end
local model,current,camera,target,ready
local function finish()
    if IsValid(model) then model:Remove() end
    hook.Remove("RenderScene","newpage_production_validation")
    hook.Remove("PostRender","newpage_production_validation")
    file.Write("newpage_production_validation/client.json",util.TableToJSON(report,true))
    RunConsoleCommand("newpage_production_done")
end
local function nextCase()
    if IsValid(model) then model:Remove() end
    current=table.remove(pending,1)
    if not current then finish() return end
    model=ClientsideModel(current.model);model:SetNoDraw(true)
    model:SetPos(vector_origin);model:SetAngles(angle_zero)
    model:SetSequence(0);model:SetCycle(0);model:SetFlexScale(1)
    model:SetSkin(current.skin or 0);model:SetLOD(current.lod or 0)
    if current.group then
        model:SetBodygroup(current.group,current.choice)
        current.selected=model:GetBodygroup(current.group)
        if current.selected~=current.choice then table.insert(report.errors,current.model..": selection mismatch "..current.name) end
    end
    for i=0,model:GetFlexNum()-1 do
        local name=model:GetFlexName(i):lower()
        if name:find("blink") or name:find("close") or name:find("smile") then model:SetFlexWeight(i,current.expression and 1 or 0) end
    end
    model:SetupBones()
    local lo,hi=Vector(math.huge,math.huge,math.huge),Vector(-math.huge,-math.huge,-math.huge)
    for i=0,model:GetBoneCount()-1 do
        local matrix=model:GetBoneMatrix(i)
        if matrix then
            local pos=matrix:GetTranslation()
            lo.x=math.min(lo.x,pos.x);lo.y=math.min(lo.y,pos.y);lo.z=math.min(lo.z,pos.z)
            hi.x=math.max(hi.x,pos.x);hi.y=math.max(hi.y,pos.y);hi.z=math.max(hi.z,pos.z)
        end
    end
    if lo.x==math.huge then lo,hi=model:GetModelBounds() end
    target=(lo+hi)*.5
    camera=target+Vector(0,-math.max((hi-lo):Length()+40,50)*1.6,10)
    if current.face then
        local bone=model:LookupBone("ValveBiped.Bip01_Head1")
        if bone then target=model:GetBonePosition(bone);camera=target+Vector(25,-5,2) end
    end
    local meshes=util.GetModelMeshes(current.model,current.lod or 0)
    current.triangles=0
    for _,mesh in ipairs(meshes or {}) do current.triangles=current.triangles+#mesh.triangles/3 end
    current.bones=model:GetBoneCount();current.flexes=model:GetFlexNum();current.skin=model:GetSkin()
    -- Large production materials may still upload after Material():IsError().
    -- Warm the first view before capturing it; later cases reuse loaded textures.
    ready=RealTime()+(current.name=="neutral" and 2 or .2)
end
hook.Add("RenderScene","newpage_production_validation",function()
    if not IsValid(model) then return end
    render.Clear(24,36,56,255,true,true)
    cam.Start3D(camera,(target-camera):Angle(),45,0,0,ScrW(),ScrH(),.1,10000)
    render.SuppressEngineLighting(true);render.ResetModelLighting(.8,.8,.8)
    model:SetupBones();model:DrawModel()
    render.SuppressEngineLighting(false);cam.End3D()
    return true
end)
hook.Add("PostRender","newpage_production_validation",function()
    if not current or RealTime()<ready then return end
    local name=(current.model:match("/([^/]+)%.mdl$") or "model").."_"..current.name
    local png=render.Capture({format="png",x=0,y=0,w=ScrW(),h=ScrH(),alpha=false})
    if png then file.Write("newpage_production_validation/"..name..".png",png);current.image=name..".png"
    else table.insert(report.errors,"capture failed: "..name) end
    table.insert(report.cases,current);current=nil;timer.Simple(.1,nextCase)
end)
timer.Simple(2,nextCase)
