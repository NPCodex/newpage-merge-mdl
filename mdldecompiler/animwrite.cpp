// animwrite.cpp - rebuilds one animation clip per local animation, as a DMX or
// - on -smdanimation - as an SMD.
//
// The clip is compressed in the .mdl (or demand-loaded from the .ani) in one of
// two encodings, both undone here:
//
//   RLE     - a per-bone chain of mstudio_rle_anim_t. A channel is either a raw
//             constant or an mstudioanimvalue_t run-length stream of int16s,
//             which are offsets from the bone's bind pose scaled by its
//             posscale/rotscale.
//   FRAMEANIM - a per-bone flag byte array, a block of values that never change,
//             then a fixed stride per frame. Values are absolute, no scaling.
//
// Either container holds the same thing: a frame is the parent-relative
// position + rotation that comes out of either encoding, so nothing is lost on
// the way through. DMX is the default; SMD stays for a tool that only reads it.

#include "animwrite.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <map>
#include <limits>
#include <stdexcept>
#include <system_error>
#include <vector>

#include "dmxwrite.h"
#include "selection.h"
#include "math/compressed.h"
#include "pulselimits.h"

namespace mdldecompiler {
namespace {

using Pose = AnimPose;

bool g_smd = false;

struct AnimationDataError : std::runtime_error {
    explicit AnimationDataError(const char* reason)
        : std::runtime_error(std::string("invalid animation data: ") + reason) {}
};

bool MultipleBits(uint8_t value) { return (value & (value - 1)) != 0; }

// A block of animation data plus the bounds it has to stay inside. Sections may
// live in the .mdl or in the .ani, so both files come through here.
struct Block {
    const char* base = nullptr;
    const char* end = nullptr;

