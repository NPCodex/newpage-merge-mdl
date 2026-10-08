#include "subd.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>

namespace pulse::subd {
namespace {
using Vec = math::Vector3;
using Four = std::array<uint16_t, 4>;
struct Work {
    Four v{}, size{}, center{}, valence{}, minimum{}, boundary{}, edge{}, corner{}, gap{}, neighbor{};
    std::array<Four, 4> uv{};
    std::array<int, 4> twin{{-1,-1,-1,-1}}, sector{};
    std::array<std::vector<uint16_t>, 4> ring;
};
int next(int e) { return (e & ~3) | ((e + 1) & 3); }
int prev(int e) { return (e & ~3) | ((e + 3) & 3); }
bool equal(const Vec& a, const Vec& b) { return a.x==b.x && a.y==b.y && a.z==b.z; }
Vec difference(const Vec& a,const Vec& b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
double dot(const Vec& a,const Vec& b) { return double(a.x)*b.x+double(a.y)*b.y+double(a.z)*b.z; }
void fail(const char* why) { throw std::runtime_error(std::string("SubD: ")+why); }

struct Builder {
    const std::vector<Vertex>& input;
    Mesh& out;
    std::vector<Work> faces;
    std::vector<int> position;
    std::vector<std::vector<int>> incident;
    const Vertex& vertex(int i) const { return input[out.vertices[i]]; }
    int twin(int e) const { return faces[e/4].twin[e%4]; }
    int id(int e) const { return faces[e/4].v[e%4]; }
    bool boundary(int e) const { return faces[e/4].edge[e%4]!=0; }
    int byTail(int e) const { int t=twin(e); return t<0 ? -1 : next(t); }
    int byHead(int e) const { int t=twin(e); return t<0 ? -1 : prev(t); }

    void adjacency() {
        std::map<std::pair<int,int>, std::vector<int>> edges;
        incident.assign(out.vertices.size(),{});
        for(size_t f=0;f<faces.size();++f) {
            auto& p=faces[f]; p.twin.fill(-1);p.edge.fill(0);p.boundary.fill(0);
            std::set<int> corners;
            for(int k=0;k<4;++k) {
                int e=int(f)*4+k, a=position[id(e)], b=position[id(next(e))];
                if(!corners.insert(a).second)fail("a control quad has repeated positions");
                incident[a].push_back(e);
                edges[std::minmax(a,b)].push_back(e);
            }
        }
        for(const auto& entry:edges) {
            const auto& es=entry.second;
            if(es.size()>2)fail("non-manifold edge has more than two incident quads");
            if(es.size()==2) {
                int a=es[0],b=es[1];
                if(position[id(a)]!=position[id(next(b))])fail("adjacent quads have inconsistent winding");
                faces[a/4].twin[a%4]=b;faces[b/4].twin[b%4]=a;
            } else faces[es[0]/4].edge[es[0]%4]=1;
        }
        // An edge-manifold mesh can still have a bow-tie vertex. The one-ring
        // shader requires one connected disk (or one closed fan) at each point.
        for(const auto& fan:incident) if(!fan.empty()) {
            std::set<int> visited;
            std::vector<int> pending{fan.front()};
            while(!pending.empty()) {
                int e=pending.back();pending.pop_back();if(!visited.insert(e).second)continue;
                int a=byTail(e),b=twin(prev(e));
                if(a>=0)pending.push_back(a);if(b>=0)pending.push_back(b);
            }
            if(visited.size()!=fan.size())fail("non-manifold vertex has disconnected quad fans");
        }
    }

    void orient() {
        std::vector<std::array<int,2>> flags(faces.size(),std::array<int,2>{-1,-1});
        auto propagate=[&](int edge,bool direction) {
            for(size_t steps=0;steps<=faces.size()*2;++steps) {
                int t=twin(edge);if(t<0)return;
                int axis=(t%2)==0 ? 1 : 0;
                int value=((t%4)==(axis==0?1:0)) ^ direction;
                int& flag=flags[t/4][axis];if(flag>=0)return;
                flag=value;edge=next(next(t));
            }
            fail("invalid cyclic patch orientation");
        };
        for(size_t f=0;f<faces.size();++f) {
            if(flags[f][0]<0) {flags[f][0]=0;propagate(int(f)*4+1,false);propagate(int(f)*4+3,true);}
            if(flags[f][1]<0) {flags[f][1]=0;propagate(int(f)*4,false);propagate(int(f)*4+2,true);}
        }
        const int rotations[4]={0,1,3,2};
        for(size_t f=0;f<faces.size();++f) {
            int count=rotations[2*flags[f][1]+flags[f][0]];Four old=faces[f].v;
            for(int k=0;k<4;++k)faces[f].v[k]=old[(k+4-count)%4];
        }
        adjacency();
    }

    void creases() {
        for(size_t f=0;f<faces.size();++f)for(int k=0;k<4;++k) {
            int e=int(f)*4+k,t=twin(e);
            if(t>=0 && (!equal(vertex(id(e)).normal,vertex(id(next(t))).normal) ||
                        !equal(vertex(id(next(e))).normal,vertex(id(t)).normal))) faces[f].edge[k]=1;
        }
        for(size_t f=0;f<faces.size();++f)for(int k=0;k<4;++k) {
            auto& p=faces[f];int e=int(f)*4+k,start=e;
            for(size_t step=0;step<=faces.size();++step) {
                if(boundary(start))break;
                int n=byTail(start);if(n<0)break;if(n==e){start=e;break;}start=n;
                if(step==faces.size())fail("invalid quad sector");
            }
            int point=position[id(e)],count=0;
            std::set<std::pair<int,int>> boundaryEdges;
            for(int ce:incident[point])for(int edge:{ce,prev(ce)})if(boundary(edge))
                boundaryEdges.insert(std::minmax(position[id(edge)],position[id(next(edge))]));
            count=int(boundaryEdges.size());
            p.boundary[k]=count>=2;p.corner[k]=count>2;
            p.sector[k]=count==1 ? e : start;
        }
    }

    void rings() {
        for(size_t f=0;f<faces.size();++f) {
            Work& p=faces[f];size_t total=0;
            for(int k=0;k<4;++k) {
                int base=int(f)*4+k, start=p.sector[k],end=twin(start),e=prev(start);
                auto& ring=p.ring[k];ring={uint16_t(id(start)),uint16_t(id(next(start)))};
                p.center[k]=1;p.valence[k]=1;
                for(size_t step=0;;++step) {
                    if(step>faces.size())fail("invalid quad one-ring traversal");
                    ring.push_back(uint16_t(id(prev(e))));
                    ring.push_back(uint16_t(id(e)));++p.valence[k];
                    if(twin(e)==base)p.center[k]=uint16_t(ring.size()-1);
                    int n=boundary(e)&&p.boundary[k] ? -1 : byHead(e);
                    if(n<0 || n==end) {
                        if(n>=0)ring.push_back(uint16_t(id(prev(n))));
                        break;
                    }
                    e=n;
                }
                if(p.valence[k]>16)fail("control point valence exceeds the topology bitfield capacity");
                p.size[k]=uint16_t(ring.size());total+=ring.size();
                if(total>52)fail("patch one-ring exceeds 52 control references");
                auto it=std::min_element(ring.begin(),ring.end(),[&](int a,int b){return position[a]<position[b];});
                p.minimum[k]=uint16_t(it-ring.begin());
                p.gap[k]=65535;
                if(p.boundary[k]) {
                    if(!p.corner[k])p.gap[k]=p.valence[k]==2?16383:32767;
                    else {
                        Vec a=difference(vertex(ring[1]).position,vertex(ring[0]).position);
                        Vec b=difference(vertex(ring.back()).position,vertex(ring[0]).position);
                        double length=std::sqrt(dot(a,a)*dot(b,b));
                        if(length<=0)fail("zero-length boundary edge");
                        p.gap[k]=uint16_t(std::acos(std::clamp(dot(a,b)/length,-1.0,1.0))*65535.0/(2*3.141592653589793));
                    }
                }
            }
        }
    }

    void texcoords() {
        for(size_t f=0;f<faces.size();++f)for(int k=0;k<4;++k) {
            Work& p=faces[f];int e=int(f)*4+k;
            for(auto& uv:p.uv)uv[k]=out.vertices[id(e)];
            int v=twin(e),u=twin(prev(e));
            if(v>=0 && v/4>int(f))p.uv[1][k]=out.vertices[id(next(v))];
            if(u>=0 && u/4>int(f))p.uv[2][k]=out.vertices[id(u)];
            int highest=e;
            for(int n:incident[position[id(e)]])if(n/4>highest/4)highest=n;
            p.uv[3][k]=out.vertices[id(highest)];
        }
    }

    void run(const std::vector<source::SrcQuad>& quads) {
        if(input.size()>65536)fail("mesh exceeds uint16 control-vertex capacity");
        // The renderer expands each patch to four vertices and uploads one
        // row per patch to its fixed 8192-row SubD texture. A mesh is emitted
        // as one strip group, including both REG and EXTRA strips.
        if(quads.size()>8192)fail("mesh exceeds the renderer capacity of 8192 SubD patches");
        std::map<uint32_t,uint16_t> mapping;
        for(const auto& quad:quads) {
            Work p;
            for(int k=0;k<4;++k) {
                uint32_t v=quad.vertex[k];if(v>=input.size())fail("control vertex index is out of range");
                auto found=mapping.find(v);
                if(found==mapping.end()) {
                    uint16_t index=uint16_t(out.vertices.size());out.vertices.push_back(uint16_t(v));
                    found=mapping.emplace(v,index).first;
                }
                p.v[k]=found->second;
            }
            faces.push_back(p);
        }
        std::map<std::tuple<float,float,float>,int> positions;
        for(size_t i=0;i<out.vertices.size();++i) {
            const Vec& p=vertex(int(i)).position;
            if(!std::isfinite(p.x)||!std::isfinite(p.y)||!std::isfinite(p.z))fail("non-finite control point");
            auto found=positions.emplace(std::make_tuple(p.x,p.y,p.z),int(i));position.push_back(found.first->second);
        }
        adjacency();orient();creases();rings();texcoords();
        for(const auto& p:faces) {
            Patch patch;patch.indices=p.v;patch.regular=true;
            for(int k=0;k<4;++k)patch.regular &= p.valence[k]==4 && !p.boundary[k] && !p.edge[k];
            auto append=[&](const Four& a){patch.topology.insert(patch.topology.end(),a.begin(),a.end());};
            append(p.size);append(p.center);append(p.valence);append(p.minimum);
            append(p.boundary);append(p.edge);append(p.corner);append(p.gap);append(p.neighbor);
            patch.topology.insert(patch.topology.end(),8,16384);
            for(const auto& uv:p.uv)append(uv);
            for(const auto& ring:p.ring)patch.topology.insert(patch.topology.end(),ring.begin(),ring.end());
            out.patches.push_back(std::move(patch));
        }
        std::stable_partition(out.patches.begin(),out.patches.end(),[](const Patch& p){return p.regular;});
    }
};
}

bool Build(const std::vector<Vertex>& vertices,const std::vector<source::SrcQuad>& quads,
           Mesh& out,std::string* error) {
    try { Mesh result;Builder{vertices,result}.run(quads);out=std::move(result);return true; }
    catch(const std::exception& e) {if(error)*error=e.what();return false;}
}

namespace {
using Stencil = std::map<int,double>;
void add(Stencil& dst,const Stencil& src,double weight) {
    for(const auto& p:src)dst[p.first]+=p.second*weight;
}
Vec scaledAdd(Vec dst,const Vec& src,double w) {
    dst.x+=float(src.x*w);dst.y+=float(src.y*w);dst.z+=float(src.z*w);return dst;
}
Vec cross(const Vec& a,const Vec& b) {
    return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};
}
bool near(const Vec& a,const Vec& b) {
    return std::abs(a.x-b.x)<=1e-5f && std::abs(a.y-b.y)<=1e-5f && std::abs(a.z-b.z)<=1e-5f;
}
bool nonzero(const Vec& v) {return v.x!=0 || v.y!=0 || v.z!=0;}
struct BakeQuad {
    std::array<int,4> v{};
    std::array<Stencil,4> attrs;
    std::array<bool,4> sharp{};
    uint16_t tag=0;
    int material=0;
};
struct BakeEdge {int a=0,b=0,point=0;bool sharp=false;std::vector<int> corners;};
struct BakeTopology {
    std::vector<BakeEdge> edges;
    std::vector<int> faceEdges,twins;
    std::vector<std::vector<int>> vertexFaces,vertexEdges;
};
BakeTopology topology(std::vector<BakeQuad>& quads,int vertexCount,bool validate) {
    BakeTopology t;t.faceEdges.resize(quads.size()*4);t.twins.assign(quads.size()*4,-1);
    t.vertexFaces.resize(vertexCount);t.vertexEdges.resize(vertexCount);
    std::map<std::pair<int,int>,int> ids;
    for(size_t f=0;f<quads.size();++f) {
        auto& q=quads[f];std::set<int> corners;
        for(int k=0;k<4;++k) {
            int a=q.v[k],b=q.v[(k+1)%4],corner=int(f)*4+k;
            if(!corners.insert(a).second)fail("a control quad has repeated positions");
            auto key=std::minmax(a,b);auto found=ids.find(key);
            int id;
            if(found==ids.end()) {id=int(t.edges.size());ids[key]=id;BakeEdge e;e.a=key.first;e.b=key.second;t.edges.push_back(e);}
            else id=found->second;
            auto& edge=t.edges[id];edge.corners.push_back(corner);edge.sharp|=q.sharp[k];
            if(edge.corners.size()>2)fail("non-manifold edge has more than two incident quads");
            t.faceEdges[corner]=id;t.vertexFaces[a].push_back(corner);
        }
    }
    for(size_t i=0;i<t.edges.size();++i) {
        auto& e=t.edges[i];t.vertexEdges[e.a].push_back(int(i));t.vertexEdges[e.b].push_back(int(i));
        e.sharp|=e.corners.size()==1;
        if(e.corners.size()==2) {
            int a=e.corners[0],b=e.corners[1];
            if(quads[a/4].v[a%4]!=quads[b/4].v[(b+1)%4])fail("adjacent quads have inconsistent winding");
            t.twins[a]=b;t.twins[b]=a;
        }
        for(int c:e.corners)quads[c/4].sharp[c%4]=e.sharp;
    }
    if(validate)for(const auto& fan:t.vertexFaces)if(!fan.empty()) {
        std::set<int> visited;std::vector<int> pending{fan.front()};
        while(!pending.empty()) {
            int e=pending.back();pending.pop_back();if(!visited.insert(e).second)continue;
            int a=t.twins[e],b=t.twins[prev(e)];
            if(a>=0)pending.push_back(next(a));if(b>=0)pending.push_back(b);
        }
        if(visited.size()!=fan.size())fail("non-manifold vertex has disconnected quad fans");
    }
    return t;
}

struct BakeMesh {
    const source::Source& src;
    std::vector<Stencil> points;
    std::vector<BakeQuad> quads;
    std::map<int,int> aliases; // authored vertex -> welded representative

