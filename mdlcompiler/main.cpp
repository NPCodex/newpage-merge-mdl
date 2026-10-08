// mdlcompiler - Source engine model compiler (.mdl/.vvd/.vtx/.phy).
//
// Usage:
//   mdlcompiler <file.pulseqc> [-game <dir>] [-pause]

#include <cctype>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <initializer_list>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

#include "compile.h"
#include "fatalerror.h"
#include "dependencies.h"
#include "perf.h"
#include "pulselimits.h"
#include "qcloader.h"
#include "writer.h"
#include "branding.h"
#include "sequence_remap.h"
#include "resources.h"
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#else
#include <sys/resource.h>
#endif

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

// Defined by CMake from TOOL_VERSION, same value the .exe version resource gets.
static constexpr const char* kAppVersion = PULSEMODEL_VERSION;

using pulse::fatal::Fail;
static const char*& g_stage = pulse::fatal::g_stage;

static void PrintHeader() {
    newpage::PrintBanner("Model Compiler", kAppVersion, "49");
}

static int Usage() {
    std::printf("usage: NewPageMergeMDL <file.qc|file.pulseqc> [-game <dir>]\n");
    std::printf("\n");
    std::printf("  -game <dir>   mod dir to install into; output goes to\n");
    std::printf("                <dir>\\models\\<modelname>.mdl (defaults to the QC directory)\n");
    std::printf("  -OutDir <dir> CE output root, relative to the QC directory; takes precedence over -game\n");
    std::printf("  -IncludePrefix <include> <prefix> / -IncludeAnimPrefix <prefix>\n");
    std::printf("  -OverrideFlexControllers / -AllowDuplicationFlexControllers / -AddInvStudioFlexes\n");
    std::printf("  -ZeroFlexDecay / -DefaqScale / -IgnoreDMXDefaq / -IgnoreDefaultFlexKey\n");
    std::printf("  -EyeballScale <scale> / -IgnoreEyeballScaling / -IgnoreEyeballIrisScale / -IgnoreEyelid\n");
    std::printf("  -ComputeDeltaNormals / -ComputeWrinkles / -ComputeNormalsAndWrinkles\n");
    std::printf("  -RemapFlexToGlobal / -CollisionBindToOneBone / -AllowCollapseVertexBone / -HBoxIgnoreChild\n");
    std::printf("  -OutputBufferSize <MB> / -MDLOutputBufferSize <MB> / -ANIOutputBufferSize <MB>\n");
    std::printf("                CE switches also accept $commands in QC; see COMPATIBILITY.md\n");
    std::printf("  -modelname <path>   overrides $modelname\n");
    std::printf("  -vtxformat <0|1>\n");
    std::printf("                .vtx layout, overriding the script's $vtxformat.\n");
    std::printf("                0 = legacy (TF2/L4D2/GMod/HL2), 1 = full (SFM/CS:GO/ASW)\n");
    std::printf("  -nodx80       skip the DirectX 8 .dx80.vtx output (also $nodx80).\n");
    std::printf("  -noremap      use script sequence order instead of preserving existing .mdl order\n");
    std::printf("  -checksequenceorder preserve existing sequence order (default)\n");
    std::printf("  -maxbones N  set final output bone limit (1..256)\n");
    std::printf("  -Dname value pin a QC variable (NekoMDL syntax)\n");
    std::printf("  -playbeep    play a completion/error tone\n");
    std::printf("  -DontDestroy CE alias for default error-output preservation (no cleanup)\n");
    std::printf("  -nvtristrip / -usenvtristrip  use the legacy NvTriStrip backend\n");
    std::printf("  -reloadhlmv  refresh the matching HLMV window after writing (Windows)\n");
    std::printf("                dx80 is only written when the vtx format is 0\n");
    std::printf("  -includesearchdir <dir>\n");
    std::printf("                extra fallback dir for $include, searched after any\n");
    std::printf("                $addincludesearchdir; repeatable\n");
    std::printf("  -filesearchdir <dir>\n");
    std::printf("                extra fallback dir for source files, searched after\n");
    std::printf("                any $addsearchdir; repeatable\n");
    std::printf("  -tempcontent <dir>   synonym for -filesearchdir\n");
    std::printf("  -defvar <name> <value>\n");
    std::printf("                define a .pulseqc script variable ($name$) before the\n");
    std::printf("                script runs; repeatable. The script cannot override it\n");
    std::printf("  -striplods    ignore all $lod and $shadowlod commands\n");
    std::printf("  -cullanims    aggressively cull unreferenced animations; overrides the QC\n");
    std::printf("  -MostlyOpaque force translucent two-pass rendering (also $mostlyopaque)\n");
    std::printf("  -AlwaysCollapseByPrefix <prefix> force-collapse matching bones; repeatable\n");
    std::printf("  -forcewritevertexdata\n");
    std::printf("                save .vvd/.vtx even when the model has no geometry;\n");
    std::printf("                same as $forcewritevertexdata in the script\n");
    std::printf("  -minlod <lod> discard higher-detail LODs and promote this LOD to root;\n");
    std::printf("                overrides $minlod in the script\n");
    std::printf("  -definebones  print the compiled skeleton as $definebone lines and stop\n");
    std::printf("  -verify       compile the model without writing output files\n");
    std::printf("  -dumpmaterials print the names of materials used by the model\n");
    std::printf("  -dumpcommands print every accepted $command, one per line, and exit\n");
    std::printf("  -dumpprocedural\n");
    std::printf("                print the final bone names and the jiggle, driver and aim-at\n");
    std::printf("                bone rules as @proc lines on stdout, then stop; no files written\n");
    std::printf("  -stdin        read the script's text from stdin; the script path is still\n");
    std::printf("                given and resolves relative paths as if the text were saved there\n");
    std::printf("  -dumpdependencies\n");
    std::printf("                after a successful compile, print every file it read as\n");
    std::printf("                @dep <script|include|source> <fnv1a-64 hex> <absolute path>\n");
    std::printf("  -pause        wait for a keypress before exiting (drag-and-drop runs)\n");
    std::printf("  -perfmetrics  print wall time in ms for each stage of the compile\n");
    std::printf("  -perfjson <file> write stage timings and peak working set as JSON\n");
    std::printf("  -steamdir <dir> override Steam root for gameinfo AppID mounts\n");
    return 1;
}