    template <typename T>
    const T* At(const void* from, int64_t off, int count = 1) const {
        const uintptr_t b = reinterpret_cast<uintptr_t>(base), e = reinterpret_cast<uintptr_t>(end);
        const uintptr_t f = reinterpret_cast<uintptr_t>(from);
        if (!base || !end || e < b || f < b || f > e || count < 0) return nullptr;
        const int64_t at = static_cast<int64_t>(f - b) + off;
        if (at < 0 || static_cast<uint64_t>(at) > e - b ||
            static_cast<size_t>(count) > (e - b - static_cast<size_t>(at)) / sizeof(T)) return nullptr;
        return reinterpret_cast<const T*>(base + at);
    }
    template <typename T>
    const T* Require(const void* from, int64_t off, int count = 1) const {
        const auto* result = At<T>(from, off, count);
        if (!result) throw AnimationDataError("record offset or byte range is out of bounds");
        return result;
    }
};

// studio.h ExtractAnimValue: the stream is (valid, total) headers each followed
// by `valid` int16s. A frame past `valid` but inside `total` holds the last
// value; a frame past `total` moves on to the next header.
float ExtractAnimValue(const Block& blk, const fm::mstudioanimvalue_t* p, int frame) {
    if (frame < 0) throw AnimationDataError("negative RLE frame");
    // Each valid run consumes at least one frame, so frame+1 bounds traversal.
    while (true) {
        blk.Require<fm::mstudioanimvalue_t>(p, 0);
        const int total = p->num.total, valid = p->num.valid;
        if (total == 0 || valid == 0 || valid > total)
            throw AnimationDataError("invalid RLE valid/total counts");
        blk.Require<fm::mstudioanimvalue_t>(p, 0, valid + 1);
        if (frame < total) {
            const int k = (valid > frame) ? frame + 1 : valid;
            return static_cast<float>(p[k].value);
        }
        frame -= total;
        p = blk.Require<fm::mstudioanimvalue_t>(p, (valid + 1) * 2);
    }
}

// One RLE section -> `out` for the frames it covers. `local` is the frame
// relative to the section's own start.
void DecodeRle(const Block& blk, const char* sect, const fm::mstudiobone_t* bones, int numbones,
               bool delta, int local, std::vector<Pose>& out) {
    const char* p = sect;
    std::vector<bool> visited(static_cast<size_t>(numbones));
    for (int guard = 0; guard <= numbones; ++guard) {
        const auto* e = blk.Require<fm::mstudio_rle_anim_t>(p, 0);
        if (e->bone == 255 && e->flags == 0 && e->nextoffset == 0) return; // empty stream
        if (e->bone >= numbones) {
            throw AnimationDataError("RLE bone index is out of range");
        }
        if (visited[e->bone]) throw AnimationDataError("duplicate or cyclic RLE bone record");
        visited[e->bone] = true;
        if ((e->flags & ~(fm::STUDIO_ANIM_RAWPOS | fm::STUDIO_ANIM_RAWROT | fm::STUDIO_ANIM_ANIMPOS |
                         fm::STUDIO_ANIM_ANIMROT | fm::STUDIO_ANIM_DELTA | fm::STUDIO_ANIM_RAWROT2)) ||
            MultipleBits(e->flags & (fm::STUDIO_ANIM_RAWPOS | fm::STUDIO_ANIM_ANIMPOS)) ||
            MultipleBits(e->flags & (fm::STUDIO_ANIM_RAWROT | fm::STUDIO_ANIM_RAWROT2 | fm::STUDIO_ANIM_ANIMROT)))
            throw AnimationDataError("invalid RLE channel flags");
        const fm::mstudiobone_t& b = bones[e->bone];
        Pose& o = out[e->bone];
        const char* d = p + sizeof(fm::mstudio_rle_anim_t);

        // rotation always comes first, raw or as a value-pointer block
        const fm::mstudioanim_valueptr_t* rotv = nullptr;
        if (e->flags & fm::STUDIO_ANIM_RAWROT2) {
            if (const auto* raw = blk.Require<char>(d, 0, sizeof(pm::Quaternion64))) {
                pm::Quaternion64 q;
                std::memcpy(&q, raw, sizeof(q));
                pm::QuaternionAngles(q.Get(), o.rot);
            }
            d += sizeof(pm::Quaternion64);
        } else if (e->flags & fm::STUDIO_ANIM_RAWROT) {
            if (const auto* q = blk.Require<pm::Quaternion48>(d, 0))
                pm::QuaternionAngles(q->Get(), o.rot);
            d += sizeof(pm::Quaternion48);
        } else if (e->flags & fm::STUDIO_ANIM_ANIMROT) {
            rotv = blk.Require<fm::mstudioanim_valueptr_t>(d, 0);
            d += sizeof(fm::mstudioanim_valueptr_t);
        }

        const fm::mstudioanim_valueptr_t* posv = nullptr;
        if (e->flags & fm::STUDIO_ANIM_RAWPOS) {
            if (const auto* v = blk.Require<pm::Vector48>(d, 0))
                o.pos = v->Get();
            d += sizeof(pm::Vector48);
        } else if (e->flags & fm::STUDIO_ANIM_ANIMPOS) {
            posv = blk.Require<fm::mstudioanim_valueptr_t>(d, 0);
            d += sizeof(fm::mstudioanim_valueptr_t);
        }

        // A stream value is an offset from the bone's STORED pos/rot in scale
        // units; a delta clip has no bind pose to offset from, so it seeds at
        // zero. The stored pair, not the poseToBone-derived one LocalPoses
        // hands the script and the DMX rig - an obfuscated file can hold a
        // decoy there, and the engine still decodes against it, so substituting
        // the real pose here contorts every clip.
        for (int k = 0; k < 3 && rotv; ++k) {
            if (!rotv->offset[k])
                continue;
            if (rotv->offset[k] < static_cast<int>(sizeof(*rotv)))
                throw AnimationDataError("invalid RLE rotation stream offset");
            const auto* s = blk.Require<fm::mstudioanimvalue_t>(rotv, rotv->offset[k]);
            (&o.rot.x)[k] = (delta ? 0.0f : (&b.rot.x)[k]) +
                            ExtractAnimValue(blk, s, local) * (&b.rotscale.x)[k];
        }
        for (int k = 0; k < 3 && posv; ++k) {
            if (!posv->offset[k])
                continue;
            if (posv->offset[k] < static_cast<int>(sizeof(*posv)))
                throw AnimationDataError("invalid RLE position stream offset");
            const auto* s = blk.Require<fm::mstudioanimvalue_t>(posv, posv->offset[k]);
            (&o.pos.x)[k] = (delta ? 0.0f : (&b.pos.x)[k]) +
                            ExtractAnimValue(blk, s, local) * (&b.posscale.x)[k];
        }

        if (e->nextoffset == 0)
            return;
        if (e->nextoffset < d - p)
            throw AnimationDataError("invalid RLE next offset");
        p = blk.Require<char>(p, e->nextoffset);
    }
    throw AnimationDataError("RLE record chain does not terminate");
}

// One STUDIO_FRAMEANIM section. Values are absolute, so the bind pose is only
// the fallback for a bone the section says nothing about.
void DecodeFrameAnim(const Block& blk, const char* sect, int numbones, int local,
                     std::vector<Pose>& out) {
    const auto* fa = blk.Require<fm::mstudio_frame_anim_t>(sect, 0);
    const uint8_t* flags = blk.Require<uint8_t>(fa, sizeof(fm::mstudio_frame_anim_t), numbones);
    if (fa->constantsoffset < 0 || fa->frameoffset < 0 || fa->framelength < 0 || local < 0)
        throw AnimationDataError("negative frame-animation offset or stride");
    for (int j = 0; j < numbones; ++j)
        if (MultipleBits(flags[j] & (fm::STUDIO_FRAME_CONST_ROT | fm::STUDIO_FRAME_CONST_ROT2 |
                                    fm::STUDIO_FRAME_ANIM_ROT | fm::STUDIO_FRAME_ANIM_ROT2)) ||
            MultipleBits(flags[j] & (fm::STUDIO_FRAME_CONST_POS | fm::STUDIO_FRAME_CONST_POS2 |
                                    fm::STUDIO_FRAME_ANIM_POS | fm::STUDIO_FRAME_ANIM_POS2)))
            throw AnimationDataError("conflicting frame-animation channel flags");

    auto rot = [&](const char* d, Pose& o, uint8_t f) -> int {
        if (f & fm::STUDIO_FRAME_CONST_ROT2 || f & fm::STUDIO_FRAME_ANIM_ROT2) {
            if (const auto* q = blk.Require<pm::Quaternion48S>(d, 0))
                pm::QuaternionAngles(q->Get(), o.rot);
            return sizeof(pm::Quaternion48S);
        }
        if (f & fm::STUDIO_FRAME_CONST_ROT || f & fm::STUDIO_FRAME_ANIM_ROT) {
            if (const auto* q = blk.Require<pm::Quaternion48>(d, 0))
                pm::QuaternionAngles(q->Get(), o.rot);
            return sizeof(pm::Quaternion48);
        }
        return 0;
    };
    auto pos = [&](const char* d, Pose& o, uint8_t f) -> int {
        if (f & fm::STUDIO_FRAME_CONST_POS2 || f & fm::STUDIO_FRAME_ANIM_POS2) {
            if (const auto* v = blk.Require<pm::Vector3>(d, 0))
                o.pos = *v;
            return sizeof(pm::Vector3);
        }
        if (f & fm::STUDIO_FRAME_CONST_POS || f & fm::STUDIO_FRAME_ANIM_POS) {
            if (const auto* v = blk.Require<pm::Vector48>(d, 0))
                o.pos = v->Get();
            return sizeof(pm::Vector48);
        }
        return 0;
    };

    const char* c = blk.Require<char>(fa, fa->constantsoffset, 0);
    for (int j = 0; j < numbones; ++j) {
        const uint8_t f = flags[j] & (fm::STUDIO_FRAME_CONST_ROT | fm::STUDIO_FRAME_CONST_ROT2 |
                                      fm::STUDIO_FRAME_CONST_POS | fm::STUDIO_FRAME_CONST_POS2);
        c += rot(c, out[j], f);
        c += pos(c, out[j], f);
    }

    const char* fr = blk.Require<char>(fa, static_cast<int64_t>(fa->frameoffset) +
                                      static_cast<int64_t>(fa->framelength) * local, fa->framelength);
    const char* frameStart = fr;
    for (int j = 0; j < numbones; ++j) {
        const uint8_t f = flags[j] & (fm::STUDIO_FRAME_ANIM_ROT | fm::STUDIO_FRAME_ANIM_ROT2 |
                                      fm::STUDIO_FRAME_ANIM_POS | fm::STUDIO_FRAME_ANIM_POS2);
        fr += rot(fr, out[j], f);
        fr += pos(fr, out[j], f);
    }
    if (fr - frameStart != fa->framelength)
        throw AnimationDataError("frame-animation channel sizes do not match the stride");
}

// All frames of one clip, in the space the .mdl stores them. Returns false when
// a section lives in a .ani that is missing or short.
bool DecodeAnim(const Mdl& m, const fm::mstudioanimdesc_t& a, const fm::mstudiobone_t* bones,
                int numbones, const Block& local, const Block& ext,
                const fm::mstudioanimblock_t* blocks, int numblocks,
                std::vector<std::vector<Pose>>& frames) {
    if (a.numframes <= 0 ||
        numbones < 0 || numbones > pulse::limits::kMaxBones || (numbones > 0 && !bones) ||
        a.sectionframes < 0 || a.animblock < 0 || !std::isfinite(a.fps) || a.fps <= 0)
        throw AnimationDataError("invalid frame count, frame rate, bone count or section size");
    const size_t perFrame = sizeof(std::vector<Pose>) + sizeof(Pose) * static_cast<size_t>(numbones);
    if (static_cast<uint64_t>(a.numframes) > pulse::limits::kMaxDecodedAnimationBytes / perFrame)
        throw AnimationDataError("decoded animation exceeds the memory budget");
    const int numframes = a.numframes;
    const bool delta = (a.flags & fm::STUDIO_DELTA) != 0;
    const bool frameanim = (a.flags & fm::STUDIO_FRAMEANIM) != 0;

    const fm::mstudioanimsections_t* sections =
        a.sectionframes > 0 ? m.At<fm::mstudioanimsections_t>(&a, a.sectionindex,
                                                              numframes / a.sectionframes + 2)
                            : nullptr;
    if (a.sectionframes > 0 && !sections)
        throw AnimationDataError("invalid animation section table");

    frames.assign(static_cast<size_t>(numframes),
                  std::vector<Pose>(static_cast<size_t>(numbones)));
    for (int f = 0; f < numframes; ++f) {
        std::vector<Pose>& out = frames[f];
        for (int j = 0; j < numbones; ++j)
            out[j] = delta ? Pose{} : Pose{bones[j].pos, bones[j].rot};
        // STUDIO_ALLZEROS is a clip the compiler found to be nothing but the
        // bind pose; it carries no data at all and rebuilds from the skeleton.
        if (a.flags & fm::STUDIO_ALLZEROS)
            continue;

        int block = a.animblock, index = a.animindex, sect = 0;
        if (sections) {
            sect = f / a.sectionframes;
            block = sections[sect].animblock;
            index = sections[sect].animindex;
        }

        const Block* blk = &local;
        Block sectionBlock;
        const char* base = nullptr;
        if (block == 0) {
            if (index <= 0) throw AnimationDataError("missing local animation offset");
            base = local.Require<char>(&a, index);
        } else if (block > 0 && ext.base && blocks && block < numblocks) {
            const auto& entry = blocks[block];
            if (entry.datastart < 0 || entry.dataend < entry.datastart || index < 0)
                throw AnimationDataError("invalid external animation block");
            const auto* begin = ext.Require<char>(ext.base, entry.datastart, entry.dataend - entry.datastart);
            sectionBlock = {begin, begin + (entry.dataend - entry.datastart)};
            blk = &sectionBlock;
            base = blk->Require<char>(begin, index);
        } else {
            return false;
        }
        if (!blk->At<char>(base, 0))
            return false;

        const int localFrame = sections ? f - sect * a.sectionframes : f;
        if (frameanim)
            DecodeFrameAnim(*blk, base, numbones, localFrame, out);
        else
            DecodeRle(*blk, base, bones, numbones, delta, localFrame, out);
    }
    return true;
}

// Undo motion extraction. `walkframe` strips the root's travel out of the frames
// and banks it as a piecewise path, so the SMD has to walk again or a recompile
// re-extracts nothing. Movement key k stores the CUMULATIVE pose at its end
// frame, so the segment's own step is prev^-1 * cur, replayed across the segment
// on the stored velocity ramp. Estimated, not exact: the `LQ` quadratic path
// replays as that same ramp, which matches at the ends and drifts in the middle.
void RestoreMotion(const Mdl& m, const fm::mstudioanimdesc_t& a, const fm::mstudiobone_t* bones,
                   int numbones, std::vector<std::vector<Pose>>& frames) {
    const fm::mstudiomovement_t* mv =
        m.At<fm::mstudiomovement_t>(&a, a.movementindex, a.nummovements);
    if (a.nummovements < 0 || (a.nummovements > 0 && !mv))
        throw AnimationDataError("invalid movement table");
    if (a.nummovements == 0 || frames.empty())
        return;
    const int last = static_cast<int>(frames.size()) - 1;
    int previousEnd = -1;
    for (int i = 0; i < a.nummovements; ++i) {
        if (mv[i].endframe < 0 || mv[i].endframe > last || mv[i].endframe <= previousEnd)
            throw AnimationDataError("movement endframe is negative, out of range or unordered");
        previousEnd = mv[i].endframe;
        if (!std::isfinite(mv[i].v0) || !std::isfinite(mv[i].v1) || !std::isfinite(mv[i].angle))
            throw AnimationDataError("non-finite movement velocity or angle");
        for (int k = 0; k < 3; ++k)
            if (!std::isfinite((&mv[i].position.x)[k]) || !std::isfinite((&mv[i].vector.x)[k]))
                throw AnimationDataError("non-finite movement position or vector");
    }

    pm::matrix3x4 prev, ident;
    pm::AngleMatrix(pm::RadianEuler{0.0f, 0.0f, 0.0f}, pm::Vector3{0.0f, 0.0f, 0.0f}, ident);
    prev = ident;
    std::vector<pm::matrix3x4> adj(frames.size(), ident);

    int start = 0;
    for (int k = 0; k < a.nummovements; ++k) {
        pm::matrix3x4 cur;
        pm::AngleMatrix(pm::RadianEuler{0.0f, 0.0f, mv[k].angle * pm::kPiF / 180.0f},
                        mv[k].position, cur);
        pm::RadianEuler srot;
        pm::Vector3 spos;
        pm::MatrixAngles(pm::ConcatTransforms(pm::MatrixInvert(prev), cur), srot, spos);
        const float slen = std::sqrt(spos.x * spos.x + spos.y * spos.y + spos.z * spos.z);
        const pm::Vector3 dir =
            slen > 0.0f ? pm::Vector3{spos.x / slen, spos.y / slen, spos.z / slen}
                        : pm::Vector3{0.0f, 0.0f, 0.0f};

        const int end = std::min(mv[k].endframe, last);
        const float n = static_cast<float>(end - start);
        for (int f = start; n > 0.0f && f <= end; ++f) {
            const float t = (f - start) / n;
            const float d = mv[k].v0 * t + 0.5f * (mv[k].v1 - mv[k].v0) * t * t;
            pm::matrix3x4 step;
            pm::AngleMatrix(pm::RadianEuler{srot.x * t, srot.y * t, srot.z * t},
                            pm::Vector3{dir.x * d, dir.y * d, dir.z * d}, step);
            adj[static_cast<size_t>(f)] = pm::ConcatTransforms(prev, step);
        }
        prev = cur;
        start = std::min(mv[k].endframe, last);
    }
    // the tail past the last key keeps the final adjustment, as the extractor did
    for (int f = start + 1; f <= last; ++f)
        adj[static_cast<size_t>(f)] = prev;

    for (int f = 0; f <= last; ++f) {
        for (int j = 0; j < numbones; ++j) {
            if (bones[j].parent >= 0)
                continue;
            pm::matrix3x4 bm;
            pm::AngleMatrix(frames[f][j].rot, frames[f][j].pos, bm);
            pm::MatrixAngles(pm::ConcatTransforms(adj[static_cast<size_t>(f)], bm),
                             frames[f][j].rot, frames[f][j].pos);
        }
    }
}

// studiomdl re-bakes a delta clip's IK touch error against anims[0], not the
// clip's own subtract base. This finds the non-delta clip whose frame-0 pose,
// used as that base, reproduces the stored error, so shipping it as anims[0]
// makes the re-bake match. Returns false when no delta clip carries a touch rule
// or no candidate reproduces the error - then the ordinary base is kept.
bool RecoverIkBase(const Mdl& m, const std::string& mdlPath, std::vector<pm::Vector3>& outPos,
                   std::vector<pm::RadianEuler>& outRot) {
    const fm::studiohdr_t& h = *m.hdr;
    const auto* descs = m.At<fm::mstudioanimdesc_t>(m.buf.data(), h.localanimindex, h.numlocalanim);
    const auto* bones = m.At<fm::mstudiobone_t>(m.buf.data(), h.boneindex, h.numbones);
    const auto* chains = m.At<fm::mstudioikchain_t>(m.buf.data(), h.ikchainindex, h.numikchains);
    if (!descs || !bones || h.numlocalanim <= 0 || h.numbones <= 0)
        return false;

    std::vector<char> ani;
    const auto* blocks =
        m.At<fm::mstudioanimblock_t>(m.buf.data(), h.animblockindex, h.numanimblocks);
    if (blocks && h.numanimblocks > 1)
        ReadWhole(StripExt(mdlPath) + ".ani", ani);
    const Block local{m.buf.data(), m.buf.data() + m.buf.size()};
    const Block ext{ani.empty() ? nullptr : ani.data(),
                    ani.empty() ? nullptr : ani.data() + ani.size()};

    auto chainEnd = [&](int c) -> int {
        if (!chains || c < 0 || c >= h.numikchains)
            return -1;
        const auto* links =
            m.At<fm::mstudioiklink_t>(&chains[c], chains[c].linkindex, chains[c].numlinks);
        if (!links || chains[c].numlinks < 3) return -1;
        if (links[2].bone < 0 || links[2].bone >= h.numbones)
            throw AnimationDataError("IK chain end bone is out of range");
        return links[2].bone;
    };

    struct Target {
        int clip, touch, hand, start, end;
        const fm::mstudioikrule_t* rule;
        Block blk;
    };
    std::vector<Target> targets;
    for (int i = 0; i < h.numlocalanim; ++i) {
        const auto& a = descs[i];
        if ((a.flags & fm::STUDIO_OVERRIDE) || !(a.flags & fm::STUDIO_DELTA))
            continue;
        const fm::mstudioikrule_t* rules =
            m.At<fm::mstudioikrule_t>(&a, a.ikruleindex, a.numikrules);
        Block rblk = local;
        if (!rules) {
            rules = m.BlockIkRules(a);
            rblk = ext;
        }
        if (!rules)
            continue;
        const float lf = a.numframes > 1 ? static_cast<float>(a.numframes - 1) : 1.0f;
        for (int r = 0; r < a.numikrules; ++r) {
            const int hand = chainEnd(rules[r].chain);
            // bone -1 is a bone-less `touch ""`: its error is the hand in model space
            if (rules[r].type != fm::IK_SELF || rules[r].compressedikerrorindex == 0 || hand < 0 ||
                rules[r].bone < -1 || rules[r].bone >= h.numbones)
                continue;
            auto frame = [&](float phase) {
                const double value = std::round(double(phase) * lf);
                if (!std::isfinite(value) || value < std::numeric_limits<int>::min() ||
                    value > std::numeric_limits<int>::max())
                    throw AnimationDataError("IK phase is not a representable frame");
                return static_cast<int>(value);
            };
            targets.push_back({i, rules[r].bone, hand, frame(rules[r].start),
                               frame(rules[r].end), &rules[r], rblk});
        }
    }
    if (targets.empty())
        return false;

    std::map<int, std::vector<std::vector<Pose>>> clipFrames;
    for (const auto& t : targets)
        if (!clipFrames.count(t.clip))
            DecodeAnim(m, descs[t.clip], bones, h.numbones, local, ext, blocks, h.numanimblocks,
                       clipFrames[t.clip]);

    auto storedError = [&](const Target& t, int frame, pm::Vector3& ep, pm::RadianEuler& er) -> bool {
        const int64_t localFrame = static_cast<int64_t>(frame) - t.start;
        if (localFrame < 0 || localFrame > std::numeric_limits<int>::max()) return false;
        const auto* cie =
            t.blk.At<fm::mstudiocompressedikerror_t>(t.rule, t.rule->compressedikerrorindex);
        if (!cie)
            return false;
        float v[6] = {0, 0, 0, 0, 0, 0};
        for (int c = 0; c < 6; ++c) {
            if (!cie->offset[c])
                continue;
            if (cie->offset[c] < static_cast<int>(sizeof(*cie)))
                throw AnimationDataError("invalid compressed IK stream offset");
            const auto* s = t.blk.At<fm::mstudioanimvalue_t>(cie, cie->offset[c]);
            if (s)
                v[c] = ExtractAnimValue(t.blk, s, static_cast<int>(localFrame)) * cie->scale[c];
        }
        ep = {v[0], v[1], v[2]};
        er = {v[3], v[4], v[5]};
        return true;
    };

    double best = 1e30;
    int bestCmp = 0;
    for (int cand = 0; cand < h.numlocalanim; ++cand) {
        if (descs[cand].flags & (fm::STUDIO_OVERRIDE | fm::STUDIO_DELTA))
            continue;
        std::vector<std::vector<Pose>> cf;
        if (!DecodeAnim(m, descs[cand], bones, h.numbones, local, ext, blocks, h.numanimblocks,
                        cf) ||
            cf.empty())
            continue;
        const std::vector<Pose>& base = cf[0];
        double score = 0;
        int cmp = 0;
        for (const auto& t : targets) {
            auto it = clipFrames.find(t.clip);
            if (it == clipFrames.end() || it->second.empty())
                continue;
            const auto& df = it->second;
            for (int fr : {t.start, static_cast<int>((static_cast<int64_t>(t.start) + t.end) / 2), t.end}) {
                if (fr < 0 || fr >= static_cast<int>(df.size()))
                    continue;
                std::vector<pm::matrix3x4> world(static_cast<size_t>(h.numbones));
                for (int b = 0; b < h.numbones; ++b) {
                    pm::Quaternion qb, qd, q3;
                    pm::AngleQuaternion(base[b].rot, qb);
                    pm::AngleQuaternion(df[fr][b].rot, qd);
                    pm::QuaternionMA(qb, 1.0f, qd, q3);
                    pm::RadianEuler e3;
                    pm::QuaternionAngles(q3, e3);
                    const pm::Vector3 p3{base[b].pos.x + df[fr][b].pos.x,
                                         base[b].pos.y + df[fr][b].pos.y,
                                         base[b].pos.z + df[fr][b].pos.z};
                    pm::matrix3x4 mm;
                    pm::AngleMatrix(e3, p3, mm);
                    world[b] = bones[b].parent < 0
                                   ? mm
                                   : pm::ConcatTransforms(world[bones[b].parent], mm);
                }
                const pm::matrix3x4 loc =
                    t.touch < 0 ? world[t.hand]
                                : pm::ConcatTransforms(pm::MatrixInvert(world[t.touch]), world[t.hand]);
                pm::RadianEuler cr;
                pm::Vector3 cp;
                pm::MatrixAngles(loc, cr, cp);
                pm::Vector3 ep;
                pm::RadianEuler er;
                if (!storedError(t, fr, ep, er))
                    continue;
                pm::Quaternion qc, qe;
                pm::AngleQuaternion(cr, qc);
                pm::AngleQuaternion(er, qe);
                const double dq =
                    1.0 - std::fabs(qc.x * qe.x + qc.y * qe.y + qc.z * qe.z + qc.w * qe.w);
                const double dp = (cp.x - ep.x) * (cp.x - ep.x) + (cp.y - ep.y) * (cp.y - ep.y) +
                                  (cp.z - ep.z) * (cp.z - ep.z);
                score += dp + dq * 100.0;
                ++cmp;
            }
        }
        if (cmp && score < best) {
            best = score;
            bestCmp = cmp;
            outPos.assign(static_cast<size_t>(h.numbones), pm::Vector3{});
            outRot.assign(static_cast<size_t>(h.numbones), pm::RadianEuler{});
            for (int b = 0; b < h.numbones; ++b) {
                outPos[b] = base[b].pos;
                outRot[b] = base[b].rot;
            }
        }
    }
    // only take the recovered base when it actually reproduces the error; a poor
    // best means the true base was never in the file, so leave the default.
    return bestCmp > 0 && best / bestCmp < 2.0;
}

} // namespace

void ComputeIkBaseRecovery(Mdl& m, const std::string& mdlPath) try {
    std::vector<pm::Vector3> pos;
    std::vector<pm::RadianEuler> rot;
    if (RecoverIkBase(m, mdlPath, pos, rot)) {
        m.ikRecovered = true;
        m.ikBasePos = std::move(pos);
        m.ikBaseRot = std::move(rot);
    }
} catch (const AnimationDataError& e) {
    ExtractionError(e.what());
}

void SetAnimFormat(bool smd) { g_smd = smd; }

const char* AnimExt() { return g_smd ? ".smd" : ".dmx"; }

namespace {

// Decodes a model's local clips into the space the decompile writes them: delta
// and motion extraction undone, root bones un-yawed.
struct ClipSource {
    const Mdl& m;
    const fm::mstudioanimdesc_t* descs = nullptr;
    const fm::mstudiobone_t* bones = nullptr;
    const fm::mstudioanimblock_t* blocks = nullptr;
    Block local, ext;
    int baseIndex = -1;
    std::vector<Pose> realBase, bindPose;
    pm::matrix3x4 unrotate;

