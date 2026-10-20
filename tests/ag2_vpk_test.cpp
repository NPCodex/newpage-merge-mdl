#include "../subtools/ag2proportions/vpk.h"

#include <chrono>
#include <iostream>

namespace fs = std::filesystem;
using Bytes = std::vector<uint8_t>;

void Put(Bytes& out, uint32_t value, int width = 4) {
    for (int i = 0; i < width; ++i) out.push_back(static_cast<uint8_t>(value >> (i * 8)));
}
void Text(Bytes& out, const std::string& text) {
    out.insert(out.end(), text.begin(), text.end()); out.push_back(0);
}
void Write(const fs::path& path, const Bytes& data) {
    std::ofstream out(path, std::ios::binary);
    out.write(reinterpret_cast<const char*>(data.data()), data.size());
    out.close();
    if (!out) throw std::runtime_error("cannot write test fixture");
}

int main() {
    const auto id = std::chrono::high_resolution_clock::now().time_since_epoch().count();
    const auto root = fs::temp_directory_path() / ("newpage-vpk-crc-" + std::to_string(id));
    fs::create_directories(root);
    int checked = 0;
    try {
        // IEEE CRC32's standard check vector, independently specified by the
        // format. Test preload + embedded/external bytes together, not separately.
        const Bytes payload{'1','2','3','4','5','6','7','8','9'};
        for (int version : {1, 2}) for (bool external : {false, true}) {
            for (int preload : {0, 3, 9}) for (int corrupt : {0, 1, 2}) {
                Bytes tree;
                Text(tree, "bin"); Text(tree, "fixtures"); Text(tree, "sample");
                Put(tree, 0xcbf43926u ^ (corrupt == 1 ? 1u : 0u));
                Put(tree, preload, 2); Put(tree, external ? 0 : 0x7fff, 2);
                Put(tree, 0); Put(tree, static_cast<uint32_t>(payload.size() - preload)); Put(tree, 0xffff, 2);
                Bytes current = payload;
                if (corrupt == 2) current[0] ^= 1;
                tree.insert(tree.end(), current.begin(), current.begin() + preload);
                tree.insert(tree.end(), 3, 0); // stem/folder/extension terminators
                Bytes directory;
                Put(directory, 0x55aa1234); Put(directory, version); Put(directory, static_cast<uint32_t>(tree.size()));
                if (version == 2) {
                    Put(directory, external ? 0 : static_cast<uint32_t>(current.size() - preload));
                    Put(directory, 0); Put(directory, 0); Put(directory, 0);
                }
                directory.insert(directory.end(), tree.begin(), tree.end());
                Bytes remainder(current.begin() + preload, current.end());
                if (external) Write(root / "pak01_000.vpk", remainder);
                else directory.insert(directory.end(), remainder.begin(), remainder.end());
                Write(root / "pak01_dir.vpk", directory);
                bool rejected = false;
                try {
                    const auto result = ag2::Vpk(root / "pak01_dir.vpk").Read("fixtures/sample.bin");
                    if (corrupt == 0 && result != payload) throw std::runtime_error("valid bytes changed");
                } catch (const std::exception& error) {
                    const std::string message = error.what();
                    if (message.find("CRC32 mismatch") == std::string::npos ||
                        message.find("fixtures/sample.bin") == std::string::npos ||
                        message.find("pak01_dir.vpk") == std::string::npos) throw;
                    rejected = true;
                }
                if (rejected != (corrupt != 0)) throw std::runtime_error("incorrect CRC acceptance");
                ++checked;
            }
        }
        fs::remove_all(root);
        std::cout << "PASS " << checked << " VPK CRC cases (v1/v2, embedded/external, preload, bad checksum/data)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL after " << checked << " cases: " << error.what() << " (fixture " << root << ")\n";
        return 1;
    }
}