// -definebones: dump the final bone table in $definebone form so it can be
// pasted back into the script and pin the skeleton (reference DumpDefineBones).
// Both sextets are the compiled matrices, so the second one marks every bone
// pre-aligned - a re-compile must not realign an already-realigned rig.
static void DumpDefineBones(const pulse::compile::CompiledModel& model) {
    std::printf("\n--- $definebone (%zu bones) ---------------------------------\n\n",
                model.bones.size());
    for (const pulse::compile::Bone& b : model.bones) {
        const pulse::math::Vector3 rot = pulse::math::MatrixAnglesDeg(b.rawLocal);
        const pulse::math::Vector3 realignRot = pulse::math::MatrixAnglesDeg(b.srcRealign);
        std::printf("$definebone \"%s\" \"%s\" %f %f %f %f %f %f %f %f %f %f %f %f\n",
                    b.name.c_str(),
                    b.parent >= 0 ? model.bones[b.parent].name.c_str() : "",
                    b.rawLocal.m[0][3], b.rawLocal.m[1][3], b.rawLocal.m[2][3],
                    rot.x, rot.y, rot.z,
                    b.srcRealign.m[0][3], b.srcRealign.m[1][3], b.srcRealign.m[2][3],
                    realignRot.x, realignRot.y, realignRot.z);
    }
    std::printf("\n------------------------------------------------------------\n");
}

static void ProcString(const std::string& s) {
    std::fputs(" \"", stdout);
    for (const char c : s) {
        if (c == '"' || c == '\\')
            std::putchar('\\');
        std::putchar(c);
    }
    std::putchar('"');
}

static void ProcFloats(std::initializer_list<float> v) {
    for (const float x : v)
        std::printf(" %.9g", static_cast<double>(x));
}