    void loadMaterial(int material,std::map<std::tuple<float,float,float>,int>& positions) {
        const auto& mesh=src.mesh[material];
        using Triangle=std::array<uint32_t,3>;
        auto key=[](uint32_t a,uint32_t b,uint32_t c){Triangle t{a,b,c};std::sort(t.begin(),t.end());return t;};
        std::map<Triangle,std::vector<uint16_t>> triangles;
        for(int i=0;i<mesh.numfaces;++i) {
            int index=mesh.faceoffset+i;const auto& f=src.face.at(index);
            triangles[key(f.a,f.b,f.c)].push_back(src.faceTag.empty()?0:src.faceTag.at(index));
        }
        for(const auto& authored:src.quads)if(authored.material==material) {
            const auto* v=authored.vertex;
            for(int k=0;k<4;++k)if(v[k]>=uint32_t(mesh.numvertices))fail("quad index no longer matches edited source vertices");
            Triangle a=key(v[0],v[1],v[2]),b=key(v[0],v[2],v[3]);
            if(triangles[a].empty() || triangles[b].empty()) {a=key(v[0],v[1],v[3]);b=key(v[1],v[2],v[3]);}
            if(triangles[a].empty() || triangles[b].empty())fail("authored quad topology was changed by a triangle mesh edit");
            BakeQuad q;q.tag=triangles[a].back();q.material=material;
            if(q.tag!=triangles[b].back())fail("a control quad has conflicting triangle face tags");
            triangles[a].pop_back();triangles[b].pop_back();
            for(int k=0;k<4;++k) {
                int original=int(v[k])+mesh.vertexoffset;const auto& p=src.vertex.at(original).position;
                if(!std::isfinite(p.x)||!std::isfinite(p.y)||!std::isfinite(p.z))fail("non-finite control point");
                auto found=positions.emplace(std::make_tuple(p.x,p.y,p.z),int(points.size()));
                if(found.second)points.push_back(Stencil{{original,1}});
                q.v[k]=found.first->second;q.attrs[k][original]=1;
                aliases[original]=points[q.v[k]].begin()->first;
            }
            quads.push_back(std::move(q));
        }
        for(const auto& entry:triangles)if(!entry.second.empty())fail("render sources must contain only authored DMX quads; triangle edits cannot be subdivided");
    }

