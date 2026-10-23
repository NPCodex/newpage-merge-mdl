#pragma once
#include <algorithm>
#include <cmath>
#include <numeric>
#include <set>
#include <vector>
#include "math/math.h"

namespace mdldecompiler {
inline float g_reducePosition = 0, g_reduceAngle = 0;
inline pm::Vector3 KeyLerp(const pm::Vector3& a, const pm::Vector3& b, float t) {
    return {a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t};
}
inline pm::Quaternion KeyLerp(const pm::Quaternion& a, const pm::Quaternion& b, float t) {
    pm::Quaternion q; pm::QuaternionSlerp(a, b, t, q); pm::QuaternionNormalize(q); return q;
}
inline double KeyError(const pm::Vector3& a, const pm::Vector3& b) {
    const double x = double(a.x) - b.x, y = double(a.y) - b.y, z = double(a.z) - b.z;
    return std::sqrt(x*x + y*y + z*z);
}
inline double KeyError(const pm::Quaternion& a, const pm::Quaternion& b) {
    const double dot = double(a.x)*b.x + double(a.y)*b.y + double(a.z)*b.z + double(a.w)*b.w;
    const double aa = double(a.x)*a.x + double(a.y)*a.y + double(a.z)*a.z + double(a.w)*a.w;
    const double bb = double(b.x)*b.x + double(b.y)*b.y + double(b.z)*b.z + double(b.w)*b.w;
    return 2 * std::acos(std::min(1.0, std::abs(dot) / std::sqrt(aa*bb))) * pm::kRad2Deg;
}
// Iterative, bounded-span Douglas-Peucker. Compare the stored tick timeline at
// every source key plus each quarter of each source interval. Endpoints and
// supplied event/IK boundaries cannot be removed; all values remain original.
template<class T>
std::vector<size_t> ReduceKeys(const std::vector<T>& values, const std::vector<float>& times,
                               float tolerance, const std::vector<size_t>* protectedKeys) {
    std::vector<size_t> result(values.size());
    std::iota(result.begin(), result.end(), 0);
    if (values.size() < 3 || tolerance <= 0) return result;
    std::set<size_t> keep{0, values.size()-1};
    if (protectedKeys) for (size_t i : *protectedKeys) if (i < values.size()) keep.insert(i);
    // Bound worst-case scanning work without changing the promised error bound.
    for (size_t i = 256; i < values.size(); i += 256) keep.insert(i);
    std::vector<std::pair<size_t, size_t>> pending;
    for (auto it = keep.begin(), next = std::next(it); next != keep.end(); ++it, ++next)
        pending.emplace_back(*it, *next);
    while (!pending.empty()) {
        const auto [a,b] = pending.back(); pending.pop_back();
        if (b <= a+1) continue;
        double worst = tolerance; size_t split = a;
        for (size_t i = a; i < b; ++i)
            for (int q = 0; q < 4; ++q) {
                const float fraction = q * 0.25f;
                const float time = times[i] + (times[i+1]-times[i])*fraction;
                const float ratio = (time-times[a])/(times[b]-times[a]);
                const auto actual = KeyLerp(values[i], values[i+1], fraction);
                const auto reduced = KeyLerp(values[a], values[b], ratio);
                const double error = KeyError(actual,reduced);
                if (!std::isfinite(error) || error > worst) {
                    worst = error;
                    split = std::clamp(i + (q != 0), a+1, b-1);
                }
            }
        if (split != a) {
            keep.insert(split);
            pending.emplace_back(a,split); pending.emplace_back(split,b);
        }
    }
    return {keep.begin(), keep.end()};
}
template<class T>
std::vector<T> SelectKeys(const std::vector<T>& values, const std::vector<size_t>& keys) {
    std::vector<T> selected; selected.reserve(keys.size());
    for (size_t i : keys) selected.push_back(values[i]);
    return selected;
}
}
