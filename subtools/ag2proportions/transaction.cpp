#include "transaction.h"

#include <algorithm>
#include <chrono>
#include <cwchar>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <utility>

namespace ag2 {
namespace fs = std::filesystem;

// Only the standalone transaction regression harness defines this hook.
// Release binaries have no environment-controlled failure injection.
#ifdef AG2_TRANSACTION_TESTING
void TransactionTestPoint(const char* point, size_t index);
#else
static void TransactionTestPoint(const char*, size_t) {}
#endif

namespace {
fs::path UniqueDirectory(const fs::path& parent, const std::string& prefix) {
    std::random_device random;
    for (int attempt = 0; attempt < 32; ++attempt) {
        const fs::path path = parent / (prefix + std::to_string(random()) + "-" +
            std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
        if (fs::create_directory(path))
            return path;
    }
    throw std::runtime_error("cannot allocate an AG2 staging directory in " + parent.u8string());
}

// symlink_status also rejects dangling symlinks, so publication never follows
// a destination link and accidentally modifies a different file.
bool ExistingFile(const fs::path& path) {
    std::error_code ec;
    const auto status = fs::symlink_status(path, ec);
    if (ec && ec != std::errc::no_such_file_or_directory)
        throw fs::filesystem_error("cannot inspect AG2 output", path, ec);
    if (!fs::exists(status))
        return false;
    if (!fs::is_regular_file(status))
        throw std::runtime_error("AG2 output is not a regular file: " + path.u8string());
    return true;
}

bool SamePath(const fs::path& a, const fs::path& b) {
#ifdef _WIN32
    return _wcsicmp(a.c_str(), b.c_str()) == 0;
#else
    return a == b;
#endif
}
} // namespace

OutputTransaction::OutputTransaction()
    : root_(UniqueDirectory(fs::temp_directory_path(), "newpage-ag2-stage-")) {}

OutputTransaction::~OutputTransaction() { Cleanup(); }

void OutputTransaction::Add(Entry entry) {
    if (committed_)
        throw std::runtime_error("AG2 transaction is already committed");
    entry.destination = fs::absolute(entry.destination).lexically_normal();
    for (const Entry& other : entries_)
        if (SamePath(other.destination, entry.destination))
            throw std::runtime_error("duplicate AG2 output: " + entry.destination.u8string());
    entries_.push_back(std::move(entry));
}

void OutputTransaction::Replace(const fs::path& staged, const fs::path& destination, bool createOnly) {
    Add({staged, destination, {}, createOnly});
}

void OutputTransaction::Remove(const fs::path& destination) { Add({{}, destination, {}}); }

void OutputTransaction::MakeParents(const fs::path& directory) {
    if (fs::is_directory(directory))
        return;
    if (directory.empty() || directory == directory.parent_path())
        throw std::runtime_error("cannot create AG2 output directory: " + directory.u8string());
    MakeParents(directory.parent_path());
    if (fs::create_directory(directory))
        createdDirectories_.push_back(directory);
}

void OutputTransaction::Cleanup() noexcept {
    if (preserve_)
        return;
    auto removeTree = [](const fs::path& path) {
        if (path.empty())
            return;
        std::error_code ec;
        fs::remove_all(path, ec);
        if (ec)
            std::cerr << "WARNING: could not remove AG2 staging directory " << path.u8string()
                      << ": " << ec.message() << '\n';
    };
    for (const Entry& entry : entries_)
        removeTree(entry.slot);
    removeTree(root_);
    // A failed job must not remove unrelated files another process put here.
    if (!committed_)
        for (auto it = createdDirectories_.rbegin(); it != createdDirectories_.rend(); ++it) {
            std::error_code ec;
            fs::remove(*it, ec); // only succeeds while empty
        }
}

void OutputTransaction::Commit() {
    if (committed_)
        throw std::runtime_error("AG2 transaction is already committed");
    try {
        // Finish every potentially large copy before moving any current output.
        // Sibling slots make the subsequent renames stay on the destination's
        // filesystem even when game/content or TEMP are on different volumes.
        for (size_t i = 0; i < entries_.size(); ++i) {
            Entry& entry = entries_[i];
            entry.hadOriginal = ExistingFile(entry.destination);
            if (entry.createOnly && entry.hadOriginal)
                throw std::runtime_error("refusing to replace the existing VMDL backup: " + entry.destination.u8string());
            if (entry.staged.empty() && !entry.hadOriginal)
                continue;
            MakeParents(entry.destination.parent_path());
            entry.slot = UniqueDirectory(entry.destination.parent_path(), ".newpage-ag2-publish-");
            if (!entry.staged.empty())
                fs::copy_file(entry.staged, entry.slot / "replacement");
            TransactionTestPoint("prepared", i);
        }
        std::ofstream recovery(root_ / "RECOVERY.txt", std::ios::binary);
        recovery << "AG2 publication recovery locations (not an automatic crash-recovery journal):\n";
        for (const Entry& entry : entries_)
            recovery << entry.destination.u8string() << "\n  backup: "
                     << (entry.slot / "previous").u8string() << '\n';
        recovery.close();
        if (!recovery)
            throw std::runtime_error("cannot write AG2 recovery locations");

        for (size_t i = 0; i < entries_.size(); ++i) {
            Entry& entry = entries_[i];
            if (entry.slot.empty())
                continue;
            if (ExistingFile(entry.destination) != entry.hadOriginal)
                throw std::runtime_error("AG2 output changed during publication: " + entry.destination.u8string());
            if (entry.hadOriginal) {
                fs::rename(entry.destination, entry.slot / "previous");
                entry.movedOriginal = true;
            }
            TransactionTestPoint("backed_up", i);
            if (!entry.staged.empty()) {
                fs::rename(entry.slot / "replacement", entry.destination);
                entry.installed = true;
            }
            TransactionTestPoint("published", i);
        }
        committed_ = true;
    } catch (const std::exception& failure) {
        std::string rollbackErrors;
        for (auto it = entries_.rbegin(); it != entries_.rend(); ++it) {
            try {
                if (it->installed) {
                    fs::remove(it->destination);
                    it->installed = false;
                }
                if (it->movedOriginal) {
                    fs::rename(it->slot / "previous", it->destination);
                    it->movedOriginal = false;
                }
            } catch (const std::exception& e) {
                rollbackErrors += "\n  " + it->destination.u8string() + ": " + e.what();
            }
        }
        if (!rollbackErrors.empty()) {
            preserve_ = true;
            throw std::runtime_error(std::string(failure.what()) + "\nAG2 rollback incomplete:" + rollbackErrors +
                "\nStaged files and backups were retained; see " + (root_ / "RECOVERY.txt").u8string());
        }
        throw;
    }
}

} // namespace ag2
