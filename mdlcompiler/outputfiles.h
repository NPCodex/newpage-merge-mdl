#pragma once
#include <filesystem>
#include <string>
#include <vector>

struct PendingOutput {
    std::filesystem::path path;
    const void* data;
    size_t size;
    // A deletion participates in the same backup/recovery protocol as writes.
    bool remove = false;
};
// Recover the same model before reading its previous sequence order. Journals
// are confined to outputRoot; altered files are retained for manual review.
bool RecoverOutputFiles(const std::filesystem::path& model,
                        const std::filesystem::path& outputRoot,std::string* error);
// Durable intent journal, per-output process locks, and idempotent recovery.
// This does not promise atomic visibility to readers or hardware-fault immunity.
bool SaveOutputSet(const std::vector<PendingOutput>& outputs,
                   const std::filesystem::path& outputRoot,std::string* error);
