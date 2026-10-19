#pragma once

#include <cstddef>
#include <string>

namespace pulse::tool::detail {

#ifdef PULSE_MESHTOOL_RESPONSE_TESTING
bool ResponseWriteTestFail(const char* stage);
#else
inline bool ResponseWriteTestFail(const char*) { return false; }
#endif

bool WriteResponseAtomically(const std::string& responsePath, const void* data,
                             std::size_t size, std::string* err);

} // namespace pulse::tool::detail
