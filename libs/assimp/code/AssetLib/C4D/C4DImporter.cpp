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

    // first convert all materials
    ReadMaterials(doc->GetFirstMaterial());

    // process C4D scene-graph recursively
    try {
        RecurseHierarchy(doc->GetFirstObject(), pScene->mRootNode);
    } catch(...) {
        for(aiMesh* mesh : meshes) {
            delete mesh;
        }
        BaseDocument::Free(doc);
        throw;
    }
    BaseDocument::Free(doc);

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
void C4DImporter::RecurseHierarchy(BaseObject* object, aiNode* parent) {
    ai_assert(parent != nullptr );
    std::vector<aiNode*> nodes;

    // based on Cineware sample code
    while (object) {
        const Int32 type = object->GetType();
        const Matrix& ml = object->GetMl();

        aiNode* const nd = new aiNode();

        nd->mParent = parent;
        nd->mName = aiStringFrom(object->GetName());

        nd->mTransformation.a1 = ml.v1.x;
        nd->mTransformation.b1 = ml.v1.y;
        nd->mTransformation.c1 = ml.v1.z;

        nd->mTransformation.a2 = ml.v2.x;
        nd->mTransformation.b2 = ml.v2.y;
        nd->mTransformation.c2 = ml.v2.z;

        nd->mTransformation.a3 = ml.v3.x;
        nd->mTransformation.b3 = ml.v3.y;
        nd->mTransformation.c3 = ml.v3.z;

        nd->mTransformation.a4 = ml.off.x;
        nd->mTransformation.b4 = ml.off.y;
        nd->mTransformation.c4 = ml.off.z;

        nodes.push_back(nd);

        GeData data;
        if (type == Ocamera) {
            object->GetParameter(CAMERAOBJECT_FOV, data);
            // TODO: read camera
        } else if (type == Olight) {
            // TODO: read light
        } else if (type == Opolygon) {
            std::unique_ptr<aiMesh> mesh(ReadMesh(object));
            if(mesh) {
                const auto assignments = ResolveMaterials(static_cast<PolygonObject*>(object));
                std::map<unsigned int, std::vector<unsigned int>> groups;
                for (unsigned int i = 0; i < mesh->mNumFaces; ++i) groups[assignments[i]].push_back(i);
                nd->mNumMeshes = static_cast<unsigned int>(groups.size());
                nd->mMeshes = new unsigned int[nd->mNumMeshes];
                if (groups.size() == 1) {
                    mesh->mMaterialIndex = groups.begin()->first;
                    nd->mMeshes[0] = static_cast<unsigned int>(meshes.size());
                    meshes.push_back(mesh.release());
                } else {
                    // Generate missing smooth normals on the original connected
                    // mesh. Generating them after splitting would create hard
                    // seams solely because neighboring faces use different materials.
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
        } else {
            LogWarn("ignoring object type: ", type);
        }

        RecurseHierarchy(object->GetDown(), nd);
        object = object->GetNext();
    }

    // copy nodes over to parent
    parent->mNumChildren = static_cast<unsigned int>(nodes.size());
    if (parent->mNumChildren) {
        parent->mChildren = new aiNode*[parent->mNumChildren]();
        std::copy(nodes.begin(), nodes.end(), parent->mChildren);
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
    ai_assert(points != nullptr);

    const CPolygon* polys = polyObject->GetPolygonR();
    ai_assert(polys != nullptr);

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

    // check if there are normals, tangents or UVW coordinates
    BaseTag* tag = object->GetTag(Tnormal);
    NormalTag* normals_src = nullptr;
    if(tag) {
        normals_src = static_cast<NormalTag*>(tag);
        normals = mesh->mNormals = new aiVector3D[mesh->mNumVertices]();
    }

    tag = object->GetTag(Ttangent);
    TangentTag* tangents_src = nullptr;
    if(tag) {
        tangents_src = static_cast<TangentTag*>(tag);
        tangents = mesh->mTangents = new aiVector3D[mesh->mNumVertices]();
        bitangents = mesh->mBitangents = new aiVector3D[mesh->mNumVertices]();
    }

    tag = object->GetTag(Tuvw);
    UVWTag* uvs_src = nullptr;
    if(tag) {
        uvs_src = static_cast<UVWTag*>(tag);
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

    return mesh.release();
}

// ------------------------------------------------------------------------------------------------
std::vector<unsigned int> C4DImporter::ResolveMaterials(PolygonObject* obj) {
    ai_assert(obj != nullptr);
    const unsigned int mat_count = static_cast<unsigned int>(materials.size());
    std::vector<unsigned int> result(obj->GetPolygonCount(), mat_count);
    // Texture tags are ordered layers. For this static, single-material-per-face
    // import the last applicable tag wins. A nonempty restriction refers to a
    // named polygon-selection tag; a missing selection must not paint the mesh.
    for (BaseTag* tag = obj->GetFirstTag(); tag; tag = tag->GetNext()) {
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
    return result;
}

#endif // ASSIMP_BUILD_NO_C4D_IMPORTER
