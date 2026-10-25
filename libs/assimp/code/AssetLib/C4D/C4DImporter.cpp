/*
Open Asset Import Library (assimp)
----------------------------------------------------------------------

Copyright (c) 2006-2026, assimp team
All rights reserved.

Redistribution and use of this software in source and binary forms,
with or without modification, are permitted provided that the
following conditions are met:

* Redistributions of source code must retain the above
  copyright notice, this list of conditions and the
  following disclaimer.

* Redistributions in binary form must reproduce the above
  copyright notice, this list of conditions and the
  following disclaimer in the documentation and/or other
  materials provided with the distribution.

* Neither the name of the assimp team, nor the names of its
  contributors may be used to endorse or promote products
  derived from this software without specific prior
  written permission of the assimp team.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

----------------------------------------------------------------------
*/

/** @file  C4DImporter.cpp
 *  @brief Implementation of the Cinema4D importer class.
 */
#ifndef ASSIMP_BUILD_NO_C4D_IMPORTER

// no #ifdefing here, Cinema4D support is carried out in a branch of assimp
// where it is turned on in the CMake settings.

#include "C4DImporter.h"
#include "PostProcessing/GenVertexNormalsProcess.h"
#include "PostProcessing/ProcessHelper.h"
#include <memory>
#include <cmath>
#include <limits>
#include <functional>
#include <assimp/IOSystem.hpp>
#include <assimp/scene.h>
#include <assimp/ai_assert.h>

#if defined(_M_X64) || defined(__amd64__)
#   define __C4D_64BIT
#endif

#define __PC
#include "c4d_file.h"
#include "default_alien_overloads.h"

namespace {

aiString aiStringFrom(cineware::String const & cinestring) {
    aiString result;
    cinestring.GetCString(result.data, AI_MAXLEN - 1);
    result.length = static_cast<ai_uint32>(cinestring.GetLength());
    return result;
}

aiMatrix4x4 aiMatrixFrom(const cineware::Matrix& m) {
    return aiMatrix4x4(m.v1.x,m.v2.x,m.v3.x,m.off.x,
        m.v1.y,m.v2.y,m.v3.y,m.off.y,m.v1.z,m.v2.z,m.v3.z,m.off.z,0,0,0,1);
}

bool finiteMatrix(const aiMatrix4x4& m) {
    for(unsigned int r=0;r<4;++r) for(unsigned int c=0;c<4;++c)
        if(!std::isfinite(m[r][c])) return false;
    return true;
}

}

using namespace Assimp;
using namespace cineware;

// overload this function and fill in your own unique data
void GetWriterInfo(int &id, String &appname) {
    id = 2424226;
    appname = "Open Asset Import Library";
}

namespace Assimp {
    template<> const char* LogFunctions<C4DImporter>::Prefix() {
        return "C4D: ";
    }
}

static constexpr aiImporterDesc desc = {
    "Cinema4D Importer",
    "",
    "",
    "",
    aiImporterFlags_SupportBinaryFlavour,
    0,
    0,
    0,
    0,
    "c4d"
};

// ------------------------------------------------------------------------------------------------
bool C4DImporter::CanRead( const std::string& pFile, IOSystem* pIOHandler, bool checkSig) const {
    const std::string& extension = GetExtension(pFile);
    if (extension == "c4d") {
        return true;
    } else if ((!extension.length() || checkSig) && pIOHandler)   {
        // TODO
    }

    return false;
}

// ------------------------------------------------------------------------------------------------
const aiImporterDesc* C4DImporter::GetInfo () const {
    return &desc;
}


// ------------------------------------------------------------------------------------------------
// Imports the given file into the given scene structure.
void C4DImporter::InternReadFile( const std::string& pFile, aiScene* pScene, IOSystem* pIOHandler) {
    std::unique_ptr<IOStream> file( pIOHandler->Open( pFile));

    if( file.get() == nullptr ) {
        ThrowException("failed to open file " + pFile);
    }

    const size_t file_size = file->FileSize();
    if (!file_size) {
        ThrowException("empty C4D document " + pFile);
    }

    std::vector<uint8_t> mBuffer(file_size);
    if (file->Read(mBuffer.data(), 1, file_size) != file_size) {
        ThrowException("incomplete C4D document " + pFile);
    }

    Filename f;
    f.SetMemoryReadMode(mBuffer.data(), file_size);

    // open document first
    BaseDocument* doc = LoadDocument(f, SCENEFILTER_OBJECTS | SCENEFILTER_MATERIALS);
    if(doc == nullptr ) {
        ThrowException("failed to read document " + pFile);
    }

    // Generate the root-node
    pScene->mRootNode = new aiNode("<C4DRoot>");

    // convert left-handed to right-handed
    pScene->mRootNode->mTransformation.a1 = 0.01f;
    pScene->mRootNode->mTransformation.b2 = 0.01f;
    pScene->mRootNode->mTransformation.c3 = -0.01f;

    // A failed read must release data not yet owned by aiScene. Keep material
    // creation and traversal inside the same cleanup boundary.
    meshes.clear();
    materials.clear();
    material_mapping.clear();
    visitedObjects.clear();
    cacheNodeId = 0;
    document = doc;
    sourceObjects.clear();
    sourceNodes.clear();
    try {
        PrepareRig(doc);
        ReadMaterials(doc->GetFirstMaterial());
        RecurseHierarchy(doc->GetFirstObject(), pScene->mRootNode);
        ReadAnimation(pScene);
    } catch(...) {
        for(aiMesh* mesh : meshes) {
            delete mesh;
        }
        for(aiMaterial* material : materials) delete material;
        meshes.clear();
        materials.clear();
        BaseDocument::Free(doc);
        document = nullptr;
        throw;
    }
    BaseDocument::Free(doc);
    document = nullptr;

    // copy meshes over
    pScene->mNumMeshes = static_cast<unsigned int>(meshes.size());
    pScene->mMeshes = new aiMesh*[pScene->mNumMeshes]();
    std::copy(meshes.begin(), meshes.end(), pScene->mMeshes);

    // copy materials over, adding a default material if necessary
    unsigned int mat_count = static_cast<unsigned int>(materials.size());
    for(aiMesh* mesh : meshes) {
        ai_assert(mesh->mMaterialIndex <= mat_count);
        if(mesh->mMaterialIndex >= mat_count) {
            ++mat_count;

            std::unique_ptr<aiMaterial> def_material(new aiMaterial());
            const aiString name(AI_DEFAULT_MATERIAL_NAME);
            def_material->AddProperty(&name, AI_MATKEY_NAME);

            materials.push_back(def_material.release());
            break;
        }
    }

    pScene->mNumMaterials = static_cast<unsigned int>(materials.size());
    pScene->mMaterials = new aiMaterial*[pScene->mNumMaterials]();
    std::copy(materials.begin(), materials.end(), pScene->mMaterials);
}

