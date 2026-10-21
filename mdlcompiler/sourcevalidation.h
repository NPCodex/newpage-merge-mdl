#pragma once

#include "source.h"
#include "strcompat.h"
#include <map>

namespace pulse::source {

// Match FindSourceAnim/FindGlobalBone exactly. Validation belongs to each
// individual imported source: matching bones across separate sources are how
// meshes and animation files intentionally share a rig.
struct SourceNameLess {
    bool operator()(const std::string& a, const std::string& b) const {
        return _stricmp(a.c_str(), b.c_str()) < 0;
    }
};

class SourceNameRegistry {
    const bool animation;
    std::map<std::string, size_t, SourceNameLess> names;
public:
    explicit SourceNameRegistry(bool animationNames) : animation(animationNames) {}
    bool Add(const std::string& name, std::string* error) {
        const auto found = names.emplace(name, names.size());
        if (name.find('\0') == std::string::npos && found.second) return true;
        if (error) {
            *error = animation ? "duplicate or reserved animation name (case-insensitive) '"
                               : "ambiguous source bone name (case-insensitive) '";
            *error += name + "'";
            if (!found.second) *error += " conflicts with '" + found.first->first + "'";
            else *error += " contains a NUL byte";
        }
        return false;
    }
};

inline bool ValidateSourceBoneNames(const Source& source, std::string* error) {
    SourceNameRegistry names(false);
    for (const auto& bone : source.localBone) {
        // Sparse SMD node numbering leaves unused, unnamed slots.
        if (!bone.name.empty() && !names.Add(bone.name, error)) return false;
    }
    return true;
}

inline bool ValidateSourceAnimationNames(const Source& source, std::string* error) {
    SourceNameRegistry names(true);
    for (const auto& animation : source.anims)
        if (!names.Add(animation.name, error)) return false;
    return true;
}

} // namespace pulse::source
