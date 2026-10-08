// dmxrig.cpp - $datamodeljoints DME bone markup reader. See dmxrig.h.

#include "strcompat.h"

#include "dmxrig.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace pulse::loader {

namespace cm = pulse::compile;
namespace pm = pulse::math;
namespace lim = pulse::limits;

namespace {

bool AddConstraints(const dmx::Datamodel& dm, float scale, cm::CompileInput& in,
                    std::string* err) {
    const auto* root=dm.root;
    const auto* list = root->GetElementArray("constraints");
    if (!list) return true;
    auto fail = [&](const std::string& s) { if (err) *err="DMX constraint: "+s; return false; };
    auto quat = [](const dmx::Element* e, const char* n) {
        pm::Quaternion q{0,0,0,1};
        if (const auto* a=e->Get(n)) if (const auto* v=std::get_if<dmx::Quaternion>(&a->value))
            q={v->x,v->y,v->z,v->w};
        return q;
    };
    auto validQ = [](const pm::Quaternion& q) {
        const float normSquared=q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w;
        return std::isfinite(q.x)&&std::isfinite(q.y)&&std::isfinite(q.z)&&std::isfinite(q.w)&&
               std::isfinite(normSquared)&&normSquared>1e-12f;
    };
    auto validV = [](const pm::Vector3& p) { return std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z); };
    auto vec = [scale](const dmx::Element* e, const char* n) {
        auto p=e->GetVector3(n); return pm::Vector3{p.x*scale,p.y*scale,p.z*scale};
    };
    for (const auto* e:*list) {
        if (!e) return fail("null operator");
        if (e->className == "DmeRigTwistConstraintOperator") {
            if(e->GetInt("mode",0)!=0)return fail("reverse rig mode is not supported");
            cm::TwistBone twist;
            twist.inverse=e->GetBool("inverse",false);
            const auto* targets=e->GetElementArray("targets");
            const auto* slaves=e->GetElementArray("twistJoints");
            if(!targets||targets->size()!=2||!slaves||slaves->empty())
                return fail("Twist requires two targets and nonempty twistJoints");
            const auto* parent=(*targets)[0]?(*targets)[0]->GetElement("target"):nullptr;
            const auto* child=(*targets)[1]?(*targets)[1]->GetElement("target"):nullptr;
            if(!parent||!child||parent->name.empty()||child->name.empty())return fail("missing Twist parent/child target");
            twist.parentName=parent->name;twist.childName=child->name;
            twist.baseRotation=quat(e,twist.inverse?"parentBindRotation":"childBindRotation");
            const auto up=e->GetVector3("upVector",{0,1,0});twist.up={up.x,up.y,up.z};
            const float upNormSquared=twist.up.x*twist.up.x+twist.up.y*twist.up.y+twist.up.z*twist.up.z;
            if(!validQ(twist.baseRotation)||!validV(twist.up)||!std::isfinite(upNormSquared)||pm::VectorNormalize(twist.up)<1e-7f)
                return fail("invalid Twist base rotation or up vector");
            pm::QuaternionNormalize(twist.baseRotation);
            const auto* skeleton=root->GetElement("skeleton");if(!skeleton)skeleton=root->GetElement("model");
            bool foundParent=false;
            auto findParent=[&](auto&& self,const dmx::Element* node,const std::string& parentName,int depth)->bool {
                if(!node||depth>512)return false;
                if(node==parent){twist.grandParentName=parentName;foundParent=true;return true;}
                if(const auto* children=node->GetElementArray("children"))for(const auto* c:*children)
                    if(self(self,c,node==skeleton?std::string():node->name,depth+1))return true;
                return false;
            };
            findParent(findParent,skeleton,{},0);
            if(!foundParent)return fail("Twist parent target is outside the rig skeleton");
            for(const auto* slave:*slaves) {
                const auto* dag=slave?slave->GetElement("target"):nullptr;
                const auto* transform=dag?dag->GetElement("transform"):nullptr;
                if(!dag||!transform||dag->name.empty())return fail("missing Twist slave target/transform");
                cm::TwistTarget target;target.name=dag->name;
                target.weight=slave->GetFloat("weight",0);
                target.position=vec(transform,"position");target.rotation=quat(slave,"orientation");
                if(!std::isfinite(target.weight)||!validV(target.position)||!validQ(target.rotation))
                    return fail("invalid Twist slave weight or base pose");
                pm::QuaternionNormalize(target.rotation);
                twist.targets.push_back(target);
            }
            // Identical repeated imports are harmless; ownership conflicts are
            // checked against all procedural kinds after name resolution.
            bool duplicate=false;
            for(const auto& old:in.twistbones) {
                bool same=old.parentName==twist.parentName&&old.childName==twist.childName&&old.grandParentName==twist.grandParentName&&
                    old.inverse==twist.inverse&&old.targets.size()==twist.targets.size()&&
                    std::memcmp(&old.up,&twist.up,sizeof(twist.up))==0&&std::memcmp(&old.baseRotation,&twist.baseRotation,sizeof(twist.baseRotation))==0;
                for(size_t i=0;same&&i<twist.targets.size();++i) {
                    const auto& a=old.targets[i];const auto& b=twist.targets[i];
                    same=a.name==b.name&&a.weight==b.weight&&std::memcmp(&a.position,&b.position,sizeof(a.position))==0&&std::memcmp(&a.rotation,&b.rotation,sizeof(a.rotation))==0;
                }
                duplicate|=same;
            }
            if(!duplicate)in.twistbones.push_back(std::move(twist));
            continue;
        }
        if(e->className=="DmeRigRotationConstraintOperator"||e->className=="DmeRigIKConstraintOperator")continue;
        cm::ConstraintBone c;
        if(e->className=="DmeRigPointConstraintOperator")c.kind=8;
        else if(e->className=="DmeRigOrientConstraintOperator")c.kind=9;
        else if(e->className=="DmeRigAimConstraintOperator")c.kind=10;
        else if(e->className=="DmeRigParentConstraintOperator")c.kind=12;
        else return fail("unsupported operator "+e->className+" '"+e->name+"'");
        if(e->GetInt("mode",0)!=0)return fail("reverse rig mode is not supported");
        const auto* s=e->GetElement("slave");
        const auto* dag=s?s->GetElement("target"):nullptr;
        if(!dag||dag->name.empty())return fail("missing slave target in '"+e->name+"'");
        c.name=dag->name;c.basePosition=vec(s,"position");c.baseRotation=quat(s,"orientation");
        if(!validV(c.basePosition)||!validQ(c.baseRotation))return fail("invalid slave pose");
        const auto* targets=e->GetElementArray("targets");
        if(!targets||targets->empty())return fail("no targets for '"+c.name+"'");
        for(const auto* t:*targets) {
            const auto* target=t?t->GetElement("target"):nullptr;
            if(!target||target->name.empty())return fail("missing target bone");
            cm::ConstraintTarget v;v.name=target->name;v.weight=t->GetFloat("targetWeight",0);
            v.offset=vec(t,"vecOffset");v.rotation=quat(t,"oOffset");
            if(!std::isfinite(v.weight)||v.weight<0||!validV(v.offset)||!validQ(v.rotation))
                return fail("invalid target weight or offset for '"+v.name+"'");
            c.targets.push_back(v);
        }
        if(c.kind==10) {
            c.aimOffset=quat(e,"aimOffset");auto up=e->GetVector3("upVector",{0,0,1});
            c.up={up.x,up.y,up.z};c.upType=e->GetInt("upType",0);
            if(const auto* upDag=e->GetElement("upSpaceTarget"))c.upName=upDag->name;
            if(!validQ(c.aimOffset)||!validV(c.up)||c.upType<0||c.upType>3)
                return fail("invalid aim parameters");
        }
        // One procedural record per bone. Repeated import of the exact same
        // document is harmless; conflicting definitions are not discarded.
        bool duplicate=false;
        for(const auto& old:in.constraintbones)if(_stricmp(old.name.c_str(),c.name.c_str())==0) {
            auto sameV=[](const pm::Vector3&a,const pm::Vector3&b){return a.x==b.x&&a.y==b.y&&a.z==b.z;};
            auto sameQ=[](const pm::Quaternion&a,const pm::Quaternion&b){return a.x==b.x&&a.y==b.y&&a.z==b.z&&a.w==b.w;};
            bool same=old.kind==c.kind&&old.upName==c.upName&&old.upType==c.upType&&
                sameV(old.basePosition,c.basePosition)&&sameQ(old.baseRotation,c.baseRotation)&&
                sameV(old.up,c.up)&&sameQ(old.aimOffset,c.aimOffset)&&old.targets.size()==c.targets.size();
            for(size_t j=0;same&&j<c.targets.size();++j) {
                const auto&a=old.targets[j];const auto&b=c.targets[j];
                same=a.name==b.name&&a.weight==b.weight&&sameV(a.offset,b.offset)&&sameQ(a.rotation,b.rotation);
            }
            // Point and orientation-only constraints may own different
            // attributes of one DAG. Keep one metadata record; the graph
            // evaluates both and rejects real attribute writer conflicts.
            const bool disjoint=(old.kind==8&&(c.kind==9||c.kind==10))||
                                (c.kind==8&&(old.kind==9||old.kind==10));
            if(!same&&!disjoint)return fail("conflicting definitions for slave '"+c.name+"'");
            duplicate=true;
        }
        if(!duplicate)in.constraintbones.push_back(std::move(c));
    }
    if(!list->empty()) {
        bool duplicate=false;for(const auto& rig:in.dmxRigs)duplicate|=rig.identity==&dm;
        if(!duplicate){DmxRigDefinition rig;if(!CaptureDmxRig(dm,scale,rig,err))return false;in.dmxRigs.push_back(std::move(rig));}
    }
    return true;
}