// ------------------------------------------------------------------------------------------------
void C4DImporter::PrepareRig(BaseDocument* doc) {
    rigScene = false;
    std::set<BaseObject*> seen;
    std::function<void(BaseObject*, unsigned int)> collect = [&](BaseObject* op, unsigned int depth) {
        if(depth > 256) ThrowException("C4D source hierarchy exceeds 256 levels");
        for(;op;op=op->GetNext()) {
            if(!seen.insert(op).second || seen.size()>1000000)
                ThrowException("invalid C4D source hierarchy");
            sourceObjects.push_back(op);
            rigScene |= op->GetFirstCTrack()!=nullptr || op->GetTag(Tweights)!=nullptr;
            collect(op->GetDown(),depth+1);
        }
    };
    collect(doc->GetFirstObject(),0);
    if(!rigScene) return;
    auto* takes=doc->GetTakeData();
    if(takes && takes->GetMainTake() && (takes->GetMainTake()->GetDown() ||
       takes->GetCurrentTake()!=takes->GetMainTake()))
        ThrowException("C4D rig takes/overrides are unsupported; bake the selected take to FBX/glTF");
    std::set<std::string> names;
    unsigned int skins=0;
    for(BaseObject* op:sourceObjects) {
        const auto name=aiStringFrom(op->GetName());
        if(!name.length || name.length>=AI_MAXLEN-1 || std::string(name.C_Str())=="<C4DRoot>" ||
           !names.insert(name.C_Str()).second)
            ThrowException("C4D rigs require unique, nonempty object names: ",name.C_Str());
        if(op->GetLayerObject() || op->GetNBit(NBIT_NOANIM) || op->GetNBit(NBIT_SOLO_ANIM) ||
           op->GetDataInstance()->GetBool(ID_BASEOBJECT_QUATERNION_ROTATION))
            ThrowException("C4D rig layer/disabled/solo/quaternion animation is unsupported: ",name.C_Str());
        const Int32 type=op->GetType();
        if(type!=Onull && type!=Ojoint && type!=Opolygon && type!=Oskin)
            ThrowException("C4D rig contains unsupported generator/deformer/plugin: ",name.C_Str());
        if(op->GetCache() || (op->GetDeformCache() && !op->GetTag(Tweights)))
            ThrowException("C4D rig contains an unsupported evaluated cache: ",name.C_Str());
        for(auto* tag=op->GetFirstTag();tag;tag=tag->GetNext()) {
            const Int32 t=tag->GetType();
            if(tag->GetFirstCTrack() || (t!=Tweights && t!=Tphong && t!=Tuvw &&
               t!=Tnormal && t!=Ttangent && t!=Ttexture && t!=Tpolygonselection &&
               t!=Tpoint && t!=Tpolygon))
                ThrowException("C4D rig tag/constraint/expression is unsupported: ",name.C_Str()," tag ",t);
        }
        if(op->GetTag(Tweights)) {
            // glTF's shared skin export cannot represent different geometry bind
            // matrices for the same joint. Keep this first implementation bounded.
            if(type!=Opolygon || ++skins>1 || op->GetTag(Tweights,1))
                ThrowException("C4D skin requires one polygon object and one weight tag per document");
            BaseObject* skin=op->GetDown();
            if(!skin || skin->GetNext() || skin->GetType()!=Oskin || skin->GetDown())
                ThrowException("C4D weighted mesh requires exactly one direct Skin deformer child");
        }
        if(type==Oskin) {
            auto* bc=op->GetDataInstance();
            if(!op->GetUp() || !op->GetUp()->GetTag(Tweights) || op->GetFirstCTrack() ||
               !op->GetDeformMode() ||
               bc->GetInt32(ID_CA_SKIN_OBJECT_TYPE)!=ID_CA_SKIN_OBJECT_TYPE_LINEAR ||
               bc->GetInt32(ID_CA_SKIN_OBJECT_COORD)!=ID_CA_SKIN_OBJECT_COORD_JOINTS ||
               bc->GetInt32(ID_CA_SKIN_OBJECT_TRANSFORM)!=ID_CA_SKIN_OBJECT_TRANSFORM_OBJECT ||
               bc->GetInt32(ID_CA_SKIN_OBJECT_SCALING)!=ID_CA_SKIN_OBJECT_SCALING_NONE)
                ThrowException("C4D Skin supports only linear joint coordinates/object transform/no bone scaling");
        }
    }
}

