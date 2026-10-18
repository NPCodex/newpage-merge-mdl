#define AG2_TRANSACTION_TESTING
#include "../subtools/ag2proportions/transaction.cpp"

#include "../subtools/ag2proportions/generated_assets.h"
#include "../subtools/ag2proportions/uncompiled_outputs.h"

#include <fstream>
#include <iostream>
#include <stdexcept>

namespace ag2 {
void TransactionTestPoint(const char*, size_t) {}
}

namespace {
void Write(const std::filesystem::path& path, const char* value) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    out << value;
    out.close();
    if (!out)
        throw std::runtime_error("cannot write test fixture");
}
}

int main(int argc, char** argv) {
    if (argc != 3)
        return 2;
    namespace fs = std::filesystem;
    const fs::path root = fs::absolute(fs::u8path(argv[1]));
    const bool generateOnly = std::string(argv[2]) == "generate-only";
    const fs::path model = root / "content/csgo_addons/addon/model.vmdl";
    const fs::path compiled = root / "game/csgo_addons/addon/model";
    const fs::path clip = compiled / (std::string(ag2::kClipFile) + "_c");
    const fs::path world = compiled / (std::string(ag2::kWorldGraphFile) + "_c");
    const fs::path ui = compiled / (std::string(ag2::kUiGraphFile) + "_c");
    const fs::path unrelated = compiled / "unrelated.resource_c";
    try {
        Write(model, "model");
        Write(clip, "old clip");
        Write(world, "old world graph");
        Write(ui, "old UI graph");
        Write(unrelated, "unrelated output");

        std::vector<fs::path> allowed{model, clip, world, ui, unrelated};
        ag2::OutputTransaction transaction(model, allowed);
        if (generateOnly)
            ag2::RemoveUncompiledResources(transaction, compiled,
                                           {ag2::kClipFile, ag2::kWorldGraphFile, ag2::kUiGraphFile});
        transaction.Commit();
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