    void load() {
        // Material and UV boundaries do not split the geometric surface.
        // Preserve face-varying attributes while sharing position stencils.
        std::map<std::tuple<float,float,float>,int> positions;
        for(int i=0;i<src.nummeshes;++i)loadMaterial(src.meshindex.at(i),positions);
        auto t=topology(quads,int(points.size()),true);
        for(auto& e:t.edges)if(e.corners.size()==2) {
            int a=e.corners[0],b=e.corners[1];
            auto normal=[&](int c)->const Vec& {return src.vertex[quads[c/4].attrs[c%4].begin()->first].normal;};
            bool crease=!equal(normal(a),normal(next(b))) || !equal(normal(next(a)),normal(b));
            quads[a/4].sharp[a%4]=quads[b/4].sharp[b%4]=crease;
        }
        auto boneMap=[](const source::SrcBoneWeight& b) {
            std::map<int,float> values;for(int i=0;i<b.numbones;++i)values[b.bone[i]]+=b.weight[i];return values;
        };
        for(const auto& pair:aliases)if(pair.first!=pair.second) {
            auto a=boneMap(src.vertex[pair.first].boneweight),b=boneMap(src.vertex[pair.second].boneweight);
            for(const auto& weight:a)if(std::abs(weight.second-b[weight.first])>1e-5f)fail("coincident control vertices have conflicting bone weights");
            for(const auto& weight:b)if(std::abs(weight.second-a[weight.first])>1e-5f)fail("coincident control vertices have conflicting bone weights");
        }
    }

