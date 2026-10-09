#include "sceneloader.h"
#include "dependencies.h"
#include "gltfscene.h"
#include "c4dbridge.h"
#include "pathcompat.h"
#include "assimp/Importer.hpp"
#include "assimp/scene.h"
#include "assimp/postprocess.h"
#include "assimp/material.h"
#include "assimp/importerdesc.h"
#include "../libs/assimp/code/AssetLib/MMD/MMDPmxParser.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <map>
#include <stdexcept>
#include <filesystem>
#include <cctype>
#include <fstream>
#include <sstream>

namespace pulse::source {
namespace {
namespace pm = pulse::math;
pm::Vector3 Vector(const aiVector3D& v) { return {v.x,v.y,v.z}; }
aiMatrix4x4 Rigid(const aiMatrix4x4& m) {
    aiVector3D s,p; aiQuaternion q; m.Decompose(s,q,p);
    return aiMatrix4x4(aiVector3D(1,1,1),q,p);
}
pm::matrix3x4 Matrix(const aiMatrix4x4& m,float scale) {
    const aiMatrix4x4 r=Rigid(m);
    pm::matrix3x4 o{};
    for(int y=0;y<3;++y) for(int x=0;x<4;++x) o.m[y][x]=r[y][x]*(x==3?scale:1);
    return o;
}
template<class Key,class Value,class Interpolate>
Value Sample(const Key* keys,unsigned count,double time,Value fallback,aiAnimBehaviour pre,
             aiAnimBehaviour post,Interpolate interpolate) {
    if(!count) return fallback;
    const bool before=time<keys[0].mTime,after=time>keys[count-1].mTime;
    if(before || after) {
        const auto behaviour=before?pre:post;
        switch(behaviour) {
        case aiAnimBehaviour_DEFAULT:return fallback;
        case aiAnimBehaviour_CONSTANT:return keys[before?0:count-1].mValue;
        case aiAnimBehaviour_LINEAR: {
            if(count==1)return keys[0].mValue;
            const unsigned lo=before?0:count-2,hi=lo+1;
            const double span=keys[hi].mTime-keys[lo].mTime;
            return interpolate(keys[lo].mValue,keys[hi].mValue,float((time-keys[lo].mTime)/span),aiAnimInterpolation_Linear);
        }
        case aiAnimBehaviour_REPEAT: {
            const double span=keys[count-1].mTime-keys[0].mTime;
            if(span<=0)return keys[0].mValue;
            double phase=std::fmod(time-keys[0].mTime,span);if(phase<0)phase+=span;
            time=keys[0].mTime+phase;break;
        }
        default:throw std::runtime_error("unknown Assimp animation boundary behaviour");
        }
    }
    if(time<=keys[0].mTime)return keys[0].mValue;
    const auto upper=std::upper_bound(keys,keys+count,time,[](double t,const Key& key){return t<key.mTime;});
    if(upper==keys+count) return keys[count-1].mValue;
    const auto lower=upper-1; const double span=upper->mTime-lower->mTime;
    if(lower->mInterpolation==aiAnimInterpolation_Step)return lower->mValue;
    if(lower->mInterpolation==aiAnimInterpolation_Cubic_Spline)
        throw std::runtime_error("Assimp cubic animation keys have no tangent data; bake this format's animation before import");
    return interpolate(lower->mValue,upper->mValue,span>0?float((time-lower->mTime)/span):0,lower->mInterpolation);
}
template<class Key>
void ValidateKeys(const Key* keys,unsigned count) {
    for(unsigned k=0;k<count;++k) {
        if(!std::isfinite(keys[k].mTime) || (k && keys[k].mTime<=keys[k-1].mTime))
            throw std::runtime_error("scene animation key times must be finite and strictly increasing");
    }
}

void AddPmxMorphs(const std::string& path,aiScene& scene) {
    // Assimp's MMD reader parses PMX morphs but does not expose them in the
    // aiScene. Its meshes duplicate vertices in material/index order, so map
    // the parsed PMX deltas through that exact index stream before unification.
    std::ifstream file(pulse::FilePath(path),std::ios::binary);
    pmx::PmxModel model;model.Read(&file);
    if(!file)throw std::runtime_error("truncated PMX morph source");
    if(scene.mNumMeshes!=unsigned(model.material_count))throw std::runtime_error("PMX material mesh mapping differs from importer");
    std::vector<std::map<int,aiVector3D>> deltas(model.morph_count);
    std::vector<unsigned char> state(model.morph_count);
    std::function<bool(int)> expand=[&](int index) {
        if(index<0 || index>=model.morph_count)throw std::runtime_error("PMX group morph references an invalid morph");
        if(state[index]==1)throw std::runtime_error("cyclic PMX group morph");
        if(state[index]>=2)return state[index]==2;
        state[index]=1;const auto& morph=model.morphs[index];
        bool supported=true;
        if(int(morph.morph_type)==1) {
            for(int k=0;k<morph.offset_count;++k) {
                const auto& offset=morph.vertex_offsets[k];
                if(offset.vertex_index<0 || offset.vertex_index>=model.vertex_count)throw std::runtime_error("PMX morph vertex index out of range");
                const auto p=offset.position_offset;
                if(!std::isfinite(p[0]) || !std::isfinite(p[1]) || !std::isfinite(p[2]))throw std::runtime_error("non-finite PMX morph delta");
                deltas[index][offset.vertex_index]+=aiVector3D(p[0],p[1],-p[2]);
            }
        } else if(int(morph.morph_type)==0) {
            for(int k=0;k<morph.offset_count;++k) {
                const auto& offset=morph.group_offsets[k];
                if(!std::isfinite(offset.morph_weight))throw std::runtime_error("non-finite PMX group morph weight");
                if(!expand(offset.morph_index)) { supported=false;continue; }
                for(const auto& entry:deltas[offset.morph_index])deltas[index][entry.first]+=entry.second*offset.morph_weight;
            }
        } else supported=false;
        state[index]=supported?2:3;return supported;
    };
    for(int m=0;m<model.morph_count;++m)expand(m);
    int indexBase=0;
    for(unsigned n=0;n<scene.mNumMeshes;++n) {
        auto mesh=scene.mMeshes[n];const int count=model.materials[n].index_count;
        if(count<0 || indexBase>model.index_count-count || mesh->mNumVertices!=unsigned(count))throw std::runtime_error("invalid PMX morph mesh index mapping");
        std::vector<std::unique_ptr<aiAnimMesh>> targets;
        for(int m=0;m<model.morph_count;++m)if(state[m]==2 && !deltas[m].empty()) {
            auto target=std::make_unique<aiAnimMesh>();const auto& morph=model.morphs[m];
            target->mName=aiString(morph.morph_name.empty()?morph.morph_english_name:morph.morph_name);
            target->mNumVertices=mesh->mNumVertices;target->mVertices=new aiVector3D[mesh->mNumVertices];
            for(unsigned v=0;v<mesh->mNumVertices;++v) {
                target->mVertices[v]=mesh->mVertices[v];auto found=deltas[m].find(model.indices[indexBase+v]);
                if(found!=deltas[m].end())target->mVertices[v]+=found->second;
            }
            targets.push_back(std::move(target));
        }
        mesh->mNumAnimMeshes=unsigned(targets.size());mesh->mAnimMeshes=new aiAnimMesh*[targets.size()]{};
        for(size_t m=0;m<targets.size();++m)mesh->mAnimMeshes[m]=targets[m].release();
        indexBase+=count;
    }
    unsigned skipped=0;for(auto status:state)if(status==3)++skipped;
    if(skipped)std::printf("PMX: %u non-vertex morphs are not representable as MDL vertex flexes (UV/material/bone/physics or groups containing them)\n",skipped);
}
}
std::string SceneImportFormats() {
    Assimp::Importer importer;std::ostringstream result;
    result<<"Native\tSource DMX/SMD/VTA, ufbx, cgltf\tdmx smd vta fbx gltf glb vrm\n";
    for(size_t i=0;i<importer.GetImporterCount();++i) {
        const auto info=importer.GetImporterInfo(i);
        result<<"Assimp\t"<<info->mName<<"\t"<<info->mFileExtensions<<"\n";
    }
    result<<"Optional bridge\tCineware C4D cached geometry ("<<(HasC4dBridge()?"available":"Windows helper not present")<<")\tc4d\n";
    return result.str();
}
bool LoadSceneSource(const std::string& path,Source& out,MaterialTable& mats,float scale,
                     std::string* err,bool morphSource,MeshFilter* filter,bool animOnly,
                     const SceneOptions& options) {
    try {
        pulse::dependencies::Note(path);
        // Private sources with different InNode values share parsed geometry.
        // The timestamp prevents reuse after an author changes the input file.
        static std::map<std::string,std::shared_ptr<aiScene>> cache;
        std::string ext=pulse::FilePath(path).extension().string();
        std::transform(ext.begin(),ext.end(),ext.begin(),[](unsigned char c){return char(std::tolower(c));});
        const bool c4d=ext==".c4d";
        const bool gltf=c4d || ext==".gltf" || ext==".glb" || ext==".vrm";
        const bool nativeInstances=gltf && !c4d && options.noFastGltf && GltfHasInstancing(path);
        const bool fast=gltf && (!options.noFastGltf || nativeInstances);
        if(nativeInstances)std::printf("glTF instancing: using native expansion because Assimp does not retain EXT_mesh_gpu_instancing\n");
        const std::string key=path+"|"+std::to_string(static_cast<long long>(std::filesystem::last_write_time(pulse::FilePath(path)).time_since_epoch().count()))+
                              "|"+std::to_string(fast)+"|"+std::to_string(options.sampleRate)+"|"+options.bakeAnimation;
        auto found=cache.find(key);
        if(found==cache.end()) {
            TemporaryC4dScene converted;
            // Generated GLB files are implementation details. Track the original
            // C4D as the source dependency, even on a conversion/import failure.
            struct ConversionDependency {
                const TemporaryC4dScene& temporary;
                ~ConversionDependency() {
                    if(!temporary.path.empty())pulse::dependencies::Files().erase(temporary.path.lexically_normal().string());
                }
            } conversionDependency{converted};
            std::string parsePath=path;
            if(c4d) {ConvertC4dScene(path,converted);parsePath=converted.path.u8string();}
            std::shared_ptr<aiScene> parsed;
            if(fast) parsed=LoadFastGltfScene(parsePath,options.sampleRate,!options.bakeAnimation.empty());
            else {
                Assimp::Importer importer;
                importer.SetPropertyFloat("NPMDL_SCENE_SAMPLE_RATE",options.sampleRate);
                if(!importer.ReadFile(parsePath,aiProcess_Triangulate|aiProcess_GenSmoothNormals)) throw std::runtime_error(importer.GetErrorString());
                parsed.reset(importer.GetOrphanedScene());
                if(ext==".pmx")AddPmxMorphs(path,*parsed);
                if (gltf && parsed->mNumAnimations) {
                    // Assimp drops glTF STEP markers and cubic tangents.
                    // Keep its geometry/skin import, but sample animation from
                    // original accessors, without building a second mesh copy.
                    auto precise = LoadFastGltfScene(parsePath, options.sampleRate,
                        !options.bakeAnimation.empty(), true);
                    for (unsigned i=0;i<parsed->mNumAnimations;++i) delete parsed->mAnimations[i];
                    delete[] parsed->mAnimations;
                    parsed->mNumAnimations = precise->mNumAnimations;
                    parsed->mAnimations = precise->mAnimations;
                    precise->mNumAnimations = 0;
                    precise->mAnimations = nullptr;
                }
            }
            found=cache.emplace(key,std::move(parsed)).first;
        }
        const aiScene* scene=found->second.get();
        if(!scene || !scene->mRootNode) throw std::runtime_error("scene has no root node");
        std::vector<const aiNode*> nodes;
        std::vector<int> parents;
        std::vector<aiMatrix4x4> worlds;
        std::map<std::string,int> byName;
        std::function<void(const aiNode*,int)> visit=[&](const aiNode* n,int parent) {
            int id=int(nodes.size()); nodes.push_back(n); parents.push_back(parent);
            worlds.push_back(parent<0?n->mTransformation:worlds[parent]*n->mTransformation);
            std::string name=n->mName.C_Str(); if(name.empty()) name="scene_node_"+std::to_string(id);
            if(byName.count(name)) throw std::runtime_error("ambiguous scene node name: "+name);
            byName[name]=id; out.localBone.push_back({name,parent,true});
            for(unsigned k=0;k<n->mNumChildren;++k) visit(n->mChildren[k],id);
        };
        visit(scene->mRootNode,-1);
        if(nodes.size()>pulse::limits::kMaxSrcBones) throw std::runtime_error("scene exceeds source bone limit");
        int selected=-1;
        if(!options.node.empty()) {
            auto i=byName.find(options.node);
            if(i==byName.end()) throw std::runtime_error("InNode not found: "+options.node);
            selected=i->second;
        }
        auto keep=[&](int n) { if(selected<0) return true; for(int p=n;p>=0;p=parents[p]) if(p==selected) return true; return false; };
        // Bone offsets define the skin's bind pose, independently of the scene's current pose.
        auto bindWorld=worlds;
        std::map<int,aiMatrix4x4> skinBinds;
        for(size_t n=0;n<nodes.size();++n) for(unsigned j=0;j<nodes[n]->mNumMeshes;++j) {
            auto mesh=scene->mMeshes[nodes[n]->mMeshes[j]];
            for(unsigned b=0;b<mesh->mNumBones;++b) {
                auto bone=mesh->mBones[b]; auto i=byName.find(bone->mName.C_Str());
                if(i==byName.end()) throw std::runtime_error("missing skin joint: "+std::string(bone->mName.C_Str()));
                if(std::abs(bone->mOffsetMatrix.Determinant())<1e-12f)
                    throw std::runtime_error("singular inverse bind matrix for skin joint: "+std::string(bone->mName.C_Str()));
                const aiMatrix4x4 bind=gltf ? aiMatrix4x4(bone->mOffsetMatrix).Inverse()
                                          : worlds[n]*aiMatrix4x4(bone->mOffsetMatrix).Inverse();
                auto existing=skinBinds.find(i->second);
                if(existing!=skinBinds.end()) for(int row=0;row<4;++row) for(int col=0;col<4;++col)
                    if(std::abs(existing->second[row][col]-bind[row][col])>1e-4f)
                        throw std::runtime_error("conflicting bind poses for shared skin joint: "+std::string(bone->mName.C_Str()));
                skinBinds[i->second]=bind; bindWorld[i->second]=bind;
                out.localBone[i->second].isNonSkeletal=false;
            }
        }
        aiMatrix4x4 axis;
        if(!(gltf?options.gltfZUp:options.zUp)) aiMatrix4x4::RotationX(float(3.141592653589793/2),axis);
        out.numbones=int(nodes.size()); out.boneToPose.resize(nodes.size());
        auto pose=[&](const std::vector<aiMatrix4x4>& w,std::vector<SrcBonePose>& dst) {
            dst.resize(nodes.size());
            for(size_t b=0;b<nodes.size();++b) {
                const aiMatrix4x4 local=parents[b]<0?axis*Rigid(w[b]):aiMatrix4x4(Rigid(w[parents[b]])).Inverse()*Rigid(w[b]);
                pm::MatrixAngles(Matrix(local,scale),dst[b].rot,dst[b].pos);
            }
        };
        SourceAnim bind; bind.name="BindPose"; bind.frames.resize(1); pose(bindWorld,bind.frames[0]);
        for(size_t b=0;b<nodes.size();++b) out.boneToPose[b]=Matrix(axis*bindWorld[b],scale);
        out.anims.push_back(std::move(bind));
        if(!std::isfinite(options.sampleRate) || options.sampleRate<=0 || options.sampleRate>1000)
            throw std::runtime_error("SampleRate must be finite and within (0, 1000]");
        std::vector<std::vector<aiMatrix4x4>> bakedWorlds;
        const aiAnimation* bakedAnimation=nullptr;
        for(unsigned a=0;a<scene->mNumAnimations;++a) {
            auto animation=scene->mAnimations[a];
            if(!options.bakeAnimation.empty()&&options.bakeAnimation!=animation->mName.C_Str())continue;
            const bool bake=!options.bakeAnimation.empty();
            if(animation->mNumMeshChannels || (!bake&&animation->mNumMorphMeshChannels))
                throw std::runtime_error("animated morph weights/mesh swaps require QC flex controllers");
            double rate=animation->mTicksPerSecond>0?animation->mTicksPerSecond:30;
            double duration=animation->mDuration/rate;
            if(!std::isfinite(duration) || duration<0 || duration*options.sampleRate>=pulse::limits::kMaxAnimFrames)
                throw std::runtime_error("scene animation exceeds frame limit");
            SourceAnim clip; clip.name=animation->mName.C_Str();
            if(clip.name.empty()) clip.name="animation_"+std::to_string(a);
            clip.numframes=1+int(std::lround(duration*options.sampleRate)); clip.endframe=clip.numframes-1;
            if(bake){clip.numframes=1+int(std::ceil(duration*options.sampleRate));clip.endframe=clip.numframes-1;
                if(clip.numframes>4096)throw std::runtime_error("BakeSceneAnimation exceeds 4096 sampled frames");bakedAnimation=animation;}
            clip.frames.resize(clip.numframes);
            for(unsigned ch=0;ch<animation->mNumChannels;++ch) {
                const auto channel=animation->mChannels[ch];
                ValidateKeys(channel->mPositionKeys,channel->mNumPositionKeys);
                ValidateKeys(channel->mRotationKeys,channel->mNumRotationKeys);
                ValidateKeys(channel->mScalingKeys,channel->mNumScalingKeys);
            }
            // Check immutable keys once, rather than for every sampled frame.
            if(!bake) for(unsigned ch=0;ch<animation->mNumChannels;++ch) {
                auto channel=animation->mChannels[ch]; auto i=byName.find(channel->mNodeName.C_Str());
                if(i==byName.end()) throw std::runtime_error("animation node not found");
                aiVector3D s,p; aiQuaternion q; nodes[i->second]->mTransformation.Decompose(s,q,p);
                for(unsigned k=0;k<channel->mNumScalingKeys;++k)
                    if((channel->mScalingKeys[k].mValue-s).SquareLength()>1e-10f)
                        throw std::runtime_error("animated scene scaling must be baked into vertex animation before MDL import");
            }
            for(int f=0;f<clip.numframes;++f) {
                double time=std::min(duration,double(f)/options.sampleRate)*rate;
                std::vector<aiMatrix4x4> locals; for(auto n:nodes) locals.push_back(n->mTransformation);
                for(unsigned ch=0;ch<animation->mNumChannels;++ch) {
                    auto channel=animation->mChannels[ch]; auto i=byName.find(channel->mNodeName.C_Str());
                    if(i==byName.end()) throw std::runtime_error("animation node not found");
                    int b=i->second; out.localBone[b].isNonSkeletal=false;
                    aiVector3D s,p; aiQuaternion q; locals[b].Decompose(s,q,p);
                    auto lerp=[](aiVector3D x,aiVector3D y,float t,aiAnimInterpolation) { return x+(y-x)*t; };
                    p=Sample(channel->mPositionKeys,channel->mNumPositionKeys,time,p,channel->mPreState,channel->mPostState,lerp);
                    s=Sample(channel->mScalingKeys,channel->mNumScalingKeys,time,s,channel->mPreState,channel->mPostState,lerp);
                    q=Sample(channel->mRotationKeys,channel->mNumRotationKeys,time,q,channel->mPreState,channel->mPostState,
                        [](aiQuaternion x,aiQuaternion y,float t,aiAnimInterpolation mode) {
                            aiQuaternion o;
                            if(mode==aiAnimInterpolation_Spherical_Linear) aiQuaternion::Interpolate(o,x,y,t);
                            else { if(x.w*y.w+x.x*y.x+x.y*y.y+x.z*y.z<0)y=aiQuaternion(-y.w,-y.x,-y.y,-y.z);
                                o=aiQuaternion(x.w+(y.w-x.w)*t,x.x+(y.x-x.x)*t,x.y+(y.y-x.y)*t,x.z+(y.z-x.z)*t); }
                            return o.Normalize(); });
                    locals[b]=aiMatrix4x4(s,q,p);
                }
                std::vector<aiMatrix4x4> w(nodes.size());
                for(size_t b=0;b<nodes.size();++b) w[b]=parents[b]<0?locals[b]:w[parents[b]]*locals[b];
                if(bake){bakedWorlds.push_back(std::move(w));out.bakedTimes.push_back(float(time/rate));clip.frames[f]=out.anims[0].frames[0];}
                else pose(w,clip.frames[f]);
            }
            out.anims.push_back(std::move(clip));
        }
        if(!options.bakeAnimation.empty()&&!bakedAnimation)throw std::runtime_error("BakeSceneAnimation animation not found: "+options.bakeAnimation);
        if(animOnly) return true;
        std::vector<TriInput> triangles;
        struct MorphMesh { const aiMesh* mesh; aiMatrix4x4 world; int base,node; };
        std::vector<MorphMesh> morphMeshes; int vertexBase=0;
        for(size_t n=0;n<nodes.size();++n) if(keep(int(n))) for(unsigned j=0;j<nodes[n]->mNumMeshes;++j) {
            auto mesh=scene->mMeshes[nodes[n]->mMeshes[j]];
            if(filter && !filter->Keep(mesh->mName.C_Str(),nodes[n]->mName.C_Str())) continue;
            aiString material;
            if(mesh->mMaterialIndex<scene->mNumMaterials) scene->mMaterials[mesh->mMaterialIndex]->Get(AI_MATKEY_NAME,material);
            std::string materialName=material.length?material.C_Str():"material_"+std::to_string(mesh->mMaterialIndex);
            if(filter && filter->MaterialRemoved(materialName)) continue;
            int mat=mats.UseTextureAsMaterial(mats.LookupTexture(materialName.c_str()));
            std::vector<SrcBoneWeight> weights(mesh->mNumVertices);
            std::vector<std::vector<std::pair<int,float>>> importedWeights(mesh->mNumVertices);
            for(unsigned b=0;b<mesh->mNumBones;++b) {
                auto bone=mesh->mBones[b]; int id=byName.at(bone->mName.C_Str());
                for(unsigned k=0;k<bone->mNumWeights;++k) {
                    auto w=bone->mWeights[k];
                    if(w.mVertexId>=mesh->mNumVertices || !std::isfinite(w.mWeight) || w.mWeight<0) throw std::runtime_error("invalid skin weight");
                    if(w.mWeight>0) importedWeights[w.mVertexId].emplace_back(id,w.mWeight);
                }
            }
            // glTF explicitly ignores a skinned mesh node's own transform:
            // skinning uses joint-world * inverse-bind, unlike a rigid mesh.
            const aiMatrix4x4 world=gltf && mesh->mNumBones ? axis : axis*worlds[n];
            aiMatrix3x3 normal(world); normal.Inverse().Transpose();
            for(unsigned v=0;v<mesh->mNumVertices;++v) {
                auto& w=weights[v];
                auto& imported=importedWeights[v];
                // The same joint can occur in multiple JOINTS streams. Sum it
                // before selecting the strongest influences, otherwise valid
                // input loses weight and spends multiple slots on one bone.
                size_t unique=0;
                for(size_t k=0;k<imported.size();++k) {
                    size_t j=0; for(;j<unique;++j) if(imported[j].first==imported[k].first) break;
                    if(j<unique) imported[j].second+=imported[k].second;
                    else imported[unique++]=imported[k];
                }
                imported.resize(unique);
                std::stable_sort(imported.begin(),imported.end(),[](const auto& a,const auto& b){return a.second>b.second;});
                for(size_t k=0;k<imported.size() && k<pulse::limits::kMaxSrcBoneWeights;++k) {
                    w.bone[k]=imported[k].first; w.weight[k]=imported[k].second; ++w.numbones;
                }
                if(w.numbones) w.numbones=SortAndBalanceBones(w.numbones,pulse::limits::kMaxSrcBoneWeights,w.bone,w.weight);
                if(!w.numbones) { w.numbones=1; w.bone[0]=int(n); w.weight[0]=1; }
            }
            for(unsigned f=0;f<mesh->mNumFaces;++f) {
                auto& face=mesh->mFaces[f]; if(face.mNumIndices!=3) continue;
                TriInput tri; tri.material=mat; tri.tag=filter?filter->Tag(mesh->mName.C_Str(),nodes[n]->mName.C_Str()):0;
                for(int c=0;c<3;++c) {
                    unsigned v=face.mIndices[c]; if(v>=mesh->mNumVertices) throw std::runtime_error("invalid scene vertex index");
                    auto& dst=tri.v[c]; dst.srcVertex=vertexBase+int(v);
                    dst.position=Vector(world*mesh->mVertices[v]); dst.position.x*=scale; dst.position.y*=scale; dst.position.z*=scale;
                    dst.normal=Vector((normal*mesh->mNormals[v]).Normalize());
                    if(mesh->HasTextureCoords(0)) dst.texcoord={mesh->mTextureCoords[0][v].x,fast ? mesh->mTextureCoords[0][v].y : 1-mesh->mTextureCoords[0][v].y};
                    dst.boneweight=weights[v];
                }
                if(world.Determinant()<0) std::swap(tri.v[1],tri.v[2]);
                triangles.push_back(tri);
            }
            morphMeshes.push_back({mesh,world,vertexBase,int(n)}); vertexBase+=int(mesh->mNumVertices);
        }
        if(triangles.empty()) throw std::runtime_error("scene contains no selected triangle meshes");
        std::vector<std::vector<int>> unified; BuildUnifiedMeshes(triangles,out,morphSource?&unified:nullptr);
        if(morphSource&&!bakedAnimation) for(const auto& entry:morphMeshes) for(unsigned m=0;m<entry.mesh->mNumAnimMeshes;++m) {
            const auto mesh=entry.mesh; const auto target=mesh->mAnimMeshes[m];
            std::string name=target->mName.length?target->mName.C_Str():"morph_"+std::to_string(m);
            auto found=std::find_if(out.morphs.begin(),out.morphs.end(),[&](const SrcMorphAnim& x){return x.name==name;});
            if(found==out.morphs.end()) { out.morphs.push_back({name,{}}); found=out.morphs.end()-1; SrcFlexKey key; key.name=name; out.flexkeys.push_back(key); }
            aiMatrix3x3 linear(entry.world), normal(entry.world); normal.Inverse().Transpose();
            if(target->mNumVertices!=mesh->mNumVertices) throw std::runtime_error("morph vertex count differs from its mesh");
            for(unsigned v=0;v<mesh->mNumVertices;++v) {
                aiVector3D delta=target->HasPositions()?linear*(target->mVertices[v]-mesh->mVertices[v])*scale:aiVector3D();
                aiVector3D ndelta=target->HasNormals()?(normal*target->mNormals[v]).Normalize()-(normal*mesh->mNormals[v]).Normalize():aiVector3D();
                if(delta.SquareLength()+ndelta.SquareLength()==0) continue;
                if(entry.base+v>=unified.size()) continue;
                for(int index:unified[entry.base+v]) { SrcVertAnim va; va.vertex=index; va.speed=1; va.side=1; va.pos=Vector(delta); va.normal=Vector(ndelta); found->vanims.push_back(va); }
            }
        }
        if(bakedAnimation&&morphSource) {
            if(uint64_t(vertexBase)*bakedWorlds.size()>16000000)throw std::runtime_error("BakeSceneAnimation exceeds 16000000 source vertex samples; reduce SceneSampleRate or split the clip");
            out.bakedController="bake_"+options.bakeAnimation;
            for(char& c:out.bakedController)if(!std::isalnum(static_cast<unsigned char>(c))&&c!='_')c='_';
            ControllerRemap remap;remap.name=out.bakedController;remap.type=RemapType::NWay;
            for(size_t f=0;f<bakedWorlds.size();++f) {
                const std::string name=out.bakedController+"_f"+std::to_string(f);
                SrcMorphAnim morph; morph.name=name;
                for(const auto& entry:morphMeshes) {
                    auto mesh=entry.mesh;std::vector<double> weights(mesh->mNumAnimMeshes);
                    for(unsigned m=0;m<mesh->mNumAnimMeshes;++m)weights[m]=mesh->mAnimMeshes[m]->mWeight;
                    for(unsigned ch=0;ch<bakedAnimation->mNumMorphMeshChannels;++ch) {
                        auto channel=bakedAnimation->mMorphMeshChannels[ch];bool matches=std::string(channel->mName.C_Str())==mesh->mName.C_Str();
                        for(int p=entry.node;p>=0;p=parents[p])matches=matches||std::string(channel->mName.C_Str())==nodes[p]->mName.C_Str();
                        if(!matches||!channel->mNumKeys)continue;
                        double ticks=out.bakedTimes[f]*(bakedAnimation->mTicksPerSecond>0?bakedAnimation->mTicksPerSecond:30);
                        unsigned hi=0;while(hi+1<channel->mNumKeys&&channel->mKeys[hi+1].mTime<=ticks)++hi;
                        unsigned next=std::min(hi+1,channel->mNumKeys-1);double span=channel->mKeys[next].mTime-channel->mKeys[hi].mTime;
                        double t=span>0?std::clamp((ticks-channel->mKeys[hi].mTime)/span,0.0,1.0):0;
                        auto apply=[&](const aiMeshMorphKey& key,double factor){for(unsigned k=0;k<key.mNumValuesAndWeights;++k){
                            if(key.mValues[k]>=weights.size())throw std::runtime_error("baked morph target index out of range");weights[key.mValues[k]]+=key.mWeights[k]*factor;}};
                        std::fill(weights.begin(),weights.end(),0);apply(channel->mKeys[hi],1-t);apply(channel->mKeys[next],t);
                    }
                    std::vector<aiMatrix4x4> skin(mesh->mNumBones);
                    for(unsigned b=0;b<mesh->mNumBones;++b)skin[b]=axis*bakedWorlds[f][byName.at(mesh->mBones[b]->mName.C_Str())]*mesh->mBones[b]->mOffsetMatrix;
                    const auto world=axis*bakedWorlds[f][entry.node];
                    std::vector<aiVector3D> positions(mesh->mNumVertices),normals(mesh->mNumVertices);
                    for(unsigned v=0;v<mesh->mNumVertices;++v){positions[v]=mesh->mVertices[v];normals[v]=mesh->mNormals[v];
                        for(unsigned m=0;m<mesh->mNumAnimMeshes;++m){auto target=mesh->mAnimMeshes[m];float weight=float(weights[m]);
                            if(!std::isfinite(weight))throw std::runtime_error("non-finite baked morph weight");
                            if(target->HasPositions())positions[v]+=(target->mVertices[v]-mesh->mVertices[v])*weight;
                            if(target->HasNormals())normals[v]+=(target->mNormals[v]-mesh->mNormals[v])*weight;}
                    }
                    std::vector<aiVector3D> transformed(mesh->mNumVertices),transformedNormals(mesh->mNumVertices);std::vector<float> total(mesh->mNumVertices);
                    for(unsigned b=0;b<mesh->mNumBones;++b){aiMatrix3x3 normal(skin[b]);if(std::abs(normal.Determinant())<1e-12f)throw std::runtime_error("singular animated skin scale");normal.Inverse().Transpose();
                        auto bone=mesh->mBones[b];for(unsigned k=0;k<bone->mNumWeights;++k){auto w=bone->mWeights[k];
                            transformed[w.mVertexId]+=(skin[b]*positions[w.mVertexId])*w.mWeight;transformedNormals[w.mVertexId]+=(normal*normals[w.mVertexId])*w.mWeight;total[w.mVertexId]+=w.mWeight;}}
                    aiMatrix3x3 normal(world);if(std::abs(normal.Determinant())<1e-12f)throw std::runtime_error("singular animated mesh scale");normal.Inverse().Transpose();
                    aiMatrix3x3 baseNormal(entry.world);baseNormal.Inverse().Transpose();
                    for(unsigned v=0;v<mesh->mNumVertices;++v){
                        auto desired=total[v]>0?transformed[v]/total[v]:world*positions[v];auto desiredNormal=total[v]>0?transformedNormals[v]:normal*normals[v];desiredNormal.Normalize();
                        auto delta=(desired-entry.world*mesh->mVertices[v])*scale;auto ndelta=desiredNormal-(baseNormal*mesh->mNormals[v]).Normalize();
                        if(delta.SquareLength()+ndelta.SquareLength()<1e-14f)continue;
                        for(int index:unified.at(entry.base+v)){SrcVertAnim va;va.vertex=index;va.speed=1;va.side=1;va.pos=Vector(delta);va.normal=Vector(ndelta);morph.vanims.push_back(va);}
                    }
                }
                SrcFlexKey key;key.name=name;key.morphIndex=int(out.morphs.size());out.flexkeys.push_back(key);out.morphs.push_back(std::move(morph));
                remap.rawControls.push_back(name);out.combinationControls.push_back({name});CombinationRule rule;rule.flex=int(f);rule.combination.push_back(int(f));out.combinationRules.push_back(std::move(rule));
            }
            out.controllerRemaps.push_back(std::move(remap));
            std::printf("Baked scene animation '%s': %zu frames into %s / multi_%s flex controls\n",options.bakeAnimation.c_str(),bakedWorlds.size(),out.bakedController.c_str(),out.bakedController.c_str());
        }
        return true;
    } catch(const std::exception& e) { if(err) *err=e.what(); return false; }
}
}
