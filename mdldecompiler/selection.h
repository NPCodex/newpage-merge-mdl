#pragma once
#include <functional>
#include <stdexcept>
#include <set>
#include <string>

namespace mdldecompiler {
inline std::set<std::string> g_animationNames, g_sequenceNames;
inline std::set<int> g_bodygroups, g_lods, g_selectedAnimations;
inline bool AssetSelection() {
    return !g_animationNames.empty() || !g_sequenceNames.empty() || !g_bodygroups.empty() || !g_lods.empty();
}
inline bool SelectMeshes() { return !g_bodygroups.empty() || !g_lods.empty(); }
inline bool SelectAnimations() { return !g_animationNames.empty() || !g_sequenceNames.empty(); }
inline bool AnimationSelected(int i) { return !AssetSelection() || g_selectedAnimations.count(i) != 0; }
// Resolve names against the stored tables. Sequence layers and delta bases are
// retained as dependencies; selection never promises an independent project.
inline void ResolveSelection(const Mdl& m) {
    g_selectedAnimations.clear();
    if (!AssetSelection()) return;
    const auto& h = *m.hdr;
    for (int part : g_bodygroups)
        if (part >= h.numbodyparts) throw std::runtime_error("selected bodygroup index does not exist: " + std::to_string(part));
    const auto refs = AnimRefs(m);
    const auto* anims = m.At<fm::mstudioanimdesc_t>(m.buf.data(), h.localanimindex, h.numlocalanim);
    for (const auto& name : g_animationNames) {
        bool found = false;
        for (size_t i = 0; i < refs.size(); ++i)
            if (BoneNameKey(refs[i].name) == BoneNameKey(name)) { g_selectedAnimations.insert(static_cast<int>(i)); found = true; }
        if (!found) throw std::runtime_error("selected animation does not exist: " + name);
    }
    const auto* seqs = m.At<fm::mstudioseqdesc_t>(m.buf.data(), h.localseqindex, h.numlocalseq);
    std::set<int> visited;
    const std::function<void(int)> select = [&](int index) {
        if (index < 0 || index >= h.numlocalseq || !seqs) throw std::runtime_error("invalid selected sequence layer");
        if (!visited.insert(index).second) return;
        const auto& s = seqs[index];
        if (s.flags & fm::STUDIO_OVERRIDE) {
            QualityWarning("Selected sequence is supplied by an included model: " + std::string(m.Str(&s, s.szlabelindex)), true);
            return;
        }
        const int64_t count = static_cast<int64_t>(s.groupsize[0]) * s.groupsize[1];
        const auto* grid = count > 0 && count <= 4096 ? m.At<int16_t>(&s, s.animindexindex, static_cast<size_t>(count)) : nullptr;
        if (!grid) throw std::runtime_error("invalid selected sequence blend grid");
        for (int i = 0; i < count; ++i) {
            if (grid[i] < 0 || grid[i] >= h.numlocalanim) throw std::runtime_error("invalid selected animation reference");
            g_selectedAnimations.insert(grid[i]);
        }
        const auto* layers = m.At<fm::mstudioautolayer_t>(&s, s.autolayerindex, s.numautolayers);
        if (s.numautolayers < 0 || (s.numautolayers && !layers)) throw std::runtime_error("invalid selected sequence autolayers");
        for (int i = 0; layers && i < s.numautolayers; ++i) select(layers[i].iSequence);
    };
    for (const auto& name : g_sequenceNames) {
        bool found = false;
        for (int i = 0; seqs && i < h.numlocalseq; ++i)
            if (BoneNameKey(m.Str(&seqs[i], seqs[i].szlabelindex)) == BoneNameKey(name)) { select(i); found = true; }
        if (!found) throw std::runtime_error("selected sequence does not exist: " + name);
    }
    const int base = SubtractBase(m, refs);
    bool delta = false;
    for (int i : g_selectedAnimations) delta |= anims && (anims[i].flags & fm::STUDIO_DELTA);
    if (delta && base >= 0) g_selectedAnimations.insert(base);
}
}