    ClipSource(const Mdl& mdl, const std::vector<char>& ani) : m(mdl) {
        const fm::studiohdr_t& h = *m.hdr;
        descs = m.At<fm::mstudioanimdesc_t>(m.buf.data(), h.localanimindex, h.numlocalanim);
        bones = m.At<fm::mstudiobone_t>(m.buf.data(), h.boneindex, h.numbones);
        blocks = m.At<fm::mstudioanimblock_t>(m.buf.data(), h.animblockindex, h.numanimblocks);
        local = {m.buf.data(), m.buf.data() + m.buf.size()};
        ext = {ani.empty() ? nullptr : ani.data(), ani.empty() ? nullptr : ani.data() + ani.size()};

        // BuildRawTransforms yaws a source clip's ROOT bones by g_defaultrotation
        // (+90 about Z) on the way in, so the clip goes back out with that removed.
        // Child bones are parent-relative and never see it.
        // Y-up bakes {pi/2,0,pi/2}, whose inverse is not a single negated euler.
        if (ModelUsesUpAxisY(m)) {
            pm::matrix3x4 fwd;
            pm::AngleMatrix(pm::RadianEuler{pm::kPiF / 2.0f, 0.0f, pm::kPiF / 2.0f}, fwd);
            unrotate = pm::MatrixInvert(fwd);
        } else {
            pm::AngleMatrix(pm::RadianEuler{0.0f, 0.0f, -pm::kPiF / 2.0f}, unrotate);
        }
        if (!Valid())
            return;
        for (int j = 0; j < h.numbones; ++j) {
            int parent = j;
            for (int depth = 0; parent >= 0; ++depth) {
                if (parent >= h.numbones || depth >= h.numbones || bones[parent].parent < -1)
                    throw AnimationDataError("invalid bone parent or cyclic hierarchy");
                parent = bones[parent].parent;
            }
            for (int k = 0; k < 3; ++k)
                if (!std::isfinite((&bones[j].pos.x)[k]) || !std::isfinite((&bones[j].rot.x)[k]))
                    throw AnimationDataError("non-finite bind pose");
        }

        // A delta clip is stored already subtracted, but the .pulseqc rebuilds it
        // with `subtract "<base>" 0` - so the SMD has to carry the pose BEFORE the
        // subtraction or the compiler takes it out twice. Decode the base once up
        // front to put it back; where the file has no clip that can serve, the bind
        // pose does, and gets written out as a clip of its own.
        baseIndex = SubtractBase(m, AnimRefs(m));
        bindPose.resize(static_cast<size_t>(h.numbones));
        for (int j = 0; j < h.numbones; ++j)
            bindPose[j] = Pose{bones[j].pos, bones[j].rot};
        // the recovered IK base ships as a_bindpose, so its pose replaces the skeleton
        // bind pose the synthesized clip would otherwise carry
        if (m.ikRecovered && static_cast<int>(m.ikBasePos.size()) == h.numbones)
            for (int j = 0; j < h.numbones; ++j)
                bindPose[j] = Pose{m.ikBasePos[j], m.ikBaseRot[j]};
        if (baseIndex >= 0) {
            std::vector<std::vector<Pose>> f;
            if (!DecodeAnim(m, descs[baseIndex], bones, h.numbones, local, ext, blocks,
                            h.numanimblocks, f) || f.empty())
                throw AnimationDataError("cannot decode subtract base (check ANI sidecar)");
            realBase = f[0];
        }
    }

