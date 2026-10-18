#pragma once

#include <charconv>
#include <cmath>
#include <string>

namespace pulse::cli {

inline bool Integer(const std::string& text, int& value) {
    if (text.empty()) return false;
    const char* first = text.data();
    const char* last = first + text.size();
    if (*first == '+') ++first;
    if (first == last || (*first == '-' && text.front() == '+')) return false;
    const auto parsed = std::from_chars(first, last, value);
    return parsed.ec == std::errc{} && parsed.ptr == last;
}

inline bool Number(const std::string& text, float& value) {
    if (text.empty()) return false;
    const char* first = text.data();
    const char* last = first + text.size();
    if (*first == '+') ++first;
    if (first == last || (*first == '-' && text.front() == '+')) return false;
    const auto parsed = std::from_chars(first, last, value);
    return parsed.ec == std::errc{} && parsed.ptr == last && std::isfinite(value);
}

// Negative numbers are values; another option is not a missing option's value.
// A path beginning with '-' can be made unambiguous with './' or an absolute path.
inline bool MissingValue(const char* value) {
    if (!value || !*value) return true;
    if (*value != '-') return false;
    float number;
    return !Number(value, number);
}

} // namespace pulse::cli
