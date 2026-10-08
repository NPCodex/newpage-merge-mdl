// Explicit Source1 FE authoring. Names refer to model bones or $cloth_pN proxy nodes.
#ifndef PULSEMDL_CLOTHADVANCED_H
#define PULSEMDL_CLOTHADVANCED_H
#include <cstdint>
#include <string>
#include <vector>
#include "math/math.h"
namespace pulse::cloth {
struct AdvancedNode {
    std::string name, parent;
    bool simulated=true, hasSimulated=false, hasPosition=false;
    math::Vector3 position;
    float mass=-1, massMultiplier=1;
    float localPosition=-1, localRotation=-1, damping=-1, gravity=-1;
    float forceAttraction=-1, vertexAttraction=-1, collisionRadius=-1, legacyStretch=-1;
    int collisionMask=-1;
};
struct AdvancedRod { std::string node[2]; float length=-1, contraction=1, bias[2]{1,1}, relaxation=1; };
struct AdvancedSpring { std::string node[2]; float stiffness=0,damping=0; };
struct AdvancedFollow { std::string parent,child; float weight=1; };
struct AdvancedSphere { std::string parent,child; bool inclusive=false; math::Vector3 center; float radius=0,stickiness=0; };
struct AdvancedPlane { std::string parent,child; math::Vector3 normal; float offset=0,stickiness=0; };
struct AdvancedCapsule { std::string node[2]; float radius[2]{}; uint16_t mask=65535; float stickiness=0; };
struct AdvancedRigid { std::string node; bool capsule=false; math::Vector3 center[2]; float radius[2]{}; uint16_t mask=65535; float stickiness=0; };
struct AdvancedSettings {
    std::vector<AdvancedNode> nodes;
    std::vector<AdvancedRod> rods;
    std::vector<AdvancedSpring> springs;
    std::vector<std::vector<std::string>> ropes;
    std::vector<AdvancedFollow> follows,osOffsets;
    std::vector<AdvancedSphere> spheres;
    std::vector<AdvancedPlane> planes;
    std::vector<AdvancedCapsule> capsules;
    std::vector<AdvancedRigid> rigids;
    bool ftl=false,uninertial=false,massDamping=false;
    float volumetric=-1,worldRadius=-1,addWorldRadius=0;
    int rodSmoothIterations=-1,quadSmoothIterations=-1;
};
// Brace tokens are retained; the outer advanced { } is removed by the caller.
// Positions/lengths capture QC scale here. Parsing is transactional.
bool ParseAdvanced(AdvancedSettings&,const std::vector<std::string>& tokens,float scale,std::string* error);
bool HasAdvanced(const AdvancedSettings&);
std::vector<std::string> AdvancedReferencedBones(const AdvancedSettings&);
const AdvancedNode* FindAdvancedNode(const AdvancedSettings&,const std::string& name);
// Must run before building element/rod weights, on all simulated point/control nodes.
float AdvancedMass(const AdvancedSettings&,const std::string& name,float automaticMass);
struct AdvancedNodeInfo {
    std::string name;
    math::Vector3 position;
    math::matrix3x4 pose;
    float invMass=0;
    bool fit=false;
};
// NodeInfo order is final FE order (including static partition). Does not renumber nodes.
// Call once after ordinary serialization and before final prerotate.
bool AppendAdvancedResource(const AdvancedSettings&,const std::vector<AdvancedNodeInfo>&,
                            std::vector<uint8_t>& resource,std::string* error);
}
#endif
