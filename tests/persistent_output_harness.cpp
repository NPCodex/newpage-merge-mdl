// Fault checkpoints exist only in this independently compiled harness.
#define AG2_TRANSACTION_TESTING
#include "../subtools/ag2proportions/transaction.cpp"
#include <thread>

namespace {
std::string hook;
std::filesystem::path root;
void Write(const std::filesystem::path& path, const std::string& contents) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream f(path, std::ios::binary); f << contents; f.close();
    if (!f) throw std::runtime_error("test fixture write failed");
}
std::string Read(const std::filesystem::path& path) {
    std::ifstream f(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>()};
}
void Pause(const std::string& label) {
    std::cout << "PAUSED " << label << '\n' << std::flush;
    for (;;) std::this_thread::sleep_for(std::chrono::seconds(1));
}
const char* names[] = {"model.vmdl", "model.vmdl.bak", "sources/anims/proportions.dmx",
    "sources/graphs/world.vnmgraph", "game/anims/proportions.vnmclip_c",
    "game/graphs/world.vnmgraph_c", "game/graphs/ui.vnmgraph_c", "sources/debug/report.kv3"};
}

namespace ag2 {
void TransactionTestPoint(const char* point, size_t index) {
    const std::string label = std::string(point) + ":" + std::to_string(index);
    if (hook == "pause:" + label) Pause(label);
    if (hook == "wait:" + label) {
        std::cout << "PAUSED " << label << '\n' << std::flush;
        while (!std::filesystem::exists(root / ".continue"))
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    if (hook == "throw:" + label) throw std::runtime_error("injected " + label);
}
}

int Main(const std::filesystem::path& directory, const std::string& kind, const std::string& operation) {
    namespace fs = std::filesystem;
    root = fs::absolute(directory);
    try {
        if (kind == "ag2") {
            std::vector<fs::path> targets; for (const char* name : names) targets.push_back(root / name);
            ag2::OutputTransaction transaction(root / names[0], targets);
            if (operation == "recover") return 0;
            if (operation == "hold") Pause("lock");
            for (size_t i = 0; i < 7; ++i) {
                const auto dest = root / names[i];
                if (i == 1 && fs::exists(dest)) continue;
                const auto stage = transaction.StageRoot() / names[i];
                Write(stage, i == 1 && fs::exists(root / names[0]) ? Read(root / names[0]) : "new " + std::string(names[i]));
                transaction.Replace(stage, dest, i == 1);
            }
            transaction.Remove(root / names[7]);
            if (operation == "generation_failure") throw std::runtime_error("injected generation failure");
            ag2::TransactionTestPoint("generated", 0);
            transaction.Commit();
        } else {
            const auto dest = root / (kind == "reserved_journal" ? ".newpage-output-transactions" :
                kind == "reserved_lock" ? ".newpage-output-locks" : "decompiled model");
            pulse::output::Transaction transaction(dest, {{dest, true}});
            if (operation == "recover") return 0;
            if (operation == "hold") Pause("lock");
            const auto stage = transaction.StageRoot() / "new" / dest.filename();
            fs::create_directories(stage.parent_path());
            if (fs::exists(dest)) pulse::output::detail::Copy(dest, stage, true);
            else fs::create_directory(stage);
            Write(stage / "model.qc", "new model script");
            Write(stage / "meshes/body.dmx", "new mesh");
            Write(stage / "anims/idle.dmx", "new clip");
            transaction.Replace(stage, dest);
            if (operation == "generation_failure") throw std::runtime_error("injected generation failure");
            ag2::TransactionTestPoint("generated", 0);
            transaction.Commit();
        }
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
    if (argc < 4 || argc > 5) return 2;
    if (argc == 5) hook = std::filesystem::path(argv[4]).u8string();
    return Main(argv[1], std::filesystem::path(argv[2]).u8string(), std::filesystem::path(argv[3]).u8string());
}
#else
int main(int argc, char** argv) {
    if (argc < 4 || argc > 5) return 2;
    if (argc == 5) hook = argv[4]; return Main(argv[1], argv[2], argv[3]);
}
#endif
