#include <assimp/Importer.hpp>
#include <assimp/Exporter.hpp>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <cstdio>
#include <filesystem>

int wmain(int argc,wchar_t** argv) {
    if(argc!=3){std::fprintf(stderr,"usage: NewPageMergeMDL-C4D <input.c4d> <output.glb>\nImports static polygons and saved evaluated caches through Cineware 22.\nAnimated objects and skin weights require an FBX/glTF export from Cinema 4D.\n");return 2;}
    const std::filesystem::path input=argv[1],output=argv[2];
    try {
        if(std::filesystem::exists(output)){std::fprintf(stderr,"Refusing to overwrite an existing converted scene.\n");return 2;}
        Assimp::Importer importer;
        std::fprintf(stderr,"Cineware: reading static scene\n");
        const aiScene* scene=importer.ReadFile(input.u8string(),aiProcess_Triangulate|aiProcess_GenSmoothNormals|aiProcess_ValidateDataStructure);
        if(!scene){std::fprintf(stderr,"Cineware import: %s\n",importer.GetErrorString());return 1;}
        if(!scene->mNumMeshes){std::fprintf(stderr,"Cineware import: no polygon geometry or saved evaluated caches; save for Cineware or make objects editable in Cinema 4D.\n");return 1;}
        Assimp::Exporter exporter;
        std::fprintf(stderr,"Cineware: exporting %u meshes\n",scene->mNumMeshes);
        if(exporter.Export(scene,"glb2",output.u8string())!=aiReturn_SUCCESS){
            std::fprintf(stderr,"GLB export: %s\n",exporter.GetErrorString());
            std::error_code ec;std::filesystem::remove(output,ec);return 1;
        }
        std::printf("Cineware static scene: %u meshes, %u materials\n",scene->mNumMeshes,scene->mNumMaterials);return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"Cineware bridge: %s\n",e.what());return 1;}
}
