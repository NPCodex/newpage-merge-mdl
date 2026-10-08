#include "cloth.h"
#include "format/cloth.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <functional>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>

namespace pulse::cloth {
namespace {
namespace disk = pulse::format::cloth;
using V = math::Vector3;
using E = dmx::Element;
V add(V a,V b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
V sub(V a,V b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
V mul(V a,float s){return {a.x*s,a.y*s,a.z*s};}
float dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
float length(V a){return std::sqrt(dot(a,a));}
bool finite(V a){return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z);}
[[noreturn]] void fail(const std::string& s){throw std::runtime_error("cloth: "+s);}
V unit(V a){float d=length(a);if(!std::isfinite(d)||d<1e-6f)fail("degenerate proxy face or control fit");return mul(a,1/d);}
std::string lower(std::string s){for(char& c:s)if(c>='A'&&c<='Z')c+=32;return s;}
void xyz(float* out,V v){out[0]=v.x;out[1]=v.y;out[2]=v.z;}
math::matrix3x4 transform(const E* e){
    if(!e)return {};
    auto p=e->GetVector3("position");math::Quaternion q;
    if(auto a=e->Get("orientation")){
        auto v=std::get_if<dmx::Quaternion>(&a->value);if(!v)fail("invalid transform orientation");
        q={v->x,v->y,v->z,v->w};
    }
    if(!finite({p.x,p.y,p.z})||!std::isfinite(q.x)||!std::isfinite(q.y)||!std::isfinite(q.z)||!std::isfinite(q.w))fail("non-finite transform");
    float n=q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w;
    if(n<1e-8f)fail("zero transform quaternion");
    q=math::QuaternionNormalized(q);
    return math::QuaternionMatrix(q,{p.x,p.y,p.z});
}
const E* bindState(const E* mesh){
    if(auto s=mesh->GetElement("bindState"))return s;
    if(auto a=mesh->GetElementArray("baseStates"))for(auto s:*a)if(s&&s->name=="bind")return s;
    return mesh->GetElement("currentState");
}
template<class T> const T* required(const T* p,const char* name){if(!p)fail(std::string("missing ")+name);return p;}
const std::vector<dmx::Vector3>* positions(const E* e){auto p=e->GetVector3Array("positions");return p?p:e->GetVector3Array("position$0");}
const std::vector<int32_t>* positionIndices(const E* e){auto p=e->GetIntArray("positionsIndices");return p?p:e->GetIntArray("position$0Indices");}

// A map can index corners independently from positions. Shared positions must agree.
std::vector<float> pointMap(const E* state,const char* name,const std::vector<int32_t>& posIndex,size_t count,float def,bool mandatory){
    auto values=state->GetFloatArray(name);
    if(!values){if(mandatory||state->Get(name))fail(std::string("missing or invalid ")+name+" map");return std::vector<float>(count,def);}
    auto indices=state->GetIntArray(std::string(name)+"Indices");
    if(!indices&&state->Get(std::string(name)+"Indices"))fail(std::string(name)+" has an invalid index array type");
    std::vector<float> out(count,def);std::vector<bool> seen(count,false);
    if(indices){
        if(indices->size()!=posIndex.size())fail(std::string(name)+" index count does not match positions");
        for(size_t c=0;c<indices->size();++c){int p=posIndex[c],v=(*indices)[c];
            if(p<0||size_t(p)>=count||v<0||size_t(v)>=values->size())fail(std::string(name)+" index out of range");
            float x=(*values)[v];if(!std::isfinite(x))fail(std::string(name)+" contains a non-finite value");
            if(seen[p]&&std::fabs(out[p]-x)>1e-6f)fail(std::string(name)+" disagrees across a shared position");out[p]=x;seen[p]=true;
        }
    }else{
        if(values->size()!=count)fail(std::string(name)+" must have one value per position or explicit indices");out=*values;
    }
    for(float x:out)if(!std::isfinite(x))fail(std::string(name)+" contains a non-finite value");
    return out;
}

void read(const dmx::Datamodel& dm,bool planes,Proxy& out,const Settings& settings){
    Proxy p;p.planeCollision=planes;
    const E* model=dm.root?dm.root->GetElement("model"):nullptr;
    if(!model&&dm.root&&dm.root->className=="DmeModel")model=dm.root;
    if(!model)fail("proxy has no DmeModel");
    if(auto axis=model->GetString("upAxis")){auto a=lower(*axis);if(a!="y"&&a!="z")fail("proxy upAxis must be Y or Z");p.upAxisY=a=="y";}
    const std::vector<E*> noJoints;
    auto joints=model->GetElementArray("jointList");
    if(!joints&&!settings.projection.enabled)fail("missing jointList (model 15+)");
    if(!joints)joints=&noJoints;
    std::map<const E*,const E*> bindTransforms;
    if(auto states=model->GetElementArray("baseStates"))for(auto state:*states)if(state&&state->name=="bind"){
        auto transforms=required(state->GetElementArray("transforms"),"bind transforms");
        if(transforms->size()!=joints->size())fail("bind transform count does not match jointList");
        for(size_t i=0;i<joints->size();++i)bindTransforms[(*joints)[i]]=(*transforms)[i];
    }
    std::set<const E*> active,visited;uint32_t meshCount=0;
    std::function<void(const E*,const math::matrix3x4&,int)> walk;
    walk=[&](const E* dag,const math::matrix3x4& parent,int depth){
        if(!dag)return;if(depth>256||!active.insert(dag).second)fail("cyclic or excessively deep proxy hierarchy");
        if(!visited.insert(dag).second)fail("proxy hierarchy contains a shared DAG node");
        auto found=bindTransforms.find(dag);
        auto world=math::ConcatTransforms(parent,transform(found==bindTransforms.end()?dag->GetElement("transform"):found->second));
        if(auto mesh=dag->GetElement("shape")){if(mesh->className=="DmeMesh"){
            auto state=required(bindState(mesh),"mesh bind state");
            auto pos=required(positions(state),"positions");auto indices=required(positionIndices(state),"positionsIndices");
            if(pos->empty()||pos->size()>4096||p.points.size()+pos->size()>4096)fail("proxy point limit is 4096");
            for(int i:*indices)if(i<0||size_t(i)>=pos->size())fail("position index out of range");
            for(auto& a:state->attributes)if(a.name.rfind("cloth_",0)==0){
                std::string n=a.name;if(n.size()>7&&n.substr(n.size()-7)=="Indices")n.resize(n.size()-7);
                static const std::set<std::string> supported{"cloth_enable","cloth_mass","cloth_gravity","cloth_drag","cloth_animation_attract","cloth_animation_force_attract","cloth_collision_radius","cloth_ground_collision","cloth_ground_friction","cloth_use_rods","cloth_anchor_free_rotate"};
                if(!supported.count(n))fail("unsupported proxy attribute "+a.name);
            }
            auto enabled=pointMap(state,"cloth_enable",*indices,pos->size(),0,!planes);
            auto mass=pointMap(state,"cloth_mass",*indices,pos->size(),0,false);
            const bool hasMassMap=state->Get("cloth_mass")!=nullptr;
            auto gravity=pointMap(state,"cloth_gravity",*indices,pos->size(),360,false);
            auto drag=pointMap(state,"cloth_drag",*indices,pos->size(),0,false);
            auto attract=pointMap(state,"cloth_animation_attract",*indices,pos->size(),0,false);
            auto force=pointMap(state,"cloth_animation_force_attract",*indices,pos->size(),0,false);
            auto radius=pointMap(state,"cloth_collision_radius",*indices,pos->size(),0,false);
            auto ground=pointMap(state,"cloth_ground_collision",*indices,pos->size(),0,false);
            auto friction=pointMap(state,"cloth_ground_friction",*indices,pos->size(),0,false);
            auto useRods=pointMap(state,"cloth_use_rods",*indices,pos->size(),0,false);
            auto freeRotate=pointMap(state,"cloth_anchor_free_rotate",*indices,pos->size(),0,false);
            int influenceCount=state->GetInt("jointCount");
            auto jointIndex=state->GetIntArray("jointIndices");
            auto weights=state->GetFloatArray("jointWeights");
            bool unskinned=settings.projection.enabled&&!planes&&(!jointIndex||jointIndex->empty())&&(!weights||weights->empty())&&influenceCount==0;
            if(!unskinned&&(influenceCount<1||influenceCount>16||!jointIndex||!weights||jointIndex->size()!=pos->size()*influenceCount||weights->size()!=jointIndex->size()))fail("invalid proxy skinning array sizes");
            size_t base=p.points.size();
            for(size_t i=0;i<pos->size();++i){
                Point point;auto v=(*pos)[i];point.position=math::VectorTransform({v.x,v.y,v.z},world);
                if(!finite(point.position))fail("non-finite proxy position");
                if(enabled[i]<0||enabled[i]>1||mass[i]<-20||mass[i]>20||gravity[i]<0||gravity[i]>1e6f||drag[i]<0||drag[i]>1e6f)fail("invalid cloth enable, mass, gravity or drag");
                point.simulated=!planes&&enabled[i]>=.5f;point.massBias=hasMassMap?std::exp(mass[i]):0;point.gravity=gravity[i];point.drag=30*drag[i];
                if(attract[i]<0||attract[i]>1e6f||force[i]<0||force[i]>1e6f||radius[i]<0||radius[i]>1e6f||ground[i]<0||ground[i]>1||friction[i]<0||friction[i]>1)fail("invalid cloth attraction, collision radius or ground map");
                point.vertexAttraction=30*attract[i];point.forceAttraction=30*force[i];point.collisionRadius=radius[i];
                point.worldFriction=1-ground[i];point.worldCollision=point.worldFriction<.999f;point.groundFriction=friction[i];
                if(useRods[i]<0||useRods[i]>1||freeRotate[i]<0||freeRotate[i]>1)fail("invalid cloth rod or anchor rotation map (expected [0,1])");
                point.useRods=useRods[i]>.5f;point.anchorFreeRotate=!point.simulated&&freeRotate[i]>.5f;
                std::map<std::string,float> combined;
                for(int j=0;j<influenceCount;++j){size_t at=i*influenceCount+j;float weight=(*weights)[at];int k=(*jointIndex)[at];
                    if(!std::isfinite(weight)||weight<0)fail("invalid skin weight");if(weight==0)continue;
                    if(k<0||size_t(k)>=joints->size()||!(*joints)[k]||(*joints)[k]->name.empty())fail("invalid skin joint");
                    combined[(*joints)[k]->name]+=weight;
                }
                float total=0;for(auto& x:combined)total+=x.second;
                if(!unskinned&&(!std::isfinite(total)||total<1e-6f))fail("unbound proxy point");
                for(auto& x:combined){point.weights.push_back({x.first,x.second/total});if(std::find(p.bones.begin(),p.bones.end(),x.first)==p.bones.end())p.bones.push_back(x.first);}
                if(planes&&point.weights.size()!=1)fail("collision proxy points must be rigidly bound to one bone");
                p.points.push_back(std::move(point));
            }
            auto sets=required(mesh->GetElementArray("faceSets"),"faceSets");const uint32_t meshGroup=meshCount++;
            for(auto set:*sets){if(!set)fail("null face set");auto faces=required(set->GetIntArray("faces"),"faces");Face face;face.mesh=meshGroup;
                for(int c:*faces){if(c==-1){
                    if(face.count<3||face.count>4)fail("proxy supports only triangles and quads");
                    std::set<uint32_t> unique(face.point.begin(),face.point.begin()+face.count);if(unique.size()!=size_t(face.count))fail("repeated position in proxy face");
                    p.faces.push_back(face);face={};face.mesh=meshGroup;
                }else{if(c<0||size_t(c)>=indices->size()||face.count==4)fail("invalid proxy face corner or unsupported polygon");face.point[face.count++]=uint32_t(base+(*indices)[c]);}}
                if(face.count)fail("unterminated proxy face");
            }
        }}
        if(auto children=dag->GetElementArray("children"))for(auto child:*children)walk(child,world,depth+1);
        active.erase(dag);
    };
    walk(model,{},0);
    if(p.faces.empty())fail("proxy has no triangle or quad faces");out=std::move(p);
}

uint32_t hashName(std::string s){
    s=lower(s);uint32_t h=0x31415926u^uint32_t(s.size());size_t i=0;
    auto mix=[](uint32_t k){k*=0x5bd1e995u;k^=k>>24;k*=0x5bd1e995u;return k;};
    while(i+4<=s.size()){uint32_t k=uint8_t(s[i])|(uint32_t(uint8_t(s[i+1]))<<8)|(uint32_t(uint8_t(s[i+2]))<<16)|(uint32_t(uint8_t(s[i+3]))<<24);h=h*0x5bd1e995u^mix(k);i+=4;}
    uint32_t k=0;size_t tail=s.size()-i;for(size_t j=0;j<tail;++j)k|=uint32_t(uint8_t(s[i+j]))<<(8*j);if(tail){h^=k;h*=0x5bd1e995u;}
    h^=h>>13;h*=0x5bd1e995u;h^=h>>15;return h;
}
struct Buffer {
    std::vector<uint8_t> bytes=std::vector<uint8_t>(sizeof(disk::Descriptor));
    template<class T> void write(size_t field,const std::vector<T>& data,size_t alignment=alignof(T)){
        if(data.empty())return;
        size_t at=(bytes.size()+alignment-1)&~(alignment-1);bytes.resize(at+sizeof(T)*data.size(),0);
        std::memcpy(bytes.data()+at,data.data(),sizeof(T)*data.size());
        disk::Array a{int32_t(at-field),uint32_t(data.size())};std::memcpy(bytes.data()+field,&a,sizeof(a));
    }
};
disk::Transform pose(const math::matrix3x4& m){disk::Transform p;math::Quaternion q;V v;math::MatrixAngles(m,q,v);xyz(p.position,v);p.orientation[0]=q.x;p.orientation[1]=q.y;p.orientation[2]=q.z;p.orientation[3]=q.w;return p;}
struct Node { std::string name; V pos; math::matrix3x4 pose; float invMass=0,gravity=360,drag=0; int bone=-1; bool fit=false;
    float forceAttraction=0,vertexAttraction=0,collisionRadius=0,worldFriction=1,groundFriction=0; bool worldCollision=false;
};

// Match the scalar runtime's Y-first orthogonalization. The adjustment restores
// the target's authored bind rotation; a reverse offset restores its position.
disk::NodeBase nodeBasis(uint16_t target,std::vector<uint16_t> nearby,const std::vector<Node>& nodes){
    std::sort(nearby.begin(),nearby.end());nearby.erase(std::unique(nearby.begin(),nearby.end()),nearby.end());
    if(nearby.size()<3)fail("sparse control or free anchor "+nodes[target].name+" needs three non-collinear neighboring proxy points");
    disk::NodeBase out;out.node=target;float longest=0,area=0;
    for(size_t i=0;i<nearby.size();++i)for(size_t j=0;j<i;++j){float d=length(sub(nodes[nearby[i]].pos,nodes[nearby[j]].pos));if(d>longest){longest=d;out.x0=nearby[j];out.x1=nearby[i];}}
    V x=sub(nodes[out.x1].pos,nodes[out.x0].pos);
    for(size_t i=0;i<nearby.size();++i)for(size_t j=0;j<i;++j){float a=length(cross(sub(nodes[nearby[i]].pos,nodes[nearby[j]].pos),x));if(a>area){area=a;out.y0=nearby[j];out.y1=nearby[i];}}
    if(longest<1e-6f||area<1e-5f)fail("sparse control or free anchor "+nodes[target].name+" has degenerate neighboring proxy points");
    V y=unit(sub(nodes[out.y1].pos,nodes[out.y0].pos));x=sub(x,mul(y,dot(x,y)));
    // The retail scalar path substitutes an arbitrary axis at <= 0.05 units.
    // Refuse that case rather than encoding an adjustment to a different basis.
    if(length(x)<=.05f)fail("sparse control or free anchor "+nodes[target].name+" has a neighboring basis smaller than the runtime 0.05-unit threshold");
    x=unit(x);V z=cross(x,y);math::matrix3x4 predicted;
    for(int row=0;row<3;++row){predicted.m[row][0]=row==0?x.x:row==1?x.y:x.z;predicted.m[row][1]=row==0?y.x:row==1?y.y:y.z;predicted.m[row][2]=row==0?z.x:row==1?z.y:z.z;predicted.m[row][3]=0;}
    auto relative=pose(math::ConcatTransforms(math::MatrixInvert(predicted),nodes[target].pose));
    std::copy(relative.orientation,relative.orientation+4,out.adjust);return out;
}

void packRods(const std::vector<disk::Rod>& rods,std::vector<disk::SimdRod>& simdRods){
    for(const auto& rod:rods){disk::SimdRod packet;for(int lane=0;lane<4;++lane){packet.node[0][lane]=rod.node[0];packet.node[1][lane]=rod.node[1];packet.maxDistance[lane]=rod.maxDistance;packet.minDistance[lane]=rod.minDistance;packet.weight0[lane]=rod.weight0;packet.relaxation[lane]=rod.relaxation;}simdRods.push_back(packet);}
}

struct Hinge { uint16_t edge[2],side[2][2]; };
std::vector<Hinge> hinges(const std::vector<Face>& faces,const std::vector<uint16_t>& pointNode){
    struct Side { uint16_t edge[2],opposite[2]; unsigned uses=1; };
    std::map<std::pair<uint16_t,uint16_t>,Side> edges;std::vector<Hinge> result;
    for(const auto& face:faces)for(int i=0;i<face.count;++i){
        uint16_t a=pointNode[face.point[i]],b=pointNode[face.point[(i+1)%face.count]];
        uint16_t c=pointNode[face.point[(i+2)%face.count]],d=face.count==3?c:pointNode[face.point[(i+3)%face.count]];
        auto key=std::minmax(a,b);auto found=edges.find(key);
        if(found==edges.end())edges.emplace(key,Side{{a,b},{c,d},1});
        else{
            auto& prior=found->second;if(++prior.uses>2)fail("non-manifold cloth edge has more than two faces");
            int reverse=prior.edge[0]!=a;
            result.push_back({{a,b},{{c,d},{prior.opposite[reverse],prior.opposite[1-reverse]}}});
        }
    }
    return result;
}

void bendConstraints(const std::vector<Hinge>& edges,const std::vector<Node>& nodes,const Settings& settings,
                     std::vector<disk::Rod>& rods,std::vector<disk::SimdRod>& simdRods,std::vector<disk::AxialEdge>& axial){
    std::map<std::pair<uint16_t,uint16_t>,size_t> rodIndex;
    for(size_t i=0;i<rods.size();++i)rodIndex[{rods[i].node[0],rods[i].node[1]}]=i;
    const size_t structuralRods=rods.size();
    const float angle=settings.curvature*3.14159265358979323846f;
    for(const auto& hinge:edges){
        if(settings.addStiffnessRods)for(int side=0;side<2;++side){
            uint16_t a=hinge.side[0][side],b=hinge.side[1][side];if(a==b)continue;
            if(a>b)std::swap(a,b);float inv0=nodes[a].invMass,inv1=nodes[b].invMass;if(inv0+inv1<1e-12f)continue;
            float relaxed=length(sub(nodes[a].pos,nodes[b].pos)),minimum=relaxed,maximum=relaxed;
            if(!settings.rigidEdgeHinges){
                V origin=nodes[hinge.edge[0]].pos,axis=unit(sub(nodes[hinge.edge[1]].pos,origin));
                V v0=sub(nodes[a].pos,origin),v1=sub(nodes[b].pos,origin);float p0=dot(v0,axis),p1=dot(v1,axis);
                float h0=length(sub(v0,mul(axis,p0))),h1=length(sub(v1,mul(axis,p1))),delta=p0-p1;
                maximum=std::sqrt(delta*delta+(h0+h1)*(h0+h1));
                minimum=std::min(relaxed,length({h1*std::cos(angle)-h0,h1*std::sin(angle),delta}));
            }
            auto key=std::make_pair(a,b);auto prior=rodIndex.find(key);
            if(prior!=rodIndex.end()){if(prior->second<structuralRods)continue;auto& rod=rods[prior->second];rod.minDistance=std::min(rod.minDistance,minimum);rod.maxDistance=std::max(rod.maxDistance,maximum);}
            else{disk::Rod rod;rod.node[0]=a;rod.node[1]=b;rod.maxDistance=maximum;rod.minDistance=minimum;rod.weight0=inv0/(inv0+inv1);if(rod.weight0<1e-6f)rod.weight0=0;if(rod.weight0>1-1e-6f)rod.weight0=1;rodIndex[key]=rods.size();rods.push_back(rod);}
        }
        if(!settings.rigidEdgeHinges)continue;
        disk::AxialEdge bend;for(int i=0;i<2;++i){bend.node[i]=hinge.edge[i];bend.node[i+2]=hinge.side[0][i];bend.node[i+4]=hinge.side[1][i];}
        V x[4]{nodes[bend.node[0]].pos,nodes[bend.node[1]].pos,mul(add(nodes[bend.node[2]].pos,nodes[bend.node[3]].pos),.5f),mul(add(nodes[bend.node[4]].pos,nodes[bend.node[5]].pos),.5f)};
        if(dot(sub(add(x[1],x[0]),add(x[2],x[3])),cross(sub(x[1],x[0]),sub(x[2],x[3])))<0){std::swap(x[0],x[1]);std::swap(bend.node[0],bend.node[1]);}
        auto pairMass=[&](int a,int b){float v0=nodes[bend.node[a]].invMass,v1=nodes[bend.node[b]].invMass;return bend.node[a]==bend.node[b]?v0:(v0+v1>0?v0*v1/(v0+v1):0);};
        float inv[4]{nodes[bend.node[0]].invMass,nodes[bend.node[1]].invMass,pairMass(2,3),pairMass(4,5)};
        if(inv[0]+inv[1]+inv[2]+inv[3]==0)continue;
        V edge=sub(x[1],x[0]),virtualEdge=sub(x[3],x[2]),normal=cross(edge,virtualEdge);
        float normalLength=length(normal);if(normalLength<.001f)continue;
        float edgeLength=length(edge),virtualLength=length(virtualEdge);V direction=mul(edge,1/edgeLength),side=cross(mul(normal,1/normalLength),direction);
        V e1=sub(x[2],x[0]),e2=sub(x[3],x[0]);float t2=dot(side,e1),t3=dot(side,e2);
        bend.tv=-t2/(t3-t2);V connection=add(e1,mul(virtualEdge,bend.tv));float f0len=dot(connection,direction);
        bend.te=f0len/edgeLength;bend.distance=length(sub(mul(direction,f0len),connection));
        float c0=inv[0]+inv[1]>=1e-8f?edgeLength*inv[0]/(inv[0]+inv[1]):.5f;
        float cv=inv[2]+inv[3]>=1e-8f?virtualLength*inv[2]/(inv[2]+inv[3]):.5f;
        auto inertia=[](float a,float x,float b,float y){
            if(a<=1e-8f)return b<=1e-8f||std::fabs(x)>1e-6f?0:b/(y*y);
            if(b<=1e-8f)return std::fabs(y)>1e-6f?0:a/(x*x);
            return a*b/(b*x*x+a*y*y);
        };
        float i0=inertia(inv[0],c0,inv[1],edgeLength-c0),iv=inertia(inv[2],cv,inv[3],virtualLength-cv);
        float f0=f0len-c0,fv=bend.tv*virtualLength-cv;
        float reaction[4]{inv[0]-i0*f0*c0,inv[1]+i0*f0*(edgeLength-c0),-(inv[2]-iv*fv*cv),-(inv[3]+iv*fv*(virtualLength-cv))};
        float sum=bend.te*reaction[0]+(1-bend.te)*reaction[1]-bend.tv*reaction[2]-(1-bend.tv)*reaction[3];
        if(sum>1e-8f){for(int i=0;i<4;++i)bend.weight[i]=reaction[i]/sum;axial.push_back(bend);}
    }
    packRods(rods,simdRods);
}

V axisPosition(V v,bool sourceY,bool targetY){if(sourceY==targetY)return v;return sourceY?V{v.x,-v.z,v.y}:V{v.x,v.z,-v.y};}
void adjustFaces(std::vector<Face>& faces,const std::vector<Point>& points,float tolerance){
    std::vector<Face> extra;
    for(auto& f:faces){
        for(int j=0;j<f.count;++j)if(f.point[j]>=points.size())fail("proxy face index out of range");
        if(f.count!=4)continue;
        std::stable_sort(f.point.begin(),f.point.end(),[&](uint32_t a,uint32_t b){return points[a].simulated<points[b].simulated;});
        int fixed=0;for(auto p:f.point)fixed+=!points[p].simulated;
        auto pos=[&](int i){return points[f.point[i]].position;};
        if(fixed==2){if(dot(sub(pos(1),pos(0)),sub(pos(2),pos(3)))<0)std::swap(f.point[2],f.point[3]);}
        else if(fixed<2){auto original=f.point;auto score=[&](const std::array<uint32_t,4>& n){return length(cross(sub(points[n[2]].position,points[n[0]].position),sub(points[n[3]].position,points[n[1]].position)));};
            float best=score(original);for(auto candidate:{std::array<uint32_t,4>{original[0],original[2],original[3],original[1]},std::array<uint32_t,4>{original[0],original[3],original[1],original[2]}}){float value=score(candidate);if(value>best){best=value;f.point=candidate;}}
        }
        if(fixed==0&&tolerance<1){
            if(length(sub(pos(2),pos(0)))>length(sub(pos(3),pos(1))))std::rotate(f.point.begin(),f.point.begin()+1,f.point.end());
            V n0=cross(sub(pos(1),pos(0)),sub(pos(2),pos(0))),n1=cross(sub(pos(3),pos(2)),sub(pos(0),pos(2)));
            if(length(cross(n0,n1))>tolerance*length(n0)*length(n1)){Face t=f;t.point={f.point[0],f.point[2],f.point[3],0};t.count=3;extra.push_back(t);f.count=3;f.point[3]=0;}
        }
    }
    faces.insert(faces.end(),extra.begin(),extra.end());
}
void build(const std::vector<Proxy>& proxies,const std::vector<Bone>& bones,const math::matrix3x4& import,float scale,std::vector<uint8_t>& resource,const Settings& settings){
    resource.clear();if(proxies.empty()&&settings.advanced.nodes.empty()&&AdvancedReferencedBones(settings.advanced).empty())return;
    if(!std::isfinite(scale)||scale<=0)fail("proxy scale must be finite and positive");
    std::map<std::string,int> boneIndex;
    for(size_t i=0;i<bones.size();++i){if(!boneIndex.emplace(lower(bones[i].name),int(i)).second)fail("duplicate model bone name");}
    std::vector<Point> points;std::vector<Face> faces;std::vector<const Proxy*> planes;
    for(auto& proxy:proxies){if(proxy.planeCollision){planes.push_back(&proxy);continue;}size_t base=points.size();
        for(auto p:proxy.points){p.position=axisPosition(p.position,proxy.upAxisY,settings.modelUpAxisY);points.push_back(std::move(p));}
        for(auto f:proxy.faces){for(int j=0;j<f.count;++j)f.point[j]+=uint32_t(base);faces.push_back(f);}
    }
    const size_t proxyPointCount=points.size();std::vector<std::string> pointNames;std::vector<int> explicitBones(points.size(),-1);
    for(size_t i=0;i<points.size();++i)pointNames.push_back("$cloth_p"+std::to_string(i));
    for(const auto& n:settings.advanced.nodes){
        auto prior=std::find_if(pointNames.begin(),pointNames.end(),[&](const std::string& name){return lower(name)==lower(n.name);});
        if(prior!=pointNames.end()){auto& point=points[size_t(prior-pointNames.begin())];if(n.hasSimulated)point.simulated=n.simulated;if(n.hasPosition)point.position=n.position;continue;}
        bool weighted=false;for(size_t i=0;i<proxyPointCount;++i)for(auto& w:points[i].weights)weighted|=lower(w.bone)==lower(n.name);if(weighted)continue;
        auto b=boneIndex.find(lower(n.name));if(!n.hasPosition&&b==boneIndex.end())fail("explicit cloth node references missing bone "+n.name);
        Point p;p.simulated=n.simulated;p.position=n.hasPosition?n.position:V{bones[b->second].bindPose.m[0][3],bones[b->second].bindPose.m[1][3],bones[b->second].bindPose.m[2][3]};
        points.push_back(p);pointNames.push_back(n.name);explicitBones.push_back(b==boneIndex.end()?-1:b->second);
    }
    if(points.empty())fail("cloth needs proxy points or explicit nodes");
    if(points.size()>4096)fail("combined cloth proxy point limit is 4096");
    std::set<int> fixedBones,dynamicBones;std::vector<std::vector<std::pair<int,float>>> influences(points.size());
    for(size_t i=0;i<points.size();++i){auto& p=points[i];p.position=math::VectorTransform(mul(p.position,scale),import);if(!finite(p.position))fail("non-finite transformed proxy");
        for(auto& w:p.weights){auto b=boneIndex.find(lower(w.bone));if(b==boneIndex.end())fail("proxy references missing model bone "+w.bone);influences[i].push_back({b->second,w.weight});
            if(w.weight>=settings.fitInfluenceThreshold)(p.simulated?dynamicBones:fixedBones).insert(b->second);}
    }
    if(settings.flexBorders){for(auto& f:faces){int dynamic=0;for(int j=0;j<f.count;++j)dynamic+=points.at(f.point[j]).simulated;if(dynamic>=2)for(int j=0;j<f.count;++j)if(!points[f.point[j]].simulated)points[f.point[j]].anchorFreeRotate=true;}
        for(int b:dynamicBones)fixedBones.erase(b);
    }else for(int b:fixedBones)dynamicBones.erase(b);
    for(const auto& n:settings.advanced.nodes)if(n.hasSimulated){auto b=boneIndex.find(lower(n.name));if(b!=boneIndex.end()&&(fixedBones.count(b->second)||dynamicBones.count(b->second))){if(n.simulated){fixedBones.erase(b->second);dynamicBones.insert(b->second);}else{dynamicBones.erase(b->second);fixedBones.insert(b->second);}}}
    for(size_t i=0;i<proxyPointCount;++i)if(!points[i].simulated||points[i].forceAttraction>0||points[i].vertexAttraction>0||settings.advanced.ftl){if(influences[i].empty())fail("unbound proxy point; enable render projection for unskinned proxies");int b=std::max_element(influences[i].begin(),influences[i].end(),[](auto a,auto b){return a.second<b.second;})->first;if(!dynamicBones.count(b))fixedBones.insert(b);}
    adjustFaces(faces,points,settings.quadBendTolerance);
    // Mixed Voronoi areas give each vertex its share of sheet mass. In an obtuse
    // triangle the obtuse corner owns half the area and the other corners a quarter.
    std::vector<float> masses(points.size());
    for(auto& f:faces){
        for(int j=0;j<f.count;++j)if(f.point[j]>=points.size())fail("proxy face index out of range");
        for(int j=1;j+1<f.count;++j){uint32_t index[3]{f.point[0],f.point[j],f.point[j+1]};V p[3]{points[index[0]].position,points[index[1]].position,points[index[2]].position};
            float twiceArea=length(cross(sub(p[1],p[0]),sub(p[2],p[0])));
            if(!std::isfinite(twiceArea)||twiceArea<1e-6f)fail("degenerate proxy face");
            float cot[3],edgeSquared[3];for(int k=0;k<3;++k){V a=sub(p[(k+1)%3],p[k]),b=sub(p[(k+2)%3],p[k]);cot[k]=dot(a,b)/twiceArea;edgeSquared[k]=dot(a,a);}
            float area[3];if(cot[0]>0&&cot[1]>0&&cot[2]>0){for(int k=0;k<3;++k)area[k]=.125f*(edgeSquared[k]*cot[(k+2)%3]+edgeSquared[(k+2)%3]*cot[(k+1)%3]);}
            else{area[0]=area[1]=area[2]=twiceArea*.125f;int obtuse=int(std::min_element(cot,cot+3)-cot);area[obtuse]*=2;}
            for(int k=0;k<3;++k)masses[index[k]]+=area[k];
        }
    }
    for(size_t i=0;i<points.size();++i){masses[i]=AdvancedMass(settings.advanced,pointNames[i],(i>=proxyPointCount?1:masses[i])+points[i].massBias);if(!std::isfinite(masses[i])||masses[i]<1e-8f)fail("invalid automatic cloth mass");}
    if(proxyPointCount&&(!std::any_of(points.begin(),points.begin()+proxyPointCount,[](const Point& p){return !p.simulated;})||!std::any_of(points.begin(),points.begin()+proxyPointCount,[](const Point& p){return p.simulated;})))fail("proxy needs fixed points and simulated points");
    for(const auto& name:AdvancedReferencedBones(settings.advanced)){if(std::any_of(pointNames.begin(),pointNames.end(),[&](const std::string& n){return lower(n)==lower(name);}))continue;auto b=boneIndex.find(lower(name));if(b==boneIndex.end())fail("advanced cloth references missing node "+name);if(!dynamicBones.count(b->second))fixedBones.insert(b->second);}
    for(auto proxy:planes)for(auto& p:proxy->points)for(auto& w:p.weights){auto b=boneIndex.find(lower(w.bone));if(b==boneIndex.end())fail("collision proxy references missing bone "+w.bone);if(dynamicBones.count(b->second))fail("collision planes must bind to animated anchor bones");fixedBones.insert(b->second);}
    if(settings.colliders.size()>1024)fail("rigid collider limit is 1024");
    for(const auto& c:settings.colliders){
        auto b=boneIndex.find(lower(c.bone));if(b==boneIndex.end())fail("rigid collider references missing bone "+c.bone);
        if(dynamicBones.count(b->second))fail("rigid colliders must bind to animated anchor bones");fixedBones.insert(b->second);
        if(c.type!=RigidCollider::Type::Sphere&&c.type!=RigidCollider::Type::Capsule)fail("unknown rigid collider type");
        if(!std::isfinite(c.stickiness)||c.stickiness<0||c.stickiness>1)fail("invalid rigid collider stickiness");
        int count=c.type==RigidCollider::Type::Sphere?1:2;
        for(int j=0;j<count;++j)if(!finite(c.center[j])||length(c.center[j])>1e6f||!std::isfinite(c.radius[j])||c.radius[j]<=0||c.radius[j]>1e6f)fail("rigid collider centers must be finite and radii positive (at most 1000000 units)");
        if(count==2&&length(sub(c.center[1],c.center[0]))<=std::fabs(c.radius[1]-c.radius[0])+1e-5f)fail("capsule endpoints must be distinct and farther apart than their radius difference; use a sphere for contained endpoints");
    }
    std::vector<Node> nodes;std::map<int,uint16_t> control;std::vector<uint16_t> pointNode(points.size());
    for(int b:fixedBones){control[b]=uint16_t(nodes.size());nodes.push_back({bones[b].name,{bones[b].bindPose.m[0][3],bones[b].bindPose.m[1][3],bones[b].bindPose.m[2][3]},bones[b].bindPose,0,360,0,b,false});}
    // Rotation-locked statics, freely rotating statics, then simulated points.
    for(int pass=0;pass<3;++pass)for(size_t i=0;i<points.size();++i)if((points[i].simulated?2:points[i].anchorFreeRotate?1:0)==pass){
        auto& p=points[i];pointNode[i]=uint16_t(nodes.size());math::matrix3x4 tm;if(explicitBones[i]>=0)tm=bones[explicitBones[i]].bindPose;tm.m[0][3]=p.position.x;tm.m[1][3]=p.position.y;tm.m[2][3]=p.position.z;
        nodes.push_back({pointNames[i],p.position,tm,p.simulated?1/masses[i]:0,p.gravity,p.drag,explicitBones[i],false});
        if(explicitBones[i]>=0)control[explicitBones[i]]=pointNode[i];
        auto& n=nodes.back();n.forceAttraction=p.forceAttraction;n.vertexAttraction=p.vertexAttraction;n.collisionRadius=p.collisionRadius*scale;n.worldFriction=p.worldFriction;n.groundFriction=p.groundFriction;n.worldCollision=p.worldCollision;
    }
    size_t staticCount=fixedBones.size()+std::count_if(points.begin(),points.end(),[](auto& p){return !p.simulated;});
    size_t lockedCount=fixedBones.size()+std::count_if(points.begin(),points.end(),[](auto& p){return !p.simulated&&!p.anchorFreeRotate;});
    for(int b:dynamicBones){control[b]=uint16_t(nodes.size());nodes.push_back({bones[b].name,{bones[b].bindPose.m[0][3],bones[b].bindPose.m[1][3],bones[b].bindPose.m[2][3]},bones[b].bindPose,1/AdvancedMass(settings.advanced,bones[b].name,1),360,0,b,true});}
    for(auto& node:nodes)if(auto advanced=FindAdvancedNode(settings.advanced,node.name)){
        if(advanced->gravity>=0)node.gravity=advanced->gravity;if(advanced->damping>=0)node.drag=advanced->damping;
        if(advanced->forceAttraction>=0)node.forceAttraction=advanced->forceAttraction;if(advanced->vertexAttraction>=0)node.vertexAttraction=advanced->vertexAttraction;if(advanced->collisionRadius>=0)node.collisionRadius=advanced->collisionRadius;
    }
    if(nodes.size()>8192)fail("FE node limit exceeded");
    std::vector<disk::CtrlOffset> offsets;
    for(size_t i=0;i<proxyPointCount;++i)if(!points[i].simulated||points[i].forceAttraction>0||points[i].vertexAttraction>0||settings.advanced.ftl){
        int b=std::max_element(influences[i].begin(),influences[i].end(),[&](auto a,auto b){return a.second+(control.count(a.first)?.05f:0)<b.second+(control.count(b.first)?.05f:0);})->first;
        disk::CtrlOffset o;o.parent=control.at(b);o.child=pointNode[i];xyz(o.position,math::VectorITransform(points[i].position,bones[b].bindPose));offsets.push_back(o);
    }
    std::vector<std::vector<uint16_t>> neighbors(points.size());
    std::vector<bool> used(points.size(),false);
    struct Tri { uint16_t n[3];float w1,w2,x,y,z;int statics; };
    struct Quad { disk::Quad data;int statics; };
    std::vector<Tri> tris;std::vector<Quad> quads;
    std::vector<disk::Rod> rods;std::vector<disk::SimdRod> simdRods;std::vector<disk::AxialEdge> axialEdges;
    std::set<std::pair<uint16_t,uint16_t>> structuralEdges;
    for(auto& f:faces){
        std::array<uint16_t,4> n{};for(int j=0;j<f.count;++j){if(f.point[j]>=points.size())fail("proxy face index out of range");n[j]=pointNode[f.point[j]];used[f.point[j]]=true;
            for(int k=0;k<f.count;++k)if(k!=j)neighbors[f.point[j]].push_back(uint16_t(f.point[k]));}
        std::stable_sort(n.begin(),n.begin()+f.count,[&](uint16_t a,uint16_t b){return (nodes[a].invMass>0)<(nodes[b].invMass>0);});
        int fixed=0;while(fixed<f.count&&nodes[n[fixed]].invMass==0)++fixed;
        if(fixed==f.count)continue;if(fixed>2)fail("a simulated proxy face may have at most two fixed vertices");
        bool useRods=false;for(int j=0;j<f.count;++j)useRods|=points[f.point[j]].useRods;
        if(useRods){
            // Reference authoring exposes this map but leaves its conversion a
            // TODO. Our bounded definition replaces a flagged face by its full
            // distance graph, including quad diagonals; shared pairs occur once.
            for(int j=0;j<f.count;++j)for(int k=0;k<j;++k){auto pair=std::minmax(n[j],n[k]);float inv0=nodes[pair.first].invMass,inv1=nodes[pair.second].invMass;
                if(inv0+inv1==0||!structuralEdges.insert(pair).second)continue;
                disk::Rod r;r.node[0]=pair.first;r.node[1]=pair.second;r.minDistance=r.maxDistance=length(sub(nodes[r.node[0]].pos,nodes[r.node[1]].pos));r.weight0=inv0/(inv0+inv1);rods.push_back(r);
            }
            continue;
        }
        if(f.count==3){V e1=sub(nodes[n[1]].pos,nodes[n[0]].pos),e2=sub(nodes[n[2]].pos,nodes[n[0]].pos);V x=unit(e1),y=unit(sub(e2,mul(x,dot(e2,x))));
            float mass[3]{},sum=0;for(int j=fixed;j<3;++j){mass[j]=1/nodes[n[j]].invMass;sum+=mass[j];}
            tris.push_back({{n[0],n[1],n[2]},mass[1]/sum,mass[2]/sum,length(e1),dot(e2,x),dot(e2,y),fixed});
        }else{
            Quad q{};q.statics=fixed;V center{};float mass[4]{},sum=0;
            for(int j=fixed;j<4;++j){mass[j]=1/nodes[n[j]].invMass;sum+=mass[j];center=add(center,mul(nodes[n[j]].pos,mass[j]));}center=mul(center,1/sum);
            if(fixed==1)center=nodes[n[0]].pos;if(fixed==2)center=mul(add(nodes[n[0]].pos,nodes[n[1]].pos),.5f);
            V e1=fixed==2?sub(nodes[n[1]].pos,nodes[n[0]].pos):sub(nodes[n[2]].pos,nodes[n[0]].pos);
            V e2=fixed==2?sub(add(nodes[n[2]].pos,nodes[n[3]].pos),mul(nodes[n[0]].pos,2)):sub(nodes[n[3]].pos,nodes[n[1]].pos);
            V x=unit(e1),y=unit(sub(e2,mul(x,dot(e2,x)))),z=cross(x,y);
            for(int j=0;j<4;++j){q.data.node[j]=n[j];V v=sub(nodes[n[j]].pos,center);q.data.shape[j][0]=dot(v,x);q.data.shape[j][1]=dot(v,y);q.data.shape[j][2]=dot(v,z);q.data.shape[j][3]=mass[j]/sum;}
            quads.push_back(q);
        }
    }
    if(proxyPointCount&&tris.empty()&&quads.empty()&&rods.empty())fail("cloth has no simulated elements");
    // Every simulated component must reach a fixed point, avoiding unintentional free-falling pieces.
    std::vector<bool> reached(points.size());std::vector<size_t> queue;
    for(size_t i=0;i<points.size();++i){if(i>=proxyPointCount){reached[i]=true;continue;}if(!used[i])fail("proxy contains an unused point");if(!points[i].simulated){reached[i]=true;queue.push_back(i);}}
    for(size_t at=0;at<queue.size();++at)for(size_t n:neighbors[queue[at]])if(!reached[n]){reached[n]=true;queue.push_back(n);}
    if(std::find(reached.begin(),reached.end(),false)!=reached.end())fail("simulated proxy component has no fixed anchor");
    bendConstraints(hinges(faces,pointNode),nodes,settings,rods,simdRods,axialEdges);
    std::vector<disk::FitMatrix> fits;std::vector<disk::FitWeight> fitWeights;
    std::vector<disk::NodeBase> nodeBases;std::vector<disk::ReverseOffset> reverseOffsets;
    auto basisNeighbors=[&](size_t point){std::vector<uint16_t> out{pointNode[point]};for(uint16_t other:neighbors[point])out.push_back(pointNode[other]);return out;};
    for(size_t i=0;i<points.size();++i)if(points[i].anchorFreeRotate)nodeBases.push_back(nodeBasis(pointNode[i],basisNeighbors(i),nodes));
    std::vector<int> fitOrder(dynamicBones.begin(),dynamicBones.end());
    auto staticInfluences=[&](int b){size_t count=0;for(size_t i=0;i<proxyPointCount;++i)if(!points[i].simulated)for(auto w:influences[i])if(w.first==b&&w.second>=settings.fitInfluenceThreshold)++count;return count;};
    std::stable_sort(fitOrder.begin(),fitOrder.end(),[&](int a,int b){return staticInfluences(a)>staticInfluences(b);});
    uint16_t fit1=0,fit2=0;
    for(int b:fitOrder){std::vector<std::pair<uint16_t,float>> cloud;V center{};float sum=0;size_t statics=0;
        for(int pass=0;pass<2;++pass){for(size_t i=0;i<proxyPointCount;++i)if(int(points[i].simulated)==pass)for(auto w:influences[i])if(w.first==b&&w.second>=settings.fitInfluenceThreshold)cloud.push_back({pointNode[i],w.second});if(pass==0)statics=cloud.size();}
        if(cloud.empty())fail("driven bone "+bones[b].name+" has no proxy influences");
        bool area=false;V origin=nodes[cloud[0].first].pos;
        for(size_t i=1;i<cloud.size()&&!area;++i)for(size_t j=i+1;j<cloud.size();++j)if(length(cross(sub(nodes[cloud[i].first].pos,origin),sub(nodes[cloud[j].first].pos,origin)))>1e-5f){area=true;break;}
        if(cloud.size()<size_t(settings.fitMinInfluences)||!area){
            auto best=std::max_element(cloud.begin(),statics?cloud.begin()+statics:cloud.end(),[](auto a,auto c){return a.second<c.second;});
            auto found=std::find(pointNode.begin(),pointNode.end(),best->first);size_t point=size_t(found-pointNode.begin());uint16_t ctrl=control.at(b);
            nodeBases.push_back(nodeBasis(ctrl,basisNeighbors(point),nodes));disk::ReverseOffset offset;offset.ctrl=ctrl;offset.target=best->first;
            xyz(offset.offset,math::VectorITransform(nodes[best->first].pos,bones[b].bindPose));reverseOffsets.push_back(offset);continue;
        }
        // Match FitCenters' actual hinge center. With two or more fixed
        // influences its scalar path uses the first two, regardless of weights.
        if(statics>=2)center=mul(add(nodes[cloud[0].first].pos,nodes[cloud[1].first].pos),.5f);
        else if(statics==1)center=nodes[cloud[0].first].pos;
        else{for(auto w:cloud){center=add(center,mul(nodes[w.first].pos,w.second));sum+=w.second;}center=mul(center,1/sum);}
        disk::FitMatrix fit;fit.node=fit.ctrl=control.at(b);fit.bone=pose(bones[b].bindPose);xyz(fit.bone.position,sub(nodes[fit.node].pos,center));xyz(fit.center,center);
        if(fitWeights.size()+cloud.size()>65535)fail("too many cloth fit weights");fit.beginDynamic=uint16_t(fitWeights.size()+statics);
        for(auto w:cloud)fitWeights.push_back({w.second,w.first,0});fit.end=uint16_t(fitWeights.size());fits.push_back(fit);
        if(statics>=1)++fit1;if(statics>=2)++fit2;
    }
    std::vector<disk::Plane> collisions;
    for(auto proxy:planes){
        std::set<uint32_t> groups;for(auto& face:proxy->faces)groups.insert(face.mesh);
        for(uint32_t group:groups){
        struct Candidate {int bone;V normal;float offset;};std::vector<Candidate> candidates;
        for(auto& f:proxy->faces){if(f.mesh!=group)continue;std::array<V,4> pos{};int bone=-1;
            for(int j=0;j<f.count;++j){auto& p=proxy->points.at(f.point[j]);if(p.weights.size()!=1)fail("collision plane must have rigid weights");int b=boneIndex.at(lower(p.weights[0].bone));if(j&&bone!=b)fail("collision face binds to multiple bones");bone=b;pos[j]=math::VectorTransform(mul(axisPosition(p.position,proxy->upAxisY,settings.modelUpAxisY),scale),import);}
            V center{},normal{};for(int j=0;j<f.count;++j){center=add(center,pos[j]);normal=add(normal,cross(pos[j],pos[(j+1)%f.count]));}center=mul(center,1.0f/f.count);normal=unit(normal);
            for(int j=0;j<f.count;++j)if(std::fabs(dot(normal,sub(pos[j],center)))>1e-3f)fail("collision polygon is not planar");
            candidates.push_back({bone,normal,dot(center,normal)});
        }
        for(size_t i=0;i<points.size();++i)if(points[i].simulated){float best=-1;const Candidate* chosen=nullptr;
            for(auto& c:candidates){float d=dot(c.normal,points[i].position)-c.offset;if(d>=best&&d>=0){best=d;chosen=&c;}}
            if(chosen){disk::Plane p;p.parent=control.at(chosen->bone);p.child=pointNode[i];xyz(p.normal,math::VectorIRotate(chosen->normal,bones[chosen->bone].bindPose));V bp{bones[chosen->bone].bindPose.m[0][3],bones[chosen->bone].bindPose.m[1][3],bones[chosen->bone].bindPose.m[2][3]};p.offset=chosen->offset-dot(bp,chosen->normal);collisions.push_back(p);}
        }
        }
    }
    if(!planes.empty()&&collisions.empty())fail("collision proxy faces face away from all simulated nodes");
    std::vector<disk::SphereRigid> sphereRigids;std::vector<disk::CapsuleRigid> capsuleRigids;
    for(const auto& c:settings.colliders){uint16_t node=control.at(boneIndex.at(lower(c.bone)));
        if(c.type==RigidCollider::Type::Sphere){disk::SphereRigid sphere;sphere.node=node;xyz(sphere.center,c.center[0]);sphere.radius=c.radius[0];sphere.stickiness=c.stickiness;sphereRigids.push_back(sphere);}
        else{disk::CapsuleRigid capsule;capsule.node=node;capsule.stickiness=c.stickiness;
            // Runtime capsule construction expects the smaller radius first.
            for(int j=0;j<2;++j){int source=c.radius[0]<=c.radius[1]?j:1-j;xyz(capsule.center[j],c.center[source]);capsule.radius[j]=c.radius[source];}capsuleRigids.push_back(capsule);}
    }
    std::stable_sort(tris.begin(),tris.end(),[](auto& a,auto& b){return a.statics>b.statics;});
    std::stable_sort(quads.begin(),quads.end(),[](auto& a,auto& b){return a.statics>b.statics;});
    // One element per SIMD packet. Identical padding lanes write identical results;
    // this avoids scheduling conflicts while preserving the four-lane engine ABI.
    std::vector<disk::SimdTri> simdTris;
    std::vector<disk::SimdQuad> simdQuads;std::vector<disk::Quad> scalarQuads;
    disk::Descriptor desc;desc.nodeCount=uint16_t(nodes.size());desc.staticNodes=uint16_t(staticCount);desc.rotLockStaticNodes=uint16_t(lockedCount);
    desc.fit1=fit1;desc.fit2=fit2;
    desc.localForce=settings.localPosition;desc.localRotation=settings.localRotation;
    desc.surfaceStretch=settings.surfaceStretch;desc.threadStretch=settings.threadStretch;
    // CSoftbody::InitFeModel treats a zero descriptor scale as an old resource
    // default and silently resets it to one. Encode disabled gravity per node.
    desc.gravityScale=settings.gravityScale==0?1:settings.gravityScale;
    desc.velocityAirDrag=settings.velocityAirDrag;desc.exponentialAirDrag=settings.exponentialAirDrag;
    desc.velocityQuadDrag=settings.velocityQuadDrag;desc.exponentialQuadDrag=settings.exponentialQuadDrag;
    desc.velocityRodDrag=settings.velocityRodDrag;desc.exponentialRodDrag=settings.exponentialRodDrag;
    desc.rodVelocitySmooth=settings.rodVelocitySmooth;desc.quadVelocitySmooth=settings.quadVelocitySmooth;
    // One smoothing pass gives the QC rates their intended effect; zero rates disable it.
    desc.rodSmoothIterations=settings.rodVelocitySmooth>0?1:0;desc.quadSmoothIterations=settings.quadVelocitySmooth>0?1:0;
    desc.windage=settings.windage;desc.windDrag=settings.windDrag;desc.worldCollisionRadius=2;
    for(auto& t:tris){disk::SimdTri d;for(int lane=0;lane<4;++lane){for(int j=0;j<3;++j)d.node[j][lane]=t.n[j];d.weight1[lane]=t.w1;d.weight2[lane]=t.w2;d.edgeLength[lane]=t.x;d.point2[0][lane]=t.y;d.point2[1][lane]=t.z;}simdTris.push_back(d);if(t.statics>=1)++desc.simdTri1;if(t.statics==2)++desc.simdTri2;}
    for(auto& q:quads){disk::SimdQuad d;for(int lane=0;lane<4;++lane)for(int j=0;j<4;++j){d.node[j][lane]=q.data.node[j];for(int k=0;k<3;++k)d.shape[j][k][lane]=q.data.shape[j][k];d.weight[j][lane]=q.data.shape[j][3];}simdQuads.push_back(d);scalarQuads.push_back(q.data);if(q.statics>=1){++desc.simdQuad1;++desc.quad1;}if(q.statics==2){++desc.simdQuad2;++desc.quad2;}}
    if(tris.size()>65535||quads.size()>65535)fail("too many FE elements");
    std::vector<disk::Transform> poses;std::vector<uint32_t> hashes;std::vector<float> inverseMasses;std::vector<disk::Integrator> integrators;std::vector<uint16_t> freeNodes;
    for(size_t i=0;i<nodes.size();++i){auto& n=nodes[i];poses.push_back(pose(n.pose));hashes.push_back(hashName(n.name));inverseMasses.push_back(n.invMass);integrators.push_back({n.drag,n.forceAttraction,n.vertexAttraction,settings.gravityScale==0?0:n.gravity});if(i>=staticCount&&!n.fit)freeNodes.push_back(uint16_t(i));}
    desc.dynamicFlags=(1u<<8)|(1u<<11); // Integrator arrays explicitly provide damping and gravity.
    for(size_t i=staticCount;i<nodes.size();++i){if(nodes[i].forceAttraction>0)desc.dynamicFlags|=1u<<9;if(nodes[i].vertexAttraction>0)desc.dynamicFlags|=1u<<10;}
    if(settings.worldCollision)desc.dynamicFlags|=(1u<<16)|(1u<<17);
    size_t dynamicCount=nodes.size()-staticCount;
    if(!dynamicCount)fail("cloth requires at least one simulated node");
    std::vector<uint16_t> treeParents(dynamicCount*2-1,65535),treeMasks(dynamicCount*2-1,0);
    std::vector<float> collisionRadii;std::vector<uint16_t> worldCollisionNodes;std::vector<disk::WorldCollisionParams> worldCollisionParams;
    bool hasRadii=false;
    for(size_t i=staticCount;i<nodes.size();++i){const auto& n=nodes[i];collisionRadii.push_back(n.collisionRadius);hasRadii|=n.collisionRadius!=0;treeMasks[i-staticCount]=n.fit?0:65535;if(n.worldCollision&&!n.fit)worldCollisionNodes.push_back(uint16_t(i));}
    if(!hasRadii)collisionRadii.clear();
    std::stable_sort(worldCollisionNodes.begin(),worldCollisionNodes.end(),[&](uint16_t a,uint16_t b){return nodes[a].worldFriction==nodes[b].worldFriction?nodes[a].groundFriction>nodes[b].groundFriction:nodes[a].worldFriction<nodes[b].worldFriction;});
    for(size_t begin=0;begin<worldCollisionNodes.size();){const auto& n=nodes[worldCollisionNodes[begin]];size_t end=begin+1;
        while(end<worldCollisionNodes.size()){const auto& next=nodes[worldCollisionNodes[end]];if(next.worldFriction-n.worldFriction>.1f||next.groundFriction-n.groundFriction>.1f)break;++end;}
        worldCollisionParams.push_back({n.worldFriction,n.groundFriction,uint16_t(begin),uint16_t(end)});begin=end;
    }
    std::vector<disk::TreeChildren> treeChildren;std::vector<uint16_t> level(dynamicCount);std::iota(level.begin(),level.end(),uint16_t(0));
    while(level.size()>1){std::vector<uint16_t> next;for(size_t i=0;i<level.size();i+=2){if(i+1==level.size()){next.push_back(level[i]);continue;}uint16_t n=uint16_t(dynamicCount+treeChildren.size());treeChildren.push_back({{level[i],level[i+1]}});treeParents[level[i]]=treeParents[level[i+1]]=n;next.push_back(n);}level=std::move(next);++desc.treeDepth;}
    for(size_t i=0;i<treeChildren.size();++i)treeMasks[dynamicCount+i]=treeMasks[treeChildren[i].child[0]]|treeMasks[treeChildren[i].child[1]];
    Buffer buf;std::memcpy(buf.bytes.data(),&desc,sizeof(desc));
#define WRITE(field,data) buf.write(offsetof(disk::Descriptor,field),data)
    WRITE(ctrlHash,hashes);WRITE(initPose,poses);WRITE(nodeInvMasses,inverseMasses);WRITE(nodeIntegrator,integrators);
    WRITE(ctrlOffsets,offsets);WRITE(fitMatrices,fits);WRITE(fitWeights,fitWeights);WRITE(collisionPlanes,collisions);
    WRITE(nodeBases,nodeBases);WRITE(reverseOffsets,reverseOffsets);WRITE(sphereRigids,sphereRigids);WRITE(capsuleRigids,capsuleRigids);
    WRITE(simdTris,simdTris);WRITE(simdQuads,simdQuads);WRITE(quads,scalarQuads);
    WRITE(rods,rods);WRITE(simdRods,simdRods);WRITE(axialEdges,axialEdges);
    WRITE(worldCollisionParams,worldCollisionParams);WRITE(worldCollisionNodes,worldCollisionNodes);WRITE(nodeCollisionRadii,collisionRadii);
    WRITE(freeNodes,freeNodes);WRITE(treeParents,treeParents);WRITE(treeMasks,treeMasks);WRITE(treeChildren,treeChildren);
    std::vector<int32_t> nameOffsets(nodes.size());WRITE(ctrlName,nameOffsets);
#undef WRITE
    disk::Array nameArray;std::memcpy(&nameArray,buf.bytes.data()+offsetof(disk::Descriptor,ctrlName),sizeof(nameArray));
    size_t names=offsetof(disk::Descriptor,ctrlName)+nameArray.offset;
    for(size_t i=0;i<nodes.size();++i){size_t field=names+i*4;int32_t offset=int32_t(buf.bytes.size()-field);std::memcpy(buf.bytes.data()+field,&offset,4);auto& s=nodes[i].name;buf.bytes.insert(buf.bytes.end(),s.begin(),s.end());buf.bytes.push_back(0);}
    resource=std::move(buf.bytes);
    std::vector<AdvancedNodeInfo> advancedNodes;for(auto& n:nodes)advancedNodes.push_back({n.name,n.pos,n.pose,n.invMass,n.fit});
    std::string advancedError;if(!AppendAdvancedResource(settings.advanced,advancedNodes,resource,&advancedError))fail(advancedError);
    if(settings.prerotate.x!=0||settings.prerotate.y!=0||settings.prerotate.z!=0){
        math::matrix3x4 rotation;math::AngleMatrix(settings.prerotate,rotation);disk::Array posesArray;std::memcpy(&posesArray,resource.data()+offsetof(disk::Descriptor,initPose),sizeof(posesArray));size_t at=offsetof(disk::Descriptor,initPose)+posesArray.offset;
        for(size_t i=0;i<nodes.size();++i){auto rotated=pose(math::ConcatTransforms(rotation,nodes[i].pose));std::memcpy(resource.data()+at+i*sizeof(rotated),&rotated,sizeof(rotated));}
    }
}
}
bool SetSetting(Settings& settings,const std::string& name,const std::string& value,std::string* error){
    try{
        const std::string key=lower(name),v=lower(value);
        bool* flag=nullptr;
        if(key=="world_collision")flag=&settings.worldCollision;
        else if(key=="add_stiffness_rods")flag=&settings.addStiffnessRods;
        else if(key=="rigid_edge_hinges")flag=&settings.rigidEdgeHinges;
        else if(key=="flex_borders")flag=&settings.flexBorders;
        else if(key=="project_render"||key=="projection")flag=&settings.projection.enabled;
        else if(key=="projection_two_sided")flag=&settings.projection.twoSided;
        if(flag){if(v=="1"||v=="true")*flag=true;else if(v=="0"||v=="false")*flag=false;else fail(key+" expects true/false or 1/0");return true;}
        if(key=="projection_root"){if(value.empty())fail("projection_root needs a bone name");settings.projection.rootBone=value;return true;}
        if(key=="fit_min_influences"||key=="projection_island"){size_t end=0;int number=0;try{number=std::stoi(value,&end);}catch(...){fail(key+" expects an integer");}if(end!=value.size()||number<(key=="projection_island"?-1:3)||number>4096)fail(key+" is outside its supported range");if(key=="projection_island")settings.projection.island=number;else settings.fitMinInfluences=number;return true;}
        if(key=="projection_envelope"){size_t end=0;float number=std::stof(value,&end);if(end!=value.size()||!std::isfinite(number)||number<0||number>1e6f)fail("projection_envelope must be in [0,1000000]");settings.projection.envelope=number;return true;}
        const std::map<std::string,float Settings::*> fields{
            {"local_position",&Settings::localPosition},{"local_rotation",&Settings::localRotation},
            {"surface_stretch",&Settings::surfaceStretch},{"thread_stretch",&Settings::threadStretch},{"gravity_scale",&Settings::gravityScale},
            {"vel_air_drag",&Settings::velocityAirDrag},{"exp_air_drag",&Settings::exponentialAirDrag},
            {"vel_quad_air_drag",&Settings::velocityQuadDrag},{"exp_quad_air_drag",&Settings::exponentialQuadDrag},
            {"vel_rod_air_drag",&Settings::velocityRodDrag},{"exp_rod_air_drag",&Settings::exponentialRodDrag},
            {"quad_vel_smooth_rate",&Settings::quadVelocitySmooth},{"quad_velocity_smooth_rate",&Settings::quadVelocitySmooth},
            {"rod_vel_smooth_rate",&Settings::rodVelocitySmooth},{"rod_velocity_smooth_rate",&Settings::rodVelocitySmooth},
            {"windage",&Settings::windage},{"wind_drag",&Settings::windDrag},{"curvature",&Settings::curvature},
            {"fit_influence_threshold",&Settings::fitInfluenceThreshold},{"quad_bend_tolerance",&Settings::quadBendTolerance}
        };
        auto field=fields.find(key);if(field==fields.end())fail("unsupported cloth setting "+name);
        size_t end=0;float number=0;try{number=std::stof(value,&end);}catch(...){fail(key+" expects a finite numeric value");}
        if(end!=value.size()||!std::isfinite(number)||number<0||number>1e6f)fail(key+" expects a finite nonnegative value at most 1000000");
        if((key=="curvature"||key=="surface_stretch"||key=="thread_stretch"||key=="local_position"||key=="local_rotation"||key=="fit_influence_threshold"||key=="quad_bend_tolerance")&&number>1)fail(key+" must be in [0,1]");
        settings.*(field->second)=number;return true;
    }catch(const std::exception& e){if(error)*error=e.what();return false;}
}
bool ReadProxy(const dmx::Datamodel& dm,bool planes,Proxy& out,std::string* error,const Settings* settings){try{read(dm,planes,out,settings?*settings:Settings{});return true;}catch(const std::exception& e){if(error)*error=e.what();return false;}}
bool Build(const std::vector<Proxy>& proxies,const std::vector<Bone>& bones,const math::matrix3x4& transform,float scale,std::vector<uint8_t>& resource,std::string* error,const Settings* settings){try{build(proxies,bones,transform,scale,resource,settings?*settings:Settings{});return true;}catch(const std::exception& e){resource.clear();if(error)*error=e.what();return false;}}
}