// -dumpprocedural: the procedural bone rules with the values the .mdl stores, bones
// named rather than indexed, one "@proc <kind>" line each; quoted names escape " and \.
static void DumpProcedural(const pulse::compile::CompiledModel& m) {
    auto boneName = [&](int i) -> std::string {
        return i >= 0 && i < static_cast<int>(m.bones.size()) ? m.bones[i].name : std::string();
    };

    for (const pulse::compile::Bone& b : m.bones) {
        std::fputs("@proc bone", stdout);
        ProcString(b.name);
        std::putchar('\n');
    }

    for (const pulse::compile::JiggleBone& j : m.jigglebones) {
        std::fputs("@proc jiggle", stdout);
        ProcString(boneName(j.bone));
        std::printf(" %d", j.flags);
        ProcFloats({j.length, j.tipMass, j.yawStiffness, j.yawDamping, j.pitchStiffness,
                       j.pitchDamping, j.alongStiffness, j.alongDamping, j.angleLimit, j.minYaw,
                       j.maxYaw, j.yawFriction, j.yawBounce, j.minPitch, j.maxPitch,
                       j.pitchFriction, j.pitchBounce, j.baseMass, j.baseStiffness, j.baseDamping,
                       j.baseMinLeft, j.baseMaxLeft, j.baseLeftFriction, j.baseMinUp, j.baseMaxUp,
                       j.baseUpFriction, j.baseMinForward, j.baseMaxForward, j.baseForwardFriction,
                       j.boingImpactSpeed, j.boingImpactAngle, j.boingDampingRate,
                       j.boingFrequency, j.boingAmplitude});
        std::putchar('\n');
    }

    // 12 floats per trigger, as many triggers as the line holds
    for (const pulse::compile::ProceduralBone& p : m.proceduralbones) {
        std::fputs("@proc driver", stdout);
        ProcString(boneName(p.helper));
        ProcString(boneName(p.driver));
        for (const pulse::compile::ProceduralBoneTrigger& tr : p.triggers) {
            // same double-then-narrow as the writer
            const float invTolerance = static_cast<float>(1.0 / static_cast<double>(tr.tolerance));
            ProcFloats({invTolerance, tr.trigger.x, tr.trigger.y, tr.trigger.z, tr.trigger.w,
                        tr.pos.x, tr.pos.y, tr.pos.z,
                        tr.quat.x, tr.quat.y, tr.quat.z, tr.quat.w});
        }
        std::putchar('\n');
    }

    for (const pulse::compile::AimAtBone& a : m.aimatbones) {
        std::fputs("@proc aimat", stdout);
        ProcString(boneName(a.bone));
        ProcString(boneName(a.parent));
        std::fputs(a.aimAttach == -1 ? " bone" : " attachment", stdout);
        ProcString(a.aimAttach == -1 ? boneName(a.aimBone) : a.aimname);
        ProcFloats({a.aimvector.x, a.aimvector.y, a.aimvector.z, a.upvector.x, a.upvector.y,
                    a.upvector.z, a.basepos.x, a.basepos.y, a.basepos.z});
        std::putchar('\n');
    }
    std::fputs("@proc end\n", stdout);
}

static std::string ReadStdin() {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
#endif
    std::string text;
    char buf[65536];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), stdin)) > 0)
        text.append(buf, n);
    return text;
}