void C4DImporter::ReadSkin(BaseObject* object, aiMesh* mesh,
    const std::vector<unsigned int>& sourcePoints) {
    auto* tag=object->GetTag(Tweights);
    if(!tag) return;
    auto* weights=dynamic_cast<WeightTagData*>(tag->GetNodeData());
    if(!weights || weights->GetJointCount()<=0 || weights->GetJointCount()>1024)
        ThrowException("C4D skin has missing/invalid joint weights");
    const Int32 pointCount=static_cast<PolygonObject*>(object)->GetPointCount();
    if(static_cast<uint64_t>(pointCount)*weights->GetJointCount()>100000000)
        ThrowException("C4D skin exceeds 100000000 point/joint weight budget");
    const aiMatrix4x4 geom=aiMatrixFrom(weights->GetGeomMg());
    if(!finiteMatrix(geom) || std::fabs(geom.Determinant())<1e-12)
        ThrowException("C4D skin has invalid geometry bind matrix");
    if(!geom.Equal(aiMatrixFrom(object->GetMg()),1e-4f))
        ThrowException("C4D skinned mesh transform must remain at its geometry bind transform");
    for(BaseObject* ancestor=object;ancestor;ancestor=ancestor->GetUp())
        if(ancestor->GetFirstCTrack())
            ThrowException("C4D skinned mesh/parent transform animation is unsupported; animate its joints");
    std::vector<double> totals(pointCount,0);
    std::vector<unsigned int> influences(pointCount,0);
    std::vector<std::unique_ptr<aiBone>> bones;
    std::set<BaseObject*> joints;
    for(Int32 j=0;j<weights->GetJointCount();++j) {
        BaseObject* joint=weights->GetJoint(j,document);
        if(!joint || joint->GetType()!=Ojoint || !joints.insert(joint).second ||
           std::find(sourceObjects.begin(),sourceObjects.end(),joint)==sourceObjects.end())
            ThrowException("C4D skin has a missing, duplicate or non-joint link");
        std::unique_ptr<aiBone> bone(new aiBone());
        bone->mName=aiStringFrom(joint->GetName());
        const JointRestState rest=weights->GetJointRestState(j);
        const aiMatrix4x4 bind=aiMatrixFrom(rest.m_oMg), inverse=aiMatrixFrom(rest.m_oMi);
        if(!finiteMatrix(bind) || !finiteMatrix(inverse) || std::fabs(bind.Determinant())<1e-12 ||
           !(bind*inverse).Equal(aiMatrix4x4(),1e-4f))
            ThrowException("C4D skin has invalid joint bind matrix: ",bone->mName.C_Str());
        bone->mOffsetMatrix=inverse*geom;
        std::vector<float> map(pointCount,0);
        const Int32 count=weights->GetWeightCount(j);
        if(count<0 || count>pointCount) ThrowException("C4D skin weight count exceeds point count");
        // Cineware 22 GetIndexWeight repeats one entry on a 2027 document.
        // The point-addressed accessor reads its quantized map correctly.
        for(Int32 point=0;point<pointCount;++point) {
            const Float weight=weights->GetWeight(j,point);
            if(!std::isfinite(weight) || weight<0 || weight>1.00001)
                ThrowException("C4D skin has invalid point weight");
            if(!weight) continue;
            map[point]=static_cast<float>(weight);totals[point]+=weight;++influences[point];
        }
        std::vector<aiVertexWeight> corners;
        for(unsigned int c=0;c<sourcePoints.size();++c)
            if(map[sourcePoints[c]]>0) corners.emplace_back(c,map[sourcePoints[c]]);
        if(corners.empty()) continue;
        bone->mNumWeights=static_cast<unsigned int>(corners.size());
        bone->mWeights=new aiVertexWeight[corners.size()];
        std::copy(corners.begin(),corners.end(),bone->mWeights);
        bones.push_back(std::move(bone));
    }
    for(unsigned int point:sourcePoints)
        if(std::fabs(totals[point]-1)>1e-4 || influences[point]>4)
            ThrowException("C4D skin requires normalized weights and at most four joints per point");
    // Weight storage is quantized (e.g. authored 0.5 reads as 0.500008).
    // Normalize only after enforcing the narrow sum tolerance above.
    for(auto& bone:bones) for(unsigned int i=0;i<bone->mNumWeights;++i)
        bone->mWeights[i].mWeight/=static_cast<float>(totals[sourcePoints[bone->mWeights[i].mVertexId]]);
    mesh->mNumBones=static_cast<unsigned int>(bones.size());
    mesh->mBones=new aiBone*[bones.size()]();
    for(size_t i=0;i<bones.size();++i) mesh->mBones[i]=bones[i].release();
}

