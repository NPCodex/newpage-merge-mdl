#pragma once

#include <algorithm>
#include <filesystem>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace ag2 {

struct RigCandidateRank {
    std::filesystem::path path;
    float scale = 1.0f;
    size_t coreBoneCount = 0;
    bool stockLengths = false;
};

inline const RigCandidateRank* SelectRigCandidate(const std::vector<RigCandidateRank>& candidates,
                                                   bool stockLengths, const char* role) {
    const RigCandidateRank* best = nullptr;
    std::vector<const RigCandidateRank*> tied;
    for (const RigCandidateRank& candidate : candidates) {
        if (!candidate.coreBoneCount || candidate.stockLengths != stockLengths)
            continue;
        if (!best || candidate.coreBoneCount > best->coreBoneCount) {
            best = &candidate;
            tied.assign(1, best);
        } else if (candidate.coreBoneCount == best->coreBoneCount) {
            const bool duplicate = std::any_of(tied.begin(), tied.end(), [&](const RigCandidateRank* other) {
                return other->path == candidate.path && other->scale == candidate.scale;
            });
            if (!duplicate)
                tied.push_back(&candidate);
        }
    }
    if (tied.size() > 1) {
        std::ostringstream message;
        message << "ambiguous automatic " << role << " rig selection ("
                << best->coreBoneCount << " CS2 core bones):";
        for (const RigCandidateRank* candidate : tied)
            message << "\n  " << candidate->path.u8string() << " (import_scale " << candidate->scale << ')';
        message << "\nset model_dmx in the job to choose the intended rig";
        throw std::runtime_error(message.str());
    }
    return best;
}

} // namespace ag2