static int RunCompile(int argc, char** argv) {
    if (argc < 2)
        return Usage();

    g_stage = "command line";
    const char* script = nullptr;
    std::string outdir;
    std::string gameDirectory,steamDirectory;
    std::string perfJson;
    std::string modelname; // -modelname: overrides the script's $modelname
    int vtxFormat = -1; // unset; otherwise wins over the script's $vtxformat
    bool noDx80 = false; // -nodx80: force-skip .dx80.vtx, overriding the script
    bool noRemap = false;
    int launchMinLod = -1;
    bool stripLods = false;
    bool forceWriteVertexData = false;
    bool definebones = false;
    bool verify = false;
    bool dumpMaterials = false;
    bool dumpProcedural = false;
    bool scriptFromStdin = false;
    bool dumpDependencies = false;
    bool cullAnims = false;
    bool mostlyOpaque = false;
    bool reloadHlmv=false;
    std::string cePrelude;
    std::vector<std::string> collapsePrefixes;
    pulse::loader::ScriptVars defvars;
    pulse::loader::SearchDirs includeDirs, fileDirs;
    for (int i = 1; i < argc; ++i) {
        std::string option=argv[i];
        for(char& ch:option) ch=static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
        const std::vector<std::string> ceFlags={"overrideflexcontrollers","allowduplicationflexcontrollers",
            "addinvstudioflexes","zeroflexdecay","defaqscale","ignoredmxdefaq","ignoreeyelid",
            "ignoreeyeballscaling","ignoreeyeballirisscale","ignoredefaultflexkey","collisionbindtoonebone",
            "allowcollapsevertexbone","hboxignorechild","computewrinkles","computedeltanormals",
            "computenormalsandwrinkles","remapflextoglobal","mostlyopaque","cebonerules",
            "uselegacyclampmethod","uselegacystripify","dontdestroy"};
        std::string ceName=option.size()>1 && option[0]=='-' ? option.substr(1) : "";
        if(std::find(ceFlags.begin(),ceFlags.end(),ceName)!=ceFlags.end()) {
            if(ceName=="mostlyopaque") mostlyOpaque=true;
            cePrelude+="$"+ceName+"\n"; continue;
        }
        int ceValues=ceName=="includeprefix" ? 2 :
            (ceName=="includeanimprefix" || ceName=="eyeballscale" || ceName=="outdir" ||
             ceName=="maxbones" || ceName=="outputbuffersize" || ceName=="mdloutputbuffersize" || ceName=="anioutputbuffersize" ? 1 : 0);
        if(ceValues) {
            if(i+ceValues>=argc) return Fail("bad option",option+" needs "+std::to_string(ceValues)+" argument(s)");
            cePrelude+="$"+ceName;
            for(int j=0;j<ceValues;++j) {
                std::string value=argv[++i];
                if(value.find_first_of("\"\r\n")!=std::string::npos) return Fail("bad option",option+" contains invalid characters");
                cePrelude+=" \""+value+"\"";
            }
            cePrelude+="\n"; continue;
        }
        // -game is studiomdl's name for it: the mod dir the model installs
        // into. The writer already roots output at <dir>/models, so it is the
        // same value as -outdir.
        if ((std::strcmp(argv[i], "-game") == 0 || std::strcmp(argv[i], "-outdir") == 0) &&
            i + 1 < argc) {
            outdir = argv[++i];
            if(std::strcmp(argv[i-1],"-game")==0)gameDirectory=outdir;
        } else if(std::strcmp(argv[i],"-steamdir")==0 && i+1<argc) {
            steamDirectory=argv[++i];
        } else if (std::strcmp(argv[i], "-modelname") == 0) {
            if (i + 1 >= argc)
                return Fail("bad option", "-modelname needs a model path");
            modelname = argv[++i];
        } else if (argv[i][0]=='-' && argv[i][1]=='D' && argv[i][2]) {
            if(i+1>=argc) return Fail("bad option","-Dname needs a value");
            std::string name=argv[i]+2; defvars.emplace_back(name,argv[++i]);
        } else if (std::strcmp(argv[i], "-checksequenceorder")==0) {
            noRemap=false;
        } else if (std::strcmp(argv[i], "-defvar") == 0) {
            // a .pulseqc $definevariable, set from the launch line and pinned
            if (i + 2 >= argc)
                return Fail("bad option", "-defvar needs two arguments: <name> <value>");
            defvars.emplace_back(argv[i + 1], argv[i + 2]);
            i += 2;
        } else if (std::strcmp(argv[i], "-includesearchdir") == 0) {
            if (i + 1 >= argc)
                return Fail("bad option", "-includesearchdir needs a directory");
            includeDirs.emplace_back(argv[++i]);
        } else if (std::strcmp(argv[i], "-filesearchdir") == 0 ||
                   std::strcmp(argv[i], "-tempcontent") == 0) {
            if (i + 1 >= argc)
                return Fail("bad option", std::string(argv[i]) + " needs a directory");
            fileDirs.emplace_back(argv[++i]);
        } else if (std::strcmp(argv[i], "-vtxformat") == 0 && i + 1 < argc) {
            vtxFormat = std::atoi(argv[++i]);
            if (vtxFormat != 0 && vtxFormat != 1)
                return Fail("bad option", std::string("-vtxformat must be 0 or 1, got \"") +
                                              argv[i] + "\"");
        } else if (std::strcmp(argv[i], "-minlod") == 0) {
            if (i + 1 >= argc)
                return Fail("bad option", "-minlod needs a non-negative LOD index");
            const std::string value = argv[++i];
            try {
                size_t used = 0;
                launchMinLod = std::stoi(value, &used);
                if (used != value.size() || launchMinLod < 0)
                    throw std::invalid_argument("invalid LOD index");
            } catch (const std::exception&) {
                return Fail("bad option", "-minlod needs a non-negative LOD index, got \"" +
                                              value + "\"");
            }
        } else if (std::strcmp(argv[i], "-cullanims") == 0) {
            cullAnims = true;
        } else if (option=="-nvtristrip" || option=="-usenvtristrip") {
            cePrelude += "$UseLegacyStripify\n";
        } else if (std::strcmp(argv[i],"-reloadhlmv")==0) {
            reloadHlmv=true;
        } else if (std::strcmp(argv[i],"-playbeep")==0) {
            // Completion tone is emitted by main(), including compile failures.
        } else if (std::strcmp(argv[i], "-noremap") == 0) {
            noRemap = true;
        } else if (std::strcmp(argv[i], "-MostlyOpaque") == 0 ||
                   std::strcmp(argv[i], "-mostlyopaque") == 0) {
            mostlyOpaque = true;
        } else if (std::strcmp(argv[i], "-AlwaysCollapseByPrefix") == 0 ||
                   std::strcmp(argv[i], "-alwayscollapsebyprefix") == 0) {
            if (i + 1 >= argc || !argv[i + 1][0] || argv[i + 1][0] == '-')
                return Fail("bad option", "-AlwaysCollapseByPrefix needs a non-empty prefix");
            collapsePrefixes.emplace_back(argv[++i]);
        } else if (std::strcmp(argv[i], "-nodx80") == 0) {
            noDx80 = true;
        } else if (std::strcmp(argv[i], "-striplods") == 0) {
            stripLods = true;
        } else if (std::strcmp(argv[i], "-forcewritevertexdata") == 0) {
            forceWriteVertexData = true;
        } else if (std::strcmp(argv[i], "-definebones") == 0) {
            definebones = true;
        } else if (std::strcmp(argv[i], "-verify") == 0) {
            verify = true;
        } else if (std::strcmp(argv[i], "-dumpprocedural") == 0) {
            dumpProcedural = true;
        } else if (std::strcmp(argv[i], "-stdin") == 0) {
            scriptFromStdin = true;
        } else if (std::strcmp(argv[i], "-dumpdependencies") == 0) {
            dumpDependencies = true;
            pulse::dependencies::g_enabled = true;
        } else if (std::strcmp(argv[i], "-dumpmaterials") == 0) {
            dumpMaterials = true;
        } else if(std::strcmp(argv[i],"-perfjson")==0 && i+1<argc) {
            perfJson=argv[++i];
            pulse::perf::g_enabled = true;
        } else if (std::strcmp(argv[i], "-perfmetrics") == 0) {
            pulse::perf::g_enabled = true;
        } else if (std::strcmp(argv[i], "-pause") == 0) {
            pulse::fatal::g_pause = true;
        } else if (argv[i][0] == '-') {
            // studiomdl GUI front ends pass switches we do not have (-nop4,
            // -verbose, ...). Warn and carry on rather than refusing to run.
            std::printf("warning: ignoring unknown option: %s\n", argv[i]);
        } else if (!script || pulse::loader::IsQcScriptPath(argv[i])) {
            // an ignored option may have eaten a value we now see as
            // positional, so a real script extension always wins
            script = argv[i];
        }
    }
    if (!script)
        return Usage();

    std::printf("Compiling: %s\n", script);

    using Clock = std::chrono::steady_clock;
    const bool timing = pulse::perf::g_enabled;
    auto t0 = Clock::now();
    auto ms = [](Clock::time_point a, Clock::time_point b) {
        return std::chrono::duration<double, std::milli>(b - a).count();
    };

    // .pulseqc (keyvalues1) is the only front end. The keyvalues2 .pulsemdl
    // loader is halted indefinitely - pulseloader.cpp is out of the build.
    if (!pulse::loader::IsQcScriptPath(script))
        return Fail("unsupported script",
                    std::string(script) + ": only .pulseqc/.qc compile scripts are supported");

    std::string err;
    std::ofstream metrics;
    if(!perfJson.empty()){auto path=pulse::FilePath(perfJson);if(path.has_parent_path())std::filesystem::create_directories(path.parent_path());
        metrics.open(path);if(!metrics)return Fail("metrics error","cannot create performance JSON");}
    if(!pulse::resources::Initialize(gameDirectory,steamDirectory,&err))return Fail("mount error",err);
    pulse::resources::Print();
    pulse::compile::CompileInput input;
    // pre-seeded so a script without $modelname still loads under -modelname
    input.outname = modelname;
    input.ce.launchPrelude=cePrelude;
    input.stripLods = stripLods;
    g_stage = "script load";
    const std::string stdinText = scriptFromStdin ? ReadStdin() : std::string();
    if (!pulse::loader::LoadQcScript(script, input, &err, defvars, includeDirs, fileDirs,
                                     scriptFromStdin ? &stdinText : nullptr))
        return Fail("script error", err);
    // CE resolves OutDir relative to the root QC and defaults to its directory.
    const auto scriptDirectory=std::filesystem::absolute(pulse::FilePath(script)).parent_path();
    if(!input.ce.outputDirectory.empty()) {
        auto selected=pulse::FilePath(input.ce.outputDirectory);
        outdir=(selected.is_absolute() ? selected : scriptDirectory/selected).lexically_normal().string();
    } else if(outdir.empty()) outdir=scriptDirectory.string();
    auto tLoad = Clock::now();
    if (cullAnims)
        input.animCullMethod = pulse::compile::AnimCullMethod::Aggressive;
    if (mostlyOpaque)
        input.renderPass = 2;
    input.alwaysCollapsePrefixes.insert(input.alwaysCollapsePrefixes.end(),
                                        collapsePrefixes.begin(), collapsePrefixes.end());
    if (forceWriteVertexData)
        input.forceWriteVertexData = true;
    if (stripLods)
        input.minLod = 0;
    else if (launchMinLod >= 0)
        input.minLod = launchMinLod;
    if (!modelname.empty()) {
        // -modelname wins over $modelname; extension stripped the same way
        const size_t dot = modelname.find_last_of('.');
        const size_t sep = modelname.find_last_of("/\\");
        input.outname = (dot != std::string::npos && (sep == std::string::npos || dot > sep))
                            ? modelname.substr(0, dot)
                            : modelname;
    }
    if (vtxFormat >= 0)
        input.vtxArchetype = vtxFormat;
    if (noDx80)
        input.noDx80 = true;
    input.stopAfterProcedural = dumpProcedural;

    pulse::compile::CompiledModel model;
    g_stage = "compile";
    if (!pulse::compile::Compile(input, model, &err))
        return Fail("compile error", err);
    auto tCompile = Clock::now();

    if (dumpProcedural) {
        g_stage = "dumpprocedural";
        DumpProcedural(model);
        return 0;
    }

    if (dumpMaterials) {
        std::printf("Used materials:\n");
        for (int texture : model.mats->materialToTexture)
            std::printf("  %s\n", model.mats->textures[texture].name.c_str());
    }

    if (definebones) {
        g_stage = "definebones";
        DumpDefineBones(model);
        return 0;
    }

    if (!verify) {
        if (!noRemap) {
            std::string warning;
            if (!newpage::PreserveSequenceOrder(model, outdir, warning)) {
                if(input.csgo.errorOnRemapFailure)return Fail("sequence remapping error",warning);
                std::fprintf(stderr, "warning: %s\n", warning.c_str());
            }
        }
        g_stage = "write";
        // dx80 only ships with the legacy archetype; Alien Swarm+ (archetype 1)
        // dropped DirectX 8, and $nodx80 / -nodx80 opt out explicitly.
        const bool legacyVtx = input.vtxArchetype == 0;
        const bool writeDx80 = legacyVtx && !input.noDx80;
        if (!pulse::writer::WriteModelFiles(model, outdir, legacyVtx, writeDx80, &err))
            return Fail("write error", err);
    }
    if (dumpDependencies)
        pulse::dependencies::Print();
    auto tWrite = Clock::now();
    g_stage = "done";
    if(reloadHlmv && !verify) {
#ifdef _WIN32
        std::string title="models\\"+model.outname+".mdl";
        std::replace(title.begin(),title.end(),'/','\\');
        HWND viewer=FindWindowExA(nullptr,nullptr,"mx_class",title.c_str());
        if(!viewer) viewer=FindWindowExA(nullptr,nullptr,"mx_class",nullptr);
        if(viewer && PostMessageA(viewer,WM_COMMAND,1017,0)) std::printf("Notified HLMV to reload\n");
        else std::printf("HLMV not found or reload notification failed.\n");
#else
        std::printf("HLMV reload is available on Windows only.\n");
#endif
    }

    // lodFlag is a bit per LOD. The pool is shared, so a decimated LOD adds no
    // verts to it - only a replacemodel LOD does. Per-LOD = verts it draws.
    std::vector<size_t> lodVerts(model.scriptLods.size(), 0);
    size_t vertsPool = 0;
    for (const auto& m : model.models) {
        vertsPool += m.vertices.size();
        for (const auto& v : m.vertices)
            for (size_t l = 0; l < lodVerts.size(); l++)
                if (v.lodFlag & (1 << l)) lodVerts[l]++;
    }
    std::printf("bones: %zu | verts: %zu in .vvd\n", model.bones.size(), vertsPool);
    for (size_t l = 0; l < lodVerts.size(); l++)
        std::printf("  %s%zu: %zu verts\n",
                    model.scriptLods[l].switchValue < 0 ? "shadowlod" : "lod", l, lodVerts[l]);
    std::printf("compile time: %.2f s\n", ms(t0, tWrite) / 1000.0);

    if (timing) {
        pulse::perf::Record("total", "script load", ms(t0, tLoad));
        pulse::perf::Record("total", "compile", ms(tLoad, tCompile));
        pulse::perf::Record("total", "write", ms(tCompile, tWrite));
        pulse::perf::Record("total", "whole compile", ms(t0, tWrite));
        pulse::perf::Report();
    }
    if(metrics) {
        uint64_t peak=0;
#ifdef _WIN32
        PROCESS_MEMORY_COUNTERS info{};info.cb=sizeof(info);if(GetProcessMemoryInfo(GetCurrentProcess(),&info,sizeof(info)))peak=info.PeakWorkingSetSize;
#else
        rusage info{};if(getrusage(RUSAGE_SELF,&info)==0)peak=uint64_t(info.ru_maxrss)*1024;
#endif
        metrics<<"{\"schema\":1,\"version\":\""<<PULSEMODEL_VERSION<<"\",\"load_ms\":"<<ms(t0,tLoad)
               <<",\"compile_ms\":"<<ms(tLoad,tCompile)<<",\"write_ms\":"<<ms(tCompile,tWrite)<<",\"total_ms\":"<<ms(t0,tWrite)
               <<",\"peak_working_set_bytes\":"<<peak<<",\"bones\":"<<model.bones.size()<<",\"vertices\":"<<vertsPool<<",\"stages\":[";
        bool first=true;
        for(const auto& entry:pulse::perf::g_entries) {
            if(!first) metrics<<","; first=false;
            metrics<<"{\"tag\":"<<std::quoted(entry.tag)<<",\"name\":"<<std::quoted(entry.name)
                   <<",\"ms\":"<<entry.ms<<",\"calls\":"<<entry.calls<<"}";
        }
        metrics<<"]}\n";
    }
    return 0;
}

