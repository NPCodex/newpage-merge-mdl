#pragma once
#include <memory>
#include <string>
struct aiScene;
namespace pulse::source {
std::shared_ptr<aiScene> LoadFastGltfScene(const std::string& path,float sampleRate,bool bakeWeights=false);
}