    bool Valid() const {
        return descs && m.hdr->numlocalanim > 0 && m.hdr->numbones >= 0 &&
               m.hdr->numbones <= pulse::limits::kMaxBones &&
               (m.hdr->numbones == 0 || bones);
    }

    void UnyawRoots(std::vector<Pose>& fr) const {
        for (int j = 0; j < m.hdr->numbones; ++j) {
            if (bones[j].parent >= 0)
                continue;
            pm::matrix3x4 mm;
            pm::AngleMatrix(fr[j].rot, fr[j].pos, mm);
            pm::MatrixAngles(pm::ConcatTransforms(unrotate, mm), fr[j].rot, fr[j].pos);
        }
    }

    // False when the clip's data is in a .ani that is missing or short.
    bool Decode(int i, std::vector<std::vector<Pose>>& frames) const {
        const fm::studiohdr_t& h = *m.hdr;
        const fm::mstudioanimdesc_t& a = descs[i];
        if (!DecodeAnim(m, a, bones, h.numbones, local, ext, blocks, h.numanimblocks, frames))
            return false;

        // Undo SubtractBaseAnimations. The script writes `subtract`, which the
        // compiler runs with STUDIO_POST - so the delta is base^-1 * pose and
        // pose - base, whatever the clip's own POST flag says. (`presubtract`
        // is the other direction; nothing here emits it.) A bone the clip's
        // weightlist zeroed was left absolute and is quietly wrong here - rare
        // enough to live with.
        if (a.flags & fm::STUDIO_DELTA) {
            const std::vector<Pose>& subBase =
                (baseIndex >= 0 && baseIndex < i && !realBase.empty()) ? realBase : bindPose;
            for (std::vector<Pose>& fr : frames) {
                for (int j = 0; j < h.numbones; ++j) {
                    pm::Quaternion qbase, qd;
                    pm::AngleQuaternion(subBase[j].rot, qbase);
                    pm::AngleQuaternion(fr[j].rot, qd);
                    pm::QuaternionSMAngles(1.0f, qbase, qd, fr[j].rot);
                    fr[j].pos = {fr[j].pos.x + subBase[j].pos.x, fr[j].pos.y + subBase[j].pos.y,
                                 fr[j].pos.z + subBase[j].pos.z};
                }
            }
        }

        // motion was extracted in the yawed compile space, so it goes back on
        // before the yaw comes off
        RestoreMotion(m, a, bones, h.numbones, frames);

        for (std::vector<Pose>& fr : frames) {
            UnyawRoots(fr);
            for (const auto& pose : fr)
                for (int k = 0; k < 3; ++k)
                    if (!std::isfinite((&pose.pos.x)[k]) || !std::isfinite((&pose.rot.x)[k]))
                        throw AnimationDataError("decoded pose is not finite");
        }
        return true;
    }
};

} // namespace

bool DecodeClip(const Mdl& m, int anim, std::vector<std::vector<AnimPose>>& frames) try {
    const ClipSource src(m, m.ani);
    return src.Valid() && anim >= 0 && anim < m.hdr->numlocalanim && src.Decode(anim, frames);
} catch (const AnimationDataError& e) {
    frames.clear();
    ExtractionError(e.what());
    return false;
}

std::vector<AnimPose> BindPose(const Mdl& m) {
    const ClipSource src(m, m.ani);
    std::vector<Pose> pose;
    for (int j = 0; src.bones && j < m.hdr->numbones; ++j)
        pose.push_back(Pose{src.bones[j].pos, src.bones[j].rot});
    if (src.bones)
        src.UnyawRoots(pose);
    return pose;
}

void WriteAnimationFiles(const Mdl& m, const std::string& mdlPath, const std::string& dir) try {
    const fm::studiohdr_t& h = *m.hdr;
    // demand-loaded sections live in the sibling .ani, addressed through the
    // block table; without it those clips are skipped rather than half written
    std::vector<char> ani;
    if (m.At<fm::mstudioanimblock_t>(m.buf.data(), h.animblockindex, h.numanimblocks) &&
        h.numanimblocks > 1)
        ReadWhole(StripExt(mdlPath) + ".ani", ani);
    const ClipSource src(m, ani);
    if (!src.Valid()) {
        if (h.numlocalanim > 0) ExtractionError("invalid animation table or skeleton");
        return;
    }
    const fm::mstudioanimdesc_t* descs = src.descs;
    const fm::mstudiobone_t* bones = src.bones;

    const std::vector<std::string> boneNames = BoneNames(m);
    const std::vector<AnimRef> refs = AnimRefs(m);
    const std::string animDir = dir + "/anims";
    std::error_code ec;
    std::filesystem::create_directories(animDir, ec);
    if (ec) {
        ExtractionError("cannot create animation directory: " + ec.message());
        return;
    }

    auto emit = [&](const std::string& name, const std::vector<std::vector<Pose>>& frames,
                    float fps, const std::vector<size_t>* keep = nullptr) {
        const std::string path = animDir + "/" + name + AnimExt();
        if (!g_smd) {
            if (!WriteAnimationDmx(m, path, name, fps, frames, nullptr, keep)) {
                ExtractionError("cannot write \"" + path + "\"");
                return false;
            }
            std::printf("  wrote %s (%d frame%s, %d bones)\n", path.c_str(),
                        static_cast<int>(frames.size()), frames.size() == 1 ? "" : "s", h.numbones);
            return true;
        }
        std::FILE* f = std::fopen(path.c_str(), "wb");
        if (!f) {
            ExtractionError("cannot write \"" + path + "\"");
            return false;
        }
        std::fprintf(f, "version 1\nnodes\n");
        for (int j = 0; j < h.numbones; ++j)
            std::fprintf(f, "%d \"%s\" %d\n", j, boneNames[j].c_str(), bones[j].parent);
        std::fprintf(f, "end\nskeleton\n");
        for (size_t fr = 0; fr < frames.size(); ++fr) {
            std::fprintf(f, "time %d\n", static_cast<int>(fr));
            for (int j = 0; j < h.numbones; ++j) {
                const Pose& p = frames[fr][j];
                std::fprintf(f, "%d %s %s %s %s %s %s\n", j, F(p.pos.x).c_str(), F(p.pos.y).c_str(),
                             F(p.pos.z).c_str(), F(p.rot.x).c_str(), F(p.rot.y).c_str(),
                             F(p.rot.z).c_str());
            }
        }
        std::fprintf(f, "end\n");
        if (!CloseOutput(f, path)) return false;
        std::printf("  wrote %s (%d frame%s, %d bones)\n", path.c_str(),
                    static_cast<int>(frames.size()), frames.size() == 1 ? "" : "s", h.numbones);
        return true;
    };

    int written = 0, skipped = 0;
    if (NeedsBindPoseAnim(m, src.baseIndex)) {
        std::vector<std::vector<Pose>> one{src.bindPose};
        src.UnyawRoots(one[0]);
        if (emit(kBindPoseAnim, one, 30)) // the fps the .pulseqc writes for it
            ++written;
    }
    for (int i = 0; i < h.numlocalanim; ++i) {
        if (!AnimationSelected(i)) continue;
        const fm::mstudioanimdesc_t& a = descs[i];
        if (a.flags & fm::STUDIO_OVERRIDE)
            continue; // $declareanimation - the data lives in the $includemodel

        std::vector<std::vector<Pose>> frames;
        if (!src.Decode(i, frames)) {
            ExtractionError("cannot decode animation \"" + refs[i].name +
                            "\": animation data is missing, truncated or invalid (check the .ani sidecar)");
            ++skipped;
            continue;
        }

        // the clip's own fps, so the DMX key times land on the frames the
        // `fps` the script writes will sample
        const float fps = a.fps > 0.0f ? a.fps : 30.0f;
        if (!std::isfinite(a.fps)) {
            ExtractionError("invalid frame rate in animation \"" + refs[i].name + "\"");
            ++skipped;
            continue;
        }
        std::set<size_t> boundaries;
        const auto keepFrame = [&](float frame) {
            if (!std::isfinite(frame)) return;
            for (int offset = -1; offset <= 1; ++offset) {
                const auto value = static_cast<int64_t>(std::floor(frame)) + offset;
                if (value >= 0 && value < static_cast<int64_t>(frames.size())) boundaries.insert(static_cast<size_t>(value));
            }
            if (frame >= 0 && frame < frames.size()) boundaries.insert(static_cast<size_t>(std::ceil(frame)));
        };
        const auto* seqs = m.At<fm::mstudioseqdesc_t>(m.buf.data(), h.localseqindex, h.numlocalseq);
        for (int si = 0; seqs && si < h.numlocalseq; ++si) {
            const auto& seq = seqs[si];
            const int64_t cells = static_cast<int64_t>(seq.groupsize[0]) * seq.groupsize[1];
            const auto* grid = cells > 0 && cells <= 4096 ? m.At<int16_t>(&seq, seq.animindexindex, static_cast<size_t>(cells)) : nullptr;
            if (!grid || std::find(grid, grid + cells, i) == grid + cells) continue;
            const float last = static_cast<float>(frames.size() - 1);
            const auto* events = m.At<fm::mstudioevent_t>(&seq, seq.eventindex, seq.numevents);
            for (int j = 0; events && j < seq.numevents; ++j) keepFrame(events[j].cycle * last);
            const auto* layers = m.At<fm::mstudioautolayer_t>(&seq, seq.autolayerindex, seq.numautolayers);
            for (int j = 0; layers && j < seq.numautolayers; ++j)
                if (!(layers[j].flags & fm::STUDIO_AL_POSE))
                    for (float phase : {layers[j].start,layers[j].peak,layers[j].tail,layers[j].end}) keepFrame(phase * last);
        }
        const auto* rules = a.animblock ? m.BlockIkRules(a) : m.At<fm::mstudioikrule_t>(&a, a.ikruleindex, a.numikrules);
        for (int j = 0; rules && j < a.numikrules; ++j)
            for (float phase : {rules[j].start,rules[j].peak,rules[j].tail,rules[j].end,rules[j].contact})
                keepFrame(phase * (frames.size()-1));
        const auto* movement = m.At<fm::mstudiomovement_t>(&a, a.movementindex, a.nummovements);
        for (int j = 0; movement && j < a.nummovements; ++j) keepFrame(static_cast<float>(movement[j].endframe));
        const std::vector<size_t> keep(boundaries.begin(),boundaries.end());
        if (emit(refs[i].name, frames, fps, &keep))
            ++written;
        else
            ++skipped;
    }

    if (written)
        std::printf("%d animation clip%s in %s\n", written, written == 1 ? "" : "s",
                    animDir.c_str());
    if (skipped)
        std::printf("  %d animation%s could not be extracted\n", skipped, skipped == 1 ? "" : "s");
} catch (const AnimationDataError& e) {
    ExtractionError(e.what());
}

} // namespace mdldecompiler
