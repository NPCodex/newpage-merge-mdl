-- Client-side VRM 0/1 adapter. Install alongside newpage_vrm metadata.
-- This is an explicit GMod runtime, not an engine-native VRM extension.
local M = {}
local categories = {
    overrideBlink = {blink=true, blinkLeft=true, blinkRight=true, blink_l=true, blink_r=true},
    overrideLookAt = {lookUp=true, lookDown=true, lookLeft=true, lookRight=true, lookup=true, lookdown=true, lookleft=true, lookright=true},
    overrideMouth = {aa=true, ih=true, ou=true, ee=true, oh=true, a=true, i=true, u=true, e=true, o=true}
}
local function vec(t) return Vector(t[1], t[2], t[3]) end
local function direction(matrix, v)
    return matrix:GetForward()*v.x - matrix:GetRight()*v.y + matrix:GetUp()*v.z
end
local function position(matrix, v) return matrix:GetTranslation()+direction(matrix,v) end
local function inversePosition(matrix,v)
    local d=v-matrix:GetTranslation()
    return Vector(d:Dot(matrix:GetForward()), -d:Dot(matrix:GetRight()), d:Dot(matrix:GetUp()))
end
local function finite(x) return type(x)=="number" and x==x and math.abs(x)<math.huge end
function M.Load(model)
    local path=model:gsub("%.mdl$", ".vrm.json")
    local raw=file.Read(path,"GAME")
    local data=raw and util.JSONToTable(raw)
    if not data or data.schema~=1 or data.type~="newpage_vrm" then return nil,"invalid/missing VRM metadata: "..path end
    return data
