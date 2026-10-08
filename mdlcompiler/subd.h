#ifndef NEWPAGE_SUBD_H
#define NEWPAGE_SUBD_H

#include "source.h"
#include <array>

namespace pulse::subd {

struct Vertex { math::Vector3 position, normal; };
struct Patch {
    std::array<uint16_t, 4> indices{}; // strip-group vertex IDs
    // Extended VTX ABI: 60 uint16 fields followed by four vertex one-rings.
    std::vector<uint16_t> topology;
    bool regular = false;
};
struct Mesh {
    std::vector<uint16_t> vertices; // strip-group vertex -> original mesh vertex
    std::vector<Patch> patches;    // regular patches precede extraordinary ones
};

bool Build(const std::vector<Vertex>& vertices, const std::vector<source::SrcQuad>& quads,
           Mesh& out, std::string* error);

// Bake authored quads to ordinary triangles for renderers without native SubD.
// Geometry changes are committed only after all topology/attribute checks pass.
bool Bake(source::Source& source, int levels, std::string* error);

} // namespace pulse::subd
#endif
