#ifndef PULSEMDL_CLOTHPROJECTION_H
#define PULSEMDL_CLOTHPROJECTION_H
#include "cloth.h"
#include "source.h"
namespace pulse::cloth {
// Call after rest-pose edits and before TagUsedBones. Returned bones must be
// retained by the compiler. Envelope misses keep their authored skinning.
bool ProjectRenderVertices(std::vector<Proxy>& proxies,
    const std::vector<source::Source*>& renderSources,const Settings& settings,
    std::vector<std::string>& generatedBones,std::string* error);
}
#endif
