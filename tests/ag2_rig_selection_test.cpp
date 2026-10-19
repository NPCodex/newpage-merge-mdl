#include "../subtools/ag2proportions/rig_selection.h"

#include <iostream>

namespace {
void Require(bool condition, const char* message) {
    if (!condition)
        throw std::runtime_error(message);
}
}

int main() {
    using ag2::RigCandidateRank;
    std::vector<RigCandidateRank> candidates{
        {"small.dmx", 1.0f, 12, false},
        {"body.dmx", 1.0f, 40, false},
        {"stock.dmx", 1.0f, 75, true},
    };
    Require(ag2::SelectRigCandidate(candidates, false, "body")->path == "body.dmx",
            "the largest non-stock rig must win");
    Require(ag2::SelectRigCandidate(candidates, true, "fallback")->path == "stock.dmx",
            "stock-length candidates are selected only as fallback");

    candidates.push_back({"other_body.dmx", 1.0f, 40, false});
    try {
        ag2::SelectRigCandidate(candidates, false, "body");
        throw std::runtime_error("equal-ranked body rigs must fail as ambiguous");
    } catch (const std::runtime_error& error) {
        const std::string message = error.what();
        Require(message.find("body.dmx") != std::string::npos &&
                message.find("other_body.dmx") != std::string::npos &&
                message.find("model_dmx") != std::string::npos,
                "ambiguity error must identify candidates and the override");
    }

    candidates.push_back({"body.dmx", 0.5f, 40, false});
    try {
        ag2::SelectRigCandidate(candidates, false, "body");
        throw std::runtime_error("the same DMX at different scales must be ambiguous");
    } catch (const std::runtime_error& error) {
        Require(std::string(error.what()).find("import_scale") != std::string::npos,
                "ambiguity error must show the scale distinction");
    }

    candidates = {{"body.dmx", 1.0f, 40, false}, {"body.dmx", 1.0f, 40, false}};
    Require(ag2::SelectRigCandidate(candidates, false, "body")->path == "body.dmx",
            "duplicate references to the same file and scale are one choice");
    return 0;
}
