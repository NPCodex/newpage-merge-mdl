#include "clothprojection.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
namespace pulse::cloth {
namespace {
using V=math::Vector3;
V add(V a,V b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
V sub(V a,V b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
V mul(V a,float s){return {a.x*s,a.y*s,a.z*s};}
float dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
float len(V a){return std::sqrt(dot(a,a));}
std::string lower(std::string s){for(auto& c:s)if(c>='A'&&c<='Z')c+=32;return s;}
[[noreturn]] void fail(const std::string& s){throw std::runtime_error("cloth projection: "+s);}
struct Surface { std::array<uint32_t,4> point{};int count=0,island=0; };
struct Contact { float distance=std::numeric_limits<float>::max(),signedDistance=0;V normal;std::array<float,4> weight{};const Surface* surface=nullptr; };
Contact project(V p,const Surface& s,const std::vector<Point*>& points){
    Contact out;out.surface=&s;V v[4];for(int i=0;i<s.count;++i)v[i]=points[s.point[i]]->position;
    V n=s.count==4?cross(sub(v[2],v[0]),sub(v[3],v[1])):cross(sub(v[1],v[0]),sub(v[2],v[0]));float size=len(n);if(size<1e-8f)return out;n=mul(n,1/size);out.normal=n;
    float side[4];bool inside=true;for(int i=0;i<s.count;++i){V edge=sub(v[(i+1)%s.count],v[i]);float el=len(edge);if(el<1e-8f)return out;side[i]=dot(sub(p,v[i]),mul(cross(n,edge),1/el));inside&=side[i]>=-1e-5f;}
    if(inside){
        if(s.count==4){float even=side[0]/(side[0]+side[2]),odd=side[1]/(side[1]+side[3]);out.weight={odd*(1-even),(1-odd)*(1-even),(1-odd)*even,odd*even};}
        else {V e0=sub(v[1],v[0]),e1=sub(v[2],v[0]),q=sub(p,v[0]);float a=dot(e0,e0),b=dot(e0,e1),c=dot(e1,e1),d=dot(q,e0),e=dot(q,e1),det=a*c-b*b;if(det<1e-12f)return out;float u=(c*d-b*e)/det,w=(a*e-b*d)/det;out.weight={1-u-w,u,w,0};}
        V at{};for(int i=0;i<s.count;++i)at=add(at,mul(v[i],out.weight[i]));out.distance=len(sub(p,at));out.signedDistance=dot(sub(p,at),n);
    }else for(int i=0;i<s.count;++i){int j=(i+1)%s.count;V edge=sub(v[j],v[i]);float t=std::clamp(dot(sub(p,v[i]),edge)/dot(edge,edge),0.f,1.f);V q=add(v[i],mul(edge,t));float distance=len(sub(p,q));if(distance<out.distance){out.distance=distance;out.signedDistance=distance;out.normal=distance>1e-8f?mul(sub(p,q),1/distance):n;out.weight={};out.weight[i]=1-t;out.weight[j]=t;}}
    return out;
}
int findBone(const source::Source& s,const std::string& name){for(size_t i=0;i<s.localBone.size();++i)if(lower(s.localBone[i].name)==lower(name))return int(i);return -1;}
int appendBone(source::Source& s,const std::string& name,int parent,V world){
    if(findBone(s,name)>=0)fail("generated bone name collides with authored bone "+name);
    // The compiler may collapse unused source bones after projection. Keep its
    // wider source budget here; the existing final VVD bone check runs later.
    if(s.localBone.size()>=size_t(pulse::limits::kMaxBones))fail("projection exceeds the source bone limit");
    int id=int(s.localBone.size());math::matrix3x4 pose;pose.m[0][3]=world.x;pose.m[1][3]=world.y;pose.m[2][3]=world.z;
    auto local=parent>=0?math::ConcatTransforms(math::MatrixInvert(s.boneToPose.at(parent)),pose):pose;source::SrcBonePose bind;math::MatrixAngles(local,bind.rot,bind.pos);
    s.localBone.push_back({name,parent,false});s.boneToPose.push_back(pose);s.numbones=int(s.localBone.size());
    for(auto& animation:s.anims)for(auto& frame:animation.frames){if(frame.size()!=size_t(id))fail("source animation bone count mismatch");frame.push_back(bind);}
    return id;
}
}
bool ProjectRenderVertices(std::vector<Proxy>& proxies,const std::vector<source::Source*>& renderSources,const Settings& settings,std::vector<std::string>& generatedBones,std::string* error){
    try{
        if(!settings.projection.enabled)return true;
        std::vector<Point*> points;std::vector<Surface> surfaces;
        for(auto& proxy:proxies){if(proxy.planeCollision)continue;size_t base=points.size();for(auto& p:proxy.points){if(proxy.upAxisY!=settings.modelUpAxisY)p.position=proxy.upAxisY?V{p.position.x,-p.position.z,p.position.y}:V{p.position.x,p.position.z,-p.position.y};points.push_back(&p);}proxy.upAxisY=settings.modelUpAxisY;
            for(auto& f:proxy.faces){Surface s;s.count=f.count;s.point=f.point;for(int i=0;i<s.count;++i){if(s.point[i]>=proxy.points.size())fail("invalid proxy face index");s.point[i]+=uint32_t(base);}surfaces.push_back(s);}}
        if(points.empty()||surfaces.empty())fail("projection requires a cloth proxy surface");
        std::vector<int> component(points.size(),-1);std::vector<std::vector<uint32_t>> edges(points.size());
        for(auto& f:surfaces)for(int i=1;i<f.count;++i){edges[f.point[0]].push_back(f.point[i]);edges[f.point[i]].push_back(f.point[0]);}
        int count=0;for(size_t i=0;i<points.size();++i)if(component[i]<0){std::vector<uint32_t> queue{uint32_t(i)};component[i]=count;for(size_t j=0;j<queue.size();++j)for(auto k:edges[queue[j]])if(component[k]<0){component[k]=count;queue.push_back(k);}++count;}
        if(settings.projection.island>=count)fail("island index is outside the proxy connected components");
        for(auto& s:surfaces)s.island=component[s.point[0]];
        std::vector<source::Source*> sources;for(auto* s:renderSources)if(s&&std::find(sources.begin(),sources.end(),s)==sources.end())sources.push_back(s);
        if(sources.empty())fail("no render source available");
        std::string root=settings.projection.rootBone;bool synthetic=root.empty();if(synthetic)root="$cloth_root";
        std::vector<std::string> names(points.size());for(size_t i=0;i<points.size();++i)if(points[i]->simulated){names[i]="$cloth_v"+std::to_string(i);generatedBones.push_back(names[i]);}
        if(synthetic)generatedBones.push_back(root);
        for(auto* source:sources){int rootIndex=findBone(*source,root);if(synthetic){if(rootIndex>=0)fail("generated root name collides with an authored bone");int parent=-1;for(size_t i=0;i<source->localBone.size();++i)if(source->localBone[i].parent<0&&!source->localBone[i].isNonSkeletal){parent=int(i);break;}rootIndex=appendBone(*source,root,parent,{});}else if(rootIndex<0)fail("projection root bone is missing from source: "+root);
            std::vector<int> generated(points.size(),-1);for(size_t i=0;i<points.size();++i)if(points[i]->simulated)generated[i]=appendBone(*source,names[i],rootIndex,points[i]->position);
            for(auto& vertex:source->vertex){Contact best,other;for(auto& surface:surfaces){if(settings.projection.island>=0&&surface.island!=settings.projection.island)continue;auto c=project(vertex.position,surface,points);if(c.distance<best.distance){other=best;best=c;}else if(c.distance<other.distance)other=c;}
                if(!best.surface||!std::isfinite(best.distance)||(settings.projection.envelope>0&&best.distance>settings.projection.envelope))continue;
                // Adjacent faces on the same side must not hide the opposite
                // enclosing surface. Find its nearest eligible interior hit.
                other=Contact{};
                if(settings.projection.twoSided&&best.signedDistance<0)for(auto& surface:surfaces){if(settings.projection.island>=0&&surface.island!=settings.projection.island)continue;auto c=project(vertex.position,surface,points);if(c.signedDistance<0&&dot(best.normal,c.normal)<-.5f&&c.distance<other.distance)other=c;}
                bool volume=settings.projection.twoSided&&other.surface&&best.signedDistance<0&&other.signedDistance<0&&dot(best.normal,other.normal)<-.5f&&(settings.projection.envelope==0||other.distance<=settings.projection.envelope);
                float fraction=volume?other.distance/(best.distance+other.distance):1;std::map<int,float> weights;
                auto bind=[&](const Contact& c,float factor){for(int j=0;j<c.surface->count;++j){size_t i=c.surface->point[j];float weight=factor*c.weight[j];if(weight<=1e-7f)continue;if(generated[i]>=0)weights[generated[i]]+=weight;else if(points[i]->weights.empty())weights[rootIndex]+=weight;else for(auto& influence:points[i]->weights){int b=findBone(*source,influence.bone);if(b<0)fail("fixed proxy bone is missing from render source: "+influence.bone);weights[b]+=weight*influence.weight;}}};
                bind(best,fraction);
                if(volume){auto first=std::move(weights);weights.clear();bind(other,1-fraction);auto second=std::move(weights);weights.clear();
                    auto retainSide=[&](const std::map<int,float>& side,size_t limit,float total){std::vector<std::pair<int,float>> sorted(side.begin(),side.end());std::stable_sort(sorted.begin(),sorted.end(),[](auto a,auto b){return a.second>b.second;});if(sorted.size()>limit)sorted.resize(limit);float sum=0;for(auto w:sorted)sum+=w.second;if(sum>0)for(auto w:sorted)weights[w.first]+=w.second*total/sum;};
                    // The VVD ABI has three weights. Reserve a slot on each
                    // surface and retain the original through-volume fraction.
                    retainSide(first,fraction>=.5f?2:1,fraction);retainSide(second,fraction>=.5f?1:2,1-fraction);
                }
                std::vector<std::pair<int,float>> sorted(weights.begin(),weights.end());std::stable_sort(sorted.begin(),sorted.end(),[](auto a,auto b){return a.second>b.second;});if(sorted.size()>3)sorted.resize(3);float sum=0;for(auto w:sorted)sum+=w.second;if(sum<=0)continue;vertex.boneweight={};for(auto w:sorted){int k=vertex.boneweight.numbones++;vertex.boneweight.bone[k]=w.first;vertex.boneweight.weight[k]=w.second/sum;}
            }
        }
        for(size_t i=0;i<points.size();++i){if(points[i]->simulated)points[i]->weights={{names[i],1}};else if(points[i]->weights.empty())points[i]->weights={{root,1}};}
        for(auto& proxy:proxies)if(!proxy.planeCollision){proxy.bones.clear();for(auto& p:proxy.points)for(auto& w:p.weights)if(std::find(proxy.bones.begin(),proxy.bones.end(),w.bone)==proxy.bones.end())proxy.bones.push_back(w.bone);}
        return true;
    }catch(const std::exception& e){if(error)*error=e.what();return false;}
}
}
