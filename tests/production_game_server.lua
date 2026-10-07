local config=include("newpage_production_validation/config.lua")
AddCSLuaFile("newpage_production_validation/config.lua")
AddCSLuaFile("newpage_production_validation/client.lua")
file.CreateDir("newpage_production_validation")
local report={schema=1,cases={},errors={}}
local ground=util.TraceLine({start=Vector(0,0,10000),endpos=Vector(0,0,-30000),mask=MASK_SOLID_BRUSHONLY})
for i,path in ipairs(config.models) do
    local spawn=Vector(i*100,0,0)
    local ground=util.TraceLine({start=spawn+Vector(0,0,10000),endpos=spawn+Vector(0,0,-30000),mask=MASK_SOLID_BRUSHONLY})
    local entity=ents.Create("prop_ragdoll")
    entity:SetModel(path);entity:SetPos(ground.HitPos+Vector(i*100,0,100));entity:Spawn();entity:Activate()
    local case={model=path,count=entity:GetPhysicsObjectCount(),ground_z=ground.HitPos.z,initial={}}
    for n=0,case.count-1 do
        local body=entity:GetPhysicsObjectNum(n)
        if IsValid(body) then local p=body:GetPos();table.insert(case.initial,{x=p.x,y=p.y,z=p.z,mass=body:GetMass(),volume=body:GetVolume()}) end
    end
    table.insert(report.cases,case)
    if case.count==0 then table.insert(report.errors,"no physics bodies: "..path) end
    timer.Simple(10,function()
        case.bodies={}
        for n=0,case.count-1 do
            local body=entity:GetPhysicsObjectNum(n)
            if not IsValid(body) then table.insert(report.errors,"invalid physics body")
            else
                local p=body:GetPos()
                local floor=util.TraceLine({start=p+Vector(0,0,100),endpos=p-Vector(0,0,1000),mask=MASK_SOLID_BRUSHONLY})
                table.insert(case.bodies,{x=p.x,y=p.y,z=p.z,mass=body:GetMass(),volume=body:GetVolume(),speed=body:GetVelocity():Length(),floor_z=floor.HitPos.z,drift=(p-Vector(case.initial[n+1].x,case.initial[n+1].y,p.z)):Length()})
                if p.x~=p.x or p.y~=p.y or p.z~=p.z or (floor.Hit and p.z<floor.HitPos.z-10) then table.insert(report.errors,"invalid settled body: "..path) end
            end
        end
        entity:Remove();file.Write("newpage_production_validation/server.json",util.TableToJSON(report,true))
    end)
end
timer.Create("newpage_production_validation",1,90,function()
    for _,ply in ipairs(player.GetHumans()) do
        ply:SendLua('include("newpage_production_validation/client.lua")')
        timer.Remove("newpage_production_validation");break
    end
end)
concommand.Add("newpage_production_done",function(ply)
    if IsValid(ply) then print("NEWPAGE_PRODUCTION_VALIDATION_COMPLETE") end
end)
