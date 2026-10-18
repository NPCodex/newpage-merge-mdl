// Standalone exception/file-error tests; no fault hook is compiled into AG2.
#define AG2_TRANSACTION_TESTING
#include "../subtools/ag2proportions/transaction.cpp"

#include <cstdlib>

namespace {
std::string mode;
std::filesystem::path testRoot;

void Write(const std::filesystem::path& path, const std::string& contents) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    out << contents;
    out.close();
    if (!out)
        throw std::runtime_error("cannot write test fixture");
}
}

namespace ag2 {
void TransactionTestPoint(const char* point, size_t index) {
    if (mode == std::string(point) + ":" + std::to_string(index))
        throw std::runtime_error("injected " + mode);
    if (mode == "publish_io_failure" && std::string(point) == "backed_up" && index == 3) {
        // Make the actual final rename fail after several successful publishes.
        for (const auto& item : fs::directory_iterator(testRoot / "content/graphs"))
            if (item.is_directory() && item.path().filename().string().find(".newpage-ag2-publish-") == 0)
                fs::remove(item.path() / "replacement");
    }
    if (mode == "rollback_failure" && std::string(point) == "published" && index == 0) {
        fs::remove(testRoot / "model.vmdl");
        Write(testRoot / "model.vmdl/obstruction", "keep this evidence");
        throw std::runtime_error("injected rollback obstruction");
    }
}
}

int main(int argc, char** argv) {
    if (argc != 3)
        return 2;
    testRoot = std::filesystem::absolute(std::filesystem::u8path(argv[1]));
    mode = argv[2];
    try {
        ag2::OutputTransaction transaction;
        const auto stage = transaction.StageRoot();
        const char* names[] = {"model.vmdl", "model.vmdl.bak", "content/anims/proportions.dmx",
            "content/graphs/world.vnmgraph", "game/anims/proportions.vnmclip_c", "game/graphs/world.vnmgraph_c"};
        for (const char* name : names) {
            if (std::string(name) == "model.vmdl.bak" && std::filesystem::exists(testRoot / name))
                continue;
            Write(stage / name, std::string("new ") + name);
            transaction.Replace(stage / name, testRoot / name, std::string(name) == "model.vmdl.bak");
        }
        transaction.Remove(testRoot / "content/debug/report.kv3");
        if (mode == "staging_failure")
            std::filesystem::remove(stage / "content/graphs/world.vnmgraph");
        if (mode == "backup_race")
            Write(testRoot / "model.vmdl.bak", "first backup created concurrently");
        if (mode == "duplicate")
            transaction.Replace(stage / "model.vmdl", testRoot / "model.vmdl");
        transaction.Commit();
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
