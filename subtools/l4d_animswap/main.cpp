// l4d_animswap - generate a $declaresequence swap script for L4D2 survivor mods.
//
// A survivor mod must keep vanilla's sequence indices or client and server
// disagree about which animation is playing. This walks vanilla's own
// $includemodel chain to recover that index order, then renames each slot to
// the matching animation from a donor survivor so the donor's include claims it.

#include <algorithm>
#include <cerrno>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <map>
#include <climits>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "../vmd2valvebiped/output_transaction.h"
#include "animwrite.h"
#include "dmxwrite.h"
#include "format/mdl.h"
#include "mdlfile.h"

namespace fm = pulse::format;
namespace dc = mdldecompiler;

namespace {

bool ParseIntOption(const char* text, int& value) {
    if (!text || !*text || std::isspace(static_cast<unsigned char>(*text)))
        return false;
    errno = 0;
    char* end = nullptr;
    const long long parsed = std::strtoll(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0' || parsed < INT_MIN || parsed > INT_MAX)
        return false;
    value = static_cast<int>(parsed);
    return true;
}

bool LooksLikeOption(const char* text) {
    return text && text[0] == '-' && std::isalpha(static_cast<unsigned char>(text[1]));
}

// Survivor name -> the codename Valve embeds in file and sequence names. Group
// picks the default donor chain: swapping inside a build-alike set keeps the
// retarget from stretching limbs.
struct Survivor {
    const char* survivor;
    const char* code;
    int group; // 0 female, 1 male
};
const Survivor kSurvivors[] = {
    {"zoey", "teenangst", 0}, {"rochelle", "producer", 0},
    {"bill", "namvet", 1},    {"francis", "biker", 1},
    {"louis", "manager", 1},  {"coach", "coach", 1},
    {"nick", "gambler", 1},   {"ellis", "mechanic", 1},
};

std::string Lower(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

// L4D2 campaign intro sequence: cXmY_intro... (e.g. c4m1_intro_coach).
bool IsCampaignIntro(const std::string& name) {
    const std::string s = Lower(name);
    size_t i = 0;
    if (i >= s.size() || s[i++] != 'c') return false;
    size_t d = i; while (i < s.size() && std::isdigit((unsigned char)s[i])) ++i;
    if (i == d || i >= s.size() || s[i++] != 'm') return false;
    d = i; while (i < s.size() && std::isdigit((unsigned char)s[i])) ++i;
    return i != d && s.compare(i, 6, "_intro") == 0;
}

bool IsGestureName(const std::string& name) {
    return Lower(name).find("_gesture_") != std::string::npos;
}

const Survivor* FindSurvivor(const std::string& name) {
    const std::string want = Lower(name);
    for (const Survivor& h : kSurvivors)
        if (want == h.survivor || want == h.code) return &h;
    return nullptr;
}

std::set<std::string> CodeTokens() {
    std::set<std::string> s;
    for (const Survivor& h : kSurvivors) s.insert(h.code);
    return s;
}

std::string Leaf(const std::string& path) {
    const size_t slash = path.find_last_of("/\\");
    return slash == std::string::npos ? path : path.substr(slash + 1);
}

// ---------------------------------------------------------------- mdl reading

struct Mdl {
    std::vector<char> bytes;
    std::vector<std::string> seqs;
    std::vector<std::string> acts; // "ACT_X <weight>", empty when the slot has none
    std::vector<bool> overrides;
    std::vector<bool> autoplay;
    std::vector<std::string> autolayers; // names every sequence here pulls in as a layer
    std::vector<std::string> params; // pose parameters the sequence blends on, space-joined
    std::vector<std::string> includes;
};

bool LoadMdl(const std::string& path, Mdl& out) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    std::fseek(f, 0, SEEK_END);
    const long len = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    out.bytes.resize(len > 0 ? static_cast<size_t>(len) : 0);
    const size_t got = out.bytes.empty() ? 0 : std::fread(out.bytes.data(), 1, out.bytes.size(), f);
    std::fclose(f);
    if (got != out.bytes.size() || out.bytes.size() < sizeof(fm::studiohdr_t)) return false;

    const char* base = out.bytes.data();
    const auto* hdr = reinterpret_cast<const fm::studiohdr_t*>(base);
    if (hdr->id != fm::kIdStudioHeader || hdr->length < sizeof(fm::studiohdr_t) ||
        static_cast<size_t>(hdr->length) > out.bytes.size()) return false;
    const size_t length = static_cast<size_t>(hdr->length);
    bool valid = true;
    const auto table = [&](int64_t off, int count, size_t stride) {
        return count >= 0 && (count == 0 || (off >= 0 && static_cast<uint64_t>(off) <= length &&
            static_cast<size_t>(count) <= (length - static_cast<size_t>(off)) / stride));
    };
    if (!table(hdr->localposeparamindex, hdr->numlocalposeparameters, sizeof(fm::mstudioposeparamdesc_t)) ||
        !table(hdr->localseqindex, hdr->numlocalseq, sizeof(fm::mstudioseqdesc_t)) ||
        !table(hdr->includemodelindex, hdr->numincludemodels, sizeof(fm::mstudiomodelgroup_t)))
        return false;
    const auto str = [&](int64_t off) {
        if (off < 0 || static_cast<uint64_t>(off) >= length) {
            valid = false;
            return std::string();
        }
        const char* start = base + off;
        const char* end = static_cast<const char*>(std::memchr(start, 0, length - static_cast<size_t>(off)));
        if (!end) {
            valid = false;
            return std::string();
        }
        return std::string(start, end);
    };
    std::vector<std::string> poses;
    for (int i = 0; i < hdr->numlocalposeparameters; ++i) {
        const size_t at = static_cast<size_t>(hdr->localposeparamindex) +
                          i * sizeof(fm::mstudioposeparamdesc_t);
        const auto* pd = reinterpret_cast<const fm::mstudioposeparamdesc_t*>(base + at);
        poses.push_back(str(static_cast<int64_t>(at) + pd->sznameindex));
    }
    for (int i = 0; i < hdr->numlocalseq; ++i) {
        const size_t at = static_cast<size_t>(hdr->localseqindex) + i * sizeof(fm::mstudioseqdesc_t);
        const auto* sd = reinterpret_cast<const fm::mstudioseqdesc_t*>(base + at);
        out.seqs.push_back(str(static_cast<int64_t>(at) + sd->szlabelindex));
        if (out.seqs.back().empty()) return false;
        std::string act = sd->szactivitynameindex
                              ? str(static_cast<int64_t>(at) + sd->szactivitynameindex)
                              : std::string();
        if (!act.empty()) act += " " + std::to_string(sd->actweight);
        out.acts.push_back(act);
        out.overrides.push_back((sd->flags & fm::STUDIO_OVERRIDE) != 0);
        out.autoplay.push_back((sd->flags & fm::STUDIO_AUTOPLAY) != 0);
        std::vector<std::string> used;
        for (const int32_t p : sd->paramindex)
            if (p >= 0 && static_cast<size_t>(p) < poses.size())
                used.push_back(poses[static_cast<size_t>(p)]);
        std::sort(used.begin(), used.end());
        std::string params;
        for (const std::string& u : used) params += (params.empty() ? "" : " ") + u;
        out.params.push_back(params);
    }
    for (int i = 0; i < static_cast<int>(out.seqs.size()); ++i) {
        const size_t at = static_cast<size_t>(hdr->localseqindex) + i * sizeof(fm::mstudioseqdesc_t);
        const auto* sd = reinterpret_cast<const fm::mstudioseqdesc_t*>(base + at);
        if (!table(static_cast<int64_t>(at) + sd->autolayerindex, sd->numautolayers,
                   sizeof(fm::mstudioautolayer_t))) return false;
        for (int k = 0; k < sd->numautolayers; ++k) {
            const size_t la =
                at + static_cast<size_t>(sd->autolayerindex) + k * sizeof(fm::mstudioautolayer_t);
            const int s = reinterpret_cast<const fm::mstudioautolayer_t*>(base + la)->iSequence;
            if (s >= 0 && s < static_cast<int>(out.seqs.size())) out.autolayers.push_back(out.seqs[s]);
        }
    }
    for (int i = 0; i < hdr->numincludemodels; ++i) {
        const size_t at =
            static_cast<size_t>(hdr->includemodelindex) + i * sizeof(fm::mstudiomodelgroup_t);
        const auto* mg = reinterpret_cast<const fm::mstudiomodelgroup_t*>(base + at);
        if (!mg->sznameindex) return false;
        out.includes.push_back(str(static_cast<int64_t>(at) + mg->sznameindex));
        if (out.includes.back().empty()) return false;
    }
    return valid;
}

// One survivor's resolved slot list: the name at each index and, for the
// model's own leading slots, the activity a mod must re-declare there.
struct Slots {
    std::vector<std::string> names;
    std::vector<std::string> acts;
    std::vector<bool> overrides;
    std::vector<std::string> params;
    std::vector<bool> stub; // override slot still waiting for its first include
};

// The engine indexes sequences as: the model's own locals, then each
// $includemodel in order, skipping names already taken. Replaying that walk
// recovers the slot order a mod has to line up with.
struct Resolver {
    std::string dir;
    std::map<std::string, Mdl> cache;
    bool missing = false;
    std::set<const Mdl*> active;

    const Mdl* Get(const std::string& modelPath) {
        const std::string leaf = Leaf(modelPath);
        const std::string key = Lower(leaf);
        auto it = cache.find(key);
        if (it != cache.end()) return it->second.bytes.empty() ? nullptr : &it->second;
        Mdl m;
        if (!LoadMdl(dir + "/" + leaf, m)) {
            std::fprintf(stderr, "  cannot read %s\n", leaf.c_str());
            missing = true;
            cache[key];
            return nullptr;
        }
        return &(cache[key] = std::move(m));
    }

    void Walk(const Mdl& m, Slots& order, std::map<std::string, size_t>& seen) {
        if (!active.insert(&m).second) {
            std::fprintf(stderr, "  cyclic animation model include chain\n");
            missing = true;
            return;
        }
        for (size_t i = 0; i < m.seqs.size(); ++i) {
            const std::string key = Lower(m.seqs[i]);
            const std::string act = i < m.acts.size() ? m.acts[i] : std::string();
            const std::string params = i < m.params.size() ? m.params[i] : std::string();
            const auto found = seen.find(key);
            if (found != seen.end()) {
                if (order.overrides[found->second] && order.acts[found->second].empty())
                    order.acts[found->second] = act;
                if (order.stub[found->second]) {
                    order.params[found->second] = params;
                    order.stub[found->second] = false;
                }
                continue;
            }
            seen[key] = order.names.size();
            order.names.push_back(m.seqs[i]);
            order.acts.push_back(act);
            order.overrides.push_back(i < m.overrides.size() && m.overrides[i]);
            order.params.push_back(params);
            order.stub.push_back(order.overrides.back());
        }
        for (const std::string& inc : m.includes)
            if (const Mdl* sub = Get(inc)) Walk(*sub, order, seen);
        active.erase(&m);
    }

    Slots Order(const Survivor& h) {
        Slots order;
        std::map<std::string, size_t> seen;
        if (const Mdl* m = Get("survivor_" + std::string(h.code) + ".mdl")) Walk(*m, order, seen);
        return order;
    }
};

// -------------------------------------------------------------- name matching

// Two keys per name: the codename token swapped for a wildcard, and the same
// with it dropped. The second catches sets that spell one animation both with
// and without the character prefix (coach_Run_Pistol vs Run_Pistol).
void Keys(const std::string& name, const std::set<std::string>& codes, std::string& swapped,
          std::string& stripped) {
    swapped.clear();
    stripped.clear();
    const std::string low = Lower(name);
    for (size_t i = 0;;) {
        const size_t end = low.find('_', i);
        const std::string tok = low.substr(i, (end == std::string::npos ? low.size() : end) - i);
        const bool isCode = codes.count(tok) != 0;
        if (!swapped.empty()) swapped += '_';
        swapped += isCode ? "@" : tok;
        if (!isCode) {
            if (!stripped.empty()) stripped += '_';
            stripped += tok;
        }
        if (end == std::string::npos) break;
        i = end + 1;
    }
}

// "ACT_X 1" -> "ACT_X".
std::string ActName(const std::string& act) { return act.substr(0, act.find(' ')); }

struct Index {
    std::map<std::string, std::string> swapped, stripped;
    std::map<std::string, std::string> actOf;                 // lowered name -> activity
    std::map<std::string, std::vector<std::string>> byAct;    // activity -> names
    std::map<std::string, std::string> paramsOf;              // lowered name -> pose params
    std::map<std::string, std::vector<std::string>> byParams; // pose params -> names

    void Build(const std::vector<std::string>& names, const std::vector<std::string>& acts,
               const std::vector<std::string>& params, const std::string& own,
               const std::set<std::string>& codes) {
        std::set<std::string> ownSw, ownSt;
        std::string sw, st;
        for (size_t i = 0; i < names.size(); ++i) {
            const std::string& n = names[i];
            const std::string act = i < acts.size() ? ActName(acts[i]) : std::string();
            actOf[Lower(n)] = act;
            if (!act.empty()) byAct[act].push_back(n);
            const std::string par = i < params.size() ? params[i] : std::string();
            paramsOf[Lower(n)] = par;
            if (!par.empty()) byParams[par].push_back(n);
            Keys(n, codes, sw, st);
            // A set carries some animations under another survivor's name
            // (anim_biker.mdl has NamVet_* entries). Own spelling wins the key.
            const bool mine = Lower(n).find(own) != std::string::npos;
            if (!swapped.count(sw) || (mine && !ownSw.count(sw))) swapped[sw] = n;
            if (!stripped.count(st) || (mine && !ownSt.count(st))) stripped[st] = n;
            if (mine) {
                ownSw.insert(sw);
                ownSt.insert(st);
            }
        }
    }
};

// ------------------------------------------------------------------ resolution

struct Result {
    std::vector<std::string> names;
    std::vector<int> from; // chain index, -1 "kept the vanilla name", -2 inert
};

// Rig == target is the no-swap case, and every slot then reports from == -1
// ("kept the vanilla name"). That is the right answer there, not a gap, so no
// fallback blocking applies - the target's own include is the correct source.
bool BlockFallback(bool flag, const Survivor& rig, const Survivor& tgt) {
    return flag && &rig != &tgt;
}

// A donor name may fill only one slot: a repeated $declaresequence compiles to
// an empty sequence, so a second claimant drops to the next donor instead.
Result Build(const std::vector<std::string>& order, const std::vector<std::string>& acts,
             const std::vector<std::string>& params, const std::vector<Index>& idx,
             const std::set<std::string>& codes, bool keepintro) {
    Result r;
    std::set<std::string> taken;
    std::string sw, st;
    for (size_t i = 0; i < order.size(); ++i) {
        const std::string& v = order[i];
        const std::string act = i < acts.size() ? ActName(acts[i]) : std::string();
        const std::string par = i < params.size() ? params[i] : std::string();
        Keys(v, codes, sw, st);
        std::string pick;
        int from = -1;
        // -keepintro: a campaign intro is never swapped - keep the target's own.
        if (keepintro && IsCampaignIntro(v)) {
            r.names.push_back(v);
            r.from.push_back(-1);
            continue;
        }
        for (size_t d = 0; d < idx.size() && pick.empty(); ++d) {
            const std::map<std::string, std::string>* tabs[2] = {&idx[d].swapped, &idx[d].stripped};
            const std::string* keys[2] = {&sw, &st};
            for (int k = 0; k < 2; ++k) {
                const auto it = tabs[k]->find(*keys[k]);
                if (it != tabs[k]->end() && !taken.count(Lower(it->second))) {
                    pick = it->second;
                    from = static_cast<int>(d);
                    break;
                }
            }
            // Sets can name one clip differently: ACT_DIESIMPLE is "Death" in L4D1 but
            // "Collapse_to_Incap" in L4D2. Take the donor's sole holder of the activity.
            // Gestures are called by name, so they keep the name match.
            if (!pick.empty() && !act.empty() && act.compare(0, 8, "ACT_GEST") != 0 &&
                idx[d].actOf.at(Lower(pick)) != act) {
                const auto holders = idx[d].byAct.find(act);
                if (holders != idx[d].byAct.end() && holders->second.size() == 1 &&
                    !taken.count(Lower(holders->second[0])))
                    pick = holders->second[0];
            }
            // Every set names its head look (head_yaw/head_pitch) differently, so it is matched
            // by pose params. A name match that blends the head elsewhere is held inert.
            const std::string pickPar =
                pick.empty() ? std::string() : idx[d].paramsOf.at(Lower(pick));
            const bool slotHead = par.find("head_") != std::string::npos;
            if ((slotHead && (pick.empty() || pickPar != par)) ||
                (!pick.empty() && pickPar != par && pickPar.find("head_") != std::string::npos)) {
                const auto holders = idx[d].byParams.find(par);
                if (slotHead && holders != idx[d].byParams.end() && holders->second.size() == 1 &&
                    !taken.count(Lower(holders->second[0]))) {
                    pick = holders->second[0];
                    from = static_cast<int>(d);
                } else if (!pick.empty()) {
                    from = -2;
                }
            }
        }
        // No donor spells the name at all (Coach's limpwalk_Shotgun is LimpWalk_PumpShotgun
        // elsewhere): take the first donor's sole holder of the activity.
        for (size_t d = 0; d < idx.size() && pick.empty() && from != -2; ++d) {
            if (act.empty() || act.compare(0, 8, "ACT_GEST") == 0) break;
            const auto holders = idx[d].byAct.find(act);
            if (holders != idx[d].byAct.end() && holders->second.size() == 1 &&
                !taken.count(Lower(holders->second[0]))) {
                pick = holders->second[0];
                from = static_cast<int>(d);
            }
        }
        // An earlier slot already claimed this name; a repeat declare would compile empty.
        if (pick.empty() && taken.count(Lower(v))) from = -2;
        if (from == -2) {
            r.names.push_back(v); // named after every real pick is known, below
            r.from.push_back(from);
            continue;
        }
        if (pick.empty()) pick = v;
        taken.insert(Lower(pick));
        r.names.push_back(pick);
        r.from.push_back(from);
    }
    // An inert slot keeps its vanilla name so it shadows the included copy, unless a real
    // slot uses that name.
    for (size_t i = 0; i < r.names.size(); ++i)
        if (r.from[i] == -2 && !taken.insert(Lower(r.names[i])).second) r.names[i] += "_inert";
    return r;
}

// ------------------------------------------------------------------- retarget

// Slots whose clip is rebuilt for the rig instead of riding the target's include.
// cXmY_intro and The Passing's dlc1_* scene clips; their delta gestures stay declares.
bool Retargetable(const std::string& name) {
    return IsCampaignIntro(name) || Lower(name).compare(0, 5, "dlc1_") == 0;
}

std::string Quote(const std::string& s) { return "\"" + s + "\""; }

// Rebuilds a target survivor's clip on the rig's skeleton: local rotations carry
// over by bone name, translations keep the rig's bone lengths and add the clip's
// offset from the target's bind pose, scaled by pelvis height (root height only).
struct Retargeter {
    std::string dir, outDir;
    const Survivor* rig = nullptr;
    const Survivor* target = nullptr;
    dc::Mdl rigMdl;
    bool rigOk = false, failed = false;
    subtool::OutputTransaction* outputs = nullptr;
    std::map<std::string, dc::Mdl> cache;
    int written = 0;

    bool Load(const std::string& leaf, dc::Mdl& m) {
        if (!dc::ReadWhole(dir + "/" + leaf, m.buf) || m.buf.size() < sizeof(fm::studiohdr_t))
            return false;
        m.hdr = reinterpret_cast<const fm::studiohdr_t*>(m.buf.data());
        if (m.hdr->id != fm::kIdStudioHeader)
            return false;
        if (m.hdr->numanimblocks > 1 &&
            !dc::ReadWhole(dir + "/" + dc::StripExt(leaf) + ".ani", m.ani)) {
            failed = true;
            std::fprintf(stderr, "  -retarget: missing animation data for %s\n", leaf.c_str());
            return false;
        }
        return true;
    }

    bool Init(const std::string& vanilla, const Survivor& r, const Survivor& t, const std::string& out) {
        dir = vanilla;
        rig = &r;
        target = &t;
        outDir = out;
        rigOk = Load("survivor_" + std::string(r.code) + ".mdl", rigMdl) && rigMdl.hdr->numbones > 0;
        if (!rigOk)
            std::fprintf(stderr, "  -retarget: cannot read survivor_%s.mdl\n", r.code);
        return rigOk;
    }

    std::string OutputClip(const std::string& name) const {
        // The same rig may replace several targets in one -all batch. Their
        // same-named sequences need not contain the same motion, including
        // optional Light models and delta bases.
        return name + "_retarget_" + rig->survivor + "_for_" + target->survivor;
    }

    const dc::Mdl* Get(const std::string& leaf) {
        const std::string key = Lower(leaf);
        auto it = cache.find(key);
        if (it == cache.end()) {
            dc::Mdl m;
            if (!Load(leaf, m))
                m.hdr = nullptr;
            it = cache.emplace(key, std::move(m)).first;
        }
        return it->second.hdr ? &it->second : nullptr;
    }

    std::vector<std::vector<dc::AnimPose>> Remap(const dc::Mdl& src,
                                                 const std::vector<std::vector<dc::AnimPose>>& in) {
        const std::vector<std::string> sNames = dc::BoneNames(src), rNames = dc::BoneNames(rigMdl);
        const std::vector<dc::AnimPose> sBind = dc::BindPose(src), rBind = dc::BindPose(rigMdl);
        const auto* sBones =
            src.At<fm::mstudiobone_t>(src.buf.data(), src.hdr->boneindex, src.hdr->numbones);
        const auto* rBones =
            rigMdl.At<fm::mstudiobone_t>(rigMdl.buf.data(), rigMdl.hdr->boneindex, rigMdl.hdr->numbones);
        std::map<std::string, int> sIndex;
        for (size_t s = 0; s < sNames.size(); ++s) sIndex[Lower(sNames[s])] = static_cast<int>(s);
        const auto parentName = [](const std::vector<std::string>& names, int p) {
            return p >= 0 && static_cast<size_t>(p) < names.size() ? Lower(names[p]) : std::string();
        };

        // A bone whose parent differs between the two skeletons keeps the rig's bind pose.
        const size_t nr = rNames.size();
        std::vector<int> map(nr, -1);
        for (size_t j = 0; j < nr; ++j) {
            const auto it = sIndex.find(Lower(rNames[j]));
            if (it != sIndex.end() &&
                parentName(sNames, sBones[it->second].parent) == parentName(rNames, rBones[j].parent))
                map[j] = it->second;
        }

        float scale = 1.0f;
        const auto pelvis = sIndex.find("valvebiped.bip01_pelvis");
        for (size_t j = 0; j < nr && pelvis != sIndex.end(); ++j)
            if (map[j] == pelvis->second && sBind[pelvis->second].pos.z > 1.0f)
                scale = rBind[j].pos.z / sBind[pelvis->second].pos.z;

        std::vector<std::vector<dc::AnimPose>> out(in.size(), rBind);
        for (size_t f = 0; f < in.size(); ++f)
            for (size_t j = 0; j < nr; ++j) {
                const int s = map[j];
                if (s < 0)
                    continue;
                const bool root = rBones[j].parent < 0;
                const pm::Vector3 d{in[f][s].pos.x - sBind[s].pos.x, in[f][s].pos.y - sBind[s].pos.y,
                                    in[f][s].pos.z - sBind[s].pos.z};
                const float k = root ? 1.0f : scale;
                out[f][j].rot = in[f][s].rot;
                out[f][j].pos = {rBind[j].pos.x + d.x * k, rBind[j].pos.y + d.y * k,
                                 rBind[j].pos.z + d.z * scale};
            }
        return out;
    }

    // The target's sequence rebuilt as a local $sequence on a retargeted clip, or
    // empty when it cannot be (no single absolute animation behind it).
    // `label` renames the rebuilt sequence; empty keeps `name`.
    std::vector<std::string> Sequence(const std::vector<std::string>& includes,
                                      const std::string& name, const std::string& label = {}) {
        if (!rigOk)
            return {};
        for (const std::string& inc : includes) {
            const dc::Mdl* m = Get(Leaf(inc));
            if (!m) {
                failed = true;
                std::fprintf(stderr, "  -retarget: cannot read required animation model %s\n", inc.c_str());
                return {};
            }
            const fm::studiohdr_t& h = *m->hdr;
            const auto* seqs =
                m->At<fm::mstudioseqdesc_t>(m->buf.data(), h.localseqindex, h.numlocalseq);
            for (int i = 0; seqs && i < h.numlocalseq; ++i)
                if (!(seqs[i].flags & fm::STUDIO_OVERRIDE) &&
                    Lower(m->Str(&seqs[i], seqs[i].szlabelindex)) == Lower(name))
                    return Build(*m, seqs[i], label.empty() ? name : label);
        }
        return {};
    }

    bool WriteClip(const std::string& clip, float fps,
                   const std::vector<std::vector<dc::AnimPose>>& frames) {
        const std::string path = outputs->Stage(outDir + "/anims/" + clip + ".dmx");
        if (!dc::WriteAnimationDmx(rigMdl, path, clip, fps, frames)) {
            failed = true;
            std::fprintf(stderr, "  -retarget: cannot write anims/%s.dmx\n", clip.c_str());
            return false;
        }
        ++written;
        return true;
    }

    // The pose a delta clip subtracts, retargeted and declared once as an $animation
    // in `pre`. Same base DecodeClip added back, so base^-1 * pose is the original delta.
    std::set<std::string> bases;
    std::string Base(const dc::Mdl& m, int anim, std::vector<std::string>& pre) {
        const std::vector<dc::AnimRef> refs = dc::AnimRefs(m);
        const int base = dc::SubtractBase(m, refs);
        const bool real = base >= 0 && base < anim;
        // Named after its source model: every _light set has a bind-pose base, and they
        // share one anims/ folder.
        const std::string animName = (real ? refs[base].name : std::string(dc::kBindPoseAnim)) +
                                     "_" + Lower(dc::StripExt(dc::BaseName(m.hdr->name)));
        const std::string clip = OutputClip(animName);
        if (bases.insert(Lower(clip)).second) {
            std::vector<std::vector<dc::AnimPose>> f;
            if (real) {
                if (!dc::DecodeClip(m, base, f) || f.empty()) {
                    failed = true;
                    std::fprintf(stderr, "  -retarget: cannot decode delta base\n");
                    return {};
                }
                f.resize(1);
            } else {
                f.push_back(dc::BindPose(m));
            }
            if (!WriteClip(clip, 30.0f, Remap(m, f)))
                return {};
            pre.push_back("$animation " + Quote(animName) + " " + Quote("anims/" + clip + ".dmx") +
                          " { fps 30 ignorescale origin 0 0 0 ignoretransformbone angles "
                          "ignoretransformbone position }  // the pose the deltas subtract");
        }
        return animName;
    }

    // `tag` goes into the clip file name; `deltas` rebuilds delta clips instead of
    // skipping them, for a model with no $includemodel to fall back on.
    std::vector<std::string> Build(const dc::Mdl& m, const fm::mstudioseqdesc_t& s,
                                   const std::string& name, const std::string& tag = {},
                                   bool deltas = false) {
        const fm::studiohdr_t& h = *m.hdr;
        const int16_t* grid = m.At<int16_t>(&s, s.animindexindex, 1);
        const auto* anims =
            m.At<fm::mstudioanimdesc_t>(m.buf.data(), h.localanimindex, h.numlocalanim);
        if (s.groupsize[0] * s.groupsize[1] != 1 || !grid || !anims || grid[0] < 0 ||
            grid[0] >= h.numlocalanim) {
            std::fprintf(stderr, "  -retarget: \"%s\" is a blend, kept as a declare\n", name.c_str());
            return {};
        }
        const fm::mstudioanimdesc_t& a = anims[grid[0]];
        std::vector<std::vector<dc::AnimPose>> frames;
        // A delta layers on whatever plays under it, so it never stretches.
        const bool delta = (a.flags & fm::STUDIO_DELTA) != 0;
        if (delta && !deltas)
            return {};
        if (!dc::DecodeClip(m, grid[0], frames)) {
            failed = true;
            std::fprintf(stderr, "  -retarget: \"%s\" could not be decoded\n",
                         name.c_str());
            return {};
        }
        std::vector<std::string> pre;
        const std::string subtract = delta ? Base(m, grid[0], pre) : std::string();
        if (delta && subtract.empty())
            return {};
        const std::string clip = OutputClip(name + tag);
        // Keep the source rate intact. DMX stores frameRate as a float for
        // fractional clips, while the QC below already emits a.fps. Rounding
        // here made the generated DMX duration disagree with the sequence's
        // declared rate (for example 23.976 became 24).
        const float fps = a.fps > 0.0f ? a.fps : 30.0f;
        if (!WriteClip(clip, fps, Remap(m, frames)))
            return {};

        const auto pick = [](const std::vector<std::string>& v, int i) {
            return i >= 0 && static_cast<size_t>(i) < v.size() ? v[i] : std::string();
        };
        std::vector<std::string> labels;
        const auto* seqs = m.At<fm::mstudioseqdesc_t>(m.buf.data(), h.localseqindex, h.numlocalseq);
        for (int i = 0; seqs && i < h.numlocalseq; ++i)
            labels.push_back(m.Str(&seqs[i], seqs[i].szlabelindex));
        const std::vector<std::string> chains = dc::IkChainNames(m);

        std::vector<std::string> out = pre;
        out.push_back("$sequence " + Quote(name) + " {");
        const auto opt = [&](const std::string& l) { out.push_back("    " + l); };
        opt(Quote("anims/" + clip + ".dmx") + "  // " + std::to_string(a.numframes) + " frames");
        std::string first = "fps " + dc::F(fps);
        if (a.flags & fm::STUDIO_LOOPING) first += " loop";
        if (a.flags & fm::STUDIO_NOFORCELOOP) first += " noforceloop";
        if (a.flags & fm::STUDIO_SNAP) first += " snap";
        if (a.flags & fm::STUDIO_POST) first += " post";
        opt(first);
        if (delta)
            opt("subtract " + Quote(subtract) + " 0");
        // Built at the rig's proportions and placement, so like the included vanilla
        // clips it must not see the model's $scale, $origin or $transformbone edits.
        opt("ignorescale");
        opt("origin 0 0 0");
        opt("ignoretransformbone angles");
        opt("ignoretransformbone position");
        const auto* mv = m.At<fm::mstudiomovement_t>(&a, a.movementindex, a.nummovements);
        for (int k = 0; mv && k < a.nummovements; ++k) {
            std::string ctrl;
            for (const auto& c : dc::kMotionControls)
                if (mv[k].motionflags & c.bit) ctrl += " " + std::string(c.name);
            if (!ctrl.empty()) opt("walkframe " + std::to_string(mv[k].endframe) + ctrl);
        }
        // A touch on a bone the rig lacks (Nick's weapon_bolt on Zoey) fails the compile.
        std::set<std::string> rigBones;
        for (const std::string& b : dc::BoneNames(rigMdl)) rigBones.insert(Lower(b));
        // A dropped rule is written commented out, so the modder can restore it per clip.
        for (const std::string& r : dc::IkRules(m, a)) {
            const size_t at = r.find(" touch \"");
            // A delta's touch error is baked against the model's first animation, which
            // on the modder's model (a T-pose a_reference) drags the hands out.
            if (delta && at != std::string::npos) {
                opt("// " + r);
                continue;
            }
            if (at != std::string::npos) {
                const size_t b = at + 8, e = r.find('"', b);
                const std::string bone = r.substr(b, e - b);
#if 0
                // HACK: a bone-less touch pins the hand to a fixed model-space spot that a
                // proportions layer lifting the pelvis leaves behind; pin to the pelvis.
                if (bone.empty() && rigBones.count("valvebiped.bip01_pelvis")) {
                    opt(r.substr(0, b) + "ValveBiped.Bip01_Pelvis" + r.substr(e));
                    continue;
                }
#endif
                // A bone-less touch pins the hand to a fixed model-space spot that a
                // proportions layer lifting the pelvis leaves behind.
                if (bone.empty()) {
                    opt("// " + r);
                    continue;
                }
                if (!rigBones.count(Lower(bone))) {
                    std::fprintf(stderr, "  -retarget: \"%s\" drops an ikrule touching \"%s\", "
                                         "%s has no such bone\n",
                                 name.c_str(), bone.c_str(), rig->survivor);
                    opt("// " + r);
                    continue;
                }
            }
            opt(r);
        }

        if (const char* act = m.Str(&s, s.szactivitynameindex); *act)
            opt("activity " + Quote(act) + " " + std::to_string(s.actweight));
        const int32_t f = s.flags & ~a.flags;
        if (f & fm::STUDIO_AUTOPLAY) opt("autoplay");
        if (f & fm::STUDIO_HIDDEN) opt("hidden");
        if (f & fm::STUDIO_REALTIME) opt("realtime");
        if (f & fm::STUDIO_WORLD_AND_RELATIVE) opt("worldrelative");
        else if (f & fm::STUDIO_WORLD) opt("worldspace");
        // `delta` is DELTA|POST, `predelta` DELTA alone - the decompiler's reading
        if (s.flags & fm::STUDIO_DELTA) {
            if (f & fm::STUDIO_POST) opt("delta");
            else if (f & fm::STUDIO_DELTA) opt("predelta");
        } else if ((f & fm::STUDIO_POST) && !(f & (fm::STUDIO_WORLD | fm::STUDIO_WORLD_AND_RELATIVE))) {
            opt("post");
        }
        if (s.fadeintime != 0.2f) opt("fadein " + dc::F(s.fadeintime));
        if (s.fadeouttime != 0.2f) opt("fadeout " + dc::F(s.fadeouttime));

        const float lastframe = static_cast<float>(a.numframes - 1);
        const auto* al = m.At<fm::mstudioautolayer_t>(&s, s.autolayerindex, s.numautolayers);
        for (int k = 0; al && k < s.numautolayers; ++k) {
            std::string tail;
            if (al[k].flags & fm::STUDIO_AL_LOCAL) tail += " local";
            if (al[k].flags & fm::STUDIO_AL_XFADE) tail += " xfade";
            if (al[k].flags & fm::STUDIO_AL_SPLINE) tail += " spline";
            if (al[k].flags & fm::STUDIO_AL_NOBLEND) tail += " noblend";
            const std::string target = Quote(pick(labels, al[k].iSequence));
            const bool ramp = al[k].start || al[k].peak || al[k].tail || al[k].end;
            if (al[k].flags & fm::STUDIO_AL_POSE) {
                std::fprintf(stderr, "  -retarget: \"%s\" drops a pose-driven layer\n", name.c_str());
                continue;
            }
            if (!ramp && (al[k].flags & ~fm::STUDIO_AL_LOCAL) == 0) {
                opt("addlayer " + target + tail);
                continue;
            }
            opt("blendlayer " + target + " " + dc::F(al[k].start * lastframe) + " " +
                dc::F(al[k].peak * lastframe) + " " + dc::F(al[k].tail * lastframe) + " " +
                dc::F(al[k].end * lastframe) + tail);
        }
        const auto* locks = m.At<fm::mstudioiklock_t>(&s, s.iklockindex, s.numiklocks);
        for (int k = 0; locks && k < s.numiklocks; ++k)
            opt("iklock " + Quote(pick(chains, locks[k].chain)) + " " + dc::F(locks[k].flPosWeight) +
                " " + dc::F(locks[k].flLocalQWeight));
        const auto* ev = m.At<fm::mstudioevent_t>(&s, s.eventindex, s.numevents);
        for (int k = 0; ev && k < s.numevents; ++k) {
            const std::string id = (ev[k].type & fm::NEW_EVENT_STYLE)
                                       ? Quote(m.Str(&ev[k], ev[k].szeventindex))
                                       : std::to_string(ev[k].event);
            std::string line = "event " + id + " " + std::to_string(std::lround(ev[k].cycle * lastframe));
            const std::string o(ev[k].options, strnlen(ev[k].options, sizeof ev[k].options));
            if (!o.empty()) line += " " + Quote(o);
            opt("{ " + line + " }");
        }
        if (s.keyvaluesize > 0)
            if (const char* kv = m.At<char>(&s, s.keyvalueindex, s.keyvaluesize))
                opt("keyvalues { " + std::string(kv, strnlen(kv, s.keyvaluesize)) + " }");
        out.push_back("}");
        return out;
    }
};

// --------------------------------------------------------------------- output

bool Write(const std::string& path, const Survivor& rig, const Survivor& tgt,
           const std::vector<const Survivor*>& chain, const Result& res, int skip, const Slots& order,
           Resolver& mdls, const std::string& ref, bool noanim, bool nofallback,
           bool keepintro, Retargeter* retarget, subtool::OutputTransaction& outputs) {
    nofallback = BlockFallback(nofallback, rig, tgt);
    std::vector<int> won(chain.size(), 0);
    int kept = 0;
    for (size_t i = static_cast<size_t>(skip); i < res.from.size(); ++i) {
        if (res.from[i] < 0) ++kept;
        else ++won[static_cast<size_t>(res.from[i])];
    }

    // Every name the emitted includes can actually supply. A slot outside this
    // set is one vanilla kept local, so a declare there compiles empty.
    // Which files a survivor pulls in is his own model's business - Louis has no
    // gestures_manager.mdl, he rides Francis's. Take the list from vanilla.
    const auto includesOf = [&](const Survivor& h) {
        const Mdl* m = mdls.Get("survivor_" + std::string(h.code) + ".mdl");
        return m ? m->includes : std::vector<std::string>();
    };
    std::set<std::string> reachable;
    const auto reach = [&](const Survivor& h) {
        for (const std::string& inc : includesOf(h))
            if (const Mdl* m = mdls.Get(inc))
                for (const std::string& s : m->seqs) reachable.insert(Lower(s));
    };
    for (size_t d = 0; d < chain.size(); ++d)
        if (won[d]) reach(*chain[d]);
    reach(tgt);

    int local = 0;
    for (size_t i = static_cast<size_t>(skip); i < res.names.size(); ++i)
        if (!reachable.count(Lower(res.names[i]))) ++local;

    // The rig's includes come first, so a name they supply already resolves to the rig's
    // clip; zeroing it would also break the rig sequences that autolayer it.
    std::set<std::string> rigIncs, rigSupplied, rigLayers;
    for (const std::string& inc : includesOf(chain.empty() ? tgt : *chain[0]))
        if (const Mdl* m = mdls.Get(inc)) {
            rigIncs.insert(Lower(Leaf(inc)));
            for (const std::string& s : m->seqs) rigSupplied.insert(Lower(s));
            for (const std::string& s : m->autolayers) rigLayers.insert(Lower(s));
        }

    subtool::OutputFile file(outputs.Stage(path));
    FILE* f = file.Get();
    if (!f) {
        std::fprintf(stderr, "cannot write %s\n", path.c_str());
        return false;
    }
    std::fprintf(f, "// l4d_animswap: a %s-rigged model filling %s's sequence slots.\n", rig.survivor,
                 tgt.survivor);
    // An included sequence carries its own activity, so only the slots the
    // model defines itself need one spelled out.
    std::fprintf(f, "// %d slots below. The first %d are the model's own - vanilla put these\n"
                    "// there, and your script must define %s in the same order:\n",
                 static_cast<int>(res.names.size()) - skip, skip, skip == 1 ? "it" : "them");
    for (int i = 0; i < skip && i < static_cast<int>(order.names.size()); ++i) {
        const std::string& act = order.acts[static_cast<size_t>(i)];
        std::fprintf(f, "//   [%d] %-24s REPLACE ME - your own $sequence", i,
                     order.names[static_cast<size_t>(i)].c_str());
        if (!act.empty()) std::fprintf(f, ", keeping activity %s", act.c_str());
        std::fputc('\n', f);
    }
    for (size_t d = 0; d < chain.size(); ++d)
        std::fprintf(f, "// %-10s %5d slots\n", chain[d]->survivor, won[d]);
    // With no donors the whole list is the target's own, so naming each is noise.
    std::fprintf(f, chain.empty() ? "// %-10s %5d slots - vanilla's own list, nothing swapped\n"
                                  : "// %-10s %5d slots - no donor equivalent, these keep %s\n",
                 tgt.survivor, kept, tgt.survivor);
    if (!chain.empty())
        for (size_t i = static_cast<size_t>(skip); i < res.from.size(); ++i)
            if (res.from[i] < 0) std::fprintf(f, "//   %s\n", res.names[i].c_str());
    if (local)
        std::fprintf(f, (ref.empty() && !noanim)
                            ? "// %d further slot(s) below are marked REPLACE ME - vanilla keeps\n"
                              "// those local, so no $includemodel can fill them.\n"
                            : "// %d further slot(s) below are emitted as local $sequence - no\n"
                              "// $includemodel can fill them.\n",
                     local);
    std::fputc('\n', f);

    // The skipped slots come first in the file too, so mark where they belong.
    for (int i = 0; i < skip && i < static_cast<int>(order.names.size()); ++i) {
        const std::string& act = order.acts[static_cast<size_t>(i)];
        std::fprintf(f, "// [%d] %s here - your own $sequence%s%s\n", i,
                     order.names[static_cast<size_t>(i)].c_str(), act.empty() ? "" : ", activity ",
                     act.c_str());
    }
    if (skip) std::fputc('\n', f);

    // Inert placeholder for a slot no included model can fill.
    const auto emitNoanim = [&](size_t i, const char* note) {
        std::fprintf(f, "$bindposesequence \"%s\" { noanimation", res.names[i].c_str());
        if (!order.acts[i].empty()) std::fprintf(f, " activity %s", order.acts[i].c_str());
        std::fprintf(f, " }   // slot %d - %s\n", static_cast<int>(i), note);
    };

    // Blank-line separate runs of unlike lines: donor declares, inert
    // bindposesequence slots, and local REPLACE ME/$sequence blocks.
    int prevKind = -1;
    const auto spacer = [&](int kind) {
        if (prevKind != -1 && kind != prevKind) std::fputc('\n', f);
        prevKind = kind;
    };
    // A donor pick can collide with a name already emitted (survivor lists hold
    // other survivors' prefixed entries). Dropping the slot would shift every
    // later index and desync multiplayer, so re-emit it as a duplicate
    // $declaresequence - the compiler allows repeats and the index is held.
    std::set<std::string> emitted;
    for (size_t i = static_cast<size_t>(skip); i < res.names.size(); ++i) {
        if (!emitted.insert(Lower(res.names[i])).second) {
            spacer(0);
            std::fprintf(f, "$declaresequence \"%s\"   // dup name, index held\n",
                         res.names[i].c_str());
            continue;
        }
        if (res.from[i] == -2) {
            spacer(2);
            std::string n = res.names[i];
            if (rigSupplied.count(Lower(n))) emitted.insert(Lower(n += "_inert"));
            std::fprintf(f, "$bindposesequence \"%s\" { noanimation }   // slot %d - no usable "
                            "donor clip\n",
                         n.c_str(), static_cast<int>(i));
            continue;
        }
        // A fidget is a cosmetic idle flourish and no donor set carries the
        // full list, so an unmatched one keeps the target's name and plays the
        // target's clip on a foreign rig. Zero it: the slot stays, the pool
        // drops it, and the fidgets a donor did fill still play.
        if (nofallback && res.from[i] < 0 &&
            order.acts[i].compare(0, 17, "ACT_TERROR_FIDGET") == 0) {
            spacer(2);
            std::fprintf(f, "$bindposesequence \"%s\" { noanimation }   // slot %d - unmatched "
                            "fidget, would play the target's own clip\n",
                         res.names[i].c_str(), static_cast<int>(i));
            continue;
        }
        // -retarget: a slot left on the target's own clip gets that clip rebuilt on the
        // rig. The local $sequence shadows the included one and holds the index.
        if (retarget && res.from[i] == -1 && &rig != &tgt && Retargetable(res.names[i]) &&
            !rigSupplied.count(Lower(res.names[i]))) {
            const std::vector<std::string> lines = retarget->Sequence(includesOf(tgt), res.names[i]);
            if (!lines.empty()) {
                spacer(3);
                std::fprintf(f, "// slot %d - %s's clip retargeted to %s\n", static_cast<int>(i),
                             tgt.survivor, rig.survivor);
                for (const std::string& l : lines) std::fprintf(f, "%s\n", l.c_str());
                std::fputc('\n', f);
                prevKind = -1;
                continue;
            }
        }
        if (reachable.count(Lower(res.names[i]))) {
            spacer(0);
            std::fprintf(f, "$declaresequence \"%s\"\n", res.names[i].c_str());
            continue;
        }
        // Vanilla keeps this slot local, so a declare here compiles empty. With
        // a reference sequence to point at we can emit the local outright.
        const std::string& act = order.acts[i];
        spacer(2);
        // The T-pose slot (index 0) and the ragdoll both need a real pose, not an
        // inert clip. Point them at an $animation the modder names "a_reference",
        // so one authored clip fills both without a REPLACE ME.
        if (i == 0 || act.compare(0, 14, "ACT_DIERAGDOLL") == 0) {
            std::fprintf(f, "$sequence \"%s\" { a_reference", res.names[i].c_str());
            if (!act.empty()) std::fprintf(f, " activity %s", act.c_str());
            std::fprintf(f, " }   // slot %d - provide an $animation named a_reference\n",
                         static_cast<int>(i));
            continue;
        }
        if (noanim) {
            emitNoanim(i, "no $includemodel provides this");
            continue;
        }
        if (ref.empty()) {
            std::fprintf(f, "// REPLACE ME - slot %d. No $includemodel provides \"%s\";\n"
                            "// vanilla defines it locally%s%s. Put your own $sequence here\n"
                            "// instead of this declare, or the slot compiles empty.\n"
                            "$declaresequence \"%s\"\n",
                         static_cast<int>(i), res.names[i].c_str(),
                         act.empty() ? "" : " with activity ", act.c_str(), res.names[i].c_str());
            continue;
        }
        std::fprintf(f, "$sequence %s \"%s\" FPS 30", res.names[i].c_str(), ref.c_str());
        if (!act.empty()) std::fprintf(f, " activity %s", act.c_str());
        std::fprintf(f, "   // slot %d - no $includemodel provides this\n", static_cast<int>(i));
    }

    // c6m1's info_survivor_position asks Nick for "c6m3_intro_gambler", a name no
    // model has; his clip is c6m1_intro_gambler. Added past the vanilla slots so no
    // index moves. NOTE: disabled - left for Valve's map fix; flip to 1 to restore.
#if 0
    if (retarget && !std::strcmp(tgt.code, "gambler") && emitted.insert("c6m3_intro_gambler").second) {
        const std::vector<std::string> lines =
            retarget->Sequence(includesOf(tgt), "c6m1_intro_gambler", "c6m3_intro_gambler");
        if (!lines.empty()) {
            std::fprintf(f, "\n// The Passing's c6m1 calls Nick's intro \"c6m3_intro_gambler\" (a map typo);\n"
                            "// this is his c6m1_intro_gambler clip under that name.\n");
            for (const std::string& l : lines) std::fprintf(f, "%s\n", l.c_str());
        }
    }
#endif

    // -nofallbackanimation: a replaced slot declares the donor's name, but the
    // fallback $includemodel re-adds the original vanilla-named sequence as a
    // stray the engine can still play by name. Zero each such re-added name with
    // a local inert bindpose (a local sequence shadows the included one).
    if (nofallback) {
        bool any = false;
        for (size_t i = static_cast<size_t>(skip); i < res.names.size(); ++i) {
            if (res.from[i] == -1) continue; // an inert slot (-2) also drops its name
            // Only names an include actually re-adds. A base-model local (a root
            // reference like "mechanic") is in no include, so nothing re-adds it.
            if (!reachable.count(Lower(order.names[i]))) continue;
            // -keepintro: leave campaign intros (cXmY_intro) for the include.
            if (keepintro && IsCampaignIntro(order.names[i])) continue;
            // Gestures (ACT_GEST_*) are called by name, so shadowing the name
            // would freeze them - leave those to the include. Every other
            // re-added name is selected by activity: zeroing it (below, with no
            // activity) drops it from the pool so only the donor swap competes.
            if (IsGestureName(order.names[i]) ||
                order.acts[i].compare(0, 8, "ACT_GEST") == 0) continue;
            if (rigSupplied.count(Lower(order.names[i]))) continue;
            // `emitted` holds every name the main loop wrote; a shared-name swap
            // declares the vanilla spelling itself, so skip any already present.
            if (!emitted.insert(Lower(order.names[i])).second) continue;
            if (!any) {
                std::fprintf(f, "\n// -nofallbackanimation: zero the original names the fallback\n"
                                "// $includemodel re-adds under a replaced slot, so a stray call\n"
                                "// lands on a do-nothing clip instead of the target's animation.\n");
                any = true;
            }
            std::fprintf(f, "$bindposesequence \"%s\" { noanimation }\n", order.names[i].c_str());
        }
        // Included sequences no slot claimed still sit in their activity's weight
        // pool. Activity-less ones may be name-called layers, so they are kept.
        std::vector<std::string> weighted;
        const auto collectUnclaimed = [&](const Survivor& h) {
            for (const std::string& inc : includesOf(h)) {
                const Mdl* m = mdls.Get(inc);
                if (!m) continue;
                const bool rigOwn = rigIncs.count(Lower(Leaf(inc))) != 0;
                for (size_t k = 0; k < m->seqs.size(); ++k) {
                    const std::string& n = m->seqs[k];
                    if (rigLayers.count(Lower(n)) || (!rigOwn && rigSupplied.count(Lower(n))))
                        continue;
                    const std::string act = k < m->acts.size() ? m->acts[k] : std::string();
                    if (act.empty() || act.compare(0, 8, "ACT_GEST") == 0 || IsGestureName(n)) continue;
                    if (keepintro && IsCampaignIntro(n)) continue;
                    if (!emitted.insert(Lower(n)).second) continue;
                    weighted.push_back(n);
                }
            }
        };
        for (size_t d = 0; d < chain.size(); ++d)
            if (won[d]) collectUnclaimed(*chain[d]);
        collectUnclaimed(tgt);
        if (!weighted.empty()) {
            std::fprintf(f, "\n// -nofallbackanimation: unclaimed included sequences that would\n"
                            "// otherwise compete in an activity's weight pool.\n");
            for (const std::string& n : weighted)
                std::fprintf(f, "$bindposesequence \"%s\" { noanimation }\n", n.c_str());
        }
    }

    // Every included autoplay runs at once, and each set's is its head look. Only the
    // rig's may stay live, or several head looks stack and turn the head wrong.
    std::vector<std::string> autoplays;
    const auto collectAutoplay = [&](const Survivor& h) {
        for (const std::string& inc : includesOf(h)) {
            const Mdl* m = mdls.Get(inc);
            if (!m || rigIncs.count(Lower(Leaf(inc)))) continue;
            for (size_t k = 0; k < m->seqs.size(); ++k)
                if (k < m->autoplay.size() && m->autoplay[k] &&
                    !rigSupplied.count(Lower(m->seqs[k])) && emitted.insert(Lower(m->seqs[k])).second)
                    autoplays.push_back(m->seqs[k]);
        }
    };
    for (size_t d = 0; d < chain.size(); ++d)
        if (won[d]) collectAutoplay(*chain[d]);
    collectAutoplay(tgt);
    if (!autoplays.empty()) {
        std::fprintf(f, "\n// Autoplay head looks from the other included sets, zeroed so only\n"
                        "// the rig's runs.\n");
        for (const std::string& n : autoplays)
            std::fprintf(f, "$bindposesequence \"%s\" { noanimation }\n", n.c_str());
    }

    std::fputc('\n', f);
    const auto include = [&](const Survivor& h) {
        for (const std::string& inc : includesOf(h))
            std::fprintf(f, "$includemodel \"survivors/%s\"\n", Leaf(inc).c_str());
        std::fputc('\n', f);
    };
    for (size_t d = 0; d < chain.size(); ++d)
        if (won[d]) include(*chain[d]); // a donor that filled nothing is dead weight
    include(tgt);                       // last resort for every slot no donor claimed
    if (!file.Close() || (retarget && retarget->failed)) {
        std::fprintf(stderr, "cannot complete %s\n", path.c_str());
        return false;
    }

    std::printf("prepared %s\n", path.c_str());
    for (size_t d = 0; d < chain.size(); ++d) std::printf("    %-10s %5d\n", chain[d]->survivor, won[d]);
    std::printf("    %-10s %5d (fallback)\n", tgt.survivor, kept);
    return true;
}

// The target's map-placed survivor_<code>_light.mdl keeps every clip local with no
// $includemodel, so its whole list is rebuilt on the rig, deltas included.
bool WriteLight(const std::string& path, const Survivor& rig, const Survivor& tgt, Retargeter& rt,
                subtool::OutputTransaction& outputs) {
    const std::string leaf = "survivor_" + std::string(tgt.code) + "_light.mdl";
    // The optional map-placed model is absent in some extracted input sets.
    // If supplied, a failure reading it is an error rather than an omission.
    if (!std::filesystem::exists(std::filesystem::u8path(rt.dir) / leaf)) return true;
    Mdl checked;
    if (!LoadMdl(rt.dir + "/" + leaf, checked)) {
        std::fprintf(stderr, "  -retarget: invalid Light model tables or strings in %s\n", leaf.c_str());
        return false;
    }
    const dc::Mdl* m = rt.Get(leaf);
    if (!m) {
        std::fprintf(stderr, "  -retarget: cannot read %s\n", leaf.c_str());
        return false;
    }
    const fm::studiohdr_t& h = *m->hdr;
    const auto* seqs = m->At<fm::mstudioseqdesc_t>(m->buf.data(), h.localseqindex, h.numlocalseq);
    if (h.numlocalseq == 0) return true;
    if (!seqs || h.numlocalseq < 0) {
        std::fprintf(stderr, "  -retarget: invalid Light sequence table in %s\n", leaf.c_str());
        return false;
    }
    subtool::OutputFile file(outputs.Stage(path));
    FILE* f = file.Get();
    if (!f) {
        std::fprintf(stderr, "cannot write %s\n", path.c_str());
        return false;
    }
    std::fprintf(f, "// l4d_animswap: %s's sequences rebuilt for a %s-rigged model.\n"
                    "// The map-placed _light model, not the playermodel - compile it on its own.\n\n",
                 leaf.c_str(), rig.survivor);
    for (int i = 0; i < h.numlocalseq; ++i) {
        const std::string name = m->Str(&seqs[i], seqs[i].szlabelindex);
        const char* actName = m->Str(&seqs[i], seqs[i].szactivitynameindex);
        const std::string act =
            *actName ? std::string(actName) + " " + std::to_string(seqs[i].actweight) : std::string();
        if (seqs[i].flags & fm::STUDIO_OVERRIDE) {
            std::fprintf(f, "$declaresequence \"%s\"\n\n", name.c_str());
            continue;
        }
        // Same convention as the playermodel script: the reference and ragdoll slots
        // take the modder's own a_reference pose.
        if (i == 0 || act.compare(0, 14, "ACT_DIERAGDOLL") == 0) {
            std::fprintf(f, "$sequence \"%s\" { a_reference", name.c_str());
            if (!act.empty()) std::fprintf(f, " activity %s", act.c_str());
            std::fprintf(f, " }   // slot %d - provide an $animation named a_reference\n\n", i);
            continue;
        }
        const std::vector<std::string> lines = rt.Build(*m, seqs[i], name, "_light", true);
        if (lines.empty()) {
            std::fprintf(f, "// REPLACE ME - slot %d could not be rebuilt; put your own $sequence here.\n"
                            "$declaresequence \"%s\"\n\n",
                         i, name.c_str());
            continue;
        }
        std::fprintf(f, "// slot %d - %s's clip retargeted to %s\n", i, tgt.survivor, rig.survivor);
        for (const std::string& l : lines) std::fprintf(f, "%s\n", l.c_str());
        std::fputc('\n', f);
    }
    if (!file.Close() || rt.failed) {
        std::fprintf(stderr, "cannot complete %s\n", path.c_str());
        return false;
    }
    std::printf("prepared %s\n", path.c_str());
    return true;
}

void PrintHeader() {
    std::printf("-------------------------------\n");
    std::printf("NewPageMergeMDL [L4D2 Anim Swap]\n");
    std::printf("version:   %s\n", PULSEMODEL_VERSION);
    std::printf("developer: Toppi\n");
    std::printf("-------------------------------\n");
}

void Usage() {
    std::printf(
        "L4D2 survivor $declaresequence swap generator\n\n"
        "  l4d_animswap -vanilla <dir> -rig <name> -replace <name> [options]\n"
        "  l4d_animswap -vanilla <dir> -all [-outdir <dir>]\n\n"
        "  -vanilla <dir>  folder with vanilla survivor_*.mdl, anim_*.mdl, gestures_*.mdl\n"
        "  -rig <name>     survivor whose skeleton the model is rigged to (first donor)\n"
        "  -replace <name> survivor whose sequence indices must be matched\n"
        "  -via <a,b,...>  donors tried after -rig; default is the rig's build-alike group\n"
        "  -skip <n>       leading slots the model defines itself (default 2)\n"
        "  -ref <name>     source clip for slots no include can fill; emits a real\n"
        "                  $sequence there instead of a declare that compiles empty\n"
        "  -usenoanimation slots no include can fill are emitted as an inert\n"
        "                  $bindposesequence { noanimation } instead of REPLACE ME\n"
        "  -nofallbackanimation\n"
        "                  also re-declare each replaced vanilla name as an inert\n"
        "                  $bindposesequence, blocking a local server's activity fallback\n"
        "  -keepintro      do not zero L4D2 campaign intros (cXmY_intro); keep the\n"
        "                  target's own intro rather than a do-nothing clip\n"
        "  -retarget       rebuild the target's own campaign intros and dlc1_* scene\n"
        "                  clips (deltas excepted) on the rig's\n"
        "                  skeleton as local $sequence, clips written beside the .qci\n"
        "                  as anims/<name>_retarget_<rig>_for_<target>.dmx; compile them yourself.\n"
        "                  A francis/zoey target also gets <out>_Light.qci, the map\n"
        "                  _light model's whole list rebuilt on the rig\n"
        "  -dmxencoding <enc>  retargeted clips: binary (default) or keyvalues2\n"
        "  -dmxmodel <n>   retargeted clips' `format model`: 15 (default), 1, 18, 22\n"
        "  -o <file>       output path (default Anims_RigTo<Rig>_Replace<Target>.qci)\n"
        "  -all            every rig x replace pair, written into -outdir\n"
        "  -selftest       run the name-matching checks and exit\n\n"
        "  survivors: bill francis louis zoey coach nick ellis rochelle\n");
}

int Fail(const std::string& message) {
    std::fprintf(stderr, "l4d_animswap: %s\n", message.c_str());
    Usage();
    return 2;
}

std::vector<const Survivor*> ParseVia(const std::string& arg, bool& ok) {
    std::vector<const Survivor*> v;
    ok = true;
    if (arg.empty()) {
        std::fprintf(stderr, "-via requires at least one survivor\n");
        ok = false;
        return v;
    }
    for (size_t i = 0;;) {
        const size_t e = arg.find(',', i);
        const std::string one = arg.substr(i, (e == std::string::npos ? arg.size() : e) - i);
        if (one.empty()) {
            std::fprintf(stderr, "-via contains an empty survivor name\n");
            ok = false;
        } else if (const Survivor* h = FindSurvivor(one)) {
            v.push_back(h);
        } else {
            std::fprintf(stderr, "unknown survivor '%s'\n", one.c_str());
            ok = false;
        }
        if (e == std::string::npos) break;
        i = e + 1;
    }
    return v;
}

int SelfTest() {
    const std::set<std::string> codes = CodeTokens();
    std::string sw, st;
    int bad = 0;
    const auto expect = [&](const char* in, const char* wantSw, const char* wantSt) {
        Keys(in, codes, sw, st);
        if (sw != wantSw || st != wantSt) {
            std::fprintf(stderr, "Keys(%s) = %s / %s, want %s / %s\n", in, sw.c_str(), st.c_str(),
                         wantSw, wantSt);
            ++bad;
        }
    };
    expect("NamVet_AimMatrix_Rifle_Standing", "@_aimmatrix_rifle_standing",
           "aimmatrix_rifle_standing");
    expect("Run_Pistol", "run_pistol", "run_pistol");
    expect("coach_gesture_head_yes", "@_gesture_head_yes", "gesture_head_yes");

    // Own spelling beats a borrowed one for the same key, whatever the order.
    Index idx;
    idx.Build({"NamVet_Idle_Rifle", "biker_Idle_Rifle"}, {}, {}, "biker", codes);
    if (idx.swapped["@_idle_rifle"] != "biker_Idle_Rifle") {
        std::fprintf(stderr, "own-codename tiebreak failed\n");
        ++bad;
    }

    // Two target slots wanting one donor name: the second must fall through
    // rather than declare a duplicate (a duplicate compiles to an empty slot).
    std::vector<Index> chain(2);
    chain[0].Build({"biker_Idle_Rifle"}, {}, {}, "biker", codes);
    chain[1].Build({"coach_Idle_Rifle", "Idle_Rifle"}, {}, {}, "coach", codes);
    const Result r = Build({"coach_Idle_Rifle", "Idle_Rifle"}, {}, {}, chain, codes, false);
    if (r.names[0] != "biker_Idle_Rifle" || r.names[1] == r.names[0]) {
        std::fprintf(stderr, "claim-once failed: %s / %s\n", r.names[0].c_str(),
                     r.names[1].c_str());
        ++bad;
    }
    Mdl local, included;
    local.seqs = {"namvet_gesture_head_nod"};
    local.acts = {""};
    local.overrides = {true};
    included.seqs = local.seqs;
    included.acts = {"ACT_GEST_HEAD_NOD 1"};
    Resolver resolver;
    Slots slots;
    std::map<std::string, size_t> seen;
    resolver.Walk(local, slots, seen);
    resolver.Walk(included, slots, seen);
    if (slots.names.size() != 1 || slots.acts[0] != "ACT_GEST_HEAD_NOD 1" ||
        !IsGestureName("namvet_gesture_head_noddefault")) {
        std::fprintf(stderr, "included gesture activity failed\n");
        ++bad;
    }
    std::printf(bad ? "selftest: %d FAILED\n" : "selftest: ok\n", bad);
    return bad ? 1 : 0;
}

} // namespace

int main(int argc, char** argv) try {
    PrintHeader();
    std::string dir, out, outdir = ".", viaArg, ref, dmxEncoding = "binary";
    const Survivor* rig = nullptr;
    const Survivor* tgt = nullptr;
    int skip = 2, dmxModel = 15;
    bool retarget = false, all = false, haveVia = false, noanim = false, nofallback = false, keepintro = false;

    for (int i = 1; i < argc; ++i) {
        const char* a = argv[i];
        std::string argumentError;
        const auto next = [&]() -> const char* {
            if (i + 1 >= argc || !argv[i + 1][0] || LooksLikeOption(argv[i + 1])) {
                argumentError = std::string(a) + " requires a value";
                return nullptr;
            }
            return argv[++i];
        };
        const auto stringArg = [&](std::string& value) {
            const char* token = next();
            if (!token) return false;
            value = token;
            return true;
        };
        const auto intArg = [&](int& value) {
            const char* token = next();
            if (!token) return false;
            if (!ParseIntOption(token, value))
                argumentError = std::string(a) + " requires a complete integer value";
            return argumentError.empty();
        };
        if (!std::strcmp(a, "-vanilla")) { if (!stringArg(dir)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-rig")) {
            std::string value;
            if (!stringArg(value)) return Fail(argumentError);
            rig = FindSurvivor(value);
            if (!rig) return Fail("unknown -rig survivor \"" + value + "\"");
        }
        else if (!std::strcmp(a, "-replace")) {
            std::string value;
            if (!stringArg(value)) return Fail(argumentError);
            tgt = FindSurvivor(value);
            if (!tgt) return Fail("unknown -replace survivor \"" + value + "\"");
        }
        else if (!std::strcmp(a, "-via")) { if (!stringArg(viaArg)) return Fail(argumentError); haveVia = true; }
        else if (!std::strcmp(a, "-skip")) { if (!intArg(skip)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-o")) { if (!stringArg(out)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-outdir")) { if (!stringArg(outdir)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-ref")) { if (!stringArg(ref)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-usenoanimation")) noanim = true;
        else if (!std::strcmp(a, "-nofallbackanimation")) nofallback = true;
        else if (!std::strcmp(a, "-keepintro")) keepintro = true;
        else if (!std::strcmp(a, "-retarget")) retarget = true;
        else if (!std::strcmp(a, "-dmxencoding")) { if (!stringArg(dmxEncoding)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-dmxmodel")) { if (!intArg(dmxModel)) return Fail(argumentError); }
        else if (!std::strcmp(a, "-all")) all = true;
        else if (!std::strcmp(a, "-selftest")) {
            if (argc != 2) return Fail("-selftest takes no additional arguments");
            return SelfTest();
        }
        else return Fail(std::string("unknown option '") + a + "'");
    }
    if (dir.empty() || skip < 0 || (!all && (!rig || !tgt))) {
        return Fail("-vanilla and non-negative -skip are required; -rig and -replace are required unless -all is used");
    }
    if (haveVia) {
        bool ok = false;
        const auto parsedVia = ParseVia(viaArg, ok);
        if (!ok) return 2;
        if (parsedVia.empty()) return Fail("-via requires at least one survivor");
    }
    if (const char* err = dc::SetDmxOutput(dmxEncoding, dmxModel)) {
        std::fprintf(stderr, "%s\n", err);
        return 1;
    }

    const std::set<std::string> codes = CodeTokens();
    Resolver res{dir, {}, false, {}};
    std::map<std::string, Slots> orders;

    std::vector<std::pair<const Survivor*, const Survivor*>> jobs;
    if (all) {
        for (const Survivor& r : kSurvivors)
            for (const Survivor& t : kSurvivors)
                if (&r != &t) jobs.emplace_back(&r, &t);
    } else {
        jobs.emplace_back(rig, tgt);
    }

    // Resolve all dependencies for the requested jobs before opening any QCI.
    // A single swap needs only its target and selected donor chain; unrelated
    // survivors need not be extracted just to convert that pair.
    std::vector<std::vector<const Survivor*>> chains;
    std::set<const Survivor*> required;
    for (const auto& job : jobs) {
        std::vector<const Survivor*> wanted{job.first};
        if (haveVia) {
            bool ok = false;
            for (const Survivor* h : ParseVia(viaArg, ok)) wanted.push_back(h);
            if (!ok) return 1;
        } else if (job.first != job.second) {
            // Rig and target being the same survivor is the no-swap case: vanilla's
            // own list, so pulling in the build-alike group would only steal slots.
            for (const Survivor& h : kSurvivors)
                if (&h != job.first && h.group == job.first->group) wanted.push_back(&h);
        }
        // The target is not a donor - it is the fallback that its own
        // $includemodel provides, so drop it here along with any repeat.
        std::vector<const Survivor*> chain;
        for (const Survivor* h : wanted)
            if (h != job.second && std::find(chain.begin(), chain.end(), h) == chain.end())
                chain.push_back(h);
        required.insert(job.first);
        required.insert(job.second);
        required.insert(chain.begin(), chain.end());
        chains.push_back(std::move(chain));
    }
    for (const Survivor* h : required) {
        orders[h->survivor] = res.Order(*h);
        if (orders[h->survivor].names.size() <= static_cast<size_t>(skip)) {
            std::fprintf(stderr, "no usable sequence list for %s - check survivor_%s.mdl in %s\n",
                         h->survivor, h->code, dir.c_str());
            return 1;
        }
    }
    if (res.missing) {
        std::fprintf(stderr, "required animation model includes are missing, malformed or cyclic; no QCI written\n");
        return 1;
    }

    subtool::OutputTransaction outputs;
    for (size_t jobIndex = 0; jobIndex < jobs.size(); ++jobIndex) {
        const auto& job = jobs[jobIndex];
        const auto& chain = chains[jobIndex];

        std::vector<Index> idx(chain.size());
        for (size_t d = 0; d < chain.size(); ++d)
            idx[d].Build(orders[chain[d]->survivor].names, orders[chain[d]->survivor].acts,
                         orders[chain[d]->survivor].params, chain[d]->code, codes);

        const Slots& order = orders[job.second->survivor];
        const Result built = Build(order.names, order.acts, order.params, idx, codes, keepintro);

        std::string path = out;
        if (path.empty() || all) {
            std::string r = job.first->survivor, t = job.second->survivor;
            r[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(r[0])));
            t[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(t[0])));
            path = (all ? outdir + "/" : std::string()) + "Anims_RigTo" + r + "_Replace" + t +
                   ".qci";
        }
        Retargeter rt;
        if (retarget) {
            const std::filesystem::path parent = std::filesystem::u8path(path).parent_path();
            rt.outputs = &outputs;
            if (!rt.Init(dir, *job.first, *job.second, parent.empty() ? "." : parent.u8string())) return 1;
        }
        if (!Write(path, *job.first, *job.second, chain, built, skip, order, res, ref, noanim,
                   nofallback, keepintro, retarget ? &rt : nullptr, outputs))
            return 1;
        // Rig == target still needs it: the modder's model stands in for the _light one too.
        if (retarget && rt.rigOk) {
            const std::string stem = path.size() > 4 && Lower(path.substr(path.size() - 4)) == ".qci"
                                         ? path.substr(0, path.size() - 4)
                                         : path;
            if (!WriteLight(stem + "_Light.qci", *job.first, *job.second, rt, outputs))
                return 1;
        }
        if (rt.written)
            std::printf("    %d clip(s) retargeted into %s/anims\n", rt.written, rt.outDir.c_str());
    }
    outputs.Commit();
    std::printf("all animation swap outputs published successfully\n");
    return 0;
} catch (const std::exception& error) {
    std::fprintf(stderr, "l4d_animswap: %s\n", error.what());
    return 1;
}
