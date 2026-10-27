// Preserve existing local sequence order, as observed in StudioMDL++.
// Read only the header, sequence table and names; never trust file offsets.
#ifndef NEWPAGE_SEQUENCE_REMAP_H
#define NEWPAGE_SEQUENCE_REMAP_H
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <numeric>
#include <string>
#include <unordered_map>
#include "compile.h"
#include "format/mdl.h"
#include "pathcompat.h"

namespace newpage {
inline std::string SequenceNameKey(std::string name) {
    for (char& c : name) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return name;
}

inline bool PreserveSequenceOrder(pulse::compile::CompiledModel& model,
                                  const std::filesystem::path& modelDirectory, std::string& warning) {
    namespace fm = pulse::format;
    const auto file = modelDirectory / pulse::FilePath(model.outname + ".mdl");
    std::error_code ec;
    if (!std::filesystem::exists(file, ec)) return true;
    auto invalid = [&]() {
        warning = "Cannot preserve sequence order from invalid/unsupported model: " + file.string();
        return false;
    };
    std::ifstream stream(file, std::ios::binary | std::ios::ate);
    if (!stream) return invalid();
    const int64_t size = static_cast<int64_t>(stream.tellg());
    if (size < static_cast<int64_t>(sizeof(fm::studiohdr_t))) return invalid();
    stream.seekg(0);
    fm::studiohdr_t header{};
    if (!stream.read(reinterpret_cast<char*>(&header), sizeof(header))) return invalid();
    if (header.id != 0x54534449 || (header.version != 48 && header.version != 49) ||
        header.length < static_cast<int32_t>(sizeof(header)) || header.length > size ||
        header.numlocalseq < 0 || header.numlocalseq > 32767 || header.localseqindex < 0 ||
        int64_t(header.localseqindex) + int64_t(header.numlocalseq) * sizeof(fm::mstudioseqdesc_t) > header.length)
        return invalid();
    std::unordered_map<std::string, int> ranks;
    for (int i = 0; i < header.numlocalseq; ++i) {
        const int64_t offset = int64_t(header.localseqindex) + int64_t(i) * sizeof(fm::mstudioseqdesc_t);
        fm::mstudioseqdesc_t sequence{};
        stream.seekg(offset);
        if (!stream.read(reinterpret_cast<char*>(&sequence), sizeof(sequence))) return invalid();
        const int64_t label = offset + int64_t(sequence.szlabelindex);
        if (label < static_cast<int64_t>(sizeof(header)) || label >= header.length) return invalid();
        stream.seekg(label);
        std::string name;
        bool terminated = false;
        // Bounds are the declared file length, not a guessed fixed name limit.
        for (int64_t p = label; p < header.length; ++p) {
            char c;
            if (!stream.get(c)) return invalid();
            if (!c) { terminated = true; break; }
            name += c;
            if (name.size() > 4096) return invalid();
        }
        if (!terminated || name.empty() || !ranks.emplace(SequenceNameKey(name), i).second) return invalid();
    }
    std::vector<size_t> order(model.sequences.size());
    std::iota(order.begin(), order.end(), 0);
    auto rank = [&](size_t i) {
        auto it = ranks.find(SequenceNameKey(model.sequences[i].name));
        return it == ranks.end() ? header.numlocalseq : it->second;
    };
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) { return rank(a) < rank(b); });
    std::vector<int> remap(order.size());
    for (size_t i = 0; i < order.size(); ++i) remap[order[i]] = static_cast<int>(i);
    for (const auto& sequence : model.sequences)
        for (const auto& layer : sequence.autolayers)
            if (layer.sequence < 0 || layer.sequence >= static_cast<int>(remap.size())) return invalid();
    std::vector<pulse::compile::Sequence> reordered;
    reordered.reserve(order.size());
    for (size_t index : order) reordered.push_back(std::move(model.sequences[index]));
    for (auto& sequence : reordered)
        for (auto& layer : sequence.autolayers) layer.sequence = remap[layer.sequence];
    model.sequences.swap(reordered);
    return true;
}
} // namespace newpage
#endif
