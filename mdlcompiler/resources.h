#pragma once
#include <filesystem>
#include <string>
namespace pulse::resources {
bool Initialize(const std::string& gameDirectory,const std::string& steamDirectory,std::string* err);
std::filesystem::path Find(const std::filesystem::path& relative);
void EnableContentSearch();
void Print();
}