void C4DImporter::ReadAnimation(aiScene* scene) {
    if(!rigScene) return;
    struct Track { CTrack* source; Int32 component,axis; };
    struct Channels { BaseObject* object; std::vector<Track> tracks; };
    std::vector<Channels> objects;
    std::set<double> times;
    const Int32 fps=document->GetFps();
    if(fps<=0 || fps>240) ThrowException("C4D animation frame rate must be in 1..240");
    for(BaseObject* op:sourceObjects) {
        if(!op->GetFirstCTrack()) continue;
        Channels channels{op,{}};
        std::set<std::pair<Int32,Int32>> used;
        for(auto* track=op->GetFirstCTrack();track;track=track->GetNext()) {
            const DescID& id=track->GetDescriptionID();
            if(id.GetDepth()!=2 || track->GetTrackCategory()!=CTRACK_CATEGORY_VALUE ||
               (id[0].id!=ID_BASEOBJECT_REL_POSITION && id[0].id!=ID_BASEOBJECT_REL_ROTATION &&
                id[0].id!=ID_BASEOBJECT_REL_SCALE) || id[1].id<VECTOR_X || id[1].id>VECTOR_Z ||
               track->GetTimeTrack(document) || track->GetBefore()!=CLOOP_CONSTANT ||
               track->GetAfter()!=CLOOP_CONSTANT || !used.emplace(id[0].id,id[1].id).second)
                ThrowException("animated C4D object has unsupported track/layer/time remapping: ",
                    aiStringFrom(op->GetName()).C_Str());
            if(track->GetBit(BIT_ANIM_OFF) || track->GetBit(BIT_ANIM_SOLO) ||
               track->GetBit(BIT_ANIM_CONSTANTVELOCITY) || track->GetLayerObject())
                ThrowException("C4D muted/solo/layer/constant velocity tracks are unsupported");
            auto* curve=track->GetCurve(CCURVE_CURVE,false);
            if(!curve || curve->GetKeyCount()<=0 || curve->GetKeyCount()>100000)
                ThrowException("C4D animation curve has invalid key count");
            double previous=-std::numeric_limits<double>::infinity();
            for(Int32 i=0;i<curve->GetKeyCount();++i) {
                auto* key=curve->GetKey(i);const double time=key->GetTime().Get();
                if(!std::isfinite(time) || time<=previous || !std::isfinite(key->GetValue()) ||
                   key->GetNBit(NBIT_CKEY_MUTE) ||
                   key->GetInterpolation()!=CINTERPOLATION_LINEAR)
                    ThrowException("animated C4D object supports only finite, ordered linear TRS keys: ",
                        aiStringFrom(op->GetName()).C_Str());
                times.insert(time);previous=time;
            }
            channels.tracks.push_back({track,id[0].id,id[1].id-VECTOR_X});
        }
        objects.push_back(std::move(channels));
    }
    if(objects.empty()) return;
    const double start=*times.begin(),end=*times.rbegin();
    if(std::fabs(start)>1000000 || std::fabs(end)>1000000 ||
       end-start>3600 || (end-start)*fps>100000 || times.size()>100000)
        ThrowException("C4D animation exceeds one hour/100000 sample budget");
    for(int f=0;f<=static_cast<int>(std::ceil((end-start)*fps));++f)
        times.insert(std::min(end,start+static_cast<double>(f)/fps));
    if(times.size()*objects.size()>1000000)
        ThrowException("C4D animation exceeds 1000000 node sample budget");
    float previousSample=-1;
    for(double time:times) {
        const float encoded=static_cast<float>(time-start);
        if(encoded<=previousSample)
            ThrowException("C4D animation key times are too close for GLB float timestamps");
        previousSample=encoded;
    }
    std::unique_ptr<aiAnimation> animation(new aiAnimation());
    animation->mName=aiString("C4D_Timeline");animation->mTicksPerSecond=fps;
    animation->mDuration=(end-start)*fps;
    animation->mNumChannels=static_cast<unsigned int>(objects.size());
    animation->mChannels=new aiNodeAnim*[objects.size()]();
    for(size_t index=0;index<objects.size();++index) {
        auto& item=objects[index];BaseObject* op=item.object;
        auto* channel=animation->mChannels[index]=new aiNodeAnim();
        channel->mNodeName=aiStringFrom(op->GetName());
        channel->mNumPositionKeys=channel->mNumRotationKeys=channel->mNumScalingKeys=static_cast<unsigned int>(times.size());
        channel->mPositionKeys=new aiVectorKey[times.size()];
        channel->mRotationKeys=new aiQuatKey[times.size()];
        channel->mScalingKeys=new aiVectorKey[times.size()];
        const Vector pos=op->GetRelPos(),rot=op->GetRelRot(),scale=op->GetRelScale();
        unsigned int i=0;
        for(double time:times) {
            Vector p=pos,r=rot,s=scale;
            for(auto& track:item.tracks) {
                Vector& value=track.component==ID_BASEOBJECT_REL_POSITION?p:
                    (track.component==ID_BASEOBJECT_REL_ROTATION?r:s);
                const Float sample=track.source->GetCurve()->GetValue(BaseTime(time));
                if(track.axis==0)value.x=sample;else if(track.axis==1)value.y=sample;else value.z=sample;
            }
            op->SetRelPos(p);op->SetRelRot(r);op->SetRelScale(s);
            const auto matrix=aiMatrixFrom(op->GetMl());
            op->SetRelPos(pos);op->SetRelRot(rot);op->SetRelScale(scale);
            aiVector3D outScale,outPos;aiQuaternion outRot;
            matrix.Decompose(outScale,outRot,outPos);
            aiMatrix4x4 recomposed(outRot.GetMatrix());
            for(unsigned int row=0;row<3;++row) {
                recomposed[row][0]*=outScale.x;recomposed[row][1]*=outScale.y;recomposed[row][2]*=outScale.z;
            }
            recomposed.a4=outPos.x;recomposed.b4=outPos.y;recomposed.c4=outPos.z;
            if(!finiteMatrix(matrix) || std::fabs(matrix.Determinant())<1e-10 ||
               !matrix.Equal(recomposed,1e-4f))
                ThrowException("C4D animated transform contains shear, singular scale or non-finite values");
            const double tick=(time-start)*fps;
            channel->mPositionKeys[i]=aiVectorKey(tick,outPos);
            channel->mScalingKeys[i]=aiVectorKey(tick,outScale);
            if(i && (channel->mRotationKeys[i-1].mValue.w*outRot.w+
               channel->mRotationKeys[i-1].mValue.x*outRot.x+channel->mRotationKeys[i-1].mValue.y*outRot.y+
               channel->mRotationKeys[i-1].mValue.z*outRot.z)<0)
                outRot=aiQuaternion(-outRot.w,-outRot.x,-outRot.y,-outRot.z);
            channel->mRotationKeys[i++]=aiQuatKey(tick,outRot);
            if(i==1) sourceNodes.at(op)->mTransformation=matrix;
        }
    }
    scene->mNumAnimations=1;scene->mAnimations=new aiAnimation*[1]{animation.release()};
}

