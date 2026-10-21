#pragma once
#include "source.h"
#include "meshedit.h"
namespace pulse::source {
// aiScene payload estimates exclude allocator overhead and transient importer
// allocations. Keep these distinct from the process peak working set.
struct SceneCacheStats {
    uint64_t hits=0, misses=0, evictions=0, stale=0, bypasses=0;
    uint64_t retainedBytes=0, peakRetainedBytes=0, budgetBytes=256ull*1024*1024;
    uint64_t geometryImports=0, geometryReuses=0, peakEntries=0;
    double importSeconds=0;
};
void BeginSceneImportSession();
void EndSceneImportSession();
void SetSceneCacheBudgetMiB(unsigned mib);
SceneCacheStats GetSceneCacheStats();
// Actual importer registry of this binary (native readers and Assimp plugins).
std::string SceneImportFormats();
// Assimp import is intentionally separate from the existing FBX reader.
bool LoadSceneSource(const std::string& path, Source& out, MaterialTable& mats,
                     float scale, std::string* err, bool morphSource,
                     MeshFilter* filter, bool animOnly, const SceneOptions& options);
}
