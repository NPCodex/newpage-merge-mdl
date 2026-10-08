// CSGO FE disk records. Resource offsets are signed and relative to the offset field.
#ifndef PULSEMDL_FORMAT_CLOTH_H
#define PULSEMDL_FORMAT_CLOTH_H
#include <cstddef>
#include <cstdint>
namespace pulse::format::cloth {
struct Array { int32_t offset=0; uint32_t count=0; };
struct Descriptor {
    Array ctrlHash, ctrlName;
    uint32_t staticFlags=0, dynamicFlags=0;
    float localForce=1, localRotation=0;
    uint16_t nodeCount=0, staticNodes=0, rotLockStaticNodes=0;
    uint16_t simdTri1=0, simdTri2=0, simdQuad1=0, simdQuad2=0;
    uint16_t quad1=0, quad2=0, sphereInclusive=0, treeDepth=0;
    uint16_t fit1=0, fit2=0, simdFit1=0, simdFit2=0, ropeCount=0;
    Array ropes, nodeBases, simdNodeBases, quads, simdQuads, simdTris, simdRods;
    Array initPose, rods, axialEdges, nodeInvMasses, ctrlOffsets, ctrlOsOffsets;
    Array followNodes, collisionSpheres, collisionPlanes, nodeIntegrator;
    Array springs, simdSprings, worldCollisionParams, legacyStretch, nodeCollisionRadii;
    Array localRotations, localForces, capsuleStretches, capsuleRigids, sphereRigids;
    Array worldCollisionNodes, treeParents, treeMasks, treeChildren, freeNodes;
    Array fitMatrices, simdFitMatrices, fitWeights, reverseOffsets;
    uint32_t reserved[30]{};
    float windage=1, windDrag=0, surfaceStretch=0, threadStretch=0, gravityScale=1;
    float velocityAirDrag=0, exponentialAirDrag=0, velocityQuadDrag=0, exponentialQuadDrag=0;
    float velocityRodDrag=0, exponentialRodDrag=0, rodVelocitySmooth=0, quadVelocitySmooth=0;
    float worldCollisionRadius=0, volumetricSolve=0;
    uint16_t rodSmoothIterations=0, quadSmoothIterations=0;
};
struct alignas(16) Transform { float position[4]{}; float orientation[4]{0,0,0,1}; };
struct Quad { uint16_t node[4]{}; float slack=0; float shape[4][4]{}; };
struct alignas(16) SimdQuad {
    uint16_t node[4][4]{}; float slack[4]{};
    float shape[4][3][4]{}; float weight[4][4]{};
};
struct alignas(16) SimdTri {
    uint32_t node[3][4]{}; float weight1[4]{},weight2[4]{},edgeLength[4]{},point2[2][4]{};
};
struct CtrlOffset { uint16_t parent=0,child=0; float position[3]{}; };
struct Plane { uint16_t parent=0,child=0; float normal[3]{},offset=0,stickiness=0; };
struct SphereRigid { uint16_t node=0,mask=65535; float center[3]{},radius=0,stickiness=0; };
struct CapsuleRigid { uint16_t node=0,mask=65535; float center[2][3]{},radius[2]{},stickiness=0; };
struct CapsuleStretch { uint16_t node[2]{},mask=65535,pad=0; float radius[2]{},stickiness=0; };
struct CollisionSphere { uint16_t parent=0,child=0; float radiusFactor=0,center[3]{},stickiness=0; };
struct FollowNode { uint16_t parent=0,child=0; float weight=1; };
struct CtrlOsOffset { uint16_t parent=0,child=0; };
struct Spring { uint16_t node[2]{}; float restLength=0,stiffness=0,damping=0,weight0=0; };
struct alignas(16) SimdSpring {
    uint16_t node[2][4]{}; float restLength[4]{},stiffness[4]{},damping[4]{},weight0[4]{};
};
struct NodeBase { uint16_t node=0,pad[3]{},x0=0,x1=0,y0=0,y1=0; float adjust[4]{0,0,0,1}; };
struct ReverseOffset { uint16_t ctrl=0,target=0; float offset[3]{}; };
struct Rod { uint16_t node[2]{}; float maxDistance=0,minDistance=0,weight0=0,relaxation=1; };
struct alignas(16) SimdRod {
    uint16_t node[2][4]{}; float maxDistance[4]{},minDistance[4]{},weight0[4]{},relaxation[4]{};
};
struct AxialEdge { float te=0,tv=0,distance=0,weight[4]{}; uint16_t node[6]{}; };
struct WorldCollisionParams { float worldFriction=1,groundFriction=0; uint16_t begin=0,end=0; };
struct Integrator { float damping=0,forceAttraction=0,vertexAttraction=0,gravity=360; };
struct FitWeight { float weight=0; uint16_t node=0,pad=0; };
struct alignas(16) FitMatrix {
    Transform bone; float center[3]{};
    uint16_t end=0,node=0,ctrl=0,beginDynamic=0;
};
struct TreeChildren { uint16_t child[2]{}; };
static_assert(sizeof(Descriptor)==536);
static_assert(offsetof(Descriptor,ropes)==64);
static_assert(sizeof(Transform)==32 && sizeof(FitMatrix)==64);
static_assert(sizeof(Quad)==76 && sizeof(SimdQuad)==304 && sizeof(SimdTri)==128);
static_assert(sizeof(Plane)==24 && sizeof(CtrlOffset)==16 && sizeof(FitWeight)==8);
static_assert(sizeof(Rod)==20 && sizeof(SimdRod)==80 && sizeof(AxialEdge)==40 && sizeof(WorldCollisionParams)==12);
static_assert(sizeof(SphereRigid)==24 && sizeof(CapsuleRigid)==40);
static_assert(sizeof(CapsuleStretch)==20 && sizeof(CollisionSphere)==24);
static_assert(sizeof(FollowNode)==8 && sizeof(CtrlOsOffset)==4);
static_assert(sizeof(Spring)==20 && sizeof(SimdSpring)==80);
static_assert(sizeof(NodeBase)==32 && offsetof(NodeBase,adjust)==16 && sizeof(ReverseOffset)==16);
}
#endif