// ------------------------------------------------------------------------------------------------
bool C4DImporter::ReadShader(aiMaterial* out, BaseShader* shader) {
    // based on Cineware sample code (C4DImportExport.cpp)
    while(shader) {
        if(shader->GetType() == Xlayer) {
            BaseContainer* container = shader->GetDataInstance();
            GeData blend = container->GetData(SLA_LAYER_BLEND);
            iBlendDataType* blend_list = reinterpret_cast<iBlendDataType*>(blend.GetCustomDataType(CUSTOMDATA_BLEND_LIST));
            if (!blend_list)
            {
                LogWarn("ignoring XLayer shader: no blend list given");
                shader = shader->GetNext();
                continue;
            }

            LayerShaderLayer *lsl = dynamic_cast<LayerShaderLayer*>(blend_list->m_BlendLayers.GetObject(0));

            // Ignore the actual layer blending - models for real-time rendering should not
            // use them in a non-trivial way. Just try to find textures that we can apply
            // to the model.
            while (lsl) {
                if (lsl->GetType() == TypeFolder) {
                    BlendFolder* const folder = dynamic_cast<BlendFolder*>(lsl);
                    LayerShaderLayer *subLsl = dynamic_cast<LayerShaderLayer*>(folder->m_Children.GetObject(0));

                    while (subLsl) {
                        if (subLsl->GetType() == TypeShader) {
                            BlendShader* const shader = dynamic_cast<BlendShader*>(subLsl);
                            if(ReadShader(out, static_cast<BaseShader*>(shader->m_pLink->GetLink()))) {
                                return true;
                            }
                        }

                        subLsl = subLsl->GetNext();
                    }
                } else if (lsl->GetType() == TypeShader) {
                    BlendShader* const shader = dynamic_cast<BlendShader*>(lsl);
                    if(ReadShader(out, static_cast<BaseShader*>(shader->m_pLink->GetLink()))) {
                        return true;
                    }
                }

                lsl = lsl->GetNext();
            }
        } else if ( shader->GetType() == Xbitmap ) {
            auto const path = aiStringFrom(shader->GetFileName().GetString());
            out->AddProperty(&path, AI_MATKEY_TEXTURE_DIFFUSE(0));
            return true;
        } else {
            LogWarn("ignoring shader type: ", GetObjectTypeName(shader->GetType()));
        }
        shader = shader->GetNext();
    }

    return false;
}

// ------------------------------------------------------------------------------------------------
void C4DImporter::ReadMaterials(BaseMaterial* mat) {
    // based on Cineware sample code
    while (mat) {
        if (mat->GetType() == Mmaterial) {
            aiMaterial* out = new aiMaterial();
            material_mapping[mat] = static_cast<unsigned int>(materials.size());
            materials.push_back(out);

            auto const ai_name = aiStringFrom(mat->GetName());
            out->AddProperty(&ai_name, AI_MATKEY_NAME);

            // Cineware exposes typed facade classes over BaseList2D nodes;
            // GetType(), not the C++ dynamic type, identifies the facade.
            Material& m = static_cast<Material&>(*mat);

            if (m.GetChannelState(CHANNEL_COLOR)) {
                GeData data;
                mat->GetParameter(MATERIAL_COLOR_COLOR, data);
                Vector color = data.GetVector();
                mat->GetParameter(MATERIAL_COLOR_BRIGHTNESS, data);
                const Float brightness = data.GetFloat();

                color *= brightness;

                aiVector3D v;
                v.x = color.x;
                v.y = color.y;
                v.z = color.z;
                out->AddProperty(&v, 1, AI_MATKEY_COLOR_DIFFUSE);
            }

            BaseShader* const shader = m.GetShader(MATERIAL_COLOR_SHADER);
            if(shader) {
                ReadShader(out, shader);
            }
        } else {
            LogWarn("ignoring plugin material: ", GetObjectTypeName(mat->GetType()));
        }
        mat = mat->GetNext();
    }
}

