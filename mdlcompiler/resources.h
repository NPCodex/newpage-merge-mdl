#pragma once
#include <filesystem>
#include <string>
#include <vector>
#include <optional>
namespace pulse::resources {
// ++ defaults: gameinfo Tools/studiomdl, then cfg/commandline.cfg/QC stem.
// Explicit launch arguments are appended by main and take precedence.
bool LaunchDefaults(const std::string& gameDirectory,const std::string& script,
                    std::vector<std::string>& arguments,std::string* err);
bool Initialize(const std::string& gameDirectory,const std::string& steamDirectory,std::string* err);
std::filesystem::path Find(const std::filesystem::path& relative);
void EnableContentSearch();
int TargetVtxFormat(); // -1 if no recognized target AppID
bool IsCsgoTarget();
// Missing materials/client shaders are normal. Malformed VMTs are diagnosed.
std::optional<std::string> MaterialClientShader(const std::string& material,
                                               const std::vector<std::string>& directories);
void Print();
}
