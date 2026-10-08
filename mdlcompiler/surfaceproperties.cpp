#include "surfaceproperties.h"

#include "compile.h"
#include "dependencies.h"
#include "pathcompat.h"
#include "resources.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace pulse::surfaceproperties {
namespace {

std::string Lower(std::string value) {
    for (char& c : value) c = char(std::tolower(static_cast<unsigned char>(c)));
    return value;
}

struct KeyValue {
    std::string key, value;
    std::vector<KeyValue> children;
    bool block = false;
};

std::vector<std::string> Tokenize(const std::string& text) {
    std::vector<std::string> tokens;
    size_t i = text.compare(0, 3, "\xef\xbb\xbf") == 0 ? 3 : 0;
    while (i < text.size()) {
        if (std::isspace(static_cast<unsigned char>(text[i]))) { ++i; continue; }
        if (text.compare(i, 2, "//") == 0) {
            while (i < text.size() && text[i] != '\n') ++i;
            continue;
        }
        if (text.compare(i, 2, "/*") == 0) {
            const size_t end = text.find("*/", i + 2);
            if (end == std::string::npos) throw std::runtime_error("unterminated comment");
            i = end + 2;
            continue;
        }
        if (text[i] == '{' || text[i] == '}') {
            tokens.push_back(text.substr(i++, 1));
            continue;
        }
        std::string token;
        if (text[i] == '"') {
            ++i;
            while (i < text.size() && text[i] != '"') {
                if (text[i] == '\\' && i + 1 < text.size() &&
                    (text[i + 1] == '"' || text[i + 1] == '\\')) ++i;
                token += text[i++];
            }
            if (i == text.size()) throw std::runtime_error("unterminated quoted string");
            ++i;
        } else {
            while (i < text.size() && !std::isspace(static_cast<unsigned char>(text[i])) &&
                   text[i] != '{' && text[i] != '}') token += text[i++];
        }
        tokens.push_back(std::move(token));
    }
    return tokens;
}

std::vector<KeyValue> Parse(const std::vector<std::string>& tokens, size_t& i,
                            bool nested = false, int depth = 0) {
    if (depth > 64) throw std::runtime_error("KeyValues nesting limit exceeded");
    std::vector<KeyValue> nodes;
    while (i < tokens.size() && tokens[i] != "}") {
        KeyValue node;
        node.key = tokens[i++];
        if (node.key == "{" || i == tokens.size() || tokens[i] == "}")
            throw std::runtime_error("missing value for '" + node.key + "'");
        if (tokens[i] == "{") {
            ++i;
            node.block = true;
            node.children = Parse(tokens, i, true, depth + 1);
        } else node.value = tokens[i++];
        bool enabled = true;
        if (i < tokens.size() && !tokens[i].empty() && tokens[i][0] == '[') {
            const auto condition = Lower(tokens[i++]);
#ifdef _WIN32
            enabled = condition != "[$linux]" && condition != "[$posix]";
#else
            enabled = condition != "[$win32]" && condition != "[$windows]";
#endif
        }
        if (enabled) nodes.push_back(std::move(node));
    }
    if (nested) {
        if (i == tokens.size()) throw std::runtime_error("missing closing brace");
        ++i;
    }
    return nodes;
}

std::vector<KeyValue> Read(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("cannot read " + path.string());
    std::ostringstream buffer;
    buffer << file.rdbuf();
    auto tokens = Tokenize(buffer.str());
    size_t cursor = 0;
    auto nodes = Parse(tokens, cursor);
    if (cursor != tokens.size()) throw std::runtime_error("unexpected closing brace");
    dependencies::Note(path.string());
    return nodes;
}

struct Properties {
    // Conventional Source default surface when no game definition is available.
    // This fallback is diagnosed; it is not a replacement for game-specific data.
    double density = 2000.0; // kg / m^3
    double thickness = -1.0; // inches; nonpositive means a solid volume
};

struct Definition {
    std::vector<KeyValue> values;
    std::string file;
};

class SurfaceTable {
public:
    void Load() {
        const auto manifest = resources::Find(FilePath("scripts/surfaceproperties_manifest.txt"));
        if (manifest.empty()) {
            std::fprintf(stderr, "WARNING: $automass: surfaceproperties_manifest.txt not found; "
                         "using default density 2000 kg/m^3 and solid volume\n");
            return;
        }
        const auto roots = Read(manifest);
        const KeyValue* root = nullptr;
        for (const auto& node : roots)
            if (Lower(node.key) == "surfaceproperties_manifest" && node.block) { root = &node; break; }
        if (!root) throw std::runtime_error("invalid surfaceproperties manifest: " + manifest.string());
        std::set<std::string> loaded;
        for (const auto& entry : root->children) {
            if (Lower(entry.key) != "file" || entry.block) continue;
            const auto logical = FilePath(entry.value);
            if (!loaded.insert(Lower(logical.generic_string())).second) continue;
            const auto path = resources::Find(logical);
            if (path.empty()) {
                std::fprintf(stderr, "WARNING: $automass: surface properties file '%s' not found\n",
                             entry.value.c_str());
                continue;
            }
            for (auto& node : Read(path)) {
                if (!node.block) continue;
                // The shipped manifest specifies that later definitions override
                // earlier properties. Keep omitted values from the earlier layer.
                auto& definition = definitions[Lower(node.key)];
                for (auto& value : node.children)
                    definition.values.push_back(std::move(value));
                definition.file = entry.value;
            }
        }
    }

