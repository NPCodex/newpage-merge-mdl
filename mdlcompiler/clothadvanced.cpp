#include "clothadvanced.h"
#include "format/cloth.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>

namespace pulse::cloth {
namespace {
namespace disk = pulse::format::cloth;
using V=math::Vector3;
[[noreturn]] void fail(const std::string& s){throw std::runtime_error("cloth advanced: "+s);}
std::string lower(std::string s){for(char& c:s)if(c>='A'&&c<='Z')c+=char('a'-'A');return s;}
V sub(V a,V b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
float length(V v){return std::sqrt(v.x*v.x+v.y*v.y+v.z*v.z);}
void xyz(float* a,V v){a[0]=v.x;a[1]=v.y;a[2]=v.z;}
struct Parser {
    const std::vector<std::string>& tokens;size_t at=0;float scale;
    std::string next(){if(at==tokens.size())fail("unexpected end of advanced block");return tokens[at++];}
    void expect(const char* s){if(next()!=s)fail(std::string("expected ")+s);}
    float number(float min=0,float max=1e6f){std::string s=next();size_t n=0;float f;
        try{f=std::stof(s,&n);}catch(...){fail("expected number, got "+s);}
        if(n!=s.size()||!std::isfinite(f)||f<min||f>max)fail("number out of range: "+s);return f;}
    float distance(){return number()*scale;}
    int integer(int max){float f=number(0,float(max));if(f!=std::floor(f))fail("expected integer");return int(f);}
    bool boolean(){auto s=lower(next());if(s=="true"||s=="1")return true;if(s=="false"||s=="0")return false;fail("expected true or false");}
    V vector(float factor){return {number(-1e6f)*factor,number(-1e6f)*factor,number(-1e6f)*factor};}
    std::string name(){auto s=next();if(s.empty()||s=="{"||s=="}")fail("expected node name");return s;}
};
bool any(const AdvancedSettings& s){return !s.nodes.empty()||!s.rods.empty()||!s.springs.empty()||!s.ropes.empty()||!s.follows.empty()||!s.osOffsets.empty()||!s.spheres.empty()||!s.planes.empty()||!s.capsules.empty()||!s.rigids.empty()||s.ftl||s.uninertial||s.massDamping||s.volumetric>=0||s.worldRadius>=0||s.addWorldRadius!=0||s.rodSmoothIterations>=0||s.quadSmoothIterations>=0;}
template<class T>std::vector<T> read(const std::vector<uint8_t>& bytes,const disk::Descriptor& d,size_t field){
    disk::Array a;std::memcpy(&a,reinterpret_cast<const uint8_t*>(&d)+field,sizeof(a));
    if(!a.count)return {};
    int64_t begin=int64_t(field)+a.offset;uint64_t end=uint64_t(begin)+uint64_t(a.count)*sizeof(T);
    if(begin<int64_t(sizeof(d))||end>bytes.size())fail("invalid input FE array");
    std::vector<T> out(a.count);std::memcpy(out.data(),bytes.data()+begin,out.size()*sizeof(T));return out;
}
template<class T>void write(std::vector<uint8_t>& bytes,disk::Descriptor& d,size_t field,const std::vector<T>& data){
    disk::Array a{};
    if(!data.empty()){
        if(data.size()>65535)fail("FE array exceeds 65535 entries");
        size_t at=(bytes.size()+alignof(T)-1)&~(alignof(T)-1);
        if(at+sizeof(T)*data.size()>size_t(std::numeric_limits<int32_t>::max()))fail("FE resource too large");
        bytes.resize(at+sizeof(T)*data.size());std::memcpy(bytes.data()+at,data.data(),sizeof(T)*data.size());
        a={int32_t(at-field),uint32_t(data.size())};
    }
    std::memcpy(reinterpret_cast<uint8_t*>(&d)+field,&a,sizeof(a));
}
template<class T>void pairReplace(std::vector<T>& v,const T& item){
    auto same=[&](const T& x){return std::minmax(x.node[0],x.node[1])==std::minmax(item.node[0],item.node[1]);};
    v.erase(std::remove_if(v.begin(),v.end(),same),v.end());v.push_back(item);
}
}

const AdvancedNode* FindAdvancedNode(const AdvancedSettings& s,const std::string& name){
    auto key=lower(name);for(const auto& n:s.nodes)if(lower(n.name)==key)return &n;return nullptr;
}
bool HasAdvanced(const AdvancedSettings& s){return any(s);}
float AdvancedMass(const AdvancedSettings& s,const std::string& name,float mass){
    if(auto n=FindAdvancedNode(s,name))mass=(n->mass>=0?n->mass:mass)*n->massMultiplier;
    if(!std::isfinite(mass)||mass<=1e-8f)fail("invalid mass for "+name);return mass;
}
bool ParseAdvanced(AdvancedSettings& original,const std::vector<std::string>& tokens,float scale,std::string* error){
    try{
        if(!std::isfinite(scale)||scale<=0||scale>1e6f)fail("invalid QC scale");
        auto s=original;Parser p{tokens,0,scale};
        while(p.at<tokens.size()){
            auto op=lower(p.next());
            if(op=="node"){
                auto name=p.name();AdvancedNode n;auto prev=FindAdvancedNode(s,name);if(prev)n=*prev;else n.name=name;
                p.expect("{");bool closed=false;
                while(p.at<tokens.size()){
                    auto key=lower(p.next());if(key=="}"){closed=true;break;}
                    if(key=="simulated"){n.simulated=p.boolean();n.hasSimulated=true;}
                    else if(key=="position"){n.position=p.vector(scale);n.hasPosition=true;}
                    else if(key=="parent")n.parent=p.name();
                    else if(key=="mass")n.mass=p.number(1e-7f);
                    else if(key=="mass_multiplier")n.massMultiplier=p.number(1e-7f);
                    else if(key=="local_position")n.localPosition=p.number(0,1);
                    else if(key=="local_rotation")n.localRotation=p.number(0,1);
                    else if(key=="damping")n.damping=p.number();
                    else if(key=="gravity")n.gravity=p.number();
                    else if(key=="force_attract")n.forceAttraction=p.number();
                    else if(key=="vertex_attract")n.vertexAttraction=p.number();
                    else if(key=="collision_radius")n.collisionRadius=p.distance();
                    else if(key=="collision_mask")n.collisionMask=p.integer(65535);
                    else if(key=="legacy_stretch")n.legacyStretch=p.number();
                    else fail("unsupported node option "+key);
                }
                if(!closed)fail("unterminated node block");
                bool replaced=false;for(auto& old:s.nodes)if(lower(old.name)==lower(name)){old=n;replaced=true;break;}if(!replaced)s.nodes.push_back(n);
            }else if(op=="rod"){
                AdvancedRod r;r.node[0]=p.name();r.node[1]=p.name();
                if(p.at<tokens.size()&&lower(tokens[p.at])=="auto")++p.at;else r.length=p.distance();
                r.contraction=p.number(0,1);r.bias[0]=p.number();r.bias[1]=p.number();r.relaxation=p.number(0,1);s.rods.push_back(r);
            }else if(op=="spring"){
                AdvancedSpring v;v.node[0]=p.name();v.node[1]=p.name();v.stiffness=p.number();v.damping=p.number();s.springs.push_back(v);
            }else if(op=="rope"){
                p.expect("{");std::vector<std::string> rope;bool closed=false;
                while(p.at<tokens.size()){auto n=p.next();if(n=="}"){closed=true;break;}if(n=="{"||n.empty())fail("invalid rope node");rope.push_back(n);}
                if(!closed||rope.size()<2)fail("rope needs a root and at least one child");s.ropes.push_back(rope);
            }else if(op=="follow"||op=="os_offset"){
                AdvancedFollow v;v.parent=p.name();v.child=p.name();if(op=="follow"){v.weight=p.number(0,1);s.follows.push_back(v);}else s.osOffsets.push_back(v);
            }else if(op=="node_sphere"){
                AdvancedSphere v;v.parent=p.name();v.child=p.name();auto mode=lower(p.next());if(mode!="in"&&mode!="out")fail("node_sphere expects in or out");v.inclusive=mode=="in";
                v.center=p.vector(scale);v.radius=p.distance();if(v.radius<=1e-6f)fail("sphere radius must be positive");s.spheres.push_back(v);
            }else if(op=="node_plane"){
                AdvancedPlane v;v.parent=p.name();v.child=p.name();v.normal=p.vector(1);v.offset=p.number(-1e6f)*scale;
                float len=length(v.normal);if(len<1e-6f)fail("plane normal is zero");v.normal={v.normal.x/len,v.normal.y/len,v.normal.z/len};v.offset/=len;s.planes.push_back(v);
            }else if(op=="stretch_capsule"){
                AdvancedCapsule v;v.node[0]=p.name();v.node[1]=p.name();v.radius[0]=p.distance();v.radius[1]=p.distance();v.mask=uint16_t(p.integer(65535));v.stickiness=p.number(0,1);s.capsules.push_back(v);
            }else if(op=="rigid_sphere"||op=="rigid_capsule"){
                AdvancedRigid v;v.node=p.name();v.capsule=op=="rigid_capsule";v.center[0]=p.vector(scale);v.radius[0]=p.distance();
                if(v.capsule){v.center[1]=p.vector(scale);v.radius[1]=p.distance();}v.mask=uint16_t(p.integer(65535));v.stickiness=p.number(0,1);s.rigids.push_back(v);
            }else if(op=="ftl")s.ftl=p.boolean();
            else if(op=="uninertial")s.uninertial=p.boolean();
            else if(op=="mass_damping")s.massDamping=p.boolean();
            else if(op=="volumetric")s.volumetric=p.number(0,1);
            else if(op=="world_radius")s.worldRadius=p.distance();
            else if(op=="add_world_radius")s.addWorldRadius=p.distance();
            else if(op=="smoothing"){s.rodSmoothIterations=p.integer(65535);s.quadSmoothIterations=p.integer(65535);}
            else fail("unsupported command "+op);
            if(s.nodes.size()>8192||s.rods.size()+s.springs.size()+s.spheres.size()+s.planes.size()+s.capsules.size()+s.rigids.size()>65535)fail("authoring limit exceeded");
        }
        original=std::move(s);return true;
    }catch(const std::exception& e){if(error)*error=e.what();return false;}
}

std::vector<std::string> AdvancedReferencedBones(const AdvancedSettings& s){
    std::map<std::string,std::string> names;
    auto add=[&](const std::string& name){if(name.empty()||lower(name).rfind("$cloth_p",0)==0)return;auto n=FindAdvancedNode(s,name);if(n&&n->hasPosition)return;names.emplace(lower(name),name);};
    for(auto& n:s.nodes){add(n.name);add(n.parent);}for(auto& r:s.rods){add(r.node[0]);add(r.node[1]);}for(auto& r:s.springs){add(r.node[0]);add(r.node[1]);}
    for(auto& r:s.ropes)for(auto& n:r)add(n);for(auto& f:s.follows){add(f.parent);add(f.child);}for(auto& f:s.osOffsets){add(f.parent);add(f.child);}
    for(auto& c:s.spheres){add(c.parent);add(c.child);}for(auto& c:s.planes){add(c.parent);add(c.child);}for(auto& c:s.capsules){add(c.node[0]);add(c.node[1]);}for(auto& c:s.rigids)add(c.node);
    std::vector<std::string> out;for(auto& p:names)out.push_back(p.second);return out;
}

bool AppendAdvancedResource(const AdvancedSettings& s,const std::vector<AdvancedNodeInfo>& nodes,std::vector<uint8_t>& resource,std::string* error){
    try{
        if(!any(s))return true;
        if(resource.size()<sizeof(disk::Descriptor))fail("advanced authoring requires FE nodes");
        auto bytes=resource;disk::Descriptor d;std::memcpy(&d,bytes.data(),sizeof(d));
        if(d.nodeCount!=nodes.size()||d.staticNodes>=d.nodeCount)fail("invalid FE node partition");
        std::map<std::string,uint16_t> ids;for(size_t i=0;i<nodes.size();++i)if(!ids.emplace(lower(nodes[i].name),uint16_t(i)).second)fail("duplicate FE node "+nodes[i].name);
        auto node=[&](const std::string& name){auto f=ids.find(lower(name));if(f==ids.end())fail("unknown FE node "+name);return f->second;};
        auto dynamic=[&](uint16_t n){if(n<d.staticNodes||nodes[n].invMass<=0)fail("constraint child must be simulated: "+nodes[n].name);};
        auto distinct=[&](uint16_t a,uint16_t b){if(a==b)fail("constraint endpoints must differ");};
#define READ(T,field) read<T>(bytes,d,offsetof(disk::Descriptor,field))
#define WRITE(field,value) write(bytes,d,offsetof(disk::Descriptor,field),value)
        auto integrators=READ(disk::Integrator,nodeIntegrator);integrators.resize(nodes.size());
        auto offsets=READ(disk::CtrlOffset,ctrlOffsets);
        std::vector<float> locals(nodes.size()-d.staticNodes,d.localForce),rotations(nodes.size()-d.staticNodes,d.localRotation);
        auto oldLocals=READ(float,localForces),oldRotations=READ(float,localRotations);if(!oldLocals.empty())locals=oldLocals;if(!oldRotations.empty())rotations=oldRotations;
        auto radii=READ(float,nodeCollisionRadii);radii.resize(nodes.size()-d.staticNodes,0);
        auto legacy=READ(float,legacyStretch);legacy.resize(nodes.size(),0);
        auto masks=READ(uint16_t,treeMasks);const size_t dyn=nodes.size()-d.staticNodes;
        if(masks.size()!=dyn*2-1)fail("invalid collision tree mask size");
        bool localChanged=false,radiiChanged=false,legacyChanged=false,masksChanged=false;
        for(const auto& n:s.nodes){
            auto i=node(n.name);auto& integrator=integrators[i];
            if(n.hasSimulated&&n.simulated!=(i>=d.staticNodes))fail("simulated override was not applied before node ordering: "+n.name);
            if(n.damping>=0)integrator.damping=n.damping;if(n.gravity>=0)integrator.gravity=n.gravity;
            if(n.forceAttraction>=0)integrator.forceAttraction=n.forceAttraction;if(n.vertexAttraction>=0)integrator.vertexAttraction=n.vertexAttraction;
            if(i>=d.staticNodes){size_t j=i-d.staticNodes;
                if(n.localPosition>=0){locals[j]=n.localPosition;localChanged=true;}if(n.localRotation>=0){rotations[j]=n.localRotation;localChanged=true;}
                if(n.collisionRadius>=0){radii[j]=n.collisionRadius;radiiChanged=true;}
                if(n.collisionMask>=0){masks[j]=uint16_t(n.collisionMask);masksChanged=true;}
                if(n.legacyStretch>=0){legacy[i]=n.legacyStretch;legacyChanged=true;}
            }
            if(n.hasPosition&&!n.parent.empty()){
                uint16_t parent=node(n.parent);distinct(parent,i);disk::CtrlOffset o;o.parent=parent;o.child=i;
                xyz(o.position,math::VectorITransform(nodes[i].position,nodes[parent].pose));
                offsets.erase(std::remove_if(offsets.begin(),offsets.end(),[&](auto& x){return x.child==i;}),offsets.end());offsets.push_back(o);
            }
        }
        if(localChanged){
            auto extrema=std::minmax_element(locals.begin(),locals.end());d.localForce=*extrema.second;
            // Source1 SetAbsOrigin gates the per-node loop on (1-localForce)!=0.
            // A heterogeneous array whose maximum is 1 otherwise never runs for
            // ordinary movement. Keep authored responses exact in the array and
            // use the smallest representable positive gate for the outer loop.
            if(*extrema.first<1&&d.localForce==1)d.localForce=std::nextafter(1.0f,0.0f);
            d.localRotation=*std::max_element(rotations.begin(),rotations.end());WRITE(localForces,locals);WRITE(localRotations,rotations);
        }
        if(radiiChanged)WRITE(nodeCollisionRadii,radii);
        if(legacyChanged){WRITE(legacyStretch,legacy);d.dynamicFlags|=1u<<4;if(std::any_of(legacy.begin(),legacy.end(),[](float x){return x!=0;}))d.dynamicFlags|=1u<<12;}
        if(masksChanged){
            std::fill(masks.begin()+dyn,masks.end(),0);auto parents=READ(uint16_t,treeParents);if(parents.size()!=masks.size())fail("invalid collision tree parents");
            for(size_t i=0;i<dyn;++i){uint16_t p=parents[i];size_t steps=0;while(p!=65535){if(p>=masks.size()||++steps>masks.size())fail("invalid collision tree parent");masks[p]|=masks[i];p=parents[p];}}
            WRITE(treeMasks,masks);
        }
        if(s.ftl)d.dynamicFlags|=1u<<5;if(s.uninertial)d.dynamicFlags|=1u<<4;
        if(s.volumetric>=0)d.volumetricSolve=s.volumetric;
        if(s.worldRadius>=0)d.worldCollisionRadius=s.worldRadius;
        d.worldCollisionRadius+=s.addWorldRadius;
        if(s.rodSmoothIterations>=0)d.rodSmoothIterations=uint16_t(s.rodSmoothIterations);
        if(s.quadSmoothIterations>=0)d.quadSmoothIterations=uint16_t(s.quadSmoothIterations);

        auto rods=READ(disk::Rod,rods);bool rodsChanged=false;
        auto makeRod=[&](uint16_t a,uint16_t b,float rest,float contraction,float bias0,float bias1,float relaxation,bool replace){
            distinct(a,b);float total=bias0*nodes[a].invMass+bias1*nodes[b].invMass;
            if(total<=1e-9f||relaxation==0)return;
            disk::Rod rod;rod.node[0]=a;rod.node[1]=b;rod.maxDistance=rest<0?length(sub(nodes[a].position,nodes[b].position)):rest;
            if(rod.maxDistance<=1e-6f)fail("zero length rod");rod.minDistance=rod.maxDistance*contraction;rod.weight0=bias0*nodes[a].invMass/total;rod.relaxation=relaxation;
            if(replace)pairReplace(rods,rod);else {auto pair=std::minmax(a,b);if(std::none_of(rods.begin(),rods.end(),[&](auto& r){return std::minmax(r.node[0],r.node[1])==pair;}))rods.push_back(rod);}rodsChanged=true;
        };
        std::vector<std::vector<uint16_t>> ropeIds;std::set<uint16_t> ropeChildren;
        for(const auto& rope:s.ropes){
            std::vector<uint16_t> chain;std::set<uint16_t> seen;
            for(const auto& name:rope){auto i=node(name);if(!seen.insert(i).second)fail("rope repeats a node");chain.push_back(i);}
            if(chain.size()<2)fail("rope needs at least two nodes");
            if(chain[0]>=d.staticNodes)fail("rope root must be fixed");
            for(size_t i=1;i<chain.size();++i){dynamic(chain[i]);if(nodes[chain[i]].fit)fail("rope cannot also use a matrix-fit control");if(!ropeChildren.insert(chain[i]).second)fail("rope child belongs to two ropes");makeRod(chain[i-1],chain[i],-1,1,1,1,1,false);}
            ropeIds.push_back(chain);
        }
        for(auto& r:s.rods)makeRod(node(r.node[0]),node(r.node[1]),r.length,r.contraction,r.bias[0],r.bias[1],r.relaxation,true);
        if(rodsChanged){
            std::vector<disk::SimdRod> packed;for(auto& r:rods){disk::SimdRod p;for(int lane=0;lane<4;++lane){p.node[0][lane]=r.node[0];p.node[1][lane]=r.node[1];p.maxDistance[lane]=r.maxDistance;p.minDistance[lane]=r.minDistance;p.weight0[lane]=r.weight0;p.relaxation[lane]=r.relaxation;}packed.push_back(p);}WRITE(rods,rods);WRITE(simdRods,packed);
        }
        if(!ropeIds.empty()){
            if(d.ropeCount)fail("cannot append rope declarations twice");
            std::vector<uint16_t> indices(ropeIds.size());for(size_t i=0;i<ropeIds.size();++i){indices.insert(indices.end(),ropeIds[i].begin(),ropeIds[i].end());if(indices.size()>65535)fail("too many rope indices");indices[i]=uint16_t(indices.size());}
            d.ropeCount=uint16_t(ropeIds.size());WRITE(ropes,indices);
            auto free=READ(uint16_t,freeNodes);free.erase(std::remove_if(free.begin(),free.end(),[&](auto n){return ropeChildren.count(n)!=0;}),free.end());WRITE(freeNodes,free);
        }
        if(!s.springs.empty()){
            auto springs=READ(disk::Spring,springs);
            for(auto& r:s.springs){uint16_t a=node(r.node[0]),b=node(r.node[1]);distinct(a,b);
                float w0=nodes[a].invMass*std::exp(-integrators[a].damping),w1=nodes[b].invMass*std::exp(-integrators[b].damping),sum=w0+w1;
                if(sum<=1e-20f||r.stiffness+r.damping==0)continue;disk::Spring spring;spring.node[0]=a;spring.node[1]=b;
                spring.restLength=length(sub(nodes[a].position,nodes[b].position));spring.stiffness=r.stiffness*sum;spring.damping=r.damping*sum;spring.weight0=w0/sum;pairReplace(springs,spring);
            }
            std::vector<disk::SimdSpring> packed;for(auto& r:springs){disk::SimdSpring p;for(int lane=0;lane<4;++lane){p.node[0][lane]=r.node[0];p.node[1][lane]=r.node[1];p.restLength[lane]=r.restLength;p.stiffness[lane]=r.stiffness;p.damping[lane]=r.damping;p.weight0[lane]=r.weight0;}packed.push_back(p);}WRITE(springs,springs);WRITE(simdSprings,packed);
        }
        if(!s.follows.empty()){
            auto follows=READ(disk::FollowNode,followNodes);for(auto& f:s.follows){auto a=node(f.parent),b=node(f.child);distinct(a,b);dynamic(b);follows.erase(std::remove_if(follows.begin(),follows.end(),[&](auto& x){return x.child==b;}),follows.end());if(f.weight>0)follows.push_back({a,b,f.weight});}
            // Follow edges may form a DAG, but never a cycle. Order parents before children.
            std::map<uint16_t,disk::FollowNode> pending;for(auto& f:follows)pending.emplace(f.child,f);std::vector<disk::FollowNode> sorted;
            while(!pending.empty()){bool progress=false;for(auto it=pending.begin();it!=pending.end();){if(pending.count(it->second.parent)==0){sorted.push_back(it->second);it=pending.erase(it);progress=true;}else ++it;}if(!progress)fail("cyclic follow chain");}WRITE(followNodes,sorted);
        }
        auto os=READ(disk::CtrlOsOffset,ctrlOsOffsets);
        for(auto& f:s.osOffsets){auto a=node(f.parent),b=node(f.child);distinct(a,b);auto spec=FindAdvancedNode(s,f.child);
            if(lower(f.child).rfind("$cloth_p",0)!=0&&(!spec||!spec->hasPosition))fail("os_offset child must be a virtual node");
            os.erase(std::remove_if(os.begin(),os.end(),[&](auto& x){return x.child==b;}),os.end());os.push_back({a,b});offsets.erase(std::remove_if(offsets.begin(),offsets.end(),[&](auto& x){return x.child==b;}),offsets.end());}
        // Runtime evaluates ordinary offsets before OS offsets. As in the reference,
        // virtual parent chains therefore terminate at a real animation control.
        std::map<uint16_t,uint16_t> parents;for(auto& o:offsets)parents[o.child]=o.parent;for(auto& o:os)parents[o.child]=o.parent;
        auto realParent=[&](uint16_t parent){std::set<uint16_t> seen;while(parents.count(parent)){if(!seen.insert(parent).second)fail("cyclic virtual node parent chain");parent=parents.at(parent);}return parent;};
        for(auto& o:offsets){auto p=realParent(o.parent);if(p==o.child)fail("cyclic virtual node parent chain");if(p!=o.parent){o.parent=p;xyz(o.position,math::VectorITransform(nodes[o.child].position,nodes[p].pose));}}
        for(auto& o:os){o.parent=realParent(o.parent);if(o.parent==o.child)fail("cyclic virtual node parent chain");}
        std::sort(offsets.begin(),offsets.end(),[](auto& a,auto& b){return a.child<b.child;});std::sort(os.begin(),os.end(),[](auto& a,auto& b){return a.child<b.child;});
        if(!s.osOffsets.empty())WRITE(ctrlOsOffsets,os);
        WRITE(ctrlOffsets,offsets);

        if(!s.spheres.empty()){
            struct Item{disk::CollisionSphere sphere;bool inclusive;};std::vector<Item> list;auto prior=READ(disk::CollisionSphere,collisionSpheres);for(size_t i=0;i<prior.size();++i)list.push_back({prior[i],i<d.sphereInclusive});
            for(auto& c:s.spheres){disk::CollisionSphere x;x.parent=node(c.parent);x.child=node(c.child);distinct(x.parent,x.child);dynamic(x.child);x.radiusFactor=c.inclusive?1/(c.radius*c.radius):c.radius;xyz(x.center,c.center);x.stickiness=c.stickiness;list.push_back({x,c.inclusive});}
            std::stable_sort(list.begin(),list.end(),[](auto& a,auto& b){return a.inclusive>b.inclusive;});std::vector<disk::CollisionSphere> out;d.sphereInclusive=0;for(auto& x:list){out.push_back(x.sphere);if(x.inclusive)++d.sphereInclusive;}WRITE(collisionSpheres,out);
        }
        if(!s.planes.empty()){
            auto planes=READ(disk::Plane,collisionPlanes);for(auto& c:s.planes){disk::Plane x;x.parent=node(c.parent);x.child=node(c.child);distinct(x.parent,x.child);dynamic(x.child);xyz(x.normal,c.normal);x.offset=c.offset;x.stickiness=c.stickiness;planes.push_back(x);}WRITE(collisionPlanes,planes);
        }
        if(!s.capsules.empty()){
            auto caps=READ(disk::CapsuleStretch,capsuleStretches);for(auto& c:s.capsules){disk::CapsuleStretch x;x.node[0]=node(c.node[0]);x.node[1]=node(c.node[1]);x.radius[0]=c.radius[0];x.radius[1]=c.radius[1];x.mask=c.mask;x.stickiness=c.stickiness;if(std::max(x.radius[0],x.radius[1])<=0)fail("capsule radius must be positive");if(x.radius[0]>x.radius[1]){std::swap(x.radius[0],x.radius[1]);std::swap(x.node[0],x.node[1]);}caps.push_back(x);}WRITE(capsuleStretches,caps);
        }
        if(!s.rigids.empty()){
            auto spheres=READ(disk::SphereRigid,sphereRigids);auto caps=READ(disk::CapsuleRigid,capsuleRigids);
            for(auto& c:s.rigids){uint16_t n=node(c.node);if(c.capsule){disk::CapsuleRigid x;x.node=n;x.mask=c.mask;x.stickiness=c.stickiness;for(int i=0;i<2;++i){xyz(x.center[i],c.center[i]);x.radius[i]=c.radius[i];}if(std::max(x.radius[0],x.radius[1])<=0)fail("capsule radius must be positive");if(x.radius[0]>x.radius[1]){std::swap(x.radius[0],x.radius[1]);for(int i=0;i<3;++i)std::swap(x.center[0][i],x.center[1][i]);}caps.push_back(x);}else {disk::SphereRigid x;x.node=n;x.mask=c.mask;x.stickiness=c.stickiness;xyz(x.center,c.center[0]);x.radius=c.radius[0];if(x.radius<=0)fail("sphere radius must be positive");spheres.push_back(x);}}
            WRITE(sphereRigids,spheres);WRITE(capsuleRigids,caps);
        }
        for(size_t i=0;i<integrators.size();++i){auto& n=integrators[i];if(s.massDamping&&i>=d.staticNodes)n.damping*=nodes[i].invMass;
            uint32_t flags=(n.damping!=0?1u<<8:0)|(n.forceAttraction!=0?1u<<9:0)|(n.vertexAttraction!=0?1u<<10:0)|(n.gravity!=360?1u<<11:0);
            if(i>=d.staticNodes)d.dynamicFlags|=flags;else d.staticFlags|=flags;
        }
        WRITE(nodeIntegrator,integrators);
        std::memcpy(bytes.data(),&d,sizeof(d));resource=std::move(bytes);return true;
#undef READ
#undef WRITE
    }catch(const std::exception& e){if(error)*error=e.what();return false;}
}
}
