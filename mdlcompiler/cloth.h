// Bounded CSGO finite-element proxy compiler. The proxy is separate from render geometry.
#ifndef PULSEMDL_CLOTH_H
#define PULSEMDL_CLOTH_H
#include <array>
#include <cstdint>
#include <string>
#include <vector>
#include "dmx/dmx.h"
#include "math/math.h"
#include "clothadvanced.h"
namespace pulse::cloth {
// Bone-local centers and radii are already in final model units. QC snapshots
// its current scale when the collider is declared; Build must not scale twice.
struct RigidCollider {
    enum class Type { Sphere, Capsule };
    Type type = Type::Sphere;
    std::string bone;
    math::Vector3 center[2];
    float radius[2]{};
    float stickiness = 0;
};
struct ProjectionSettings {
    bool enabled=false, twoSided=true;
    float envelope=0; // Zero means unlimited; misses retain their original skin weights.
    int island=-1; // Connected proxy component, in deterministic point order; -1 selects all.
    std::string rootBone;
};
struct Settings {
    AdvancedSettings advanced;
    ProjectionSettings projection;
    bool flexBorders=false, modelUpAxisY=false;
    float fitInfluenceThreshold=.05f, quadBendTolerance=.05f;
    int fitMinInfluences=3; // Set 8 for the reference small-cloud policy.
    math::RadianEuler prerotate;
    std::vector<RigidCollider> colliders;
    bool worldCollision = false, addStiffnessRods = true, rigidEdgeHinges = false;
    float localPosition = 1, localRotation = 0, surfaceStretch = 0, threadStretch = 0;
    float gravityScale = 1, velocityAirDrag = 0, exponentialAirDrag = 0;
    float velocityQuadDrag = 0, exponentialQuadDrag = 0, velocityRodDrag = 0, exponentialRodDrag = 0;
    float quadVelocitySmooth = 0, rodVelocitySmooth = 0, windage = 1, windDrag = 0, curvature = 0;
};
// Strict single-value settings parser shared by QC and programmatic importers.
bool SetSetting(Settings&, const std::string& name, const std::string& value, std::string* error);
struct Influence { std::string bone; float weight = 0; };
struct Point {
    math::Vector3 position;
    std::vector<Influence> weights;
    bool simulated = false;
    float massBias = 0, gravity = 360, drag = 0;
    float forceAttraction = 0, vertexAttraction = 0, collisionRadius = 0;
    float worldFriction = 1, groundFriction = 0;
    bool worldCollision = false;
    bool useRods = false, anchorFreeRotate = false;
};
struct Face { std::array<uint32_t,4> point{}; int count = 0; uint32_t mesh = 0; };
struct Proxy {
    bool planeCollision = false;
    bool upAxisY = false;
    std::vector<Point> points;
    std::vector<Face> faces;
    std::vector<std::string> bones;
};
struct Bone { std::string name; math::matrix3x4 bindPose; };
// Reads explicit enable, mass, gravity, damping, attraction and ground collision maps.
// Unknown cloth maps are rejected. A plane proxy needs no cloth maps.
bool ReadProxy(const dmx::Datamodel&, bool planeCollision, Proxy&, std::string* error, const Settings* settings = nullptr);
// importTransform rotates/translates positions after scale. Bone poses are final model-space poses.
// The returned resource starts with the FE descriptor and is relocatable as a whole.
// Append it at a 32-byte boundary and set the studiohdr2 FE offset relative to its own field.
bool Build(const std::vector<Proxy>&, const std::vector<Bone>&,
           const math::matrix3x4& importTransform, float scale,
           std::vector<uint8_t>& resource, std::string* error, const Settings* settings = nullptr);
}
#endif
