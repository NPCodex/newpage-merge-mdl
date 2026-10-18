// Batch publication for VMD conversion and L4D animation swaps. All generation
// finishes before destination files are moved. Ordinary errors roll back the
// entire batch; power loss and concurrent writers require manual recovery.
#pragma once

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace subtool {
namespace fs = std::filesystem;

// Defined only by the standalone fault-injection regression harness.
#ifdef NEWPAGE_SUBTOOL_TRANSACTION_TESTING
void TransactionTestPoint(const char*, size_t);
#else
inline void TransactionTestPoint(const char*, size_t) {}
#endif

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

struct PathLess {
    bool operator()(const fs::path& a, const fs::path& b) const {
#ifdef _WIN32
        return CompareStringOrdinal(a.c_str(), static_cast<int>(a.native().size()),
                                    b.c_str(), static_cast<int>(b.native().size()), TRUE) == CSTR_LESS_THAN;
#else
        return a < b;
#endif
    }
};

class OutputTransaction {
    struct Entry {
        fs::path staged, destination, slot;
        bool original = false, backedUp = false, published = false;
    };
    fs::path root_;
    std::vector<Entry> entries_;
    std::map<fs::path, size_t, PathLess> destinations_;
    std::map<fs::path, fs::path, PathLess> directories_;
    std::vector<fs::path> created_;
    bool committed_ = false, preserve_ = false;

    static fs::path Unique(const fs::path& parent, const char* prefix) {
        std::random_device random;
        for (int i = 0; i < 32; ++i) {
            const fs::path path = parent / (std::string(prefix) + std::to_string(random()) + "-" +
                std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
            if (fs::create_directory(path)) return path;
        }
        throw std::runtime_error("cannot create output staging directory in " + parent.u8string());
    }
    static bool ExistingFile(const fs::path& path) {
        std::error_code ec;
        const auto status = fs::symlink_status(path, ec);
        if (ec && ec != std::errc::no_such_file_or_directory)
            throw fs::filesystem_error("cannot inspect output", path, ec);
        if (!fs::exists(status)) return false;
        if (!fs::is_regular_file(status))
            throw std::runtime_error("output is not a regular file: " + path.u8string());
        return true;
    }
    static fs::path Destination(const fs::path& path) {
        const fs::path absolute = fs::absolute(path).lexically_normal();
        // Resolve parent aliases without following a destination file symlink.
        return fs::weakly_canonical(absolute.parent_path()) / absolute.filename();
    }
    void MakeParents(const fs::path& parent) {
        if (fs::is_directory(parent)) return;
        if (parent.empty() || parent == parent.parent_path())
            throw std::runtime_error("cannot create output directory: " + parent.u8string());
        MakeParents(parent.parent_path());
        if (fs::create_directory(parent)) created_.push_back(parent);
    }
    void Add(const fs::path& staged, const fs::path& destination) {
        if (committed_) throw std::runtime_error("output transaction already committed");
        if (!destinations_.emplace(destination, entries_.size()).second)
            throw std::runtime_error("duplicate output: " + destination.u8string());
        entries_.push_back({staged, destination, {}});
    }
public:
    OutputTransaction() : root_(Unique(fs::temp_directory_path(), "newpage-subtool-stage-")) {}
    OutputTransaction(const OutputTransaction&) = delete;
    OutputTransaction& operator=(const OutputTransaction&) = delete;
    ~OutputTransaction() {
        if (preserve_) return;
        const auto remove = [](const fs::path& path) {
            if (path.empty()) return;
            std::error_code ec;
            fs::remove_all(path, ec);
            if (ec) std::fprintf(stderr, "warning: cannot remove staging directory %s: %s\n",
                                 path.u8string().c_str(), ec.message().c_str());
        };
        for (const auto& entry : entries_) remove(entry.slot);
        remove(root_);
        if (!committed_)
            for (auto it = created_.rbegin(); it != created_.rend(); ++it) {
                std::error_code ec;
                fs::remove(*it, ec); // Never remove a nonempty user directory.
            }
    }
    const fs::path& Root() const { return root_; }
    // Files in one final directory share a staging directory, preserving QC's
    // relative references. L4D -all may regenerate the same shared clip.
    std::string Stage(const std::string& destination) {
        const fs::path final = Destination(fs::u8path(destination));
        const auto found = destinations_.find(final);
        if (found != destinations_.end()) return entries_[found->second].staged.u8string();
        ExistingFile(final);
        const auto parent = final.parent_path();
        auto directory = directories_.find(parent);
        if (directory == directories_.end()) {
            const auto path = root_ / ("directory-" + std::to_string(directories_.size()));
            fs::create_directory(path);
            directory = directories_.emplace(parent, path).first;
        }
        const fs::path staged = directory->second / final.filename();
        Add(staged, final);
        TransactionTestPoint("stage", entries_.size() - 1);
        return staged.u8string();
    }
    void Replace(const fs::path& staged, const fs::path& destination) {
        Add(staged, Destination(destination));
    }
    void Remove(const fs::path& destination) { Add({}, Destination(destination)); }
    void Commit() {
        if (committed_) throw std::runtime_error("output transaction already committed");
        try {
            // Copy onto each destination volume before modifying any original.
            for (size_t i = 0; i < entries_.size(); ++i) {
                auto& entry = entries_[i];
                entry.original = ExistingFile(entry.destination);
                if (entry.staged.empty() && !entry.original) continue;
                if (!entry.staged.empty() && !ExistingFile(entry.staged))
                    throw std::runtime_error("staged output is missing: " + entry.staged.u8string());
                MakeParents(entry.destination.parent_path());
                entry.slot = Unique(entry.destination.parent_path(), ".newpage-subtool-publish-");
                if (!entry.staged.empty()) fs::copy_file(entry.staged, entry.slot / "replacement");
                TransactionTestPoint("prepared", i);
            }
            std::ofstream recovery(root_ / "RECOVERY.txt", std::ios::binary);
            recovery << "Manual recovery locations (not a crash-recovery journal):\n";
            for (const auto& entry : entries_)
                recovery << entry.destination.u8string() << "\n  backup: "
                         << (entry.slot / "previous").u8string() << '\n';
            recovery.close();
            if (!recovery) throw std::runtime_error("cannot write output recovery locations");
            for (size_t i = 0; i < entries_.size(); ++i) {
                auto& entry = entries_[i];
                if (entry.slot.empty()) continue;
                if (ExistingFile(entry.destination) != entry.original)
                    throw std::runtime_error("output changed during publication: " + entry.destination.u8string());
                if (entry.original) {
                    fs::rename(entry.destination, entry.slot / "previous");
                    entry.backedUp = true;
                }
                TransactionTestPoint("backed_up", i);
                if (!entry.staged.empty()) {
                    fs::rename(entry.slot / "replacement", entry.destination);
                    entry.published = true;
                }
                TransactionTestPoint("published", i);
            }
            committed_ = true;
        } catch (const std::exception& failure) {
            std::string errors;
            for (auto it = entries_.rbegin(); it != entries_.rend(); ++it) {
                try {
                    if (it->published) { fs::remove(it->destination); it->published = false; }
                    if (it->backedUp) {
                        fs::rename(it->slot / "previous", it->destination);
                        it->backedUp = false;
                    }
                } catch (const std::exception& e) {
                    errors += "\n  " + it->destination.u8string() + ": " + e.what();
                }
            }
            if (!errors.empty()) {
                preserve_ = true;
                throw std::runtime_error(std::string(failure.what()) + "\noutput rollback incomplete:" + errors +
                    "\nStaging and backups retained; see " + (root_ / "RECOVERY.txt").u8string());
            }
            throw;
        }
    }
};
} // namespace subtool
