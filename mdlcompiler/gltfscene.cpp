#include "gltfscene.h"
#include "cgltf.h"
#include "assimp/scene.h"
#include "assimp/material.h"
#include "pulselimits.h"
#include "dependencies.h"
#include "pathcompat.h"
#include "meshoptimizer.h"
#include "resources.h"
#include "draco/compression/decode.h"
#include "draco/core/decoder_buffer.h"
#include "draco/mesh/mesh.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <map>
#include <stdexcept>
#include <vector>
#include <array>
#include <fstream>
#include <cstdlib>
#include <limits>
#include <set>
#include <deque>

namespace pulse::source {
namespace {
cgltf_result ReadFile(const cgltf_memory_options* memory,const cgltf_file_options*,const char* path,cgltf_size* size,void** data) {
    std::ifstream f(pulse::FilePath(path),std::ios::binary|std::ios::ate);
    if(!f) {auto mounted=pulse::resources::Find(pulse::FilePath(path));if(!mounted.empty())f.open(mounted,std::ios::binary|std::ios::ate);}
    if(!f) return cgltf_result_file_not_found;
    const auto length=f.tellg(); if(length<0) return cgltf_result_io_error;
    cgltf_size bytes=*size ? *size : cgltf_size(length);
    if(bytes>cgltf_size(length)) return cgltf_result_io_error;
    void* buffer=memory->alloc_func ? memory->alloc_func(memory->user_data,bytes) : std::malloc(bytes);
    if(!buffer) return cgltf_result_out_of_memory;
    f.seekg(0); f.read(static_cast<char*>(buffer),bytes);
    if(!f) { if(memory->free_func) memory->free_func(memory->user_data,buffer); else std::free(buffer); return cgltf_result_io_error; }
    *data=buffer; *size=bytes; pulse::dependencies::Note(path); return cgltf_result_success;
}
void ReleaseFile(const cgltf_memory_options* memory,const cgltf_file_options*,void* data,cgltf_size) {
    if(memory->free_func) memory->free_func(memory->user_data,data); else std::free(data);
}
aiMatrix4x4 Matrix(const float* column) {
    aiMatrix4x4 m; for(int r=0;r<4;++r) for(int c=0;c<4;++c) m[r][c]=column[c*4+r]; return m;
}
std::vector<float> Values(const cgltf_accessor* a,int width) {
    if(!a) return {};
    std::vector<float> data(a->count*width);
    if(cgltf_accessor_unpack_floats(a,data.data(),data.size())!=data.size()) throw std::runtime_error("invalid glTF accessor");
    return data;
}
const cgltf_accessor* Attribute(const cgltf_attribute* a,size_t count,cgltf_attribute_type type,int set=0) {
    for(size_t k=0;k<count;++k) if(a[k].type==type && a[k].index==set) return a[k].data;
    return nullptr;
}
void DecodeMeshopt(cgltf_data* data) {
    for(size_t b=0;b<data->buffer_views_count;++b) {
        auto& view=data->buffer_views[b];
        if(!view.has_meshopt_compression) continue;
        const auto& c=view.meshopt_compression;
        if(!c.buffer || !c.buffer->data || c.offset>c.buffer->size || c.size>c.buffer->size-c.offset ||
           !c.count || !c.stride || c.count>std::numeric_limits<size_t>::max()/c.stride ||
           c.count*c.stride!=view.size)
            throw std::runtime_error("invalid meshopt compressed buffer range or size");
        if(c.mode==cgltf_meshopt_compression_mode_attributes && (c.stride%4 || c.stride>256))
            throw std::runtime_error("invalid meshopt attribute stride");
        if(c.mode!=cgltf_meshopt_compression_mode_attributes && c.stride!=2 && c.stride!=4)
            throw std::runtime_error("invalid meshopt index stride");
        view.data=data->memory.alloc_func(data->memory.user_data,view.size);
        if(!view.data) throw std::bad_alloc();
        const auto* bytes=static_cast<const unsigned char*>(c.buffer->data)+c.offset;
        int status=-1;
        if(c.mode==cgltf_meshopt_compression_mode_attributes) status=meshopt_decodeVertexBuffer(view.data,c.count,c.stride,bytes,c.size);
        else if(c.mode==cgltf_meshopt_compression_mode_triangles) status=meshopt_decodeIndexBuffer(view.data,c.count,c.stride,bytes,c.size);
        else if(c.mode==cgltf_meshopt_compression_mode_indices) status=meshopt_decodeIndexSequence(view.data,c.count,c.stride,bytes,c.size);
        if(status) throw std::runtime_error("invalid meshopt compressed stream");
        if(c.filter==cgltf_meshopt_compression_filter_octahedral) meshopt_decodeFilterOct(view.data,c.count,c.stride);
        else if(c.filter==cgltf_meshopt_compression_filter_quaternion) meshopt_decodeFilterQuat(view.data,c.count,c.stride);
        else if(c.filter==cgltf_meshopt_compression_filter_exponential) meshopt_decodeFilterExp(view.data,c.count,c.stride);
        else if(c.filter==cgltf_meshopt_compression_filter_color) meshopt_decodeFilterColor(view.data,c.count,c.stride);
    }
}
struct DracoViews {
    std::deque<cgltf_buffer_view> views;
    std::deque<std::vector<unsigned char>> buffers;
    void Assign(cgltf_accessor& a, size_t count, size_t stride) {
        if(count!=a.count) throw std::runtime_error("Draco accessor count does not match decoded mesh");
        buffers.emplace_back(count*stride);views.emplace_back();
        views.back().data=buffers.back().data();views.back().size=buffers.back().size();views.back().stride=stride;
        a.buffer_view=&views.back();a.offset=0;a.stride=stride;
    }
};
template<class T> void CopyDraco(const draco::Mesh& mesh,const draco::PointAttribute& attribute,void* destination) {
    T* out=static_cast<T*>(destination);
    for(draco::PointIndex p(0);p<mesh.num_points();++p)
        if(!attribute.ConvertValue<T>(attribute.mapped_index(p),attribute.num_components(),out+p.value()*attribute.num_components()))
            throw std::runtime_error("cannot convert Draco attribute");
}
void DecodeDraco(cgltf_data* data,DracoViews& storage) {
    for(size_t m=0;m<data->meshes_count;++m) for(size_t p=0;p<data->meshes[m].primitives_count;++p) {
        auto& primitive=data->meshes[m].primitives[p];if(!primitive.has_draco_mesh_compression) continue;
        const auto& compression=primitive.draco_mesh_compression;
        const auto* view=compression.buffer_view;
        const auto* bytes=cgltf_buffer_view_data(view);
        if(!bytes || primitive.type!=cgltf_primitive_type_triangles) throw std::runtime_error("invalid Draco triangle buffer");
        draco::DecoderBuffer buffer;buffer.Init(reinterpret_cast<const char*>(bytes),view->size);
        draco::Decoder decoder;auto result=decoder.DecodeMeshFromBuffer(&buffer);
        if(!result.ok()) throw std::runtime_error("invalid Draco compressed stream: "+result.status().error_msg_string());
        auto mesh=std::move(result).value();
        for(size_t k=0;k<compression.attributes_count;++k) {
            const auto& mapping=compression.attributes[k];
            auto accessor=const_cast<cgltf_accessor*>(Attribute(primitive.attributes,primitive.attributes_count,mapping.type,mapping.index));
            const auto* attr=mesh->GetAttributeByUniqueId(uint32_t(reinterpret_cast<uintptr_t>(mapping.data)-1));
            if(!accessor || !attr || cgltf_num_components(accessor->type)!=size_t(attr->num_components()))
                throw std::runtime_error("invalid Draco attribute mapping");
            size_t stride=cgltf_calc_size(accessor->type,accessor->component_type);
            storage.Assign(*accessor,mesh->num_points(),stride);
            void* destination=accessor->buffer_view->data;
            switch(accessor->component_type) {
            case cgltf_component_type_r_8:CopyDraco<int8_t>(*mesh,*attr,destination);break;
            case cgltf_component_type_r_8u:CopyDraco<uint8_t>(*mesh,*attr,destination);break;
            case cgltf_component_type_r_16:CopyDraco<int16_t>(*mesh,*attr,destination);break;
            case cgltf_component_type_r_16u:CopyDraco<uint16_t>(*mesh,*attr,destination);break;
            case cgltf_component_type_r_32u:CopyDraco<uint32_t>(*mesh,*attr,destination);break;
            case cgltf_component_type_r_32f:CopyDraco<float>(*mesh,*attr,destination);break;
            default:throw std::runtime_error("unsupported Draco attribute component type");
            }
        }
        if(!primitive.indices) throw std::runtime_error("Draco mesh requires an index accessor");
        auto& indices=*primitive.indices;indices.component_type=cgltf_component_type_r_32u;
        storage.Assign(indices,size_t(mesh->num_faces())*3,4);
        auto* out=static_cast<uint32_t*>(indices.buffer_view->data);
        for(draco::FaceIndex f(0);f<mesh->num_faces();++f) for(int c=0;c<3;++c) out[f.value()*3+c]=mesh->face(f)[c].value();
    }
}
aiVector3D V(const std::vector<float>& x,size_t k) { return {x[k*3],x[k*3+1],x[k*3+2]}; }
// Evaluate glTF samplers before handing a regular frame grid to the shared
// converter. This retains STEP and CUBICSPLINE semantics (including tangents).
using SamplerCache = std::map<std::pair<const cgltf_animation_sampler*,int>,std::pair<std::vector<float>,std::vector<float>>>;
std::vector<float> Evaluate(const cgltf_animation_sampler& s,double time,int width,bool rotation,SamplerCache& cache) {
    const auto key=std::make_pair(&s,width);
    auto found=cache.find(key);
    if(found==cache.end()) {
        auto times=Values(s.input,1), values=Values(s.output,s.output->type==cgltf_type_scalar?1:width);
        for(size_t i=0;i<times.size();++i)
            if(!std::isfinite(times[i]) || times[i]<0 || (i && times[i]<=times[i-1]))
                throw std::runtime_error("glTF animation times must be finite, nonnegative and strictly increasing");
        for(float v:values) if(!std::isfinite(v)) throw std::runtime_error("non-finite glTF animation value");
        found=cache.emplace(key,std::make_pair(std::move(times),std::move(values))).first;
    }
    const auto& times=found->second.first; const auto& values=found->second.second;
    if(times.empty()) throw std::runtime_error("empty glTF animation sampler");
    const bool cubic=s.interpolation==cgltf_interpolation_type_cubic_spline;
    if(values.size()!=times.size()*width*(cubic?3:1)) throw std::runtime_error("invalid glTF animation sample count");
    size_t hi=std::upper_bound(times.begin(),times.end(),float(time))-times.begin();
    size_t lo=hi?hi-1:0; hi=std::min(hi,times.size()-1);
    float span=times[hi]-times[lo],t=span>0?float((time-times[lo])/span):0; t=std::clamp(t,0.0f,1.0f);
    std::vector<float> result(width);
    const size_t a=(cubic?lo*3+1:lo)*width,b=(cubic?hi*3+1:hi)*width;
    if(rotation && !cubic && s.interpolation==cgltf_interpolation_type_linear) {
        aiQuaternion x(values[a+3],values[a],values[a+1],values[a+2]),y(values[b+3],values[b],values[b+1],values[b+2]),q;
        aiQuaternion::Interpolate(q,x,y,t); q.Normalize(); return {q.x,q.y,q.z,q.w};
    }
    for(int k=0;k<width;++k) {
        if(cubic && lo!=hi) {
            const float t2=t*t,t3=t2*t;
            result[k]=(2*t3-3*t2+1)*values[a+k]+(t3-2*t2+t)*span*values[a+width+k]
                     +(-2*t3+3*t2)*values[b+k]+(t3-t2)*span*values[b-width+k];
        } else result[k]=s.interpolation==cgltf_interpolation_type_step?values[a+k]:values[a+k]+(values[b+k]-values[a+k])*t;
    }
    if(rotation) { float length=0; for(float x:result) length+=x*x; if(length<=0) throw std::runtime_error("zero glTF rotation quaternion"); for(float& x:result) x/=std::sqrt(length); }
    return result;
}
}
std::shared_ptr<aiScene> LoadFastGltfScene(const std::string& path,float sampleRate,bool bakeWeights) {
    cgltf_options options{}; cgltf_data* raw=nullptr;
    options.file.read=ReadFile; options.file.release=ReleaseFile;
    if(cgltf_parse_file(&options,path.c_str(),&raw)!=cgltf_result_success) throw std::runtime_error("cannot parse glTF/GLB");
    std::unique_ptr<cgltf_data,decltype(&cgltf_free)> data(raw,cgltf_free);
    if(cgltf_load_buffers(&options,raw,path.c_str())!=cgltf_result_success || cgltf_validate(raw)!=cgltf_result_success)
        throw std::runtime_error("invalid glTF buffers or accessors; compressed extensions may require $NoFastGltf");
    DecodeMeshopt(raw);
    DracoViews dracoStorage;DecodeDraco(raw,dracoStorage);
    if(!std::isfinite(sampleRate) || sampleRate<=0 || sampleRate>1000) throw std::runtime_error("invalid glTF sample rate");
    auto scene=std::make_shared<aiScene>();
    scene->mRootNode=new aiNode("gltf_scene_root");
    std::map<const cgltf_node*,std::string> names;
    for(size_t i=0;i<raw->nodes_count;++i) names[&raw->nodes[i]]=raw->nodes[i].name?raw->nodes[i].name:"gltf_node_"+std::to_string(i);
    std::set<std::string> reservedNames;
    for(const auto& entry:names) reservedNames.insert(entry.second);
    scene->mNumMaterials=unsigned(raw->materials_count+1); scene->mMaterials=new aiMaterial*[scene->mNumMaterials]{};
    for(unsigned i=0;i<scene->mNumMaterials;++i) {
        scene->mMaterials[i]=new aiMaterial(); aiString name(i<raw->materials_count && raw->materials[i].name?raw->materials[i].name:"material");
        scene->mMaterials[i]->AddProperty(&name,AI_MATKEY_NAME);
    }
    std::vector<std::unique_ptr<aiMesh>> meshes;
    std::function<aiNode*(const cgltf_node*,aiNode*)> node=[&](const cgltf_node* n,aiNode* parent) {
        std::unique_ptr<aiNode> out(new aiNode(names.at(n))); out->mParent=parent;
        float local[16]; cgltf_node_transform_local(n,local); out->mTransformation=Matrix(local);
        out->mNumChildren=unsigned(n->children_count); out->mChildren=new aiNode*[out->mNumChildren]{};
        for(unsigned k=0;k<out->mNumChildren;++k) out->mChildren[k]=node(n->children[k],out.get());
        if(n->mesh) {
            out->mNumMeshes=unsigned(n->mesh->primitives_count); out->mMeshes=new unsigned[out->mNumMeshes]{};
            for(unsigned p=0;p<out->mNumMeshes;++p) {
                auto& primitive=n->mesh->primitives[p];
                auto position=Attribute(primitive.attributes,primitive.attributes_count,cgltf_attribute_type_position);
                if(!position) throw std::runtime_error("glTF mesh has no POSITION");
                std::unique_ptr<aiMesh> mesh(new aiMesh()); out->mMeshes[p]=unsigned(meshes.size());
                mesh->mName=aiString(n->mesh->name?n->mesh->name:names[n].c_str()); mesh->mNumVertices=unsigned(position->count);
                mesh->mMaterialIndex=primitive.material?unsigned(primitive.material-raw->materials):unsigned(raw->materials_count);
                auto positions=Values(position,3); mesh->mVertices=new aiVector3D[mesh->mNumVertices];
                auto normals=Values(Attribute(primitive.attributes,primitive.attributes_count,cgltf_attribute_type_normal),3);
                auto uv=Values(Attribute(primitive.attributes,primitive.attributes_count,cgltf_attribute_type_texcoord),2);
                mesh->mNormals=new aiVector3D[mesh->mNumVertices]{};
                if(!uv.empty()) { mesh->mTextureCoords[0]=new aiVector3D[mesh->mNumVertices]; mesh->mNumUVComponents[0]=2; }
                for(unsigned v=0;v<mesh->mNumVertices;++v) {
                    mesh->mVertices[v]=V(positions,v); if(!normals.empty()) mesh->mNormals[v]=V(normals,v);
                    if(!uv.empty()) mesh->mTextureCoords[0][v]={uv[v*2],uv[v*2+1],0};
                }
                size_t count=primitive.indices?primitive.indices->count:position->count;
                auto index=[&](size_t i) { auto v=primitive.indices?cgltf_accessor_read_index(primitive.indices,i):i; if(v>=position->count) throw std::runtime_error("glTF vertex index out of bounds"); return unsigned(v); };
                std::vector<std::array<unsigned,3>> faces;
                if(primitive.type==cgltf_primitive_type_triangles) for(size_t f=0;f+2<count;f+=3) faces.push_back({index(f),index(f+1),index(f+2)});
                else if(primitive.type==cgltf_primitive_type_triangle_strip) for(size_t f=2;f<count;++f) faces.push_back(f%2?std::array<unsigned,3>{index(f-1),index(f-2),index(f)}:std::array<unsigned,3>{index(f-2),index(f-1),index(f)});
                else if(primitive.type==cgltf_primitive_type_triangle_fan) for(size_t f=2;f<count;++f) faces.push_back({index(0),index(f-1),index(f)});
                else throw std::runtime_error("glTF primitive must contain triangles");
                mesh->mNumFaces=unsigned(faces.size()); mesh->mFaces=new aiFace[mesh->mNumFaces];
                for(unsigned f=0;f<mesh->mNumFaces;++f) {
                    auto& face=mesh->mFaces[f]; face.mNumIndices=3; face.mIndices=new unsigned[3]; std::copy(faces[f].begin(),faces[f].end(),face.mIndices);
                    if(normals.empty()) { aiVector3D normal=(mesh->mVertices[face.mIndices[1]]-mesh->mVertices[face.mIndices[0]])^(mesh->mVertices[face.mIndices[2]]-mesh->mVertices[face.mIndices[0]]); for(unsigned v:faces[f]) mesh->mNormals[v]+=normal; }
                }
                for(unsigned v=0;v<mesh->mNumVertices;++v) mesh->mNormals[v].Normalize();
                if(n->skin) {
                    mesh->mNumBones=unsigned(n->skin->joints_count); mesh->mBones=new aiBone*[mesh->mNumBones]{};
                    auto inverse=Values(n->skin->inverse_bind_matrices,16);
                    std::vector<std::vector<aiVertexWeight>> weights(mesh->mNumBones);
                    for(int set=0;set<2;++set) {
                        auto joints=Attribute(primitive.attributes,primitive.attributes_count,cgltf_attribute_type_joints,set);
                        auto w=Values(Attribute(primitive.attributes,primitive.attributes_count,cgltf_attribute_type_weights,set),4);
                        if(!joints || w.empty()) continue;
                        for(unsigned v=0;v<mesh->mNumVertices;++v) { cgltf_uint ids[4]; if(!cgltf_accessor_read_uint(joints,v,ids,4)) throw std::runtime_error("invalid glTF joint stream"); for(int k=0;k<4;++k) { if(ids[k]>=mesh->mNumBones) throw std::runtime_error("glTF joint index out of bounds"); if(w[v*4+k]>0) weights[ids[k]].push_back(aiVertexWeight(v,w[v*4+k])); } }
                    }
                    for(unsigned b=0;b<mesh->mNumBones;++b) {
                        auto bone=mesh->mBones[b]=new aiBone(); bone->mName=aiString(names.at(n->skin->joints[b]));
                        bone->mOffsetMatrix=inverse.empty()?aiMatrix4x4():Matrix(inverse.data()+b*16);
                        bone->mNumWeights=unsigned(weights[b].size()); bone->mWeights=new aiVertexWeight[bone->mNumWeights]; std::copy(weights[b].begin(),weights[b].end(),bone->mWeights);
                    }
                }
                mesh->mNumAnimMeshes=unsigned(primitive.targets_count); mesh->mAnimMeshes=new aiAnimMesh*[mesh->mNumAnimMeshes]{};
                for(unsigned m=0;m<mesh->mNumAnimMeshes;++m) {
                    auto target=mesh->mAnimMeshes[m]=new aiAnimMesh(); target->mNumVertices=mesh->mNumVertices;
                    target->mName=aiString(m<n->mesh->target_names_count?n->mesh->target_names[m]: ("morph_"+std::to_string(m)).c_str());
                    target->mWeight=m<n->weights_count?n->weights[m]:(m<n->mesh->weights_count?n->mesh->weights[m]:0);
                    auto& shape=primitive.targets[m]; auto delta=Values(Attribute(shape.attributes,shape.attributes_count,cgltf_attribute_type_position),3);
                    auto normal=Values(Attribute(shape.attributes,shape.attributes_count,cgltf_attribute_type_normal),3);
                    if(!delta.empty()) { target->mVertices=new aiVector3D[mesh->mNumVertices]; for(unsigned v=0;v<mesh->mNumVertices;++v) target->mVertices[v]=mesh->mVertices[v]+V(delta,v); }
                    if(!normal.empty()) { target->mNormals=new aiVector3D[mesh->mNumVertices]; for(unsigned v=0;v<mesh->mNumVertices;++v) target->mNormals[v]=mesh->mNormals[v]+V(normal,v); }
                }
                meshes.push_back(std::move(mesh));
            }
        }
        if(n->has_mesh_gpu_instancing) {
            if(n->skin || !n->mesh) throw std::runtime_error("glTF instancing requires an unskinned mesh");
            const auto& inst=n->mesh_gpu_instancing;
            size_t count=inst.attributes[0].data->count;
            if(count>size_t(limits::kMaxSrcBones)) throw std::runtime_error("glTF instance count exceeds source bone limit");
            std::vector<float> translation,rotation,scale;
            for(size_t k=0;k<inst.attributes_count;++k) {
                const auto& attr=inst.attributes[k];
                const std::string name=attr.name?attr.name:"";
                int width=name=="ROTATION"?4:3;
                if(name!="TRANSLATION" && name!="ROTATION" && name!="SCALE") continue;
                if(attr.data->type!=(width==4?cgltf_type_vec4:cgltf_type_vec3)) throw std::runtime_error("invalid glTF instance attribute type");
                auto values=Values(attr.data,width);
                for(float v:values) if(!std::isfinite(v)) throw std::runtime_error("non-finite glTF instance transform");
                if(name=="TRANSLATION") translation=std::move(values);
                else if(name=="ROTATION") rotation=std::move(values);
                else scale=std::move(values);
            }
            const unsigned previous=out->mNumChildren;
            auto children=new aiNode*[previous+count]{};
            if(previous) std::copy(out->mChildren,out->mChildren+previous,children);
            delete[] out->mChildren;out->mChildren=children;out->mNumChildren=unsigned(previous+count);
            for(size_t i=0;i<count;++i) {
                std::string instanceName=names.at(n)+"_instance_"+std::to_string(i);
                while(!reservedNames.insert(instanceName).second) instanceName+="_";
                auto child=out->mChildren[previous+i]=new aiNode(instanceName);
                child->mParent=out.get();
                aiVector3D p=translation.empty()?aiVector3D():V(translation,i);
                aiVector3D s=scale.empty()?aiVector3D(1,1,1):V(scale,i);
                aiQuaternion q;
                if(!rotation.empty()) {
                    q=aiQuaternion(rotation[i*4+3],rotation[i*4],rotation[i*4+1],rotation[i*4+2]);
                    if(q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w<1e-12f) throw std::runtime_error("zero glTF instance rotation quaternion");
                    q.Normalize();
                }
                if(s.x==0 || s.y==0 || s.z==0) throw std::runtime_error("singular glTF instance scale");
                child->mTransformation=aiMatrix4x4(s,q,p);
                child->mNumMeshes=out->mNumMeshes;child->mMeshes=new unsigned[child->mNumMeshes];
                std::copy(out->mMeshes,out->mMeshes+out->mNumMeshes,child->mMeshes);
            }
            delete[] out->mMeshes;out->mMeshes=nullptr;out->mNumMeshes=0;
        }
        return out.release();
    };
    std::vector<const cgltf_node*> roots;
    if(raw->scene) for(size_t i=0;i<raw->scene->nodes_count;++i) roots.push_back(raw->scene->nodes[i]);
    else for(size_t i=0;i<raw->nodes_count;++i) if(!raw->nodes[i].parent) roots.push_back(&raw->nodes[i]);
    scene->mRootNode->mNumChildren=unsigned(roots.size()); scene->mRootNode->mChildren=new aiNode*[roots.size()]{};
    for(size_t i=0;i<roots.size();++i) scene->mRootNode->mChildren[i]=node(roots[i],scene->mRootNode);
    scene->mNumMeshes=unsigned(meshes.size()); scene->mMeshes=new aiMesh*[meshes.size()]{};
    for(size_t i=0;i<meshes.size();++i) scene->mMeshes[i]=meshes[i].release();
    SamplerCache samplerCache;
    scene->mNumAnimations=unsigned(raw->animations_count); scene->mAnimations=new aiAnimation*[raw->animations_count]{};
    for(unsigned a=0;a<scene->mNumAnimations;++a) {
        auto& animation=raw->animations[a]; auto result=scene->mAnimations[a]=new aiAnimation(); result->mTicksPerSecond=1;
        result->mName=aiString(animation.name?animation.name:("animation_"+std::to_string(a)).c_str());
        std::map<const cgltf_node*,std::vector<const cgltf_animation_channel*>> channels;
        std::vector<const cgltf_animation_channel*> morphChannels;
        double duration=0;
        for(size_t c=0;c<animation.channels_count;++c) {
            auto& channel=animation.channels[c]; auto times=Values(channel.sampler->input,1);
            if(!times.empty()) duration=std::max(duration,double(times.back()));
            if(channel.target_path==cgltf_animation_path_type_weights) {
                if(!bakeWeights)throw std::runtime_error("animated glTF morph weights require QC flex controllers or BakeSceneAnimation");
                morphChannels.push_back(&channel);continue;
            }
            channels[channel.target_node].push_back(&channel);
        }
        if(!std::isfinite(duration) || duration<0 || duration*sampleRate>=limits::kMaxAnimFrames) throw std::runtime_error("glTF animation exceeds frame limit");
        result->mDuration=duration; result->mNumChannels=unsigned(channels.size()); result->mChannels=new aiNodeAnim*[channels.size()]{};
        unsigned ch=0; unsigned frames=1+unsigned(std::lround(duration*sampleRate));
        if(bakeWeights)frames=1+unsigned(std::ceil(duration*sampleRate));
        result->mNumMorphMeshChannels=unsigned(morphChannels.size());
        result->mMorphMeshChannels=new aiMeshMorphAnim*[morphChannels.size()]{};
        for(size_t k=0;k<morphChannels.size();++k) {
            auto channel=morphChannels[k];const auto* node=channel->target_node;
            if(!node||!node->mesh||!node->mesh->primitives_count)throw std::runtime_error("invalid glTF morph animation target");
            size_t width=node->mesh->primitives[0].targets_count;
            if(!width)throw std::runtime_error("glTF morph animation has no targets");
            auto dst=result->mMorphMeshChannels[k]=new aiMeshMorphAnim();dst->mName=aiString(names.at(node));dst->mNumKeys=frames;dst->mKeys=new aiMeshMorphKey[frames];
            for(unsigned f=0;f<frames;++f){double time=std::min(duration,double(f)/sampleRate);auto weights=Evaluate(*channel->sampler,time,int(width),false,samplerCache);
                auto& key=dst->mKeys[f];key.mTime=time;key.mNumValuesAndWeights=unsigned(width);key.mValues=new unsigned[width];key.mWeights=new double[width];
                for(size_t m=0;m<width;++m){if(!std::isfinite(weights[m]))throw std::runtime_error("non-finite glTF morph weight");key.mValues[m]=unsigned(m);key.mWeights[m]=weights[m];}
            }
        }
        for(const auto& entry:channels) {
            auto dst=result->mChannels[ch++]=new aiNodeAnim(); dst->mNodeName=aiString(names.at(entry.first));
            dst->mNumPositionKeys=dst->mNumRotationKeys=dst->mNumScalingKeys=frames;
            dst->mPositionKeys=new aiVectorKey[frames]; dst->mRotationKeys=new aiQuatKey[frames]; dst->mScalingKeys=new aiVectorKey[frames];
            float transform[16]; cgltf_node_transform_local(entry.first,transform); aiVector3D baseS,baseP; aiQuaternion baseQ; Matrix(transform).Decompose(baseS,baseQ,baseP);
            for(unsigned f=0;f<frames;++f) {
                double time=std::min(duration,double(f)/sampleRate); auto p=baseP,s=baseS; auto q=baseQ;
                for(auto channel:entry.second) {
                    bool rot=channel->target_path==cgltf_animation_path_type_rotation; auto values=Evaluate(*channel->sampler,time,rot?4:3,rot,samplerCache);
                    if(rot) q=aiQuaternion(values[3],values[0],values[1],values[2]);
                    else if(channel->target_path==cgltf_animation_path_type_translation) p={values[0],values[1],values[2]};
                    else if(channel->target_path==cgltf_animation_path_type_scale) s={values[0],values[1],values[2]};
                }
                dst->mPositionKeys[f]=aiVectorKey(time,p); dst->mRotationKeys[f]=aiQuatKey(time,q); dst->mScalingKeys[f]=aiVectorKey(time,s);
            }
        }
    }
    return scene;
}
}
