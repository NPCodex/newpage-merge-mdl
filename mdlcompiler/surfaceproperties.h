#pragma once

#include <string>

namespace pulse::compile { struct CompiledModel; }

namespace pulse::surfaceproperties {

// Resolve surface names and physical masses before any output files are written.
// Automatic mass uses the mounted game's surface-properties manifest.
bool ResolvePhysicsMass(compile::CompiledModel& model, bool automatic, std::string* err);

} // namespace pulse::surfaceproperties
