#include "../subtools/ag2proportions/ag2.h"
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
void Require(bool ok,const char* message) { if(!ok) throw std::runtime_error(message); }
ag2::Bone MakeBone(const char* name,int parent,float x,float y=0,float z=0) {
    return {name,parent,{x,y,z},{0,0,0,1}};
}
const ag2::Bone& Find(const std::vector<ag2::Bone>& bones,const std::string& name) {
    for(const auto& b:bones) if(b.name==name) return b;
    throw std::runtime_error("missing "+name);
}
}
int main() {
    using namespace ag2;
    // An arms-only authoring rig uses the ordinary shoulder -> elbow -> hand
    // hierarchy, with an arbitrary root offset unrelated to graph shoulders.
    std::vector<Bone> rig{MakeBone("root_motion",-1,200,100,50),
        MakeBone("arm_upper_L",0,4,5,6),MakeBone("arm_lower_L",1,14),MakeBone("hand_L",2,6),
        MakeBone("arm_upper_R",0,-4,-5,6),MakeBone("arm_lower_R",4,-9),MakeBone("hand_R",5,-8)};
    std::vector<Bone> stock{MakeBone("root_motion",-1,0),
        MakeBone("armUpperShoulder_L",0,8,4,-2),MakeBone("arm_lower_L",1,10),MakeBone("hand_L",2,7),
        MakeBone("armUpperStraighten_0_L",2,0),MakeBone("arm_upper_L",4,10),
        MakeBone("armUpperShoulder_R",0,-1,-4,-2),MakeBone("arm_lower_R",6,-10),MakeBone("hand_R",7,-7),
        MakeBone("armUpperStraighten_0_R",7,0),MakeBone("arm_upper_R",9,-10)};
    std::vector<std::string> warnings;
    auto pose=TargetViewPose(rig,stock,warnings);
    for(const char* name:{"arm_upper_L","arm_lower_L"}) Require(std::abs(Find(pose,name).position.x-14)<1e-5,"left upper arm length lost");
    for(const char* name:{"arm_upper_R","arm_lower_R"}) Require(std::abs(Find(pose,name).position.x+9)<1e-5,"right upper arm length lost");
    Require(Find(pose,"hand_L").position.x==6 && Find(pose,"hand_R").position.x==-8,"forearm lengths lost");
    Require(Find(pose,"armUpperShoulder_L").position.x==8,"graph shoulder moved with authoring root");
    Require(warnings.empty(),"valid anatomical arm axes must not produce artificial reparenting warnings");
    rig[0].position={-900,1300,-200};
    auto moved=TargetViewPose(rig,stock,warnings);
    for(size_t i=0;i<pose.size();++i) {
        const auto&a=pose[i].position;const auto&b=moved[i].position;
        Require(std::abs(a.x-b.x)+std::abs(a.y-b.y)+std::abs(a.z-b.z)<1e-4,"root placement leaked into arm proportions");
    }
    rig[2].position={};
    try { TargetViewPose(rig,stock,warnings); throw std::logic_error("zero length arm accepted"); }
    catch(const std::runtime_error&e) { Require(std::string(e.what()).find("upper arm length")!=std::string::npos,"unexpected invalid-arm error"); }
    std::cout<<"AG2 first-person limb lengths and source-space invariance passed\n";
}
