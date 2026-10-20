#pragma once

#include <cstdint>
#include <cstring>
#include <limits>

namespace pulse::tool::detail {

// Bulk mesh arrays are passed directly to meshoptimizer/VHACD. Keep the v1/v2
// wire layout unchanged, but reject unsupported hosts rather than silently
// interpreting little-endian array data in host byte order.
inline bool SupportsBinaryProtocol() {
    static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
                  "meshtool requires IEEE-754 binary32 floats");
    static_assert(sizeof(unsigned int) == 4 && sizeof(std::int32_t) == 4,
                  "meshtool requires 32-bit mesh indices");
    static_assert(sizeof(std::size_t) >= 8, "meshtool requires a 64-bit host");
    const std::uint32_t one = 1;
    unsigned char first = 0;
    std::memcpy(&first, &one, 1);
    return first == 1;
}

} // namespace pulse::tool::detail
