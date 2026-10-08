// Offline DMX animation evaluation. Unsupported connected operators fail
// explicitly rather than baking an unanimated or partially evaluated pose.
#ifndef PULSEMDL_DMXEVAL_H
#define PULSEMDL_DMXEVAL_H
#include "dmx/dmx.h"
#include "source.h"
#include <map>
#include <memory>
namespace pulse::loader {
struct DmxRigBone {
    std::string authoredName, name;
    int bone = -1;
    bool output = false;
};
struct DmxRigDefinition {
    std::shared_ptr<const dmx::Datamodel> document;
    std::vector<DmxRigBone> bones;
    // Authored output/input bone names; local-only IK length inputs are kept
    // in bones but do not introduce world-transform feedback edges.
    std::vector<std::pair<std::string,std::string>> dependencies;
    std::vector<std::string> operatorIds;
    float scale = 1;
    const void* identity = nullptr;
};
bool CaptureDmxRig(const dmx::Datamodel& dm, float scale, DmxRigDefinition& out, std::string* error);
bool EvaluateDmxRigFrame(const DmxRigDefinition& rig,
    const std::map<std::string,math::matrix3x4>& authoredWorld,
    std::map<std::string,math::matrix3x4>& solvedWorld, std::string* error);
bool EvaluateDmxAnimations(const dmx::Datamodel& dm, const dmx::Element* animationList,
    const std::vector<const dmx::Element*>& transforms, float scale,
    source::Source& out, std::string* error);
}
#endif
