#include "../subtools/meshtool/response_writer.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
static std::string failAt;

bool pulse::tool::detail::ResponseWriteTestFail(const char* stage) {
    return failAt == stage;
}

static void Require(bool value, const std::string& message) {
    if (!value)
        throw std::runtime_error(message);
}

static void Write(const fs::path& path, const std::string& contents) {
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file.write(contents.data(), static_cast<std::streamsize>(contents.size()));
    file.close();
    Require(bool(file), "could not prepare response fixture");
}

static std::string Read(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}

static std::size_t TemporaryCount(const fs::path& directory) {
    std::size_t count = 0;
    for (const auto& entry : fs::directory_iterator(directory))
        if (entry.path().filename().u8string().find(".meshtool-") != std::string::npos)
            ++count;
    return count;
}

int main(int argc, char** argv) {
    try {
        Require(argc == 2, "usage: meshtool_response_test <test directory>");
        const fs::path root = fs::u8path(argv[1]);
        Require(!fs::exists(root), "test directory must not already exist");
        fs::create_directories(root);
        const fs::path response = root / fs::u8path(u8"响应.bin");
        const std::string old = "previous response must survive";
        const std::string replacement = "complete replacement response";
        std::size_t checks = 0;

        for (const std::string stage : {"write", "flush", "close", "replace"}) {
            Write(response, old);
            failAt = stage;
            std::string error;
            const bool written = pulse::tool::detail::WriteResponseAtomically(
                response.u8string(), replacement.data(), replacement.size(), &error);
            failAt.clear();
            Require(!written && !error.empty(), "injected " + stage + " failure was accepted");
            Require(Read(response) == old, "injected " + stage + " failure changed the old response");
            Require(TemporaryCount(root) == 0, "injected " + stage + " failure leaked its temporary file");
            ++checks;
        }

        Write(response, old);
        std::string error;
        Require(pulse::tool::detail::WriteResponseAtomically(
                    response.u8string(), replacement.data(), replacement.size(), &error),
                "successful response publication failed: " + error);
        Require(Read(response) == replacement, "successful response did not replace the old file");
        Require(TemporaryCount(root) == 0, "successful publication left its temporary file");
        ++checks;

        const fs::path directoryTarget = root / "directory-target";
        fs::create_directory(directoryTarget);
        Write(directoryTarget / "sentinel", old);
        error.clear();
        Require(!pulse::tool::detail::WriteResponseAtomically(
                    directoryTarget.u8string(), replacement.data(), replacement.size(), &error),
                "replacement over an existing directory unexpectedly succeeded");
        Require(Read(directoryTarget / "sentinel") == old,
                "failed operating-system replacement changed the existing directory");
        Require(TemporaryCount(root) == 0, "operating-system replacement failure leaked its temporary file");
        ++checks;

        std::cout << checks << " meshtool response publication checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        failAt.clear();
        std::cerr << error.what() << '\n';
        return 1;
    }
}
