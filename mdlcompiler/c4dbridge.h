#pragma once
#include <filesystem>
#include <string>
namespace pulse::source {
// Owns exactly one conversion output and its exclusively created directory.
struct TemporaryC4dScene {
    std::filesystem::path path;
    TemporaryC4dScene()=default;
    TemporaryC4dScene(const TemporaryC4dScene&)=delete;
    TemporaryC4dScene& operator=(const TemporaryC4dScene&)=delete;
    ~TemporaryC4dScene();
};
void ConvertC4dScene(const std::string& input,TemporaryC4dScene& result);
bool HasC4dBridge();
}