    void refine() {
        auto t=topology(quads,int(points.size()),false);
        std::vector<Stencil> facePoints(quads.size());
        for(size_t f=0;f<quads.size();++f)for(int k=0;k<4;++k)add(facePoints[f],points[quads[f].v[k]],.25);
        std::vector<Stencil> refined(points.size());
        for(size_t v=0;v<points.size();++v) {
            std::vector<int> sharp;
            for(int e:t.vertexEdges[v])if(t.edges[e].sharp)sharp.push_back(t.edges[e].a==int(v)?t.edges[e].b:t.edges[e].a);
            if(sharp.size()>2)refined[v]=points[v];
            else if(sharp.size()==2) {
                add(refined[v],points[v],.75);add(refined[v],points[sharp[0]],.125);add(refined[v],points[sharp[1]],.125);
            } else {
                const double n=double(t.vertexFaces[v].size());
                if(n<3)fail("smooth control vertex needs at least three incident quads");
                add(refined[v],points[v],(n-3)/n);
                for(int corner:t.vertexFaces[v])add(refined[v],facePoints[corner/4],1/(n*n));
                for(int e:t.vertexEdges[v]) {
                    add(refined[v],points[t.edges[e].a],1/(n*n));add(refined[v],points[t.edges[e].b],1/(n*n));
                }
            }
        }
        for(auto& edge:t.edges) {
            edge.point=int(refined.size());Stencil p;
            double weight=edge.sharp?.5:.25;
            add(p,points[edge.a],weight);add(p,points[edge.b],weight);
            if(!edge.sharp)for(int c:edge.corners)add(p,facePoints[c/4],.25);
            refined.push_back(std::move(p));
        }
        int faceBase=int(refined.size());
        for(auto& point:facePoints)refined.push_back(std::move(point));
        std::vector<BakeQuad> children;children.reserve(quads.size()*4);
        for(size_t f=0;f<quads.size();++f) {
            const auto& q=quads[f];Stencil center;
            for(int k=0;k<4;++k)add(center,q.attrs[k],.25);
            for(int k=0;k<4;++k) {
                int before=(k+3)%4,after=(k+1)%4;BakeQuad child;
                child.v={q.v[k],t.edges[t.faceEdges[f*4+k]].point,faceBase+int(f),t.edges[t.faceEdges[f*4+before]].point};
                child.attrs[0]=q.attrs[k];child.attrs[2]=center;
                add(child.attrs[1],q.attrs[k],.5);add(child.attrs[1],q.attrs[after],.5);
                add(child.attrs[3],q.attrs[before],.5);add(child.attrs[3],q.attrs[k],.5);
                child.sharp={q.sharp[k],false,false,q.sharp[before]};child.tag=q.tag;child.material=q.material;
                children.push_back(std::move(child));
            }
        }
        points=std::move(refined);quads=std::move(children);
    }

