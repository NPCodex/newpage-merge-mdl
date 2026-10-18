// Batch publication for VMD conversion and L4D animation swaps.
#pragma once

#include <cstdio>
#include <filesystem>
#include <string>
#include "../durable_output_transaction.h"

namespace subtool {
namespace fs = std::filesystem;

inline bool CloseFile(std::FILE* file) {
    // ferror remembers short/failed writes even if fclose itself succeeds.
    const bool written = std::ferror(file) == 0 && std::fflush(file) == 0;
    const bool closed = std::fclose(file) == 0;
    return written && closed;
}

class OutputFile {
    std::FILE* file_ = nullptr;
public:
    explicit OutputFile(const std::string& path) {
#ifdef _WIN32
        file_ = _wfopen(fs::u8path(path).c_str(), L"wb");
#else
        file_ = std::fopen(path.c_str(), "wb");
#endif
    }
    ~OutputFile() { if (file_) std::fclose(file_); }
    OutputFile(const OutputFile&) = delete;
    OutputFile& operator=(const OutputFile&) = delete;
    std::FILE* Get() const { return file_; }
    bool Close() {
        std::FILE* file = file_;
        file_ = nullptr;
        return file && CloseFile(file);
    }
};

using OutputTransaction = DurableOutputTransaction;
} // namespace subtool
