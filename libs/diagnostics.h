#pragma once
#include <cstdio>
#include <string>
#include <vector>

namespace pulse::diagnostics {
inline bool enabled = false;
inline std::string source;
struct Entry { std::string code, severity, stage, message; };
inline std::vector<Entry> entries;
inline std::string Json(const std::string& value) {
    std::string result = "\"";
    for (const unsigned char c : value) {
        if (c == '"' || c == '\\') { result += '\\'; result += char(c); }
        else if (c < 32) { char escaped[7]; std::snprintf(escaped, sizeof escaped, "\\u%04x", c); result += escaped; }
        else result += char(c);
    }
    return result + '"';
}
inline const char* Code(const std::string& category) {
    if (category == "bad option" || category == "bad defaults" || category == "unsupported script") return "NP1001";
    if (category == "script error") return "NP1100";
    if (category == "mount error") return "NP1200";
    if (category == "compile error") return "NP1300";
    if (category == "write error") return "NP1400";
    if (category == "output recovery error") return "NP1401";
    if (category == "metrics error" || category == "dependency report error") return "NP1402";
    if (category == "sequence remapping error") return "NP1500";
    if (category == "out of memory") return "NP9001";
    return "NP9000";
}
inline void Error(const char* category, const char* stage, const std::string& message) {
    if (enabled) entries.push_back({Code(category), "error", stage, message});
}
inline void Warning(const char* code, const char* stage, const std::string& message) {
    if (enabled) entries.push_back({code, "warning", stage, message});
}
// QC diagnostics carry an exact file(line): prefix, including nested .qci
// files. Preserve this source location; do not invent lines for other errors.
inline std::pair<std::string, unsigned> Location(const std::string& message) {
    const auto end = message.find("): ");
    if (end != std::string::npos) {
        const auto begin = message.rfind('(', end);
        if (begin != std::string::npos && begin > 0 && begin + 1 < end) {
            unsigned line = 0;
            for (size_t i = begin + 1; i < end; ++i) {
                const auto c = message[i];
                if (c < '0' || c > '9' || line > 214748363u) return {source, 0};
                line = line * 10 + unsigned(c - '0');
            }
            if (line) return {message.substr(0, begin), line};
        }
    }
    return {source, 0};
}
inline void Emit(int result, const char* version) {
    if (!enabled) return;
    if (result && entries.empty()) entries.push_back({"NP1001", "error", "command line", "Missing or invalid command-line arguments"});
    std::string text = "@diagnostic {\"schema\":1,\"version\":" + Json(version) +
        ",\"source\":" + Json(source) + ",\"success\":" + (result ? "false" : "true") +
        ",\"exit_code\":" + std::to_string(result) + ",\"diagnostics\":[";
    bool first = true;
    for (const auto& e : entries) {
        if (!first) text += ',';
        first = false;
        const auto location = Location(e.message);
        text += "{\"code\":" + Json(e.code) + ",\"severity\":" + Json(e.severity) +
            ",\"stage\":" + Json(e.stage) + ",\"source\":" + Json(location.first) +
            ",\"line\":" + (location.second ? std::to_string(location.second) : "null") +
            ",\"message\":" + Json(e.message) + "}";
    }
    text += "]}\n";
    std::fputs(text.c_str(), stdout);
}
}
