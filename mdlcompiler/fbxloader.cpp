// fbxloader.cpp - PulseMDL
//
// See fbxloader.h. ufbx does the parsing; this file only maps its scene onto
// Source. The corner unify/sort/mesh build is shared with the SMD path
// (BuildUnifiedMeshes in source.h).

#include "strcompat.h"

#include "fbxloader.h"
#include "sourcevalidation.h"
#include "dependencies.h"

#include <cmath>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <stdexcept>

#include "math/math.h"
#include "pulselimits.h"
#include "ufbx.h"

namespace pm = pulse::math;
namespace lim = pulse::limits;

namespace pulse::source {

namespace {

// ufbx_matrix is column-major (m<row><col> named fields, 4 columns of 3);
// matrix3x4 is row-major float[3][4]. Same contents, transposed storage.
pm::matrix3x4 ToMatrix3x4(const ufbx_matrix& m) {
    pm::matrix3x4 o;
    for (int c = 0; c < 4; ++c)
        for (int r = 0; r < 3; ++r)
            o.m[r][c] = static_cast<float>(m.cols[c].v[r]);
    return o;
}

pm::Vector3 ToVec3(const ufbx_vec3& v) {
    return pm::Vector3{static_cast<float>(v.x), static_cast<float>(v.y), static_cast<float>(v.z)};
}

// DFS from the root so localBone[] is parents-before-children, which the
// compile stage's bind-matrix fold depends on. The FBX root and the empty
// container nodes above the skeleton (an exporter's "root" / "Armature" Null)
// are dropped - they are scene structure, not joints, and the DMX loader skips
// the same container dag. `inSkeleton` keeps that to the chain above the first
// real node: a Null *inside* a rig is a helper joint and stays.
void AddNodes(const ufbx_node* node, int parentIndex, bool inSkeleton, Source& out,
              std::unordered_map<uint32_t, int>& nodeToBone,
              const std::unordered_set<uint32_t>& skinJoints) {
    const bool isContainer = !node->attrib || node->attrib_type == UFBX_ELEMENT_EMPTY;
    int index = parentIndex;
    if (inSkeleton || !isContainer || skinJoints.count(node->typed_id)) {
        index = static_cast<int>(out.localBone.size());
        LocalBone lb;
        lb.name = std::string(node->name.data, node->name.length);
        lb.parent = parentIndex;
        // a mesh node is exporter structure, not a joint - same exemption the
        // DMX loader gives mesh dags
        lb.isNonSkeletal = node->mesh != nullptr;
        out.localBone.push_back(lb);
        nodeToBone[node->typed_id] = index;
        inSkeleton = true;
    }
    for (size_t i = 0; i < node->children.count; ++i)
        AddNodes(node->children.data[i], index, inSkeleton, out, nodeToBone,skinJoints);
}

// Parent-relative transform for a bone node, container-folded for a root (its
// FBX parent is a dropped container, so take world instead of losing it), with
// translation scaled. Same rule for the bind pose and every animated frame.
pm::matrix3x4 BoneLocal(const ufbx_node* node, bool isRoot, float scale) {
    pm::matrix3x4 local = ToMatrix3x4(isRoot ? node->node_to_world : node->node_to_parent);
    for (int r = 0; r < 3; ++r)
        local.m[r][3] *= scale;
    return local;
}

// Fill one frame's pose for every bone from an (evaluated) scene. A bone is a
// root when its FBX parent is not itself a mapped bone.
bool SampleFrame(const ufbx_scene* scene, const std::unordered_map<uint32_t, int>& nodeToBone,
                 const std::vector<ufbx_matrix>& rest, float scale,
                 std::vector<SrcBonePose>& frame, std::string* err) {
    for (size_t i = 0; i < scene->nodes.count; ++i) {
        const ufbx_node* node = scene->nodes.data[i];
        auto it = nodeToBone.find(node->typed_id);
        if (it == nodeToBone.end())
            continue;
        const bool isRoot = !node->parent ||
                            nodeToBone.find(node->parent->typed_id) == nodeToBone.end();
        const auto& sampled = isRoot ? node->node_to_world : node->node_to_parent;
        const auto& original = rest[it->second];
        // M^T M removes rotation while retaining scale and shear. Comparing
        // sampled matrices also catches deformation inherited from containers.
        bool changed = ufbx_matrix_determinant(&sampled) * ufbx_matrix_determinant(&original) < 0;
        for (int a=0;a<3;++a) for (int b=0;b<3;++b) {
            double x=0,y=0;
            for (int r=0;r<3;++r) { x+=sampled.cols[a].v[r]*sampled.cols[b].v[r]; y+=original.cols[a].v[r]*original.cols[b].v[r]; }
            if (!std::isfinite(x) || !std::isfinite(y) || std::abs(x-y)>1e-5*std::max(1.0,std::max(std::abs(x),std::abs(y)))) changed=true;
        }
        if (changed) {
            if (err) *err = "animated FBX scaling/shear on '" + std::string(node->name.data,node->name.length) +
                "' cannot be represented by MDL bone animation; bake into vertex animation before import";
            return false;
        }
        const pm::matrix3x4 local = BoneLocal(node, isRoot, scale);
        pm::MatrixAngles(local, frame[it->second].rot, frame[it->second].pos);
    }
    return true;
}

bool SameMatrix(const ufbx_matrix& a, const ufbx_matrix& b) {
    for (int c=0;c<4;++c) for (int r=0;r<3;++r)
        if (!std::isfinite(a.cols[c].v[r]) || !std::isfinite(b.cols[c].v[r]) ||
            std::abs(a.cols[c].v[r]-b.cols[c].v[r])>1e-4 *
                std::max(1.0, std::max(std::abs(a.cols[c].v[r]),std::abs(b.cols[c].v[r])))) return false;
    return true;
}

// Skin clusters retain the actual bind matrices even when an exporter saves
// the scene in an animated pose. Mesh geometry and joints must use that same
// bind space; the separately sampled takes still use the evaluated scene.
void BuildSkeleton(const ufbx_scene* scene, float scale, Source& out,
                   std::unordered_map<uint32_t, int>& nodeToBone,
                   std::unordered_map<uint32_t, ufbx_matrix>& geometryBinds) {
    std::unordered_set<uint32_t> skinJoints;
    for(size_t c=0;c<scene->skin_clusters.count;++c)
        if(scene->skin_clusters.data[c]->bone_node)skinJoints.insert(scene->skin_clusters.data[c]->bone_node->typed_id);
    AddNodes(scene->root_node, -1, false, out, nodeToBone,skinJoints);
    out.numbones = static_cast<int>(out.localBone.size());

    SourceAnim anim;
    anim.name = "BindPose";
    anim.numframes = 1;
    anim.frames.assign(1, std::vector<SrcBonePose>(out.numbones));
    std::unordered_map<uint32_t,ufbx_matrix> binds;
    // Pose entries fill unweighted helper joints. A cluster is authoritative
    // for its joint; separate clusters sharing a joint must agree.
    for (size_t p=0;p<scene->poses.count;++p) {
        const auto pose=scene->poses.data[p];
        if (!pose->is_bind_pose) continue;
        for (size_t b=0;b<pose->bone_poses.count;++b) {
            const auto& entry=pose->bone_poses.data[b];
            if (entry.bone_node) binds.emplace(entry.bone_node->typed_id,entry.bone_to_world);
        }
    }
    std::unordered_map<uint32_t,ufbx_matrix> clusterBinds;
    for (size_t n=0;n<scene->nodes.count;++n) {
        const auto node=scene->nodes.data[n];
        if (!node->mesh || !node->mesh->skin_deformers.count) continue;
        const auto skin=node->mesh->skin_deformers.data[0];
        for (size_t c=0;c<skin->clusters.count;++c) {
            const auto cluster=skin->clusters.data[c];
            if (!cluster->bone_node) continue;
            const auto id=cluster->bone_node->typed_id;
            if (std::abs(ufbx_matrix_determinant(&cluster->bind_to_world))<1e-12)
                throw std::runtime_error("singular FBX skin bind for joint: "+std::string(cluster->bone_node->name.data,cluster->bone_node->name.length));
            auto previous=clusterBinds.find(id);
            if (previous!=clusterBinds.end() && !SameMatrix(previous->second,cluster->bind_to_world))
                throw std::runtime_error("conflicting FBX bind poses for shared skin joint: "+std::string(cluster->bone_node->name.data,cluster->bone_node->name.length));
            binds[id]=clusterBinds[id]=cluster->bind_to_world;
            const auto geometry=ufbx_matrix_mul(&cluster->bind_to_world,&cluster->geometry_to_bone);
            auto existing=geometryBinds.find(node->typed_id);
            if (existing!=geometryBinds.end() && !SameMatrix(existing->second,geometry))
                throw std::runtime_error("conflicting FBX geometry bind matrices in mesh: "+std::string(node->name.data,node->name.length));
            geometryBinds[node->typed_id]=geometry;
        }
    }
    std::vector<const ufbx_node*> boneNodes(out.numbones);
    for (size_t i=0;i<scene->nodes.count;++i) {
        const auto node=scene->nodes.data[i]; auto it=nodeToBone.find(node->typed_id);
        if (it!=nodeToBone.end()) boneNodes[it->second]=node;
    }
    // AddNodes produces parent-before-child indices, independently of the
    // exporter's object ordering in scene->nodes.
    out.boneToPose.resize(out.numbones);
    std::vector<ufbx_matrix> worlds(out.numbones);
    for (int b=0;b<out.numbones;++b) {
        const auto node=boneNodes[b];
        const int parent = out.localBone[b].parent;
        auto explicitBind=binds.find(node->typed_id);
        worlds[b]=explicitBind!=binds.end()?explicitBind->second:
            parent<0?node->node_to_world:ufbx_matrix_mul(&worlds[parent],&node->node_to_parent);
        ufbx_matrix local=worlds[b];
        if (parent>=0) { const auto inverse=ufbx_matrix_invert(&worlds[parent]); local=ufbx_matrix_mul(&inverse,&worlds[b]); }
        auto pose=ToMatrix3x4(local);
        for (int r=0;r<3;++r) pose.m[r][3]*=scale;
        pm::MatrixAngles(pose,anim.frames[0][b].rot,anim.frames[0][b].pos);
        out.boneToPose[b]=ToMatrix3x4(worlds[b]);
        for (int r=0;r<3;++r) out.boneToPose[b].m[r][3]*=scale;
    }

    out.anims.push_back(std::move(anim));
}

// Each FBX take (ufbx_anim_stack) becomes one named SourceAnim, sampled at the
// scene's own frame rate. $animation/$sequence pick one with blockname; the
// default is the first non-BindPose clip.
bool LoadAnimStacks(const ufbx_scene* scene, float scale, Source& out, std::string* err,
                    const std::unordered_map<uint32_t, int>& nodeToBone,float requestedRate) {
    double fps = requestedRate>0 ? requestedRate : scene->settings.frames_per_second;
    if (fps <= 0.0)
        fps = 30.0;
    const float outputFps=static_cast<float>(fps);
    if (!std::isfinite(fps) || !std::isfinite(outputFps) || outputFps<=0) {
        if (err) *err="invalid FBX animation frame rate";
        return false;
    }
    std::vector<ufbx_matrix> rest(out.numbones);
    for (size_t i=0;i<scene->nodes.count;++i) {
        const auto* node=scene->nodes.data[i];const auto found=nodeToBone.find(node->typed_id);
        if (found==nodeToBone.end()) continue;
        const bool root=!node->parent || nodeToBone.find(node->parent->typed_id)==nodeToBone.end();
        rest[found->second]=root?node->node_to_world:node->node_to_parent;
    }

    SourceNameRegistry names(true);
    for (const auto& animation : out.anims)
        if (!names.Add(animation.name, err)) return false;
    for (size_t s = 0; s < scene->anim_stacks.count; ++s) {
        const auto* stack = scene->anim_stacks.data[s];
        if (!names.Add(std::string(stack->name.data, stack->name.length), err)) return false;
    }
    for (size_t s = 0; s < scene->anim_stacks.count; ++s) {
        const ufbx_anim_stack* stack = scene->anim_stacks.data[s];
        const std::string name(stack->name.data, stack->name.length);
        const double duration=stack->time_end-stack->time_begin;
        const double intervals=std::round(duration*fps);
        if (!std::isfinite(duration) || duration<0 || !std::isfinite(intervals) || intervals>=lim::kMaxAnimFrames) {
            if (err)
                *err = "FBX animation \"" + name + "\" has invalid duration or exceeds frame limit (max " + std::to_string(lim::kMaxAnimFrames) + ")";
            return false;
        }
        const int numframes=1+static_cast<int>(intervals);

        SourceAnim anim;
        anim.name = name;
        anim.sampleFps = outputFps;
        anim.startframe = 0;
        anim.endframe = numframes - 1;
        anim.numframes = numframes;
        anim.frames.assign(numframes, std::vector<SrcBonePose>(out.numbones));
        for (int f = 0; f < numframes; ++f) {
            const double time = stack->time_begin + static_cast<double>(f) / fps;
            ufbx_evaluate_opts eopts = {};
            ufbx_error everr;
            ufbx_scene* frameScene = ufbx_evaluate_scene(scene, stack->anim, time, &eopts, &everr);
            if (!frameScene) {
                if (err) {
                    char buf[1024];
                    ufbx_format_error(buf, sizeof(buf), &everr);
                    *err = buf;
                }
                return false;
            }
            const bool sampled=SampleFrame(frameScene, nodeToBone, rest, scale, anim.frames[f], err);
            ufbx_free_scene(frameScene);
            if (!sampled) return false;
        }
        out.anims.push_back(std::move(anim));
    }
    return true;
}

// Per-corner skin weights. An unskinned mesh rides its own node bone.
SrcBoneWeight CornerWeights(const ufbx_mesh* mesh, const ufbx_skin_deformer* skin,
                            const std::vector<int>& clusterToBone, uint32_t index,
                            int meshBone) {
    SrcBoneWeight bw;
    if (skin) {
        const uint32_t vi = mesh->vertex_indices.data[index];
        const ufbx_skin_vertex& sv = skin->vertices.data[vi];
        int bones[lim::kMaxSrcBoneWeights];
        float weights[lim::kMaxSrcBoneWeights];
        int count = 0;
        for (uint32_t w = 0; w < sv.num_weights && count < lim::kMaxSrcBoneWeights; ++w) {
            const ufbx_skin_weight& sw = skin->weights.data[sv.weight_begin + w];
            const int bone = clusterToBone[sw.cluster_index];
            if (bone < 0 || sw.weight <= 0)
                continue;
            bones[count] = bone;
            weights[count] = static_cast<float>(sw.weight);
            ++count;
        }
        if (count > 0) {
            bw.numbones = SortAndBalanceBones(count, lim::kMaxSrcBoneWeights, bones, weights);
            for (int k = 0; k < bw.numbones; ++k) {
                bw.bone[k] = bones[k];
                bw.weight[k] = weights[k];
            }
            return bw;
        }
    }
    bw.numbones = 1;
    bw.bone[0] = meshBone;
    bw.weight[0] = 1.0f;
    return bw;
}

// ---------------------------------------------------------------------------
// Blend shapes -> morphs. One blend channel is one delta state; its offsets are
// per logical vertex, so a delta fans out to every unified vertex that vertex
// became (a UV or material seam splits one source vertex into several).
//
// FBX carries no stereo balance channel, so every vertex takes the DMX loader's
// 1.0 default.
// ---------------------------------------------------------------------------
void LoadMorphs(const std::vector<const ufbx_node*>& meshes, const std::vector<int>& bases,
                const std::vector<std::vector<int>>& srcToUnified, float scale, Source& out,
                const std::unordered_map<uint32_t,ufbx_matrix>& geometryBinds) {
    // one morph per channel NAME - the same shape key can live on several
    // meshes, and the compile stage wants a single delta state driving them all
    for (size_t m = 0; m < meshes.size(); ++m) {
        const ufbx_node* node = meshes[m];
        const ufbx_mesh* mesh = node->mesh;
        const auto bind=geometryBinds.find(node->typed_id);
        const auto& geometry=bind==geometryBinds.end()?node->geometry_to_world:bind->second;
        const auto normalMatrix=ufbx_matrix_for_normals(&geometry);
        for (size_t d = 0; d < mesh->blend_deformers.count; ++d) {
            const ufbx_blend_deformer* def = mesh->blend_deformers.data[d];
            for (size_t c = 0; c < def->channels.count; ++c) {
                const ufbx_blend_channel* chan = def->channels.data[c];
                const ufbx_blend_shape* shape = chan->target_shape;
                if (!shape || shape->num_offsets == 0)
                    continue;
                const std::string name = std::string(chan->name.data, chan->name.length);

                SrcMorphAnim* morph = nullptr;
                for (SrcMorphAnim& existing : out.morphs)
                    if (existing.name == name) { morph = &existing; break; }
                if (!morph) {
                    out.morphs.emplace_back();
                    morph = &out.morphs.back();
                    morph->name = name;
                }

                for (size_t k = 0; k < shape->num_offsets; ++k) {
                    const uint32_t v = shape->offset_vertices.data[k];
                    if (v >= mesh->num_vertices)
                        continue;
                    const int srcVertex = bases[m] + static_cast<int>(v);
                    if (srcVertex >= static_cast<int>(srcToUnified.size()))
                        continue;

                    // offsets are geometry-space directions, placed the same
                    // way the positions they displace were
                    pm::Vector3 pos = ToVec3(ufbx_transform_direction(
                        &geometry, shape->position_offsets.data[k]));
                    pos.x *= scale; pos.y *= scale; pos.z *= scale;
                    // Blender sizes normal_offsets to match but fills it with
                    // zeros, so in practice these arrive empty; an exporter
                    // that does write them gets them through to ndelta.
                    pm::Vector3 nrm;
                    if (k < shape->normal_offsets.count)
                        nrm = ToVec3(ufbx_transform_direction(&normalMatrix,
                                                              shape->normal_offsets.data[k]));
                    // Blender writes an offset entry for every vertex in the
                    // shape's group, noise included, where a DMX delta state is
                    // sparse. Same thresholds the DMX exporter applies: a
                    // position delta counts above 1e-5, a normal delta above a
                    // 1-dot of 1e-3, which for unit normals is |d|^2 >= 2e-3.
                    const float posLen2 = pos.x * pos.x + pos.y * pos.y + pos.z * pos.z;
                    const float nrmLen2 = nrm.x * nrm.x + nrm.y * nrm.y + nrm.z * nrm.z;
                    if (posLen2 <= 1e-10f && nrmLen2 < 2e-3f)
                        continue;

                    for (int unified : srcToUnified[srcVertex]) {
                        SrcVertAnim va;
                        va.vertex = unified;
                        va.speed = 1.0f; // FBX carries no per-vertex morph speed/balance
                        va.side = 1.0f;
                        va.pos = pos;
                        va.normal = nrm;
                        morph->vanims.push_back(va);
                    }
                }
            }
        }
    }

    // AddFlexKeys: one flexkey per delta state.
    for (const SrcMorphAnim& morph : out.morphs) {
        bool seen = false;
        for (const SrcFlexKey& key : out.flexkeys)
            if (_stricmp(key.name.c_str(), morph.name.c_str()) == 0) { seen = true; break; }
        if (!seen) {
            SrcFlexKey key;
            key.name = morph.name;
            out.flexkeys.push_back(std::move(key));
        }
    }
}

} // namespace

bool LoadFbxSource(const std::string& path, Source& out, MaterialTable& mats, float scale,
                   std::string* err, bool morphSource, MeshFilter* filter, bool animOnly,const SceneOptions* options) {
    if (options && options->fbxAssimp)
        return LoadSceneSource(path,out,mats,scale,err,morphSource,filter,animOnly,*options);
    ufbx_load_opts opts = {};
    // Source is right-handed Z-up; ADJUST_TRANSFORMS bakes the conversion into
    // each node so it survives dropping the root node.
    opts.target_axes = ufbx_axes_right_handed_z_up;
    opts.space_conversion = UFBX_SPACE_CONVERSION_ADJUST_TRANSFORMS;
    // FBX units are the author's problem ($scale / $upaxis), same as DMX.
    opts.target_unit_meters = 0.0f;
    // PRESERVE, not MODIFY_GEOMETRY: baking the geometry transform into the
    // mesh does NOT bake it into the blend shape offsets, so deltas would come
    // out short of the transform the base vertices already took. Everything
    // here goes through geometry_to_world, which carries it either way - and
    // PRESERVE also never injects the helper nodes AddNodes would see as bones.
    opts.geometry_transform_handling = UFBX_GEOMETRY_TRANSFORM_HANDLING_PRESERVE;
    opts.generate_missing_normals = true;
    opts.ignore_embedded = true;
    opts.open_file_cb.fn = [](void* user, ufbx_stream* stream, const char* filename, size_t length,
                             const ufbx_open_file_info* info) {
        if (!ufbx_default_open_file(user, stream, filename, length, info)) return false;
        pulse::dependencies::Note(std::string(filename, length));
        return true;
    };

    pulse::dependencies::Note(path);
    ufbx_error error;
    ufbx_scene* scene = ufbx_load_file_len(path.c_str(), path.size(), &opts, &error);
    if (!scene) {
        if (err) {
            char buf[1024];
            ufbx_format_error(buf, sizeof(buf), &error);
            *err = buf;
        }
        return false;
    }

    std::unordered_map<uint32_t, int> nodeToBone;
    std::unordered_map<uint32_t,ufbx_matrix> geometryBinds;
    try { BuildSkeleton(scene, scale, out, nodeToBone,geometryBinds); }
    catch (const std::exception& e) { if(err)*err=e.what(); ufbx_free_scene(scene); return false; }
    if (!ValidateSourceBoneNames(out, err)) {
        ufbx_free_scene(scene);
        return false;
    }
    if (out.numbones <= 0) {
        if (err) *err = "the scene has no nodes";
        ufbx_free_scene(scene);
        return false;
    }

    // Load takes for every kind, not just animOnly: the source cache treats a
    // higher LoadKind as a superset, so a mesh load must carry the anims too.
    if (!LoadAnimStacks(scene, scale, out, err, nodeToBone,options && options->explicitSampleRate?options->sampleRate:0)) {
        ufbx_free_scene(scene);
        return false;
    }

    if (animOnly) {
        ufbx_free_scene(scene);
        return true;
    }

    const ufbx_node* selected=nullptr;
    if(options && !options->node.empty()) {
        for(size_t n=0;n<scene->nodes.count;++n) { const auto node=scene->nodes.data[n]; if(std::string(node->name.data,node->name.length)==options->node) selected=node; }
        if(!selected) { if(err) *err="InNode not found: "+options->node; ufbx_free_scene(scene); return false; }
    }
    std::vector<TriInput> tris;
    std::vector<uint32_t> triIndices;
    // every mesh's logical vertices laid end to end, so one id space covers the
    // whole source. Morph deltas are looked up in it.
    std::vector<const ufbx_node*> morphMeshes;
    std::vector<int> morphBase;
    int srcVertexCount = 0;

    for (size_t i = 0; i < scene->nodes.count; ++i) {
        const ufbx_node* node = scene->nodes.data[i];
        const ufbx_mesh* mesh = node->mesh;
        if (!mesh)
            continue;
        const auto bind=geometryBinds.find(node->typed_id);
        const auto& geometry=bind==geometryBinds.end()?node->geometry_to_world:bind->second;
        const auto normalMatrix=ufbx_matrix_for_normals(&geometry);
        if(selected) { bool keep=false; for(auto parent=node;parent;parent=parent->parent) if(parent==selected) keep=true; if(!keep) continue; }
        // a rejected mesh skips its geometry only - the node is already a bone
        if (filter && !filter->Keep(std::string(mesh->name.data, mesh->name.length),
                                    std::string(node->name.data, node->name.length)))
            continue;
        const int meshTag =
            filter ? filter->Tag(std::string(mesh->name.data, mesh->name.length),
                                 std::string(node->name.data, node->name.length))
                   : 0;
        const int meshBone = nodeToBone[node->typed_id];
        const int vertexBase = srcVertexCount;
        srcVertexCount += static_cast<int>(mesh->num_vertices);
        morphMeshes.push_back(node);
        morphBase.push_back(vertexBase);

        // one deformer only - stacked skins are a rig authoring mistake here
        const ufbx_skin_deformer* skin =
            mesh->skin_deformers.count ? mesh->skin_deformers.data[0] : nullptr;
        std::vector<int> clusterToBone;
        if (skin) {
            clusterToBone.reserve(skin->clusters.count);
            for (size_t c = 0; c < skin->clusters.count; ++c) {
                const ufbx_node* bn = skin->clusters.data[c]->bone_node;
                auto it = bn ? nodeToBone.find(bn->typed_id) : nodeToBone.end();
                clusterToBone.push_back(it == nodeToBone.end() ? -1 : it->second);
            }
        }

        // per-instance materials win over the mesh's own list (ufbx note)
        const ufbx_material_list& matList =
            node->materials.count ? node->materials : mesh->materials;
        std::vector<int> materialIndex(matList.count, 0);
        std::vector<char> materialRemoved(matList.count, 0);
        for (size_t m = 0; m < matList.count; ++m) {
            const ufbx_string& name = matList.data[m]->name;
            std::string nm(name.data, name.length);
            // $removemeshword: leave the slot out of the table; faces referencing
            // it are dropped below, so its verts never unify.
            if (filter && filter->MaterialRemoved(nm)) {
                materialRemoved[m] = 1;
                continue;
            }
            // Relative-path flagged like DMX: no derived "models/<outname>/",
            // the empty cdmaterials entry resolves the name as authored.
            materialIndex[m] = mats.UseTextureAsMaterial(mats.LookupTexture(nm.c_str()));
        }

        triIndices.resize(mesh->max_face_triangles * 3);
        for (size_t f = 0; f < mesh->faces.count; ++f) {
            const ufbx_face face = mesh->faces.data[f];
            int material = 0;
            bool removed = false;
            if (mesh->face_material.count && !materialIndex.empty()) {
                const uint32_t mi = mesh->face_material.data[f];
                if (mi < materialIndex.size()) {
                    material = materialIndex[mi];
                    removed = materialRemoved[mi];
                }
            } else if (!materialIndex.empty()) {
                material = materialIndex[0];
                removed = materialRemoved[0];
            }
            if (removed)
                continue;

            const uint32_t numTris =
                ufbx_triangulate_face(triIndices.data(), triIndices.size(), mesh, face);
            for (uint32_t t = 0; t < numTris; ++t) {
                TriInput tri;
                tri.material = material;
                tri.tag = meshTag;
                for (int j = 0; j < 3; ++j) {
                    const uint32_t index = triIndices[t * 3 + j];
                    TriCorner& corner = tri.v[j];
                    // Source vertices are model space; bones carry the same
                    // hierarchy, so both come from the node's world transform.
                    corner.position = ToVec3(ufbx_transform_position(
                        &geometry,
                        ufbx_get_vertex_vec3(&mesh->vertex_position, index)));
                    corner.position.x *= scale;
                    corner.position.y *= scale;
                    corner.position.z *= scale;
                    if (mesh->vertex_normal.exists) {
                        corner.normal = ToVec3(ufbx_transform_direction(
                            &normalMatrix,
                            ufbx_get_vertex_vec3(&mesh->vertex_normal, index)));
                        pm::VectorNormalize(corner.normal);
                    }
                    if (mesh->vertex_uv.exists) {
                        const ufbx_vec2 uv = ufbx_get_vertex_vec2(&mesh->vertex_uv, index);
                        corner.texcoord = pm::Vector2{static_cast<float>(uv.x),
                                                      1.0f - static_cast<float>(uv.y)};
                    }
                    corner.boneweight =
                        CornerWeights(mesh, skin, clusterToBone, index, meshBone);
                    if (morphSource)
                        corner.srcVertex =
                            vertexBase + static_cast<int>(mesh->vertex_indices.data[index]);
                }
                tris.push_back(tri);
            }
        }
    }

    std::vector<std::vector<int>> srcToUnified;
    BuildUnifiedMeshes(tris, out, morphSource ? &srcToUnified : nullptr);
    if (morphSource)
        LoadMorphs(morphMeshes, morphBase, srcToUnified, scale, out,geometryBinds);

    ufbx_free_scene(scene);
    return true;
}

} // namespace pulse::source