// ------------------------------------------------------------------------------------------------
void C4DImporter::RecurseHierarchy(BaseObject* object, aiNode* parent,
    std::vector<BaseObject*> materialOwners, unsigned int depth, bool consumed, bool cache) {
    ai_assert(parent != nullptr);
    if (depth > 256) ThrowException("object/cache hierarchy exceeds 256 levels");
    std::vector<std::unique_ptr<aiNode>> nodes;

    while (object) {
        if (!visitedObjects.insert(object).second)
            ThrowException("cyclic or multiply referenced object/cache hierarchy");
        if (visitedObjects.size() > 1000000)
            ThrowException("object/cache hierarchy exceeds 1000000 objects");
        const Int32 type = object->GetType();
        const auto name = aiStringFrom(object->GetName());
        const Matrix& ml = object->GetMl();
        std::unique_ptr<aiNode> owned(new aiNode());
        aiNode* const nd = owned.get();
        nd->mParent = parent;
        nd->mName = cache ? aiString(std::string(parent->mName.C_Str()) + "__cache_" +
            std::to_string(++cacheNodeId)) : name;
        if (!cache) sourceNodes[object] = nd;
        nd->mTransformation.a1 = ml.v1.x; nd->mTransformation.b1 = ml.v1.y; nd->mTransformation.c1 = ml.v1.z;
        nd->mTransformation.a2 = ml.v2.x; nd->mTransformation.b2 = ml.v2.y; nd->mTransformation.c2 = ml.v2.z;
        nd->mTransformation.a3 = ml.v3.x; nd->mTransformation.b3 = ml.v3.y; nd->mTransformation.c3 = ml.v3.z;
        nd->mTransformation.a4 = ml.off.x; nd->mTransformation.b4 = ml.off.y; nd->mTransformation.c4 = ml.off.z;
        for (unsigned int row = 0; row < 4; ++row)
            for (unsigned int col = 0; col < 4; ++col)
                if (!std::isfinite(nd->mTransformation[row][col]))
                    ThrowException("non-finite C4D object transform: ", name.C_Str());

        auto owners = materialOwners;
        owners.push_back(object);
        // Deform cache supersedes the generator cache and editable geometry.
        // Both can contain further caches/hierarchies, and the generator cache
        // can be a sibling list. Never emit the underlying polygon twice.
        BaseObject* evaluated = object->GetDeformCache();
        if (!evaluated) evaluated = object->GetCache();
        // A skin's saved cache is already deformed. Export its original points
        // and weight tag, otherwise the skin would be applied twice.
        if (object->GetTag(Tweights)) evaluated = nullptr;
        if (evaluated) {
            RecurseHierarchy(evaluated, nd, owners, depth + 1, false, true);
        } else if (type == Opolygon && (!object->GetBit(BIT_CONTROLOBJECT) || object->GetTag(Tweights))) {
            std::unique_ptr<aiMesh> mesh(ReadMesh(object));
            if (mesh) {
                const auto assignments = ResolveMaterials(static_cast<PolygonObject*>(object), owners);
                std::map<unsigned int, std::vector<unsigned int>> groups;
                for (unsigned int i = 0; i < mesh->mNumFaces; ++i) groups[assignments[i]].push_back(i);
                nd->mNumMeshes = static_cast<unsigned int>(groups.size());
                nd->mMeshes = new unsigned int[nd->mNumMeshes];
                if (groups.size() == 1) {
                    mesh->mMaterialIndex = groups.begin()->first;
                    nd->mMeshes[0] = static_cast<unsigned int>(meshes.size());
                    meshes.push_back(mesh.release());
                } else {
                    // Smooth on the connected geometry before material splitting.
                    if (!mesh->HasNormals()) {
                        GenVertexNormalsProcess generator;
                        generator.GenMeshVertexNormals(mesh.get(), 0);
                    }
                    unsigned int index = 0;
                    for (const auto& group : groups) {
                        std::unique_ptr<aiMesh> part(MakeSubmesh(mesh.get(), group.second, 0));
                        part->mMaterialIndex = group.first;
                        nd->mMeshes[index++] = static_cast<unsigned int>(meshes.size());
                        meshes.push_back(part.release());
                    }
                }
            }
        } else if (!consumed && !object->GetBit(BIT_CONTROLOBJECT) &&
                   type != Onull && type != Ocamera && type != Olight && type != Ojoint && type != Oskin) {
            ThrowException("missing saved polygon cache or unsupported C4D object/plugin: ",
                name.C_Str(), " (type ", type, "); save the evaluated scene for Cineware with its plugins installed, "
                "or make the object editable in Cinema 4D");
        }
        // Control children of a generator are still hierarchy nodes; their
        // geometry is excluded by BIT_CONTROLOBJECT. Unknown modifiers/splines
        // are only harmless when their parent has a saved evaluated cache.
        RecurseHierarchy(object->GetDown(), nd, owners, depth + 1, consumed || evaluated != nullptr, cache);
        nodes.push_back(std::move(owned));
        object = object->GetNext();
    }
    if (!nodes.empty()) {
        const unsigned int oldCount = parent->mNumChildren;
        auto** children = new aiNode*[oldCount + nodes.size()]();
        if (oldCount) std::copy(parent->mChildren, parent->mChildren + oldCount, children);
        for (size_t i = 0; i < nodes.size(); ++i) children[oldCount + i] = nodes[i].release();
        delete[] parent->mChildren;
        parent->mChildren = children;
        parent->mNumChildren = oldCount + static_cast<unsigned int>(nodes.size());
    }
}

