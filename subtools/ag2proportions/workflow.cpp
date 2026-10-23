// workflow.cpp - one job end to end: locate the addon, read the stock assets,
// build the poses and the wrapper, write the outputs, then compile.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <functional>
#include <iostream>
#include <variant>
#include <stdexcept>

#include "ag2.h"
#include "rig_selection.h"
#include "strcompat.h"
#include "transaction.h"
#include "uncompiled_outputs.h"
#include "vpk.h"

namespace ag2 {
namespace {

namespace dmx = pulse::dmx;
using std::runtime_error;

// Every source a run owns. Obsolete debug files are removed in the same
// transaction as replacements; an input reused from a previous run is read
// completely before any output is changed.
const char* const kGeneratedFiles[] = {
    kWorldGraphFile, kUiGraphFile, kViewGraphFile, kClipFile, kProportionsFile, kReferenceFile, kSkeletonFile,
    "debug/skeleton_descriptor.kv3", "debug/report.kv3", "debug/MODEL_SETUP.txt",
};


bool Disabled(const kv::Value& node) {
    if (!node.Has("disabled"))
        return false;
    const kv::Value& flag = node.At("disabled");
    return std::holds_alternative<bool>(flag.data) && flag.Boolean();
}

// Visits every enabled node; a node ModelDoc has disabled is skipped with its children.
void Walk(kv::Value& value, const std::function<void(kv::Value&)>& visit) {
    if (value.IsObject()) {
        if (Disabled(value))
            return;
        visit(value);
        for (auto& member : value.Members())
            Walk(member.second, visit);
    } else if (value.IsArray()) {
        for (auto& item : value.Items())
            Walk(item, visit);
    }
}

std::string ClassOf(const kv::Value& node) {
    return node.Has("_class") ? node.At("_class").String() : std::string();
}

std::string ReadText(const fs::path& path) {
    const auto bytes = kv::ReadFile(path.u8string());
    return {bytes.begin(), bytes.end()};
}

// The VMDL must sit in <cs2>/content/csgo_addons/<addon>/; the output folder is
// a sibling of it named after it.
Paths Locate(const fs::path& vmdl) {
    Paths p;
    for (fs::path dir = vmdl.parent_path(); dir.has_relative_path(); dir = dir.parent_path()) {
        if (dir.parent_path().filename() == "csgo_addons" &&
            dir.parent_path().parent_path().filename() == "content") {
            p.addon = dir;
            break;
        }
    }
    if (p.addon.empty())
        throw runtime_error("the VMDL is not inside content/csgo_addons/<addon>");
    p.cs2 = p.addon.parent_path().parent_path().parent_path();
    p.output = vmdl.parent_path() / vmdl.stem();
    p.relative = p.output.lexically_relative(p.addon).generic_u8string();
    return p;
}

// A ModelDoc path is addon-relative; a model-relative one is accepted too.
fs::path ResolveImport(const std::string& name, const Paths& paths, const fs::path& vmdl) {
    const fs::path file = fs::u8path(name);
    for (const fs::path& candidate : {paths.addon / file, vmdl.parent_path() / file})
        if (fs::is_regular_file(candidate))
            return fs::weakly_canonical(candidate);
    throw runtime_error("cannot find VMDL import " + name);
}

struct RigSource {
    fs::path path;
    float scale = 1.0f; // the import's import_scale, baked into the skeleton
};

// model_dmx, else the render mesh carrying the most CS2 core bones (the body),
// else the SkeletonFile that does. The generated skeleton is never a source.
RigSource FindRig(kv::Value& vmdl, const Job& job, const Paths& paths, const std::vector<Bone>& viewmodel,
                  const std::vector<Bone>& worldmodel) {
    const fs::path generated = paths.output / kSkeletonFile;
    std::vector<RigSource> meshes, files;
    Walk(vmdl, [&](kv::Value& node) {
        const std::string cls = ClassOf(node);
        if ((cls != "RenderMeshFile" && cls != "SkeletonFile") || !node.Has("filename"))
            return;
        const std::string name = node.At("filename").String();
        if (_stricmp(fs::u8path(name).extension().u8string().c_str(), ".dmx") != 0)
            return;
        RigSource source{ResolveImport(name, paths, job.vmdl),
                         node.Has("import_scale") ? static_cast<float>(node.At("import_scale").Number()) : 1.0f};
        if (fs::exists(generated) && fs::equivalent(source.path, generated))
            return;
        (cls == "RenderMeshFile" ? meshes : files).push_back(source);
    });
    if (!job.modelDmx.empty()) {
        for (const auto* list : {&meshes, &files})
            for (const RigSource& source : *list)
                if (fs::equivalent(source.path, job.modelDmx))
                    return {job.modelDmx, source.scale};
        return {job.modelDmx, 1.0f};
    }
    // A mesh on stock bone lengths (first-person arms) is only used
    // when every candidate is one.
    for (const auto* list : {&meshes, &files}) {
        std::vector<RigCandidateRank> ranked;
        for (const RigSource& source : *list) {
            std::string err;
            auto dm = dmx::Datamodel::Load(source.path.u8string(), &err);
            const size_t count = dm ? CountBones(*dm) : 0;
            if (!count)
                continue;
            bool stockLengths = false;
            try {
                stockLengths = HasStockLengths(ReadRig(*dm, source.scale, false), {&viewmodel, &worldmodel});
            } catch (const std::exception&) {
            }
            if (stockLengths) {
                std::cout << "Skipping " << source.path.filename().u8string()
                          << ": its bone lengths match the stock skeletons\n";
            }
            ranked.push_back({source.path, source.scale, count, stockLengths});
        }
        if (const RigCandidateRank* best = SelectRigCandidate(ranked, false, "body"))
            return {best->path, best->scale};
        if (const RigCandidateRank* best = SelectRigCandidate(ranked, true, "stock-length fallback"))
            return {best->path, best->scale};
    }
    throw runtime_error("no DMX import carries the CS2 body bones; set model_dmx in the job");
}

pm::Vector3 Triple(const kv::Value& v, const std::string& bone) {
    const auto& items = v.Items();
    if (items.size() != 3)
        throw runtime_error("Bone node " + bone + " needs three origin/angles values");
    return {static_cast<float>(items[0].Number()), static_cast<float>(items[1].Number()),
            static_cast<float>(items[2].Number())};
}

// ModelDoc Bone nodes under Skeleton, parent-first. origin is parent-local and
// angles a QAngle in degrees (pitch, yaw, roll); nesting gives the parent.
std::vector<Bone> BoneNodes(const kv::Value& vmdl) {
    std::vector<Bone> bones;
    std::function<void(const kv::Value&, int)> visit = [&](const kv::Value& node, int parent) {
        if (!node.IsObject() || Disabled(node))
            return;
        if (ClassOf(node) == "Bone") {
            Bone b;
            b.name = node.At("name").String();
            b.parent = parent;
            b.position = node.Has("origin") ? Triple(node.At("origin"), b.name) : pm::Vector3{};
            const pm::Vector3 a = node.Has("angles") ? Triple(node.At("angles"), b.name) : pm::Vector3{};
            pm::AngleQuaternion(pm::RadianEuler{a.z * pm::kDeg2Rad, a.x * pm::kDeg2Rad, a.y * pm::kDeg2Rad}, b.rotation);
            parent = static_cast<int>(bones.size());
            bones.push_back(b);
        }
        if (node.Has("children") && node.At("children").IsArray())
            for (const kv::Value& child : node.At("children").Items())
                visit(child, parent);
    };
    std::function<void(const kv::Value&)> findSkeletons = [&](const kv::Value& node) {
        if (node.IsObject()) {
            if (Disabled(node))
                return;
            if (ClassOf(node) == "Skeleton") {
                visit(node, -1);
                return;
            }
            for (const auto& member : node.Members())
                findSkeletons(member.second);
        } else if (node.IsArray()) {
            for (const kv::Value& item : node.Items())
                findSkeletons(item);
        }
    };
    findSkeletons(vmdl);
    return bones;
}

std::unique_ptr<dmx::Datamodel> LoadDmx(const fs::path& path) {
    std::string err;
    auto dm = dmx::Datamodel::Load(path.u8string(), &err);
    if (!dm)
        throw runtime_error("cannot load " + path.u8string() + ": " + err);
    return dm;
}

// The skeleton's stock bones as nested Bone nodes. ModelDoc takes a bone's parent
// from the render mesh over any SkeletonFile; only a Bone node overrides it.
kv::Value::Array StockBoneNodes(const std::vector<Bone>& bones, const std::vector<Bone>& stock,
                                const std::vector<std::string>& authored) {
    auto isStock = [&](const std::string& name) {
        return std::any_of(stock.begin(), stock.end(),
                           [&](const Bone& s) { return _stricmp(s.name.c_str(), name.c_str()) == 0; });
    };
    std::vector<kv::Value> nodes(bones.size());
    std::vector<bool> emitted(bones.size(), false);
    // The replacement removes the original Bone nodes. Carry authored helpers
    // and their ancestors into that replacement too: the generated SkeletonFile
    // is disabled by default and cannot keep them alive by itself.
    for (size_t i = 0; i < bones.size(); ++i) {
        if (!isStock(bones[i].name) &&
            std::find(authored.begin(), authored.end(), bones[i].name) == authored.end()) continue;
        for (int parent = static_cast<int>(i); parent >= 0; parent = bones[parent].parent)
            emitted[parent] = true;
    }
    for (size_t i = 0; i < bones.size(); ++i) {
        const Bone& bone = bones[i];
        if (!emitted[i])
            continue;
        pm::RadianEuler e;
        pm::QuaternionAngles(bone.rotation, e);
        nodes[i] = kv::Value::Object{
            {"_class", "Bone"},
            {"name", bone.name},
            {"origin", kv::Value::Array{double(bone.position.x), double(bone.position.y), double(bone.position.z)}},
            {"angles", kv::Value::Array{double(e.y * pm::kRad2Deg), double(e.z * pm::kRad2Deg), double(e.x * pm::kRad2Deg)}},
            {"do_not_discard", true},
            {"children", kv::Value::Array{}},
        };
    }
    // children before parents, so each finished subtree moves into its parent
    kv::Value::Array roots;
    for (size_t i = bones.size(); i-- > 0;) {
        if (!emitted[i])
            continue;
        auto& siblings = bones[i].parent >= 0 ? nodes[bones[i].parent]["children"].Items() : roots;
        siblings.insert(siblings.begin(), std::move(nodes[i]));
    }
    return roots;
}

// Build the replacement VMDL (the generated skeleton as its only
// SkeletonFile, the stock hierarchy as Bone nodes, graph bindings). The first
// edit's backup and replacement are published only after the whole job succeeds.
std::string EditedModel(const std::string& originalText, kv::Value model, const Paths& paths,
               const kv::Value::Array& boneNodes) {
    const std::string skeletonFile = paths.relative + "/" + kSkeletonFile;
    // the generated SkeletonFile starts disabled; a rerun keeps the user's choice
    bool skeletonDisabled = true;
    std::function<void(kv::Value&)> strip = [&](kv::Value& node) {
        if (!node.IsObject() || !node.Has("children") || !node.At("children").IsArray())
            return;
        auto& children = node["children"].Items();
        children.erase(std::remove_if(children.begin(), children.end(), [&](const kv::Value& child) {
            const std::string cls = ClassOf(child);
            if (cls == "SkeletonFile" && child.Has("filename") &&
                _stricmp(child.At("filename").String().c_str(), skeletonFile.c_str()) == 0) {
                skeletonDisabled = Disabled(child);
                return true;
            }
            return (cls == "SkeletonFile" || cls == "Bone") && !Disabled(child);
        }), children.end());
        for (kv::Value& child : children)
            strip(child);
    };
    kv::Value* skeleton = nullptr;
    Walk(model, [&](kv::Value& node) {
        if (ClassOf(node) != "Skeleton")
            return;
        strip(node);
        if (!skeleton)
            skeleton = &node;
    });
    if (!skeleton) {
        auto& children = model["rootNode"]["children"].Items();
        children.push_back(kv::Value::Object{{"_class", "Skeleton"}, {"children", kv::Value::Array{}}});
        skeleton = &children.back();
    }
    if (!skeleton->Has("children"))
        (*skeleton)["children"] = kv::Value::Array{};
    auto& skeletonChildren = (*skeleton)["children"].Items();
    skeletonChildren.insert(skeletonChildren.begin(), kv::Value::Object{
        {"_class", "SkeletonFile"},
        {"name", "ag2_skeleton"},
        {"note", "Enable to keep custom bones that ModelDoc culls from the render mesh (unweighted bones).\n"
                 "The Bone nodes alone already set the stock hierarchy.\n"},
        {"disabled", skeletonDisabled},
        {"filename", skeletonFile},
        {"import_scale", 1.0},
        {"merge_behavior", "do_not_modify_existing"},
    });
    skeletonChildren.insert(skeletonChildren.begin() + 1, boneNodes.begin(), boneNodes.end());

    const std::string graph = paths.relative + "/" + kWorldGraphFile;
    const std::string uiGraph = paths.relative + "/" + kUiGraphFile;
    kv::Value* list = nullptr;
    Walk(model, [&](kv::Value& node) {
        if (ClassOf(node) == "AnimGraph2List")
            list = &node;
    });
    if (!list) {
        auto& children = model["rootNode"]["children"].Items();
        children.push_back(kv::Value::Object{{"_class", "AnimGraph2List"}, {"children", kv::Value::Array{}}});
        list = &children.back();
    }
    // The game plays the entries named worldmodel and uimodel (the UI preview).
    bool haveWorld = false, haveUi = false;
    for (auto& node : (*list)["children"].Items()) {
        const std::string cls = ClassOf(node);
        if (cls == "AnimGraph2" && node.Has("name") && node.At("name").String() == "worldmodel") {
            node["filename"] = graph;
            haveWorld = true;
        } else if (cls == "AnimGraph2" && node.Has("name") && node.At("name").String() == "uimodel") {
            node["filename"] = uiGraph;
            haveUi = true;
        } else if (cls == "AnimGraph2" && node.Has("name") && node.At("name").String() == "hudmodel") {
            node["note"] = "Bones outside viewmodel.vnmskel (twist bones, helpers) take the body's position.\n"
                           "Rename them in the arms DMX (e.g. arm_lower_L_twist_1 -> arm_lower_L_twist_1_fp)\n"
                           "and give them their own constraints.\n";
        }
    }
    auto& graphs = (*list)["children"].Items();
    graphs.erase(std::remove_if(graphs.begin(), graphs.end(), [&](const kv::Value& node) {
        return ClassOf(node) == "DefaultAnimGraph2" && node.Has("filename") && node.At("filename").String() == graph;
    }), graphs.end());
    if (!haveWorld)
        (*list)["children"].Items().push_back(
            kv::Value::Object{{"_class", "AnimGraph2"}, {"name", "worldmodel"}, {"filename", graph}});
    if (!haveUi)
        (*list)["children"].Items().push_back(
            kv::Value::Object{{"_class", "AnimGraph2"}, {"name", "uimodel"}, {"filename", uiGraph}});

    const size_t header = originalText.find("-->");
    if (header == std::string::npos)
        throw runtime_error("the VMDL has no KV3 header");
    return originalText.substr(0, header + 3) + "\n" + kv::TextBody(model) + "\n";
}

std::string SetupNotes(const Paths& paths, const SkeletonBuild& skeleton, const std::vector<std::string>& warnings,
                       bool wroteModel, bool firstPerson) {
    if (firstPerson) {
        std::string note = "AG2 FIRST-PERSON PROPORTIONS (experimental)\n\nSet the hudmodel AnimGraph2 to:\n  " +
            paths.relative + "/" + kViewGraphFile +
            "\n\nThe wrapper references the installed viewmodel graph and adds translation-only\n"
            "proportions from the explicit arms DMX. Body/UI graphs and model skeleton stay\n"
            "unchanged. This does not re-rig meshes or correct bind axes. Validate arms,\n"
            "weapon grip, recoil, inspect and reload in an isolated local game.\n";
        for (const auto& warning : warnings) note += "WARNING: " + warning + "\n";
        return note;
    }
    std::string note = "AG2 PROPORTIONS (experimental)\n\n"
                       "Use this as the VMDL's only SkeletonFile, with its stock bones as nested Bone nodes\n"
                       "(write_model does this):\n  " +
                       paths.relative + "/" + kSkeletonFile + "\n\n";
    auto list = [&](const char* title, const std::vector<std::string>& names) {
        if (names.empty())
            return;
        note += title;
        for (const std::string& name : names)
            note += "  " + name + "\n";
        note += "\n";
    };
    list("Stock bones added at their stock offset:\n", skeleton.added);
    list("Bones moved under their stock parent (model-space pose kept):\n", skeleton.reparented);
    list("Bones kept from VMDL Bone nodes:\n", skeleton.fromNodes);
    note += "Set the worldmodel AnimGraph2 to:\n  " + paths.relative + "/" + kWorldGraphFile + "\n\n";
    if (wroteModel)
        note += "The input VMDL was edited in place; its first backup is <model>.vmdl.bak.\n\n";
    note += "Attachment starting points (keep any you already tuned):\n"
            "  weapon         parent wpn     origin 0 0 0         angles 0 0 0\n"
            "  weapon_hand_r  parent hand_R  origin -2.6 -1.4 0   angles 0 180 0\n"
            "  weapon_hand_l  parent hand_L  origin 2.6 1.4 0     angles 0 0 180\n\n"
            "Keep viewmodel/UI graph entries. The clip changes translations only; it does not\n"
            "fix bind axes or re-rig the mesh. Compile the VMDL in ModelDoc, then test pistol,\n"
            "rifle, knife, reload, crouch, aim pitch, movement and first-person arms.\n\n";
    for (const std::string& warning : warnings)
        note += "WARNING: " + warning + "\n";
    return note;
}

kv::Value Report(const Job& job, const std::string& rig, const std::string& pose, const Paths& paths,
                 const std::vector<Bone>& stock, const std::vector<Bone>& target) {
    auto triple = [](const pm::Vector3& v) {
        return kv::Value::Array{double(v.x), double(v.y), double(v.z)};
    };
    kv::Value::Array bones;
    for (size_t i = 0; i < stock.size(); ++i)
        bones.push_back(kv::Value::Object{{"bone", stock[i].name},
                                          {"reference", triple(stock[i].position)},
                                          {"target", triple(target[i].position)}});
    return kv::Value::Object{
        {"model", job.vmdl.generic_u8string()},
        {"rig", rig},
        {"pose", pose},
        {"graph", paths.relative + "/" + (job.firstPerson ? kViewGraphFile : kWorldGraphFile)},
        {"firstPerson", job.firstPerson},
        {"boneTranslations", bones},
        {"compiled", false},
    };
}

bool IsAxisNote(const std::string& warning) { return warning.rfind("bone axes differ", 0) == 0; }

// What the user has to do next, on the console; the full notes are --debug only.
void PrintSummary(const Paths& paths, const SkeletonBuild& skeleton, const std::vector<std::string>& warnings,
                  const Job& job, bool generateOnly) {
    std::cout << (job.firstPerson ? "First-person diagnostic skeleton " : "Skeleton ") << paths.relative << "/" << kSkeletonFile << ": " << skeleton.added.size()
              << " stock bones added, " << skeleton.reparented.size() << " moved under their stock parent\n";
    if (job.writeModel)
        std::cout << "Edited " << job.vmdl.filename().u8string() << " (original kept as "
                  << job.vmdl.filename().u8string() << ".bak)\n";
    else if (job.firstPerson)
        std::cout << "Set the hudmodel AnimGraph2 to " << paths.relative << "/" << kViewGraphFile << "\n";
    else
        std::cout << "Run with write_model to make it the VMDL's only SkeletonFile with its stock bones as Bone nodes\n"
                  << "Set the worldmodel AnimGraph2 to " << paths.relative << "/" << kWorldGraphFile << "\n"
                  << "Set the uimodel AnimGraph2 to " << paths.relative << "/" << kUiGraphFile << "\n";
    const auto axes = std::count_if(warnings.begin(), warnings.end(), IsAxisNote);
    for (const std::string& warning : warnings)
        if (!IsAxisNote(warning))
            std::cout << "WARNING: " << warning << '\n';
    if (axes)
        std::cout << "WARNING: " << axes << " bones have axes unlike stock and may be placed off "
                  << "(--debug lists them)\n";
    if (generateOnly) {
        std::cout << "WARNING: Generated VMDL source assets were not compiled. Existing generated *_c files "
                     "were removed; do not use *_c until these sources are compiled with ResourceCompiler.\n"
                     "Next step: run this job again without --generate-only (or compile the generated sources "
                     "in ModelDoc/ResourceCompiler).\n";
    }
}

} // namespace

void Generate(const Job& job, const Options& options) {
    std::cout << "Processing " << job.vmdl.u8string() << '\n';
    Paths paths = Locate(job.vmdl);
    if (job.firstPerson) {
        if (job.modelDmx.empty()) throw runtime_error("first_person requires an explicit arms model_dmx");
        paths.output += "_viewmodel";
        paths.relative = paths.output.lexically_relative(paths.addon).generic_u8string();
    }
    // Register every possible output so interrupted jobs remain recoverable
    // even when this run changes debug/generate-only/write_model switches.
    std::vector<fs::path> destinations{job.vmdl, fs::u8path(job.vmdl.u8string() + ".bak")};
    for (const char* name : kGeneratedFiles) destinations.push_back(paths.output / name);
    const fs::path compiledOutput = paths.cs2 / "game/csgo_addons" / paths.addon.filename() / fs::u8path(paths.relative);
    for (const char* name : {kClipFile, kWorldGraphFile, kUiGraphFile, kViewGraphFile})
        destinations.push_back(compiledOutput / fs::u8path(std::string(name) + "_c"));
    OutputTransaction transaction(job.vmdl, destinations);
    // Recover saved user outputs even if the game data disappeared after a
    // killed run. Installation/toolchain availability belongs after recovery.
    if (!fs::exists(paths.cs2 / "game/csgo/pak01_dir.vpk"))
        throw runtime_error("no CS2 install above the addon (game/csgo/pak01_dir.vpk is missing)");
    for (const fs::path* input : {&job.vmdl, &job.modelDmx, &job.proportions, &job.vnmskel})
        if (!input->empty() && !fs::is_regular_file(*input))
            throw runtime_error("not found: " + input->u8string());
    if (!options.generateOnly)
        PreflightCompiler(options, paths);
    const std::string vmdlText = ReadText(job.vmdl);
    kv::Value vmdl = kv::ParseText(vmdlText);
    const Vpk package(paths.cs2 / "game/csgo/pak01_dir.vpk");
    std::vector<uint8_t> skeletonBytes = package.Read(std::string(job.firstPerson ? kStockViewSkeleton : kStockSkeleton) + "_c");
    const StockSkeleton installed = ReadStockSkeleton(skeletonBytes);
    if (!job.vnmskel.empty()) {
        skeletonBytes = kv::ReadFile(job.vnmskel.u8string());
        RequireSameSkeleton(installed, ReadStockSkeleton(skeletonBytes));
    }
    const StockSkeleton viewmodel = ReadStockSkeleton(package.Read(std::string(kStockViewSkeleton) + "_c"));
    const RigSource rigSource = FindRig(vmdl, job, paths, viewmodel.bones, installed.bones);
    const std::vector<Bone> nodes = BoneNodes(vmdl);
    const std::string clip = paths.relative + "/" + kClipFile;
    const auto stockGraphPath = job.firstPerson ? kStockViewGraph : kStockGraph;
    const std::vector<uint8_t> graphBytes = package.Read(std::string(stockGraphPath) + "_c");
    const std::vector<uint8_t> uiGraphBytes = job.firstPerson ? std::vector<uint8_t>{} : package.Read(std::string(kStockUiGraph) + "_c");
    const kv::Value graph = WrapperGraph(kv::ReadResource(graphBytes), stockGraphPath, clip, job.firstPerson);
    const kv::Value uiGraph = job.firstPerson ? kv::Value{} : WrapperGraph(kv::ReadResource(uiGraphBytes), kStockUiGraph, clip);

    std::vector<std::string> warnings;
    const std::vector<Bone> modelStock = job.firstPerson ? installed.bones : ModelStock(installed.bones);
    const auto rig = ReadRig(*LoadDmx(rigSource.path), rigSource.scale, false);
    const SkeletonBuild skeleton =
        BuildSkeleton(rig, modelStock, nodes, job.firstPerson);
    for (const std::string& bone : skeleton.added)
        warnings.push_back("custom model is missing stock bone " + bone +
                           "; added to the generated skeleton at its stock offset");
    for (const std::string& change : skeleton.reparented)
        warnings.push_back("custom model bone parenting differs from stock: " + change +
                           "; corrected in the generated skeleton with the model-space bind pose kept");
    const std::vector<Bone> target = job.firstPerson
        ? TargetViewPose(job.proportions.empty() ? rig : ReadRig(*LoadDmx(job.proportions),rigSource.scale,true),
                         installed.bones,warnings)
        : job.proportions.empty()
            ? TargetPose(skeleton.bones, installed.bones, warnings)
            : TargetPose(BuildSkeleton(ReadRig(*LoadDmx(job.proportions), rigSource.scale, true), installed.bones, {})
                             .bones,
                         installed.bones, warnings);
    // Weapon attachments are the user's to author and tune; only their bones are checked.
    struct WeaponAttachment { const char *name, *parent; };
    const WeaponAttachment kAttachments[] = {{"weapon", "wpn"}, {"weapon_hand_r", "hand_R"}, {"weapon_hand_l", "hand_L"}};
    for (const WeaponAttachment& want : kAttachments) {
        if (job.firstPerson) break;
        std::string parent;
        bool found = false;
        Walk(vmdl, [&](kv::Value& node) {
            if (ClassOf(node) == "Attachment" && node.Has("name") && node.At("name").String() == want.name) {
                found = true;
                parent = node.Has("parent_bone") ? node.At("parent_bone").String() : std::string();
            }
        });
        if (!found)
            warnings.push_back(std::string("no ") + want.name + " attachment; add one on " + want.parent +
                               " or the weapon will not follow the hands");
        else if (_stricmp(parent.c_str(), want.parent) != 0)
            warnings.push_back(std::string("attachment ") + want.name + " is on " + (parent.empty() ? "no bone" : parent) +
                               "; Valve's agents put it on " + want.parent);
    }

    // ModelDoc refuses a primary root bone that has a parent
    Walk(vmdl, [&](kv::Value& node) {
        if (ClassOf(node) != "BoneMarkupList" || !node.Has("primary_root_bone"))
            return;
        const std::string root = node.At("primary_root_bone").String();
        for (const Bone& bone : skeleton.bones)
            if (!root.empty() && _stricmp(bone.name.c_str(), root.c_str()) == 0 && bone.parent >= 0)
                warnings.push_back("BoneMarkupList primary_root_bone \"" + root + "\" sits under " +
                                   skeleton.bones[bone.parent].name +
                                   ", so ModelDoc will refuse to compile; remove it or name a root bone");
    });
    std::sort(warnings.begin(), warnings.end());
    warnings.erase(std::unique(warnings.begin(), warnings.end()), warnings.end());

    // A target equal to stock compiles to a clip that changes nothing.
    float change = 0;
    for (size_t i = 0; i < target.size(); ++i)
        change = std::max(change, std::abs(target[i].position.x - installed.bones[i].position.x) +
                                      std::abs(target[i].position.y - installed.bones[i].position.y) +
                                      std::abs(target[i].position.z - installed.bones[i].position.z));
    if (change < 1e-3f)
        warnings.insert(warnings.begin(), "the target pose equals the stock skeleton, so the clip changes nothing");

    Paths staged = paths;
    staged.output = transaction.StageRoot() / "sources";
    std::cout << "Output: " << paths.output.u8string() << '\n';

    for (const char* name : {kSkeletonFile, kReferenceFile})
        fs::create_directories((staged.output / name).parent_path());
    WriteSkeleton(staged.output / kSkeletonFile, skeleton.bones);
    WriteHeldPose(staged.output / kReferenceFile, installed.bones, installed.lowLodCount);
    WriteHeldPose(staged.output / kProportionsFile, target, installed.lowLodCount);
    const kv::Value descriptor = SkeletonDescriptor(ReadStockSkeleton(skeletonBytes), paths.relative + "/" + kReferenceFile);
    kv::WriteFile((staged.output / kClipFile).u8string(), kv::WriteText(ProportionClip(paths.relative, job.firstPerson)));
    kv::WriteFile((staged.output / (job.firstPerson ? kViewGraphFile : kWorldGraphFile)).u8string(), kv::WriteText(graph));
    if (!job.firstPerson) kv::WriteFile((staged.output / kUiGraphFile).u8string(), kv::WriteText(uiGraph));
    if (job.writeModel) {
        const fs::path stagedModel = transaction.StageRoot() / "model.vmdl";
        if (job.firstPerson) {
            bool found = false;
            Walk(vmdl, [&](kv::Value& node) {
                if (ClassOf(node) == "AnimGraph2" && node.Has("name") && node.At("name").String() == "hudmodel") {
                    node["filename"] = paths.relative + "/" + kViewGraphFile;
                    found = true;
                }
            });
            if (!found) throw runtime_error("first_person write_model requires an enabled hudmodel AnimGraph2 entry");
            const auto header = vmdlText.find("-->");
            if (header == std::string::npos) throw runtime_error("the VMDL has no KV3 header");
            kv::WriteFile(stagedModel.u8string(), vmdlText.substr(0,header+3) + "\n" + kv::TextBody(vmdl) + "\n");
        } else {
            kv::WriteFile(stagedModel.u8string(), EditedModel(vmdlText, vmdl, paths,
                StockBoneNodes(skeleton.bones, modelStock, skeleton.fromNodes)));
        }
        fs::path backup = job.vmdl;
        backup += ".bak";
        const auto backupStatus = fs::symlink_status(backup);
        if (fs::exists(backupStatus) && !fs::is_regular_file(backupStatus))
            throw runtime_error("the VMDL backup is not a regular file: " + backup.u8string());
        if (!fs::exists(backupStatus)) {
            const fs::path stagedBackup = transaction.StageRoot() / "model.vmdl.bak";
            kv::WriteFile(stagedBackup.u8string(), vmdlText);
            transaction.Replace(stagedBackup, backup, true);
        }
        transaction.Replace(stagedModel, job.vmdl);
    }
    // what the clip was built from, for issue reports
    if (options.debug) {
        const std::string rigName = rigSource.path.generic_u8string();
        const std::string poseName = job.proportions.empty() ? rigName : job.proportions.generic_u8string();
        kv::WriteFile((staged.output / "debug/skeleton_descriptor.kv3").u8string(), kv::WriteText(descriptor));
        kv::WriteFile((staged.output / "debug/report.kv3").u8string(),
                      kv::WriteText(Report(job, rigName, poseName, paths, installed.bones, target)));
        kv::WriteFile((staged.output / "debug/MODEL_SETUP.txt").u8string(),
                      SetupNotes(paths, skeleton, warnings, job.writeModel, job.firstPerson));
    }
    if (!options.generateOnly) {
        const fs::path stagedCompiled = transaction.StageRoot() / "compiled";
        Compile(options, staged, skeletonBytes, graphBytes, uiGraphBytes, descriptor, stagedCompiled, job.firstPerson);
        const fs::path published = paths.cs2 / "game/csgo_addons" / paths.addon.filename() / fs::u8path(paths.relative);
        for (const char* source : RuntimeAssets(job.firstPerson)) {
            const fs::path name = fs::u8path(std::string(source) + "_c");
            transaction.Replace(stagedCompiled / name, published / name);
        }
    } else {
        // A previous full run may have left compiled resources beside these
        // newly generated sources. Remove them in the same transaction so a
        // caller cannot accidentally consume an *_c file made from an older
        // VMDL/DMX/graph set.
        RemoveUncompiledResources(transaction, compiledOutput, {kClipFile, kWorldGraphFile, kUiGraphFile, kViewGraphFile});
    }
    for (const char* name : kGeneratedFiles) {
        if (fs::is_regular_file(staged.output / name)) {
            transaction.Replace(staged.output / name, paths.output / name);
        } else {
            // Optional debug output from the previous run is obsolete, unless
            // it is also one of this job's explicitly supplied inputs.
            bool input = false;
            for (const fs::path& source : {job.proportions, job.vnmskel, rigSource.path})
                if (!source.empty() && fs::exists(paths.output / name) && fs::equivalent(paths.output / name, source))
                    input = true;
            if (!input)
                transaction.Remove(paths.output / name);
        }
    }
    transaction.Commit();
    if (options.generateOnly) {
        // Keep the addon tree tidy when the three generated files were the
        // only contents of the old compiled-resource directory. Failure here
        // is harmless: the transaction has already removed the stale files.
        std::error_code ec;
        fs::remove(compiledOutput / "anims", ec);
        ec.clear();
        fs::remove(compiledOutput / "graphs", ec);
        ec.clear();
        fs::remove(compiledOutput, ec);
    }
    PrintSummary(paths, skeleton, warnings, job, options.generateOnly);
    std::cout << "DONE: " << paths.output.u8string()
              << (options.generateOnly ? " (source assets only)\n" : " (graph and clip compiled)\n");
}

} // namespace ag2
