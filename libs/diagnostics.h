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
// Decode only the loader's explicit quoted path + repeated path:line prefix.
// This keeps the QC call site while exposing the actual malformed source line;
// arbitrary numbers or words elsewhere in a message never become locations.
inline std::pair<std::string, unsigned> LoadedSourceLocation(const std::string& message) {
    const std::string marker = "cannot load \"";
    const auto start = message.find(marker);
    if (start == std::string::npos) return {{}, 0};
    const auto begin = start + marker.size(), end = message.find("\": ", begin);
    if (end == std::string::npos) return {{}, 0};
    const auto path = message.substr(begin, end - begin);
    if (path.empty()) return {{}, 0};
    const auto repeated = end + 3;
    if (message.compare(repeated, path.size() + 1, path + ":") != 0) return {{}, 0};
    size_t at = repeated + path.size() + 1;
    const size_t digits = at;
    unsigned line = 0;
    for (; at < message.size() && message[at] >= '0' && message[at] <= '9'; ++at) {
        const unsigned digit = unsigned(message[at] - '0');
        if (line > (2147483647u - digit) / 10u) return {{}, 0};
        line = line * 10u + digit;
    }
    if (at == digits || !line || message.compare(at, 2, ": ") != 0) return {{}, 0};
    return {path, line};
}
inline void Error(const char* category, const char* stage, const std::string& message) {
    if (enabled) entries.push_back({LoadedSourceLocation(message).second ? "NP1101" : Code(category), "error", stage, message});
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
        const auto loaded = LoadedSourceLocation(e.message);
        text += "{\"code\":" + Json(e.code) + ",\"severity\":" + Json(e.severity) +
            ",\"stage\":" + Json(e.stage) + ",\"source\":" + Json(location.first) +
            ",\"line\":" + (location.second ? std::to_string(location.second) : "null") +
            ",\"message\":" + Json(e.message) + ",\"related_locations\":[";
        if (loaded.second) text += "{\"source\":" + Json(loaded.first) + ",\"line\":" + std::to_string(loaded.second) + "}";
        text += "],\"hint\":";
        if (loaded.second) text += Json("Correct the named field at the related source line, or re-export that source file; the primary location is the QC command that loaded it.");
        else if (e.code == "NP1200") text += Json("Use -game with the actual target game directory containing gameinfo.txt; check its mounted search paths.");
        else if (e.code == "NP1401") text += Json("Keep the recovery journal and backups. Resolve the reported external file conflict before retrying the same output.");
        else if (e.code == "NP1402") text += Json("Choose a writable report path separate from source files, their dependencies and all model output files.");
        else text += "null";
        text += "}";
    }
    text += "]}\n";
    std::fputs(text.c_str(), stdout);
}
}