// ------------------------------------------------------------------------------------------------
aiMesh* C4DImporter::ReadMesh(BaseObject* object) {
    ai_assert(object != nullptr);
    ai_assert( object->GetType() == Opolygon );

    // based on Cineware sample code
    // SDK object nodes are BaseObject instances with a checked type ID. A
    // dynamic_cast returns null even for a valid Opolygon saved by Cineware.
    PolygonObject* const polyObject = static_cast<PolygonObject*>(object);
    ai_assert(polyObject != nullptr);

    const Int32 pointCount = polyObject->GetPointCount();
    const Int32 polyCount = polyObject->GetPolygonCount();
    if(pointCount <= 0 || polyCount <= 0) {
        LogWarn("ignoring mesh with zero vertices or faces");
        return nullptr;
    }

    const Vector* points = polyObject->GetPointR();
    if (!points) ThrowException("missing polygon point data");

    const CPolygon* polys = polyObject->GetPolygonR();
    if (!polys) ThrowException("missing polygon face data");
    if (static_cast<uint64_t>(polyCount) * 4 > std::numeric_limits<unsigned int>::max())
        ThrowException("polygon corner count exceeds supported range");
    for (Int32 i = 0; i < pointCount; ++i)
        if (!std::isfinite(points[i].x) || !std::isfinite(points[i].y) || !std::isfinite(points[i].z))
            ThrowException("non-finite C4D polygon point: ", i);
    for (Int32 i = 0; i < polyCount; ++i)
        for (Int32 index : {polys[i].a, polys[i].b, polys[i].c, polys[i].d})
            if (index < 0 || index >= pointCount)
                ThrowException("C4D polygon point index out of range at polygon ", i);

    std::unique_ptr<aiMesh> mesh(new aiMesh());
    mesh->mName = aiStringFrom(object->GetName());
    mesh->mNumFaces = static_cast<unsigned int>(polyCount);
    aiFace* face = mesh->mFaces = new aiFace[mesh->mNumFaces]();

    mesh->mPrimitiveTypes = aiPrimitiveType_TRIANGLE;
    mesh->mMaterialIndex = 0;

    unsigned int vcount = 0;

    // first count vertices
    for (Int32 i = 0; i < polyCount; i++)
    {
        vcount += 3;

        // TODO: do we also need to handle lines or points with similar checks?
        if (polys[i].c != polys[i].d)
        {
            mesh->mPrimitiveTypes |= aiPrimitiveType_POLYGON;
            ++vcount;
        }
    }

    ai_assert(vcount > 0);

    mesh->mNumVertices = vcount;
    aiVector3D* verts = mesh->mVertices = new aiVector3D[mesh->mNumVertices];
    aiVector3D* normals, *uvs, *tangents, *bitangents;
    unsigned int n = 0;
    std::vector<unsigned int> sourcePoints;
    sourcePoints.reserve(vcount);

    // check if there are normals, tangents or UVW coordinates
    BaseTag* tag = object->GetTag(Tnormal);
    NormalTag* normals_src = nullptr;
    if(tag) {
        normals_src = static_cast<NormalTag*>(tag);
        if (normals_src->GetDataCount() != polyCount)
            ThrowException("C4D normal tag count does not match polygon count");
        normals = mesh->mNormals = new aiVector3D[mesh->mNumVertices]();
    }

    tag = object->GetTag(Ttangent);
    TangentTag* tangents_src = nullptr;
    if(tag) {
        tangents_src = static_cast<TangentTag*>(tag);
        if (tangents_src->GetDataCount() != pointCount)
            ThrowException("C4D tangent tag count does not match point count");
        tangents = mesh->mTangents = new aiVector3D[mesh->mNumVertices]();
        bitangents = mesh->mBitangents = new aiVector3D[mesh->mNumVertices]();
    }

    tag = object->GetTag(Tuvw);
    UVWTag* uvs_src = nullptr;
    if(tag) {
        uvs_src = static_cast<UVWTag*>(tag);
        if (uvs_src->GetDataCount() != polyCount)
            ThrowException("C4D UV tag count does not match polygon count");
        uvs = mesh->mTextureCoords[0] = new aiVector3D[mesh->mNumVertices]();
        mesh->mNumUVComponents[0] = 2;
    }

    // copy vertices and extra channels over and populate faces
    for (Int32 i = 0; i < polyCount; ++i, ++face) {
        ai_assert(polys[i].a < pointCount && polys[i].a >= 0);
        const Vector& pointA = points[polys[i].a];
        verts->x = pointA.x;
        verts->y = pointA.y;
        verts->z = pointA.z;
        ++verts;

        ai_assert(polys[i].b < pointCount && polys[i].b >= 0);
        const Vector& pointB = points[polys[i].b];
        verts->x = pointB.x;
        verts->y = pointB.y;
        verts->z = pointB.z;
        ++verts;

        ai_assert(polys[i].c < pointCount && polys[i].c >= 0);
        const Vector& pointC = points[polys[i].c];
        verts->x = pointC.x;
        verts->y = pointC.y;
        verts->z = pointC.z;
        ++verts;

        // TODO: do we also need to handle lines or points with similar checks?
        if (polys[i].c != polys[i].d) {
            ai_assert(polys[i].d < pointCount && polys[i].d >= 0);

            face->mNumIndices = 4;
            mesh->mPrimitiveTypes |= aiPrimitiveType_POLYGON;
            const Vector& pointD = points[polys[i].d];
            verts->x = pointD.x;
            verts->y = pointD.y;
            verts->z = pointD.z;
            ++verts;
        } else {
            face->mNumIndices = 3;
        }
        face->mIndices = new unsigned int[face->mNumIndices];
        for(unsigned int j = 0; j < face->mNumIndices; ++j) {
            face->mIndices[j] = n++;
            const Int32 corners[] = {polys[i].a,polys[i].b,polys[i].c,polys[i].d};
            sourcePoints.push_back(static_cast<unsigned int>(corners[j]));
        }

        // copy normals
        if (normals_src) {
            if(i >= normals_src->GetDataCount()) {
                LogError("unexpected number of normals, ignoring");
            } else {
                ConstNormalHandle normal_handle = normals_src->GetDataAddressR();
                NormalStruct nor;
                NormalTag::Get(normal_handle, i, nor);
                normals->x = nor.a.x;
                normals->y = nor.a.y;
                normals->z = nor.a.z;
                ++normals;

                normals->x = nor.b.x;
                normals->y = nor.b.y;
                normals->z = nor.b.z;
                ++normals;

                normals->x = nor.c.x;
                normals->y = nor.c.y;
                normals->z = nor.c.z;
                ++normals;

                if(face->mNumIndices == 4) {
                    normals->x = nor.d.x;
                    normals->y = nor.d.y;
                    normals->z = nor.d.z;
                    ++normals;
                }
            }
        }

        // copy tangents and bitangents
        if (tangents_src) {

            for(unsigned int k = 0; k < face->mNumIndices; ++k) {
                Int32 l;
                switch(k) {
                case 0:
                    l = polys[i].a;
                    break;
                case 1:
                    l = polys[i].b;
                    break;
                case 2:
                    l = polys[i].c;
                    break;
                case 3:
                    l = polys[i].d;
                    break;
                default:
                    ai_assert(false);
                }
                if(l >= tangents_src->GetDataCount()) {
                    LogError("unexpected number of tangents, ignoring");
                    break;
                }

                Tangent tan = tangents_src->GetDataR()[l];
                tangents->x = tan.vl.x;
                tangents->y = tan.vl.y;
                tangents->z = tan.vl.z;
                ++tangents;

                bitangents->x = tan.vr.x;
                bitangents->y = tan.vr.y;
                bitangents->z = tan.vr.z;
                ++bitangents;
            }
        }

        // copy UVs
        if (uvs_src) {
            if(i >= uvs_src->GetDataCount()) {
                LogError("unexpected number of UV coordinates, ignoring");
            }
            else {
                UVWStruct uvw;
                uvs_src->Get(uvs_src->GetDataAddressR(),i,uvw);

                uvs->x = uvw.a.x;
                uvs->y = 1.0f-uvw.a.y;
                uvs->z = uvw.a.z;
                ++uvs;

                uvs->x = uvw.b.x;
                uvs->y = 1.0f-uvw.b.y;
                uvs->z = uvw.b.z;
                ++uvs;

                uvs->x = uvw.c.x;
                uvs->y = 1.0f-uvw.c.y;
                uvs->z = uvw.c.z;
                ++uvs;

                if(face->mNumIndices == 4) {
                    uvs->x = uvw.d.x;
                    uvs->y = 1.0f-uvw.d.y;
                    uvs->z = uvw.d.z;
                    ++uvs;
                }
            }
        }
    }

    ReadSkin(object, mesh.get(), sourcePoints);
    return mesh.release();
}