int main(int argc, char** argv) {
    // progress lines are useless if they sit in the CRT buffer until exit -
    // MSVC has no line buffering (_IOLBF == _IOFBF), so go unbuffered
    std::setvbuf(stdout, nullptr, _IONBF, 0);

    pulse::fatal::Install();

    // -dumpcommands takes no script and runs before the banner: the output is
    // read by tools, so stdout carries the command list and nothing else.
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "-dumpcommands") == 0) {
            pulse::loader::PrintCommandNames();
            return 0;
        }
    }

    PrintHeader();

    // a leak past a stage's own error path still gets named in the footer
    int rc;
    try {
        rc = RunCompile(argc, argv);
    } catch (const std::bad_alloc&) {
        rc = Fail("out of memory", "an allocation failed - the model may exceed available RAM");
    } catch (const std::exception& e) {
        rc = Fail("internal error", e.what());
    } catch (...) {
        rc = Fail("internal error", "unknown C++ exception");
    }
    for(int i=1;i<argc;++i) if(std::strcmp(argv[i],"-playbeep")==0) {
#ifdef _WIN32
        Beep(rc==0?880:220,150);
#else
        if(isatty(fileno(stdout))) std::fputc('\a',stdout);
#endif
        break;
    }
    pulse::fatal::PauseIfAsked();
    return rc;
}
