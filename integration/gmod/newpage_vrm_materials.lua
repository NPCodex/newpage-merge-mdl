-- Explicit common Source shader mapping for newpage_vrm material expressions.
-- Clone materials per entity, so an expression never recolors other players.
local M = {}
local serial = 0
local function finite(v) return type(v)=="number" and v==v and math.abs(v)<math.huge end
local function values(t,n)
    if type(t)~="table" or #t~=n then return false end
    for i=1,n do if not finite(t[i]) then return false end end
    return true
end
local function vector(v,fallback)
    if v then return {v.x,v.y,v.z} end
    return {fallback[1],fallback[2],fallback[3]}
end
local function copy(t) local r={} for i,v in ipairs(t) do r[i]=v end return r end
local function property(binding)
    if binding.kind=="texture" then return "uv" end
    if binding.kind=="color" then
        if binding.property=="color" then return "color" end
        if binding.property=="emissionColor" then return "emission" end
    elseif binding.kind=="legacy" then
        if binding.property=="_Color" then return "color" end
        if binding.property=="_EmissionColor" then return "emission" end
        if binding.property=="_MainTex_ST" then return "uv" end
    end
end
local function basename(name)
    return name:gsub("\\","/"):gsub("%.vmt$",""):match("([^/]+)$"):lower()
end
function M.New(entity,data,options)
    if not IsValid(entity) then return nil,"invalid material entity" end
    options=options or {}
    local sourceNames=entity:GetMaterials()
    local required={}
    for _,expression in pairs(data.expressions) do
        for _,binding in ipairs(expression.material_binds) do required[binding.material]=true end
    end
    local entries,overrides,applied={},{},{}
    for index in pairs(required) do
        local metadata=data.materials[index+1]
        if not metadata then return nil,"missing material metadata" end
        local slots={}
        if options.slots and options.slots[index]~=nil then slots={options.slots[index]}
        else
            for i,name in ipairs(sourceNames) do
                if basename(name)==metadata.name:lower() then slots[#slots+1]=i-1 end
            end
        end
        if #slots==0 then return nil,"missing Source material for "..metadata.name end
        entries[index]={}
        for _,slot in ipairs(slots) do
            if not finite(slot) or slot~=math.floor(slot) or slot<0 or slot>=#sourceNames then return nil,"invalid material slot" end
            if overrides[slot]~=nil then return nil,"multiple VRM materials map to the same Source slot" end
            -- GMod issue #3362: the client getter reports the server value.
            -- A caller that already has a local override must provide it.
            local override=options.previousOverrides and options.previousOverrides[slot]
            if override==nil then override=entity:GetSubMaterial(slot) or "" end
            if type(override)~="string" then return nil,"invalid previous material override" end
            overrides[slot]=override
            local source=Material(override~="" and override:gsub("^!","") or sourceNames[slot+1])
            if source:IsError() then return nil,"cannot load Source material: "..sourceNames[slot+1] end
            local base=vector(source:GetVector("$color2"),metadata.base_color or {1,1,1})
            local keys=source:GetKeyValues()
            base[4]=keys["$alpha"]~=nil and source:GetFloat("$alpha") or (metadata.base_color and metadata.base_color[4] or 1)
            local emission=vector(source:GetVector("$selfillumtint"),{1,1,1})
            local uv=source:GetMatrix("$basetexturetransform")
            uv=uv and Matrix(uv) or Matrix()
            local sx,sy=uv:GetField(1,1),uv:GetField(2,2)
            local translation=uv:GetTranslation()
            -- A general rotated/skewed UV basis needs a shader-specific adapter.
            local simpleUV=math.abs(uv:GetField(1,2))+math.abs(uv:GetField(2,1))<1e-6
            serial=serial+1
            local name="newpage_vrm_entity_"..entity:EntIndex().."_"..serial
            local material=CreateMaterial(name,source:GetShader(),keys)
            applied[slot]={name=name,material=material}
            entries[index][#entries[index]+1]={slot=slot,name=name,material=material,color=base,emission=emission,
                uv={sx,sy,translation.x,translation.y},simpleUV=simpleUV,baseUV=uv}
        end
    end
    local detached=false
    local function adapter(target,bindings)
        if detached or target~=entity or not IsValid(entity) then return false,"material adapter belongs to another or removed entity" end
        local pending={}
        for index,group in pairs(entries) do
            pending[index]={}
            for i,entry in ipairs(group) do pending[index][i]={color=copy(entry.color),emission=copy(entry.emission),uv=copy(entry.uv)} end
        end
        for _,item in ipairs(bindings) do
            local binding,w=item.binding,item.weight
            if not finite(w) or w<0 or w>1 then return false,"invalid material expression weight" end
            local kind=property(binding)
            if not kind and w>0 then return false,"unsupported Source mapping for VRM material property: "..tostring(binding.property) end
            if kind then
                local target
                if kind=="uv" and binding.kind=="texture" then
                    if not values(binding.scale,2) or not values(binding.offset,2) then return false,"invalid VRM UV binding" end
                    target={binding.scale[1],binding.scale[2],binding.offset[1],binding.offset[2]}
                else
                    target=binding.target
                    if not values(target,kind=="emission" and 3 or 4) then
                        if not (kind=="emission" and values(target,4)) then return false,"invalid VRM material target" end
                    end
                end
                local group=entries[binding.material]
                if not group then return false,"unmapped VRM material index" end
                for i,entry in ipairs(group) do
                    if kind=="uv" and not entry.simpleUV and w>0 then return false,"rotated/skewed Source UV transforms require a custom adapter" end
                    local base=entry[kind];local output=pending[binding.material][i][kind]
                    for k=1,#base do output[k]=output[k]+w*(target[k]-base[k]) end
                end
            end
        end
        -- Validate every binding before touching an engine material.
        for index,group in pairs(entries) do for i,entry in ipairs(group) do
            local p=pending[index][i]
            entry.material:SetVector("$color2",Vector(math.max(0,p.color[1]),math.max(0,p.color[2]),math.max(0,p.color[3])))
            entry.material:SetFloat("$alpha",math.Clamp(p.color[4],0,1))
            entry.material:SetVector("$selfillumtint",Vector(math.max(0,p.emission[1]),math.max(0,p.emission[2]),math.max(0,p.emission[3])))
            local uv=Matrix(entry.baseUV)
            uv:SetField(1,1,p.uv[1]);uv:SetField(2,2,p.uv[2]);uv:SetTranslation(Vector(p.uv[3],p.uv[4],0))
            entry.material:SetMatrix("$basetexturetransform",uv)
            entity:SetSubMaterial(entry.slot,"!"..entry.name)
        end end
        return true
    end
    local function detach()
        if IsValid(entity) then for slot,value in pairs(overrides) do entity:SetSubMaterial(slot,value) end end
        detached=true
    end
    return adapter,detach,{materials=applied,previousOverrides=overrides}
end
return M