// ------------------------------------------------------------------------------------------------
std::vector<unsigned int> C4DImporter::ResolveMaterials(PolygonObject* obj,
    const std::vector<BaseObject*>& owners) {
    ai_assert(obj != nullptr);
    const unsigned int mat_count = static_cast<unsigned int>(materials.size());
    std::vector<unsigned int> result(obj->GetPolygonCount(), mat_count);
    // Texture tags are ordered layers. For this static, single-material-per-face
    // import the last applicable tag wins. A nonempty restriction refers to a
    // named polygon-selection tag; a missing selection must not paint the mesh.
    for (BaseObject* owner : owners) {
    for (BaseTag* tag = owner->GetFirstTag(); tag; tag = tag->GetNext()) {
        if (tag->GetType() != Ttexture) continue;
        TextureTag& texture = static_cast<TextureTag&>(*tag);
        const auto material = material_mapping.find(texture.GetMaterial());
        if (material == material_mapping.end()) continue;
        const String restriction = tag->GetDataInstance()->GetString(TEXTURETAG_RESTRICTION);
        BaseSelect* selected = nullptr;
        if (restriction.GetLength()) {
            for (BaseTag* candidate = obj->GetFirstTag(); candidate; candidate = candidate->GetNext()) {
                if (candidate->GetType() == Tpolygonselection && candidate->GetName() == restriction) {
                    selected = static_cast<SelectionTag*>(candidate)->GetBaseSelect();
                    break;
                }
            }
            if (!selected) {
                LogWarn("ignoring texture tag with missing polygon selection: ", aiStringFrom(restriction).C_Str());
                continue;
            }
        }
        for (unsigned int face = 0; face < result.size(); ++face)
            if (!selected || selected->IsSelected(static_cast<Int32>(face))) result[face] = material->second;
    }
    }
    return result;
}

#endif // ASSIMP_BUILD_NO_C4D_IMPORTER
