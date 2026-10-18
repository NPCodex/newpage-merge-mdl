#include "mesh_simplify.h"

#include <cstdint>
#include <cmath>
#include <cstring>
#include <fstream>
#include <vector>

#include "meshoptimizer/meshoptimizer.h"

namespace pulse::tool {
namespace {

constexpr std::uint32_t kMagic = 0x4D535750u; // "PWSM"
constexpr std::uint32_t kVersion = 1u;
constexpr std::uint32_t kLockBorder = 1u;

// The reference's own target error, from mdlcompiler's SimplifyFaces: the face
// budget is the constraint and the error is left free.
constexpr float kTargetError = 1.0f;

struct Reader {
    const std::uint8_t* at;
    const std::uint8_t* end;

    bool U32(std::uint32_t& out) {
        if (end - at < 4)
            return false;
        std::memcpy(&out, at, 4);
        at += 4;
        return true;
    }

    // Hands back a view into the buffer rather than a copy - the request is
    // megabytes of positions and indices for a character.
    const void* Block(std::size_t bytes) {
        if (static_cast<std::size_t>(end - at) < bytes)
            return nullptr;
        const void* p = at;
        at += bytes;
        return p;
    }
};

void Put(std::vector<std::uint8_t>& out, const void* data, std::size_t bytes) {
    const auto* p = static_cast<const std::uint8_t*>(data);
    out.insert(out.end(), p, p + bytes);
}

void PutU32(std::vector<std::uint8_t>& out, std::uint32_t value) {
    Put(out, &value, 4);
}

} // namespace

bool RunSimplify(const std::string& requestPath, const std::string& responsePath,
                 std::string* err) {
    auto fail = [&](const char* message) {
        if (err)
            *err = message;
        return false;
    };

    std::ifstream in(requestPath, std::ios::binary | std::ios::ate);
    if (!in)
        return fail("cannot open the request file");
    const std::streamoff size = in.tellg();
    if (size <= 0)
        return fail("the request file is empty");
    std::vector<std::uint8_t> request(static_cast<std::size_t>(size));
    in.seekg(0);
    if (!in.read(reinterpret_cast<char*>(request.data()), size))
        return fail("cannot read the request file");
    in.close();

    Reader r{request.data(), request.data() + request.size()};
    std::uint32_t magic = 0, version = 0, vertexCount = 0, runCount = 0;
    if (!r.U32(magic) || magic != kMagic)
        return fail("the request is not a simplify request");
    if (!r.U32(version) || version != kVersion)
        return fail("the request is a version this build does not read");
    if (!r.U32(vertexCount))
        return fail("the request ends before its vertex count");

    const auto* positions = static_cast<const float*>(
        r.Block(static_cast<std::size_t>(vertexCount) * 3u * sizeof(float)));
    if (vertexCount > 0 && !positions)
        return fail("the request ends inside its positions");
    for (std::size_t i = 0; i < static_cast<std::size_t>(vertexCount) * 3; ++i)
        if (!std::isfinite(positions[i]))
            return fail("the request contains a non-finite vertex position");
    if (!r.U32(runCount))
        return fail("the request ends before its run count");

    // Validate the whole request before entering meshoptimizer. Its API assumes
    // triangle lists and valid indices, and malformed data can otherwise crash
    // a release build instead of producing the protocol's ordinary error.
    struct Run {
        std::uint32_t indexCount, target, flags;
        const unsigned int* indices;
    };
    std::vector<Run> runs;
    for (std::uint32_t run = 0; run < runCount; ++run) {
        std::uint32_t indexCount = 0, target = 0, flags = 0;
        if (!r.U32(indexCount) || !r.U32(target) || !r.U32(flags))
            return fail("the request ends inside a run header");
        if (indexCount % 3 != 0)
            return fail("a run's index count is not a multiple of three");
        if (target > indexCount)
            return fail("a run's target exceeds its index count");
        if (flags & ~kLockBorder)
            return fail("a run contains unsupported simplify flags");
        const auto* indices = static_cast<const unsigned int*>(
            r.Block(static_cast<std::size_t>(indexCount) * sizeof(unsigned int)));
        if (indexCount > 0 && !indices)
            return fail("the request ends inside a run's indices");
        for (std::uint32_t i = 0; i < indexCount; ++i)
            if (indices[i] >= vertexCount)
                return fail("a run contains an index outside the vertex pool");
        runs.push_back({indexCount, target, flags, indices});
    }
    if (r.at != r.end)
        return fail("the request contains trailing data");

    std::vector<std::uint8_t> response;
    PutU32(response, kMagic);
    PutU32(response, runCount);

    std::vector<unsigned int> simplified;
    for (const Run& run : runs) {
        const auto [indexCount, target, flags, indices] = run;

        float error = 0.0f;
        std::size_t kept = 0;
        if (indexCount >= 3 && vertexCount > 0) {
            simplified.resize(indexCount);
            kept = meshopt_simplify(simplified.data(), indices, indexCount, positions,
                                    vertexCount, sizeof(float) * 3, target, kTargetError,
                                    (flags & kLockBorder) ? meshopt_SimplifyLockBorder : 0u,
                                    &error);
        }

        PutU32(response, static_cast<std::uint32_t>(kept));
        Put(response, &error, sizeof(float));
        if (kept > 0)
            Put(response, simplified.data(), kept * sizeof(unsigned int));
    }

    std::ofstream out(responsePath, std::ios::binary | std::ios::trunc);
    if (!out)
        return fail("cannot open the response file");
    out.write(reinterpret_cast<const char*>(response.data()),
              static_cast<std::streamsize>(response.size()));
    if (!out)
        return fail("cannot write the response file");
    return true;
}

} // namespace pulse::tool
