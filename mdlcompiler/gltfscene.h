#pragma once
#include <memory>
#include <string>
struct aiScene;
namespace pulse::source {
bool GltfHasInstancing(const std::string& path);
std::shared_ptr<aiScene> LoadFastGltfScene(const std::string& path,float sampleRate,bool bakeWeights=false,
                                       bool animationsOnly=false,bool nativeNodeNames=false);
}
