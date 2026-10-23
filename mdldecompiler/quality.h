#pragma once
#include <algorithm>
#include <filesystem>
#include <set>
#include <string>
#include <vector>
#include "diagnostics.h"

namespace mdldecompiler {
struct QualityReport {
    bool enabled = false, assetsOnly = false;
    std::string source, destination, staging;
    std::vector<std::string> warnings, errors, unsupported, recovered, missingDependencies;
    std::vector<std::pair<std::string, std::string>> renamedBones;
    std::set<std::string> files;
};
inline QualityReport g_quality;
inline void QualityWarning(const std::string& message, bool unsupported = false) {
    if (!g_quality.enabled) return;
    auto& list = unsupported ? g_quality.unsupported : g_quality.warnings;
    if (std::find(list.begin(), list.end(), message) == list.end()) list.push_back(message);
}
inline void QualityWritten(const std::string& path) {
    if (!g_quality.enabled) return;
    const auto rel = std::filesystem::path(path).lexically_relative(g_quality.staging);
    if (!rel.empty()) g_quality.files.insert(rel.generic_u8string());
}
inline std::string QualityJson(int result, const char* version) {
    using pulse::diagnostics::Json;
    const auto array = [](const auto& values) {
        std::string s = "[";
        for (const auto& value : values) { if (s.size() > 1) s += ','; s += Json(value); }
        return s + ']';
    };
    std::string renamed = "[";
    for (const auto& pair : g_quality.renamedBones) {
        if (renamed.size() > 1) renamed += ',';
        std::string bytes;
        constexpr char hex[] = "0123456789abcdef";
        for (unsigned char value : pair.first) { bytes += hex[value >> 4]; bytes += hex[value & 15]; }
        renamed += "{\"original_bytes_hex\":" + Json(bytes) + ",\"exported\":" + Json(pair.second) + '}';
    }
    renamed += ']';
    // Staged writes on failure never become a published successful export.
    return "{\"schema\":1,\"tool_version\":" + Json(version) +
        ",\"source\":" + Json(g_quality.source) + ",\"destination\":" + Json(g_quality.destination) +
        ",\"success\":" + (result ? "false" : "true") + ",\"exit_code\":" + std::to_string(result) +
        ",\"export_kind\":" + Json(g_quality.assetsOnly ? "assets_only" : "project") +
        ",\"warnings\":" + array(g_quality.warnings) + ",\"errors\":" + array(g_quality.errors) +
        ",\"unsupported_content\":" + array(g_quality.unsupported) + ",\"recovered\":" + array(g_quality.recovered) +
        ",\"missing_dependencies\":" + array(g_quality.missingDependencies) + ",\"renamed_bones\":" + renamed +
        ",\"written_files\":" + (result ? "[]" : array(g_quality.files)) +
        ",\"requires_external_game_validation\":true}";
}
}