end
function M.ResolveExpressions(data, weights)
    local values, factors = {}, {overrideBlink=1,overrideLookAt=1,overrideMouth=1}
    for name,e in pairs(data.expressions) do
        local w=weights[name] or 0
        if not finite(w) then return nil,"non-finite expression weight" end
        w=math.Clamp(w,0,1)
        if e.binary then w=w>.5 and 1 or 0 end
        values[name]=w
        for category,mode in pairs(e.overrides) do
            if mode=="block" and w>0 then factors[category]=0
            elseif mode=="blend" then factors[category]=math.max(0,factors[category]-w) end
        end
    end
    local controls, materials = {}, {}
    for name,e in pairs(data.expressions) do
        local w=values[name]
        for category,names in pairs(categories) do if names[name] then w=w*factors[category] end end
        for _,b in ipairs(e.binds) do controls[b.controller]=(controls[b.controller] or 0)+w*b.weight end
        for _,b in ipairs(e.material_binds) do materials[#materials+1]={binding=b,weight=w} end
    end
    for name,w in pairs(controls) do controls[name]=math.Clamp(w,0,1) end
    return controls,materials
end
-- Material properties are delivered to an explicit adapter because MToon and
-- arbitrary Unity shader parameters have no universal Source shader mapping.
function M.SetExpressions(entity,data,weights,materialAdapter)
    if not IsValid(entity) then return false,"invalid entity" end
    local controls,materials=M.ResolveExpressions(data,weights)
    if not controls then return false,materials end
    local ids={}
    for name in pairs(controls) do
        local id=entity:GetFlexIDByName(name)
        if id==nil or id<0 then return false,"missing VRM flex controller: "..name end
        ids[name]=id
    end
    if #materials>0 and not materialAdapter then return false,"VRM material expressions require a material adapter" end
    if materialAdapter then
        local ok,err=materialAdapter(entity,materials,data.materials)
        if ok==false then return false,err end
    end
    for name,w in pairs(controls) do entity:SetFlexWeight(ids[name],w) end
    return true
end
function M.SampleClip(entity,data,seconds,loop,materialAdapter)
    local clip=data.clip
    if not clip or not finite(seconds) then return false,"missing clip/invalid time" end
    seconds=math.max(0,seconds)
    if loop and clip.duration>0 then seconds=seconds%clip.duration end
    seconds=math.min(seconds,clip.duration)
    local f=seconds*clip.fps; local a=math.min(math.floor(f)+1,#clip.samples)
    local b=math.min(a+1,#clip.samples)
    -- The last baked sample is at duration, which need not land on 1/fps.
    local begin=(a-1)/clip.fps;local finish=math.min(a/clip.fps,clip.duration)
    local u=b>a and finish>begin and math.Clamp((seconds-begin)/(finish-begin),0,1) or 0
    local weights={}
    for name in pairs(data.expressions) do weights[name]=(clip.samples[a][name] or 0)*(1-u)+(clip.samples[b][name] or 0)*u end
    return M.SetExpressions(entity,data,weights,materialAdapter)
end
local function rotated(v,axis,c,s)
    return v*c + axis:Cross(v)*s + axis*axis:Dot(v)*(1-c)
end
local function align(matrix,from,to)
    local a,b=from:GetNormalized(),to:GetNormalized()
    local c=math.Clamp(a:Dot(b),-1,1);local cross=a:Cross(b);local s=cross:Length()
    if s<1e-8 then
        if c>0 then return matrix end
        cross=a:Cross(math.abs(a.x)<.9 and Vector(1,0,0) or Vector(0,1,0));s=0
    end
    local axis=cross:GetNormalized();local m=Matrix(matrix)
    m:SetForward(rotated(matrix:GetForward(),axis,c,s))
    m:SetRight(rotated(matrix:GetRight(),axis,c,s))
    m:SetUp(rotated(matrix:GetUp(),axis,c,s))
    return m
end
local function project(origin,tail,length,fallback)
    local d=tail-origin
    if d:LengthSqr()<1e-12 then d=fallback end
    return origin+d:GetNormalized()*length
end
local function collide(tail,radius,collider,matrix)
    local a=position(matrix,vec(collider.offset));local closest=a
    if collider.shape=="capsule" then
        local b=position(matrix,vec(collider.tail));local ab=b-a;local length=ab:LengthSqr()
        if length>1e-12 then closest=a+ab*math.Clamp((tail-a):Dot(ab)/length,0,1) end
    end
    local delta=tail-closest;local minimum=radius+collider.radius
    if delta:LengthSqr()<minimum*minimum then
        if delta:LengthSqr()<1e-12 then delta=Vector(1,0,0) end
        tail=closest+delta:GetNormalized()*minimum
    end
    return tail
end
function M.NewSpringState(entity,data)
    if not IsValid(entity) then return nil,"invalid entity" end
    local state={data=data,bones={},tails={},parents={},order={}}
    local function resolve(name)
        if state.bones[name]~=nil then return true end
        local id=entity:LookupBone(name)
        if id==nil or id<0 then return false,"missing spring bone: "..name end
        state.bones[name]=id;return true
    end
    for _,spring in ipairs(data.springs) do
        if spring.center then local ok,err=resolve(spring.center);if not ok then return nil,err end end
        for _,joint in ipairs(spring.joints) do local ok,err=resolve(joint.bone);if not ok then return nil,err end end
    end
    for _,c in ipairs(data.colliders) do local ok,err=resolve(c.bone);if not ok then return nil,err end end
    -- Topological traversal works even when the compiler preserves a bone order
    -- in which a parent has a larger numeric index than its child.
    local active,done,rank={},{},{}
    local function visit(i)
        if done[i] then return true end
        if active[i] then return false,"cyclic engine skeleton" end
        active[i]=true;local p=entity:GetBoneParent(i);state.parents[i]=p
        if p and p>=0 then
            if p>=entity:GetBoneCount() then return false,"invalid engine bone parent" end
            local ok,err=visit(p);if not ok then return false,err end
        end
        active[i]=nil;done[i]=true;state.order[#state.order+1]=i
        rank[i]=#state.order
        return true
    end
    for i=0,entity:GetBoneCount()-1 do local ok,err=visit(i);if not ok then return nil,err end end
    state.joints={}
    for _,spring in ipairs(data.springs) do
        for _,joint in ipairs(spring.joints) do state.joints[#state.joints+1]={spring=spring,joint=joint} end
    end
    -- Parent simulation must precede child simulation across spring groups as
    -- well as within a group; otherwise descendant propagation erases a child.
    table.sort(state.joints,function(a,b) return rank[state.bones[a.joint.bone]]<rank[state.bones[b.joint.bone]] end)
    return state
end
function M.StepSprings(entity,state,seconds)
    if not IsValid(entity) or not finite(seconds) or seconds<0 then return false,"invalid spring step" end
    if entity.GetModelScale and math.abs(entity:GetModelScale()-1)>1e-5 then return false,"bake entity scale before VRM spring playback" end
    if seconds>.25 then state.tails={};seconds=0 end
    local original,current={},{}
    for _,i in ipairs(state.order) do
        local matrix=entity:GetBoneMatrix(i)
        if not matrix then return false,"spring step needs built bone matrices" end
        original[i]=Matrix(matrix);current[i]=Matrix(matrix)
    end
    local function descendants(parent)
        local changed={[parent]=true}
        for _,i in ipairs(state.order) do
            local p=state.parents[i]
            if changed[p] then
                current[i]=current[p]*original[p]:GetInverse()*original[i];changed[i]=true
            end
        end
    end
    local steps=math.max(1,math.ceil(seconds*60));local dt=seconds/steps
    for _,entry in ipairs(state.joints) do
        local spring,j=entry.spring,entry.joint
        local center=spring.center and current[state.bones[spring.center]] or nil
            local id=state.bones[j.bone];local matrix=current[id];local origin=matrix:GetTranslation()
            local rest=direction(matrix,vec(j.tail));local length=rest:Length()
            local history=state.tails[j.bone]
            local tail=history and (center and position(center,history.now) or history.now) or origin+rest
            local previous=history and (center and position(center,history.previous) or history.previous) or tail
            local gravity=vec(j.gravity_dir)
            -- Gravity is in model space, then rotated into this entity's world.
            if entity.LocalToWorld then gravity=entity:LocalToWorld(gravity)-entity:LocalToWorld(Vector(0,0,0)) end
            for _=1,steps do
                local candidate=tail+(tail-previous)*(1-j.drag)+rest:GetNormalized()*(j.stiffness*dt)+gravity*(j.gravity*dt)
                candidate=project(origin,candidate,length,rest)
                for _=1,2 do
                    for _,ci in ipairs(spring.colliders) do
                        local c=state.data.colliders[ci+1]
                        candidate=collide(candidate,j.radius,c,current[state.bones[c.bone]])
                    end
                    candidate=project(origin,candidate,length,rest)
                end
                previous=tail;tail=candidate
            end
            if seconds==0 and history then tail=center and position(center,history.now) or history.now;previous=center and position(center,history.previous) or history.previous end
            state.tails[j.bone]={now=center and inversePosition(center,tail) or tail,previous=center and inversePosition(center,previous) or previous}
            current[id]=align(matrix,rest,tail-origin);descendants(id)
    end
    for _,i in ipairs(state.order) do entity:SetBoneMatrix(i,current[i]) end
    return true
end
function M.Attach(entity,data)
    local state,err=M.NewSpringState(entity,data)
    if not state then return nil,err end
    local last=SysTime();local frame=-1
    local callback=entity:AddCallback("BuildBonePositions",function(ent)
        local now=SysTime();local dt=FrameNumber()==frame and 0 or math.max(0,now-last)
        if FrameNumber()~=frame then last=now;frame=FrameNumber() end
        local ok,message=M.StepSprings(ent,state,dt)
        if not ok and state.error~=message then state.error=message;ErrorNoHalt("newpage_vrm: "..message.."\n") end
    end)
    return {state=state,detach=function() if IsValid(entity) then entity:RemoveCallback("BuildBonePositions",callback) end end}
end
return M