// The reference converts through DOUBLE; a float pi/180 is off by 1 ULP on
// values like 35 deg and that lands in the .mdl (same helper as qcloader).
float DegToRad(float deg) {
    return static_cast<float>(deg * 3.14159265358979323846 / 180.0);
}

float Clamp(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

pm::Vector3 ToVec(const dmx::Vector3& v) { return {v.x, v.y, v.z}; }

// DmeJiggleBone. The struct defaults in compile.h already match the reference's
// seed values, so only the attributes the element carries are read.
void AddJiggleBone(const dmx::Element* dag, cm::CompileInput& in) {
    for (const cm::JiggleBone& prev : in.jigglebones)
        if (_stricmp(prev.bonename.c_str(), dag->name.c_str()) == 0)
            return; // first definition wins
    if (in.jigglebones.size() >= static_cast<size_t>(lim::kMaxJiggleBones)) {
        std::fprintf(stderr, "warning: too many jigglebones, ignoring \"%s\"\n",
                     dag->name.c_str());
        return;
    }

    cm::JiggleBone jb;
    jb.bonename = dag->name;

    jb.length = dag->GetFloat("length", 10.0f);
    jb.tipMass = dag->GetFloat("tipMass", 0.0f);
    if (dag->GetBool("lengthConstrained", false))
        jb.flags |= cm::kJiggleHasLengthConstraint;
    if (dag->GetBool("angleConstrained", false))
        jb.flags |= cm::kJiggleHasAngleConstraint;
    jb.angleLimit = DegToRad(dag->GetFloat("angleLimit", 0.0f));

    if (dag->GetBool("yawConstrained", false))
        jb.flags |= cm::kJiggleHasYawConstraint;
    jb.minYaw = DegToRad(dag->GetFloat("yawMin", 0.0f));
    jb.maxYaw = DegToRad(dag->GetFloat("yawMax", 0.0f));
    jb.yawFriction = dag->GetFloat("yawFriction", 0.0f);
    jb.yawBounce = dag->GetFloat("yawBounce", 0.0f);

    jb.minPitch = DegToRad(dag->GetFloat("pitchMin", 0.0f));
    jb.maxPitch = DegToRad(dag->GetFloat("pitchMax", 0.0f));
    jb.pitchFriction = dag->GetFloat("pitchFriction", 0.0f);
    jb.pitchBounce = dag->GetFloat("pitchBounce", 0.0f);

    const bool flexible = dag->GetBool("flexible", false);
    const bool rigid = dag->GetBool("rigid", false);
    if (flexible) {
        if (rigid)
            std::fprintf(stderr, "warning: jigglebone %s: both flexible and rigid set, "
                                 "ignoring rigid\n", jb.bonename.c_str());
        jb.flags |= cm::kJiggleIsFlexible;
        if (dag->GetBool("pitchConstrained", false))
            jb.flags |= cm::kJiggleHasPitchConstraint;

        // stiffness [0,1000], damping [0,10] - the DMX path's own ranges
        // (HandleDmeJiggleBone), tighter than $jigglebone's
        jb.yawStiffness = Clamp(dag->GetFloat("yawStiffness", 100.0f), 0.0f, 1000.0f);
        jb.yawDamping = Clamp(dag->GetFloat("yawDamping", 0.0f), 0.0f, 10.0f);
        jb.pitchStiffness = Clamp(dag->GetFloat("pitchStiffness", 100.0f), 0.0f, 1000.0f);
        jb.pitchDamping = Clamp(dag->GetFloat("pitchDamping", 0.0f), 0.0f, 10.0f);
        jb.alongStiffness = Clamp(dag->GetFloat("alongStiffness", 100.0f), 0.0f, 1000.0f);
        jb.alongDamping = Clamp(dag->GetFloat("alongDamping", 0.0f), 0.0f, 10.0f);
    } else if (rigid) {
        jb.flags |= cm::kJiggleIsRigid | cm::kJiggleHasLengthConstraint;
    }

    if (dag->GetBool("baseSpring", false)) {
        jb.flags |= cm::kJiggleHasBaseSpring;
        jb.baseMass = dag->GetFloat("baseMass", 0.0f);
        jb.baseStiffness = Clamp(dag->GetFloat("baseStiffness", 100.0f), 0.0f, 1000.0f);
        jb.baseDamping = Clamp(dag->GetFloat("baseDamping", 0.0f), 0.0f, 10.0f);

        jb.baseMinLeft = dag->GetFloat("baseYawMin", -100.0f);
        jb.baseMaxLeft = dag->GetFloat("baseYawMax", 100.0f);
        jb.baseLeftFriction = dag->GetFloat("baseYawFriction", 0.0f);

        jb.baseMinUp = dag->GetFloat("basePitchMin", -100.0f);
        jb.baseMaxUp = dag->GetFloat("basePitchMax", 100.0f);
        jb.baseUpFriction = dag->GetFloat("basePitchFriction", 0.0f);

        jb.baseMinForward = dag->GetFloat("baseAlongMin", -100.0f);
        jb.baseMaxForward = dag->GetFloat("baseAlongMax", 100.0f);
        jb.baseForwardFriction = dag->GetFloat("baseAlongFriction", 0.0f);
    }

    if (dag->GetBool("boing", false)) {
        jb.flags |= cm::kJiggleIsBoing;
        jb.boingImpactSpeed = dag->GetFloat("boingImpactSpeed", 100.0f);
        // authored in degrees, stored as a cosine
        jb.boingImpactAngle = std::cos(DegToRad(dag->GetFloat("boingImpactAngle", 45.0f)));
        jb.boingDampingRate = dag->GetFloat("boingDampingRate", 0.25f);
        jb.boingFrequency = dag->GetFloat("boingFrequency", 30.0f);
        jb.boingAmplitude = dag->GetFloat("boingAmplitude", 0.35f);
    }

    in.jigglebones.push_back(std::move(jb));
}

// DmeQuatInterpBone - the DMX form of $driverbone. The dag itself is the helper
// bone; parent names stay empty and are filled from the final skeleton by
// MapProceduralBones. `unlockBones` picks which form the pose is in: set, it is
// a delta from the bind pose and the compile stage folds the bind pose in;
// clear - the usual export - basePos IS the helper's rest position, so the pose
// is already absolute parent-relative and folding again would double the
// helper's offset from its parent.
void AddQuatInterpBone(const dmx::Element* dag, float scale, cm::CompileInput& in) {
    const std::string& name = dag->name;
    for (const cm::ProceduralBone& prev : in.proceduralbones)
        if (_stricmp(prev.helpername.c_str(), name.c_str()) == 0)
            return;

    const std::string* control = dag->GetString("controlBone");
    if (!control || control->empty()) {
        std::fprintf(stderr, "warning: DmeQuatInterpBone \"%s\" has no controlBone, skipping\n",
                     name.c_str());
        return;
    }

    const std::vector<float>* tolerances = dag->GetFloatArray("tolerances");
    const std::vector<dmx::Quaternion>* triggers = dag->GetQuaternionArray("triggerRotations");
    const std::vector<dmx::Vector3>* positions = dag->GetVector3Array("targetPositions");
    const std::vector<dmx::Quaternion>* rotations = dag->GetQuaternionArray("targetRotations");
    const size_t count = triggers ? triggers->size() : 0;
    if (count == 0) {
        std::fprintf(stderr, "warning: DmeQuatInterpBone \"%s\" has no triggers, skipping\n",
                     name.c_str());
        return;
    }
    if (!tolerances || tolerances->size() != count || !positions || positions->size() != count ||
        !rotations || rotations->size() != count) {
        std::fprintf(stderr, "warning: DmeQuatInterpBone \"%s\" trigger arrays are mismatched, "
                             "skipping\n", name.c_str());
        return;
    }
    if (in.proceduralbones.size() >= static_cast<size_t>(lim::kMaxProceduralBones)) {
        std::fprintf(stderr, "warning: too many procedural bones, ignoring \"%s\"\n",
                     name.c_str());
        return;
    }

    cm::ProceduralBone pb;
    pb.helpername = name;
    pb.drivername = *control;

    const dmx::Vector3 basePos = dag->GetVector3("basePos");
    for (size_t t = 0; t < count; ++t) {
        if (pb.triggers.size() >= static_cast<size_t>(lim::kMaxProceduralTriggers)) {
            std::fprintf(stderr, "animconstraint \"%s\": more than %d triggers; "
                                 "dropping the rest\n",
                         name.c_str(), lim::kMaxProceduralTriggers);
            break;
        }
        float tolDeg = (*tolerances)[t];
        if (tolDeg <= 0.0f) {
            // the writer stores 1/tolerance, so zero would put an inf on disk
            std::fprintf(stderr, "warning: DmeQuatInterpBone \"%s\" trigger %zu has a "
                                 "non-positive tolerance, using 1.0\n", name.c_str(), t);
            tolDeg = 1.0f;
        }
        cm::ProceduralBoneTrigger tr;
        tr.absolutePose = !dag->GetBool("unlockBones", false);
        tr.tolerance = DegToRad(tolDeg);
        const dmx::Quaternion& q = (*triggers)[t];
        tr.trigger = {q.x, q.y, q.z, q.w};
        const dmx::Quaternion& tq = (*rotations)[t];
        tr.quat = {tq.x, tq.y, tq.z, tq.w};
        // basePos is added before the scale, like `(basePos + pos) * g_currentscale`
        const dmx::Vector3& p = (*positions)[t];
        tr.pos = {(basePos.x + p.x) * scale, (basePos.y + p.y) * scale,
                  (basePos.z + p.z) * scale};
        pb.triggers.push_back(tr);
    }

    in.proceduralbones.push_back(std::move(pb));
}

// DmeAimAtBone - the DMX form of $driveraimat. basePos is the full base
// position already, so autobasepos stays false and the compile stage must not
// re-add the bone's rest pose on top of it.
void AddAimAtBone(const dmx::Element* dag, float scale, cm::CompileInput& in) {
    const std::string& name = dag->name;
    for (const cm::AimAtBone& prev : in.aimatbones)
        if (_stricmp(prev.bonename.c_str(), name.c_str()) == 0)
            return;

    const std::string* target = dag->GetString("aimTarget");
    if (!target || target->empty()) {
        std::fprintf(stderr, "warning: DmeAimAtBone \"%s\" has no aimTarget, skipping\n",
                     name.c_str());
        return;
    }
    if (in.aimatbones.size() >= static_cast<size_t>(lim::kMaxProceduralBones)) {
        std::fprintf(stderr, "warning: too many procedural bones, ignoring \"%s\"\n",
                     name.c_str());
        return;
    }

    cm::AimAtBone ab;
    ab.bonename = name;
    ab.aimname = *target;
    if (const std::string* parent = dag->GetString("parentBone"))
        ab.parentname = *parent; // empty = derived from the resolved skeleton

    ab.aimvector = ToVec(dag->GetVector3("aimVector", {0.0f, 0.0f, 1.0f}));
    ab.upvector = ToVec(dag->GetVector3("upVector", {1.0f, 0.0f, 0.0f}));
    pm::VectorNormalize(ab.aimvector);
    pm::VectorNormalize(ab.upvector);

    const pm::Vector3 base = ToVec(dag->GetVector3("basePos"));
    ab.basepos = {base.x * scale, base.y * scale, base.z * scale};
    ab.autobasepos = false;

    in.aimatbones.push_back(std::move(ab));
}

// DmeTransform -> matrix, translation scaled like the DMX skeleton loader's.
pm::matrix3x4 DagLocal(const dmx::Element* dag, float scale) {
    const dmx::Element* t = dag->GetElement("transform");
    if (!t)
        return pm::matrix3x4();
    pm::Quaternion rot{0, 0, 0, 1};
    if (const dmx::Attribute* a = t->Get("orientation"))
        if (auto q = std::get_if<dmx::Quaternion>(&a->value))
            rot = {q->x, q->y, q->z, q->w};
    const pm::Vector3 p = ToVec(t->GetVector3("position"));
    return pm::QuaternionMatrix(rot, {p.x * scale, p.y * scale, p.z * scale});
}

// A DMX attachment is a dag whose SHAPE is a DmeAttachment: the shape names the
// attachment. The BONE is the dag itself when the shape hangs on a joint, and
// otherwise the nearest ancestor joint, with the plain-dag chain below it baked
// into the local transform - an exporter that writes attachments as locators
// parented under the joint would otherwise link to a bone that only exists if
// this same DMX also supplies the mesh (every dag becomes one there, which is
// all reference LoadAttachments relies on). The static-prop case needs no
// special handling, because LinkAttachments already rebases onto the surviving
// bone when the named one collapses.
void WalkAttachments(const dmx::Element* dag, float scale, cm::CompileInput& in,
                     const std::string& boneName, const pm::matrix3x4& boneToDag) {
    // a procedural joint (DmeJiggleBone / DmeQuatInterpBone / DmeAimAtBone) is
    // a bone too - it survives the cull, so an attachment may name it directly
    const bool isJoint = dag->className == "DmeJoint" ||
                         dag->className == "DmeJiggleBone" ||
                         dag->className == "DmeQuatInterpBone" ||
                         dag->className == "DmeAimAtBone";
    const std::string& bone = isJoint ? dag->name : boneName;
    const pm::matrix3x4 local =
        isJoint ? pm::matrix3x4() : pm::ConcatTransforms(boneToDag, DagLocal(dag, scale));

    const dmx::Element* shape = dag->GetElement("shape");
    if (shape && shape->className == "DmeAttachment") {
        bool dup = false; // first definition wins, like the jigglebone/procedural dedup
        for (const cm::Attachment& prev : in.attachments)
            if (_stricmp(prev.name.c_str(), shape->name.c_str()) == 0) { dup = true; break; }
        if (!dup) {
            cm::Attachment att;
            att.name = shape->name;
            att.bonename = bone;
            att.local = local;
            att.type = cm::kAttachIsFromSource;
            if (shape->GetBool("isRigid", false))
                att.type |= cm::kAttachIsRigid;
            if (shape->GetBool("isWorldAligned", false))
                att.flags |= cm::kAttachFlagWorldAlign;
            in.attachments.push_back(std::move(att));
        }
    }

    if (auto kids = dag->GetElementArray("children"))
        for (const dmx::Element* c : *kids)
            if (c)
                WalkAttachments(c, scale, in, bone, local);
}

// root."hitboxSetList" -> DmeHitboxSetList."hitboxSetList" -> DmeHitboxSet
// ("hitboxList" of DmeHitbox). Reference LoadDmxHitboxes: hitboxes are
// model-global and first-to-populate wins, so an existing $hitboxset makes the
// whole DMX list a no-op. An EMPTY set is skipped - a stray "default" set would
// suppress the compile stage's auto-generation.
void AddHitboxes(const dmx::Element* root, cm::CompileInput& in) {
    const dmx::Element* list = root->GetElement("hitboxSetList");
    if (!list)
        return;
    const std::vector<dmx::ElementPtr>* sets = list->GetElementArray("hitboxSetList");
    if (!sets || sets->empty())
        return;
    if (!in.hitboxsets.empty()) {
        std::fprintf(stderr, "warning: DMX hitboxSetList ignored - hitbox sets are already "
                             "defined ($hitboxset or an earlier $datamodeljoints)\n");
        return;
    }

    for (const dmx::Element* set : *sets) {
        if (!set) continue;
        const std::vector<dmx::ElementPtr>* boxes = set->GetElementArray("hitboxList");
        if (!boxes || boxes->empty())
            continue;
        if (in.hitboxsets.size() >= static_cast<size_t>(lim::kMaxHitboxSets)) {
            std::fprintf(stderr, "warning: too many hitbox sets, ignoring \"%s\"\n",
                         set->name.c_str());
            break;
        }

        cm::HitboxSet hs;
        hs.name = set->name;
        for (const dmx::Element* box : *boxes) {
            if (!box) continue;
            if (hs.hitboxes.size() >= static_cast<size_t>(lim::kMaxHitboxesPerSet)) {
                std::fprintf(stderr, "warning: too many hitboxes for hitbox set \"%s\", max %d\n",
                             hs.name.c_str(), lim::kMaxHitboxesPerSet);
                break;
            }
            cm::HitBox hb;
            if (const std::string* bone = box->GetString("boneName"))
                hb.bonename = *bone;
            hb.group = box->GetInt("groupId", 0);
            // scaled like Cmd_Hitbox's scale_vertex, so DMX hitboxes respect $scale
            const dmx::Vector3 lo = box->GetVector3("minBounds");
            const dmx::Vector3 hi = box->GetVector3("maxBounds");
            hb.bmin = {lo.x * in.scale, lo.y * in.scale, lo.z * in.scale};
            hb.bmax = {hi.x * in.scale, hi.y * in.scale, hi.z * in.scale};
            hb.capsuleRadius = box->GetFloat("radius", -1.0f); // <= 0 = a box
            if (hb.capsuleRadius > 0.0f) hb.capsuleRadius *= in.scale;
            hb.angOffset = ToVec(box->GetVector3("orientation"));
            // the DmeHitbox element's own name is not the hitbox name - the
            // reference leaves these unnamed, like an $hbox with no `name`
            hs.hitboxes.push_back(std::move(hb));
        }
        in.hitboxsets.push_back(std::move(hs));
    }
}

// Walk the dag tree the way the skeleton load does (reference AddDagJoint): a
// dag with no transform is not a joint, and neither it nor its subtree counts.
void WalkDag(const dmx::Element* dag, float scale, cm::CompileInput& in, bool jigglebones,
             bool proceduralbones) {
    if (!dag->GetElement("transform"))
        return;

    if (jigglebones && dag->className == "DmeJiggleBone")
        AddJiggleBone(dag, in);
    if (proceduralbones) {
        if (dag->className == "DmeQuatInterpBone")
            AddQuatInterpBone(dag, scale, in);
        else if (dag->className == "DmeAimAtBone")
            AddAimAtBone(dag, scale, in);
    }

    if (auto kids = dag->GetElementArray("children"))
        for (const dmx::Element* c : *kids)
            if (c)
                WalkDag(c, scale, in, jigglebones, proceduralbones);
}

} // namespace

bool LoadDmxJoints(const dmx::Datamodel& dm, cm::CompileInput& in, bool jigglebones,
                   bool proceduralbones, bool hitboxes, bool attachments, std::string* err) {
    const dmx::Element* root = dm.root;
    if (!root) {
        if (err) *err = "DMX has no root element";
        return false;
    }
    const dmx::Element* skeleton = root->GetElement("skeleton");
    if (!skeleton) skeleton = root->GetElement("model");
    if (!skeleton) {
        if (err) *err = "no 'model'/'skeleton' element on root";
        return false;
    }

    // the root dag is never a joint (or an attachment) itself - start at its
    // children
    if (const auto* kids = skeleton->GetElementArray("children")) {
        for (const dmx::Element* c : *kids) {
            if (!c) continue;
            if (jigglebones || proceduralbones)
                WalkDag(c, in.scale, in, jigglebones, proceduralbones);
            if (attachments)
                WalkAttachments(c, in.scale, in, std::string(), pm::matrix3x4());
        }
    }
    if (hitboxes)
        AddHitboxes(root, in);
    if (proceduralbones && !AddConstraints(dm, in.scale, in, err))
        return false;
    return true;
}

} // namespace pulse::loader
