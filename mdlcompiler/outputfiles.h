#pragma once
#include <filesystem>
#include <string>
#include <vector>

struct PendingOutput {
    std::filesystem::path path;
    const void* data;
    size_t size;
};
// Checked staging and rollback for handled failures, not crash-safe atomicity.
bool SaveOutputSet(const std::vector<PendingOutput>& outputs, std::string* error);
