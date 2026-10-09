#pragma once
#include "source.h"
#include "meshedit.h"
namespace pulse::source {
// Actual importer registry of this binary (native readers and Assimp plugins).
std::string SceneImportFormats();
// Assimp import is intentionally separate from the existing FBX reader.
bool LoadSceneSource(const std::string& path, Source& out, MaterialTable& mats,
                     float scale, std::string* err, bool morphSource,
                     MeshFilter* filter, bool animOnly, const SceneOptions& options);
}