    Properties Get(const std::string& name) {
        const auto key = Lower(name);
        if (definitions.count(key)) return Resolve(key, 0);
        if (key != "default" && warned.insert(key).second)
            std::fprintf(stderr, "WARNING: $automass: unknown surface '%s'; using default\n", name.c_str());
        return Resolve("default", 0);
    }

private:
    double Number(const std::string& text, const std::string& key, const Definition& def) {
        char* end = nullptr;
        const double value = std::strtod(text.c_str(), &end);
        const bool parsed = end != text.c_str();
        while (end && std::isspace(static_cast<unsigned char>(*end))) ++end;
        if (!parsed || !end || *end || !std::isfinite(value) ||
            (key == "density" && value < 0))
            throw std::runtime_error("invalid " + key + " in " + def.file + ": '" + text + "'");
        return value;
    }

    Properties Resolve(const std::string& name, int depth) {
        if (depth > 64) throw std::runtime_error("surface base inheritance limit exceeded");
        if (auto cached = resolved.find(name); cached != resolved.end()) return cached->second;
        if (!resolving.insert(name).second)
            throw std::runtime_error("surface base inheritance cycle at '" + name + "'");
        Properties result;
        const auto found = definitions.find(name);
        if (found != definitions.end()) {
            const auto& def = found->second;
            std::string base = name == "default" ? "" : "default";
            for (const auto& value : def.values)
                if (!value.block && Lower(value.key) == "base") base = Lower(value.value);
            if (!base.empty()) {
                if (base != "default" && !definitions.count(base) && warned.insert(base).second)
                    std::fprintf(stderr, "WARNING: $automass: unknown base surface '%s'; using default\n", base.c_str());
                result = Resolve(definitions.count(base) ? base : "default", depth + 1);
            }
            for (const auto& value : def.values) {
                if (value.block) continue;
                const auto key = Lower(value.key);
                if (key == "density") result.density = Number(value.value, key, def);
                else if (key == "thickness") result.thickness = Number(value.value, key, def);
            }
        }
        resolving.erase(name);
        resolved.emplace(name, result);
        return result;
    }

    std::map<std::string, Definition> definitions;
    std::map<std::string, Properties> resolved;
    std::set<std::string> resolving, warned;
};

} // namespace

bool ResolvePhysicsMass(compile::CompiledModel& model, bool automatic, std::string* err) {
    if (model.physSolids.empty()) return true;
    try {
        SurfaceTable surfaces;
        if (automatic) surfaces.Load();
        double totalMass = automatic ? 0.0 : model.physTotalMass;
        double weightedVolume = 0.0;
        constexpr double cubicMetersPerCubicInch = 0.0254 * 0.0254 * 0.0254;
        for (auto& solid : model.physSolids) {
            if (!std::isfinite(solid.volume) || solid.volume < 0 ||
                !std::isfinite(solid.massBias) || solid.massBias <= 0)
                throw std::runtime_error("collision volume or mass bias is not representable for solid '" + solid.name + "'");
            solid.surfaceprop = model.surfaceprop;
            if (solid.bone >= 0 && solid.bone < static_cast<int>(model.bones.size()) &&
                !model.bones[solid.bone].surfaceprop.empty())
                solid.surfaceprop = model.bones[solid.bone].surfaceprop;
            weightedVolume += static_cast<double>(solid.volume) * solid.massBias;
            if (automatic) {
                const auto props = surfaces.Get(solid.surfaceprop);
                if (!std::isfinite(solid.surfaceArea) || solid.surfaceArea < 0)
                    throw std::runtime_error("invalid collision surface area for solid '" + solid.name + "'");
                // CJointedModel::ComputeMass sums the material-derived masses.
                // Thickness remains in inches, so both branches convert in^3.
                const double volume = props.thickness > 0 ?
                    static_cast<double>(solid.surfaceArea) * props.thickness : solid.volume;
                totalMass += volume * cubicMetersPerCubicInch * props.density;
            }
        }
        if (!std::isfinite(totalMass) || totalMass < 0 || totalMass > std::numeric_limits<float>::max())
            throw std::runtime_error("collision total mass is not representable");
        model.physTotalMass = static_cast<float>(totalMass);
        if (weightedVolume <= 0) weightedVolume = 1.0;
        for (auto& solid : model.physSolids) {
            // Reference CollisionModel_Write distributes even automatic total
            // mass by volume * massbias, then floors each individual body at 1 kg.
            solid.mass = std::max(1.0f, static_cast<float>(
                static_cast<double>(solid.volume) * solid.massBias / weightedVolume * model.physTotalMass));
        }
        if (automatic) std::printf("Computed Mass: %.2f kg\n", model.physTotalMass);
        return true;
    } catch (const std::exception& e) {
        if (err) *err = "physics mass: " + std::string(e.what());
        return false;
    }
}

} // namespace pulse::surfaceproperties
