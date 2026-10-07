AddCSLuaFile("newpage_validation_v124/game_validation_client.lua")
AddCSLuaFile("newpage_validation_v124/newpage_vertexanim.lua")
file.CreateDir("newpage_validation_v124")
local report={schema=1,errors={}}
local rag=ents.Create("prop_ragdoll")
rag:SetModel("models/newpage_validation_v124/ragdoll.mdl")
local ground=util.TraceLine({start=Vector(0,0,10000),endpos=Vector(0,0,-30000),mask=MASK_SOLID_BRUSHONLY})
rag:SetPos(ground.HitPos+Vector(0,0,100));rag:Spawn();rag:Activate()
report.ground_z=ground.HitPos.z
report.physics_count=rag:GetPhysicsObjectCount();report.initial={}
for i=0,report.physics_count-1 do
    local object=rag:GetPhysicsObjectNum(i)
    if IsValid(object) then
        report.initial[i+1]={mass=object:GetMass(),volume=object:GetVolume()}
        object:Wake()
    else table.insert(report.errors,"invalid physics object "..i) end
end
timer.Simple(5,function()
    report.final={}
    for i=0,report.physics_count-1 do
        local object=rag:GetPhysicsObjectNum(i)
        local pos=object:GetPos();report.final[i+1]={x=pos.x,y=pos.y,z=pos.z}
        if pos.x~=pos.x or pos.y~=pos.y or pos.z~=pos.z then table.insert(report.errors,"non-finite physics position") end
        if pos.z<report.ground_z-5 then table.insert(report.errors,"physics body fell through ground") end
    end
    file.Write("newpage_validation_v124/server.json",util.TableToJSON(report,true))
end)
local dispatched=false
timer.Create("newpage_validation_v124",1,90,function()
    if dispatched then return end
    for _,ply in ipairs(player.GetHumans()) do
        dispatched=true;ply:SendLua('include("newpage_validation_v124/game_validation_client.lua")')
        timer.Remove("newpage_validation_v124")
    end
end)
concommand.Add("newpage_validation_done",function(ply)
    if not IsValid(ply) then return end
    print("NEWPAGE_VALIDATION_COMPLETE")
end)