    void emit(source::Source& dst) {
        auto t=topology(quads,int(points.size()),false);
        std::vector<int> sectors(quads.size()*4);
        for(size_t i=0;i<sectors.size();++i)sectors[i]=int(i);
        auto root=[&](int v){while(sectors[v]!=v){sectors[v]=sectors[sectors[v]];v=sectors[v];}return v;};
        auto join=[&](int a,int b){a=root(a);b=root(b);if(a!=b)sectors[b]=a;};
        for(const auto& e:t.edges)if(!e.sharp && e.corners.size()==2) {
            int a=e.corners[0],b=e.corners[1];join(a,next(b));join(next(a),b);
        }
        for(size_t i=0;i<sectors.size();++i)sectors[i]=root(int(i));
        auto normals=[&](const std::vector<Vec>& positions) {
            std::vector<Vec> result(sectors.size());
            for(size_t f=0;f<quads.size();++f) {
                const auto& q=quads[f];const auto& a=positions[q.v[0]];
                Vec n=cross(difference(positions[q.v[2]],a),difference(positions[q.v[1]],a));
                n=scaledAdd(n,cross(difference(positions[q.v[3]],a),difference(positions[q.v[2]],a)),1);
                for(int k=0;k<4;++k)result[sectors[f*4+k]]=scaledAdd(result[sectors[f*4+k]],n,1);
            }
            for(auto& n:result)if(nonzero(n))math::VectorNormalize(n);
            return result;
        };
        std::vector<Vec> positions(points.size());std::vector<source::SrcBoneWeight> weights(points.size());
        for(size_t i=0;i<points.size();++i) {
            std::map<int,double> bones;
            for(const auto& p:points[i]) {
                const auto& v=src.vertex[p.first];positions[i]=scaledAdd(positions[i],v.position,p.second);
                for(int b=0;b<v.boneweight.numbones;++b)bones[v.boneweight.bone[b]]+=v.boneweight.weight[b]*p.second;
            }
            std::vector<int> ids;std::vector<float> values;
            for(const auto& bone:bones) {ids.push_back(bone.first);values.push_back(float(bone.second));}
            if(!ids.empty()) {
                auto& out=weights[i];out.numbones=source::SortAndBalanceBones(int(ids.size()),limits::kMaxSrcBoneWeights,ids.data(),values.data());
                for(int b=0;b<out.numbones;++b){out.bone[b]=ids[b];out.weight[b]=values[b];}
            }
        }
        auto baseNormals=normals(positions);
        struct Ref {int point,sector;Stencil attrs;};std::vector<Ref> refs;
        using Key=std::tuple<int,int,Stencil>;std::map<Key,int> cornerIds;
        int currentMaterial=-1;
        for(size_t f=0;f<quads.size();++f) {
            int material=quads[f].material;auto& mesh=dst.mesh[material];
            if(material!=currentMaterial) {
                currentMaterial=material;cornerIds.clear();
                mesh.vertexoffset=int(dst.vertex.size());mesh.faceoffset=int(dst.face.size());
            }
            std::array<uint32_t,4> ids;
            for(int k=0;k<4;++k) {
                int point=quads[f].v[k],sector=sectors[f*4+k];const auto& attrs=quads[f].attrs[k];
                Key key{point,sector,attrs};auto found=cornerIds.emplace(key,int(dst.vertex.size())-mesh.vertexoffset);ids[k]=uint32_t(found.first->second);
                if(!found.second)continue;
                source::SrcVertex v{};v.position=positions[point];v.normal=baseNormals[sector];v.boneweight=weights[point];v.material=material;
                if(!nonzero(v.normal))fail("subdivision produced a degenerate surface normal");
                double outline=0;bool hasOutline=true;
                for(const auto& a:attrs) {
                    const auto& old=src.vertex[a.first];v.texcoord.x+=float(old.texcoord.x*a.second);v.texcoord.y+=float(old.texcoord.y*a.second);
                    hasOutline&=old.outline>=0;outline+=old.outline*a.second;
                }
                v.outline=hasOutline?float(outline):-1;
                dst.vertex.push_back(v);refs.push_back({point,sector,attrs});
            }
            dst.face.push_back({ids[0],ids[1],ids[2]});dst.face.push_back({ids[0],ids[2],ids[3]});
            dst.faceTag.push_back(quads[f].tag);dst.faceTag.push_back(quads[f].tag);
            mesh.numvertices=int(dst.vertex.size())-mesh.vertexoffset;mesh.numfaces=int(dst.face.size())-mesh.faceoffset;
        }
        for(size_t m=0;m<src.morphs.size();++m) {
            std::map<int,const source::SrcVertAnim*> authored;
            for(const auto& v:src.morphs[m].vanims)authored[v.vertex]=&v;
            auto delta=[&](int v){auto i=authored.find(v);return i==authored.end()?Vec{}:i->second->pos;};
            for(const auto& a:aliases)if(!near(delta(a.first),delta(a.second)))fail("coincident control vertices have conflicting morph positions");
            std::vector<Vec> deformed=positions;
            for(size_t v=0;v<points.size();++v)for(const auto& p:points[v])deformed[v]=scaledAdd(deformed[v],delta(p.first),p.second);
            auto shapeNormals=normals(deformed);
            for(size_t i=0;i<refs.size();++i) {
                const auto& r=refs[i];source::SrcVertAnim v;v.vertex=int(i);
                v.pos=difference(deformed[r.point],positions[r.point]);v.normal=difference(shapeNormals[r.sector],baseNormals[r.sector]);
                double active=0;
                for(const auto& p:points[r.point]) {auto a=authored.find(p.first);if(a==authored.end())continue;
                    active+=p.second;v.speed+=float(a->second->speed*p.second);v.side+=float(a->second->side*p.second);}
                if(active>0){v.speed/=float(active);v.side/=float(active);}
                else {v.speed=1;v.side=1;} // synthesized normal deltas use the DMX defaults
                for(const auto& p:r.attrs){auto a=authored.find(p.first);if(a!=authored.end())v.wrinkle+=float(a->second->wrinkle*p.second);}
                if(nonzero(v.pos)||nonzero(v.normal)||v.wrinkle!=0)dst.morphs[m].vanims.push_back(v);
            }
        }
    }
};
}

bool Bake(source::Source& src,int levels,std::string* error) {
    try {
        if(levels<1 || levels>3)fail("baked subdivision levels must be between 1 and 3");
        if(!src.mergedParts.empty() || !src.vertexPart.empty())fail("baked subdivision cannot preserve fused source-part identities");
        size_t count=src.quads.size();
        for(int i=0;i<levels;++i) {if(count>262144/4)fail("baked subdivision exceeds 262144 refined quads per source");count*=4;}
        for(const auto& morph:src.morphs) {
            bool position=false,normal=false;
            for(const auto& v:morph.vanims){position|=nonzero(v.pos);normal|=nonzero(v.normal);}
            if(normal&&!position)fail("baked subdivision cannot preserve a normal-only morph; use authored geometry deltas");
        }
        source::Source result;result.mesh.resize(src.mesh.size());result.meshindex=src.meshindex;result.nummeshes=src.nummeshes;
        for(const auto& m:src.morphs){source::SrcMorphAnim out;out.name=m.name;result.morphs.push_back(std::move(out));}
        BakeMesh mesh{src};mesh.load();for(int i=0;i<levels;++i)mesh.refine();mesh.emit(result);
        source::CalcModelTangentSpaces(result);
        src.vertex=std::move(result.vertex);src.face=std::move(result.face);src.faceTag=std::move(result.faceTag);
        src.mesh=std::move(result.mesh);src.morphs=std::move(result.morphs);src.quads.clear();src.subdivisionSurface=false;
        src.globalVertices.clear();return true;
    } catch(const std::exception& e) {if(error)*error=e.what();return false;}
}
} // namespace pulse::subd
