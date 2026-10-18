#pragma once

#include <filesystem>
#include <initializer_list>
#include <string>

#include "generated_assets.h"
#include "transaction.h"

namespace ag2 {

inline void RemoveUncompiledResources(OutputTransaction& transaction, const std::filesystem::path& output,
                                      std::initializer_list<const char*> sources) {
    for (const char* source : sources)
        transaction.Remove(output / std::filesystem::u8path(std::string(source) + "_c"));
}

} // namespace ag2
