// Shared exception/crash recovery for a known set of files or one directory.
// Readers may observe publication in progress; flushes cannot guarantee survival
// of every hardware/power failure. Recovery refuses changed destinations/backups.
#pragma once

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <io.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace pulse::output {
namespace fs = std::filesystem;

#ifdef PULSE_OUTPUT_TESTING
void TestPoint(const char* point, size_t index);
#else
inline void TestPoint(const char*, size_t) {}
#endif

struct Target { fs::path path; bool directory = false; };

namespace detail {
constexpr uint64_t kBasis = 14695981039346656037ULL;
struct Digest {
    uint64_t size = 0, hash = kBasis;
    bool operator==(const Digest& other) const { return size == other.size && hash == other.hash; }
};
inline void Hash(Digest& d, const void* data, size_t size) {
    const auto* p = static_cast<const unsigned char*>(data);
    d.size += size;
    while (size--) { d.hash ^= *p++; d.hash *= 1099511628211ULL; }
}
inline void Hash(Digest& d, const std::string& s) { Hash(d, s.data(), s.size()); }
inline std::string Hex(uint64_t value) { std::ostringstream s; s << std::hex << value; return s.str(); }
inline std::string Key(const fs::path& path) {
#ifdef _WIN32
    const auto text = path.generic_wstring();
    const int count = LCMapStringEx(LOCALE_NAME_INVARIANT, LCMAP_UPPERCASE, text.data(),
                                  static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr, 0);
    if (!count) throw std::runtime_error("cannot normalize output identity");
    std::wstring folded(count, L'\0');
    if (!LCMapStringEx(LOCALE_NAME_INVARIANT, LCMAP_UPPERCASE, text.data(), static_cast<int>(text.size()),
                       folded.data(), count, nullptr, nullptr, 0))
        throw std::runtime_error("cannot normalize output identity");
    return fs::path(folded).generic_u8string();
#else
    return path.generic_u8string();
#endif
}
inline fs::file_status Status(const fs::path& path) {
    std::error_code ec;
    auto s = fs::symlink_status(path, ec);
    if (ec && ec != std::errc::no_such_file_or_directory)
        throw fs::filesystem_error("cannot inspect transaction path", path, ec);
    if (fs::is_symlink(s)) throw std::runtime_error("transaction path is a link: " + path.u8string());
#ifdef _WIN32
    const DWORD attrs = GetFileAttributesW(path.c_str());
    if (attrs != INVALID_FILE_ATTRIBUTES && (attrs & FILE_ATTRIBUTE_REPARSE_POINT))
        throw std::runtime_error("transaction path is a reparse point: " + path.u8string());
#endif
    return s;
}
inline bool Exists(const fs::path& path) { return fs::exists(Status(path)); }

// Canonicalize the existing parent, including Windows junctions and 8.3 names.
// The final component remains a destination, not a link to follow.
inline fs::path Destination(fs::path path) {
    path = fs::absolute(path).lexically_normal();
    auto at = path.parent_path(); std::vector<fs::path> tail;
    while (!fs::exists(at)) {
        if (at.empty() || at == at.parent_path()) throw std::runtime_error("output has no existing ancestor");
        tail.push_back(at.filename()); at = at.parent_path();
    }
    at = fs::canonical(at);
#ifdef _WIN32
    HANDLE h = CreateFileW(at.c_str(), 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                          nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    if (h == INVALID_HANDLE_VALUE) throw std::runtime_error("cannot resolve output parent: " + at.u8string());
    const DWORD length = GetFinalPathNameByHandleW(h, nullptr, 0, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
    std::wstring finalPath(length, L'\0');
    const DWORD got = length ? GetFinalPathNameByHandleW(h, finalPath.data(), length, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS) : 0;
    CloseHandle(h);
    if (!got || got >= length) throw std::runtime_error("cannot resolve output parent: " + at.u8string());
    finalPath.resize(got);
    if (finalPath.rfind(L"\\\\?\\UNC\\", 0) == 0) finalPath = L"\\\\" + finalPath.substr(8);
    else if (finalPath.rfind(L"\\\\?\\", 0) == 0) finalPath.erase(0, 4);
    at = finalPath;
#endif
    for (auto i = tail.rbegin(); i != tail.rend(); ++i) at /= *i;
    at /= path.filename();
    // Resolve an existing final component's long spelling, without accepting links.
    if (Exists(at)) at = fs::canonical(at);
    return at;
}
inline void CheckParents(const fs::path& path) {
    auto current = path.root_path();
    for (const auto& part : path.relative_path()) { current /= part; Status(current); }
}
inline void SyncDirectory(const fs::path& path) {
#ifndef _WIN32
    const int fd = open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) throw std::runtime_error("cannot open directory for sync: " + path.u8string());
    const int result = fsync(fd); close(fd);
    if (result) throw std::runtime_error("cannot sync directory: " + path.u8string());
#else
    (void)path; // Windows files are flushed; renames use WRITE_THROUGH below.
#endif
}
inline FILE* Open(const fs::path& path, bool write) {
#ifdef _WIN32
    return _wfopen(path.c_str(), write ? L"wbx" : L"rb");
#else
    return std::fopen(path.c_str(), write ? "wbx" : "rb");
#endif
}
inline void Finish(FILE* f, const fs::path& path) {
    bool ok = std::fflush(f) == 0;
#ifdef _WIN32
    if (ok) ok = FlushFileBuffers(reinterpret_cast<HANDLE>(_get_osfhandle(_fileno(f)))) != 0;
#else
    if (ok) ok = fsync(fileno(f)) == 0;
#endif
    if (std::fclose(f)) ok = false;
    if (!ok) throw std::runtime_error("cannot flush staged output: " + path.u8string());
    SyncDirectory(path.parent_path());
}
inline void Write(const fs::path& path, const std::string& text) {
    FILE* f = Open(path, true);
    if (!f) throw std::runtime_error("cannot write transaction metadata: " + path.u8string());
    if (std::fwrite(text.data(), 1, text.size(), f) != text.size()) {
        std::fclose(f); throw std::runtime_error("short transaction metadata write: " + path.u8string());
    }
    Finish(f, path);
}
inline void Rename(const fs::path& from, const fs::path& to, bool replace = false) {
#ifdef _WIN32
    if (!MoveFileExW(from.c_str(), to.c_str(), MOVEFILE_WRITE_THROUGH | (replace ? MOVEFILE_REPLACE_EXISTING : 0)))
        throw std::runtime_error("cannot rename " + from.u8string() + " to " + to.u8string() +
                                 " (Windows error " + std::to_string(GetLastError()) + ")");
#else
    if (!replace && Exists(to)) throw std::runtime_error("rename destination exists: " + to.u8string());
    fs::rename(from, to); SyncDirectory(from.parent_path());
    if (from.parent_path() != to.parent_path()) SyncDirectory(to.parent_path());
#endif
}
inline std::vector<fs::path> Tree(const fs::path& directory) {
    std::vector<fs::path> paths;
    if (!fs::is_directory(Status(directory))) throw std::runtime_error("output is not a directory: " + directory.u8string());
    for (const auto& item : fs::recursive_directory_iterator(directory)) {
        const auto s = Status(item.path());
        if (!fs::is_regular_file(s) && !fs::is_directory(s))
            throw std::runtime_error("output contains a special file: " + item.path().u8string());
        paths.push_back(item.path());
    }
    std::sort(paths.begin(), paths.end()); return paths;
}
inline void FileHash(Digest& digest, const fs::path& path) {
    if (!fs::is_regular_file(Status(path))) throw std::runtime_error("output is not a regular file: " + path.u8string());
    std::ifstream f(path, std::ios::binary); if (!f) throw std::runtime_error("cannot read output: " + path.u8string());
    char buffer[65536];
    while (f) { f.read(buffer, sizeof(buffer)); Hash(digest, buffer, static_cast<size_t>(f.gcount())); }
    if (!f.eof()) throw std::runtime_error("cannot finish reading output: " + path.u8string());
}
inline Digest Fingerprint(const fs::path& path, bool directory) {
    CheckParents(path); Digest result;
    if (!directory) { FileHash(result, path); return result; }
    Hash(result, "directory\n");
    for (const auto& item : Tree(path)) {
        const bool dir = fs::is_directory(Status(item));
        const auto name = item.lexically_relative(path).generic_u8string();
        Hash(result, std::string(dir ? "D " : "F ") + std::to_string(name.size()) + ":" + name + "\n");
        if (!dir) {
            const auto size = fs::file_size(item); Hash(result, std::to_string(size) + ":");
            FileHash(result, item);
        }
    }
    return result;
}
inline void Match(const fs::path& path, bool directory, const Digest& expected) {
    if (!Exists(path) || !(Fingerprint(path, directory) == expected))
        throw std::runtime_error("output changed since transaction; recovery retained for review: " + path.u8string());
}
inline void CopyFile(const fs::path& from, const fs::path& to) {
    FILE* in = Open(from, false); if (!in) throw std::runtime_error("cannot read staged output: " + from.u8string());
    FILE* out = Open(to, true);
    if (!out) { std::fclose(in); throw std::runtime_error("cannot prepare output: " + to.u8string()); }
    char buffer[65536]; bool ok = true;
    for (;;) {
        const auto n = std::fread(buffer, 1, sizeof(buffer), in);
        if (n && std::fwrite(buffer, 1, n, out) != n) { ok = false; break; }
        if (n < sizeof(buffer)) { ok = !std::ferror(in); break; }
    }
    if (std::fclose(in)) ok = false;
    if (!ok) { std::fclose(out); throw std::runtime_error("cannot finish staging output: " + to.u8string()); }
    Finish(out, to);
}
inline void Copy(const fs::path& from, const fs::path& to, bool directory) {
    if (!directory) { CopyFile(from, to); return; }
    const auto entries = Tree(from); fs::create_directory(to);
    for (const auto& item : entries) {
        const auto dest = to / item.lexically_relative(from);
        if (fs::is_directory(Status(item))) fs::create_directory(dest);
        else CopyFile(item, dest);
    }
    for (auto it = entries.rbegin(); it != entries.rend(); ++it)
        if (fs::is_directory(Status(*it))) SyncDirectory(to / it->lexically_relative(from));
    SyncDirectory(to); SyncDirectory(to.parent_path());
}
inline void Remove(const fs::path& path, bool disposal = false) {
    const auto s = Status(path); if (!fs::exists(s)) return;
    if (fs::is_directory(s)) {
        auto entries = Tree(path); // validate all children before deleting any
        for (auto it = entries.rbegin(); it != entries.rend(); ++it) {
            fs::remove(*it);
            if (disposal) TestPoint("discard_child", 0);
        }
    } else if (!fs::is_regular_file(s)) throw std::runtime_error("refusing to remove special transaction path");
    fs::remove(path); SyncDirectory(path.parent_path());
    if (disposal) TestPoint("discard_root", 0);
}
struct Lock {
#ifdef _WIN32
    HANDLE handle = INVALID_HANDLE_VALUE;
    explicit Lock(const fs::path& path) {
        handle = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_HIDDEN, nullptr);
        if (handle == INVALID_HANDLE_VALUE) throw std::runtime_error("output is locked by another process: " + path.u8string());
    }
    ~Lock() { if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle); }
#else
    int fd = -1;
    explicit Lock(const fs::path& path) {
        fd = open(path.c_str(), O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (fd < 0) throw std::runtime_error("cannot open output lock: " + path.u8string());
        if (flock(fd, LOCK_EX | LOCK_NB)) { close(fd); fd = -1; throw std::runtime_error("output is locked by another process: " + path.u8string()); }
    }
    ~Lock() { if (fd >= 0) { flock(fd, LOCK_UN); close(fd); } }
#endif
};
} // namespace detail

class Transaction {
public:
    Transaction(const fs::path& primary, const std::vector<Target>& allowed) {
        using namespace detail;
        const auto target = Destination(primary);
        const auto leaf = Key(target.filename());
        if (target == target.root_path() || leaf.empty() ||
            leaf == Key(fs::path(".newpage-output-locks")) ||
            leaf == Key(fs::path(".newpage-output-transactions")))
            throw std::runtime_error("output overlaps reserved transaction storage: " + target.u8string());
        fs::create_directories(target.parent_path());
        CheckParents(target.parent_path());
        const auto key = Key(target); Digest identity; Hash(identity, key);
        const auto locks = target.parent_path() / ".newpage-output-locks";
        const auto journals = target.parent_path() / ".newpage-output-transactions";
        CheckParents(locks); CheckParents(journals);
        fs::create_directories(locks); fs::create_directories(journals);
        const auto lockPath = locks / (Hex(identity.hash) + ".lock"); Status(lockPath);
        lock_ = std::make_unique<Lock>(lockPath);
        location_ = journals / Hex(identity.hash); CheckParents(location_);
        fs::create_directory(location_);
        work_ = location_ / "work";
        for (const auto& item : allowed) {
            Target canonical{Destination(item.path), item.directory};
            CheckParents(canonical.path);
            const auto name = Key(canonical.path);
            if (!allowed_.emplace(name, canonical).second) throw std::runtime_error("duplicate allowed output");
        }
        Recover();
        // Snapshot before generation/copying previous output, not just before
        // publication: edits made by a non-cooperating writer are detected.
        for (const auto& [name, item] : allowed_) {
            Snapshot old; old.present = Exists(item.path);
            if (old.present) old.digest = Fingerprint(item.path, item.directory);
            old_[name] = old;
        }
        nonce_ = std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        WriteJournal(); // durable zero-entry intent owns only the work directory
        active_ = true;
        fs::create_directory(work_); SyncDirectory(location_);
        TestPoint("begin", 0);
    }
    ~Transaction() {
        if (!active_) return;
        try { Recover(); }
        catch (const std::exception& e) { std::cerr << "WARNING: transaction recovery retained: " << e.what() << '\n'; }
    }
    Transaction(const Transaction&) = delete;
    Transaction& operator=(const Transaction&) = delete;
    const fs::path& StageRoot() const { return work_; }
    const fs::path& JournalDirectory() const { return location_; }
    void Replace(const fs::path& staged, const fs::path& destination, bool createOnly = false) {
        Add(staged, destination, false, createOnly);
    }
    void Remove(const fs::path& destination) { Add({}, destination, true, false); }
    void Commit() {
        using namespace detail;
        bool committed = false;
        try {
            for (auto& e : entries_) {
                CheckOriginal(e);
                if (!e.remove) e.fresh = Fingerprint(e.source, e.directory);
            }
            WriteJournal(); TestPoint("journal", 0);
            for (size_t i = 0; i < entries_.size(); ++i) {
                auto& e = entries_[i]; CheckParents(e.path.parent_path()); fs::create_directories(e.path.parent_path());
                if (!e.remove) { Copy(e.source, e.stage, e.directory); Match(e.stage, e.directory, e.fresh); }
                TestPoint("prepared", i);
            }
            Marker("ready"); TestPoint("ready", 0);
            for (size_t i = 0; i < entries_.size(); ++i) {
                auto& e = entries_[i]; CheckOriginal(e);
                if (e.old.present) Rename(e.path, e.backup);
                TestPoint("backed_up", i);
                if (!e.remove) Rename(e.stage, e.path);
                TestPoint("published", i);
            }
            Marker("commit"); committed = true; TestPoint("committed", 0);
            Recover(); active_ = false;
        } catch (const std::exception& e) {
            const std::string message = e.what();
            try { Recover(); active_ = false; }
            catch (const std::exception& recovery) {
                active_ = false;
                throw std::runtime_error(message + "\nRecovery retained at " + location_.u8string() + ": " + recovery.what());
            }
            if (committed) {
                std::cerr << "WARNING: output committed; cleanup recovery completed: " << message << '\n'; return;
            }
            throw;
        }
    }
private:
    struct Snapshot { bool present = false; detail::Digest digest; };
    struct Entry {
        fs::path source, path, stage, backup, stageTrash, backupTrash;
        bool directory = false, remove = false;
        Snapshot old;
        detail::Digest fresh;
    };
    std::unique_ptr<detail::Lock> lock_;
    fs::path location_, work_;
    std::map<std::string, Target> allowed_;
    std::map<std::string, Snapshot> old_;
    std::vector<Entry> entries_;
    std::string nonce_;
    bool active_ = false;
    void Derive(Entry& e, size_t index) const {
        const std::string suffix = ".newpage-txn-" + nonce_ + "-" + std::to_string(index);
        e.stage = e.path; e.stage += suffix + ".stage";
        e.backup = e.path; e.backup += suffix + ".backup";
        e.stageTrash = e.path; e.stageTrash += suffix + ".stage-discard";
        e.backupTrash = e.path; e.backupTrash += suffix + ".backup-discard";
        detail::CheckParents(e.stage); detail::CheckParents(e.backup);
        detail::CheckParents(e.stageTrash); detail::CheckParents(e.backupTrash);
    }
    void Add(const fs::path& source, const fs::path& destination, bool remove, bool createOnly) {
        if (!active_) throw std::runtime_error("output transaction is not active");
        const auto key = detail::Key(detail::Destination(destination));
        const auto at = allowed_.find(key);
        if (at == allowed_.end()) throw std::runtime_error("unregistered transaction destination");
        for (const auto& other : entries_)
            if (detail::Key(other.path) == key) throw std::runtime_error("duplicate transaction output");
        Entry e; e.source = source; e.path = at->second.path; e.directory = at->second.directory;
        e.remove = remove; e.old = old_.at(key);
        if (createOnly && (e.old.present || detail::Exists(e.path))) throw std::runtime_error("refusing to replace existing first backup");
        Derive(e, entries_.size()); entries_.push_back(std::move(e));
    }
    void CheckOriginal(const Entry& e) {
        if (e.old.present) detail::Match(e.path, e.directory, e.old.digest);
        else if (detail::Exists(e.path)) throw std::runtime_error("output appeared during transaction: " + e.path.u8string());
    }
    void WriteJournal() {
        std::ostringstream text;
        text << "NEWPAGE_OUTPUT_1 " << nonce_ << ' ' << entries_.size() << '\n';
        for (const auto& e : entries_)
            text << std::quoted(e.path.generic_u8string()) << ' ' << e.directory << ' ' << e.remove << ' '
                 << e.old.present << ' ' << e.old.digest.size << ' ' << e.old.digest.hash << ' '
                 << e.fresh.size << ' ' << e.fresh.hash << '\n';
        const auto pending = location_ / "intent.tmp";
        detail::Remove(pending); detail::Write(pending, text.str());
        detail::Rename(pending, location_ / "intent", true);
    }
    void Marker(const char* name) {
        const auto pending = location_ / (std::string(name) + ".tmp");
        detail::Remove(pending); detail::Write(pending, nonce_ + "\n");
        detail::Rename(pending, location_ / name, true);
    }
    bool HasMarker(const char* name) const {
        const auto path = location_ / name;
        if (!detail::Exists(path)) return false;
        if (fs::file_size(path) > 128) throw std::runtime_error("oversized transaction marker");
        std::ifstream f(path, std::ios::binary); std::string value, extra;
        if (!(f >> value) || value != nonce_ || (f >> extra)) throw std::runtime_error("invalid transaction marker: " + path.u8string());
        return true;
    }
    void Recover() {
        using namespace detail;
        const auto intent = location_ / "intent";
        if (!Exists(intent)) {
            // Metadata replacement can leave an inert temporary/commit marker.
            // No destination is changed before a complete intent is durable.
            for (const char* name : {"intent.tmp", "ready", "ready.tmp", "commit", "commit.tmp"}) detail::Remove(location_ / name);
            if (Exists(work_)) throw std::runtime_error("orphaned transaction workspace retained: " + work_.u8string());
            return;
        }
        if (fs::file_size(intent) > 4 * 1024 * 1024) throw std::runtime_error("oversized output recovery journal");
        std::ifstream f(intent, std::ios::binary); std::string magic, nonce; size_t count = 0;
        if (!(f >> magic >> nonce >> count) || magic != "NEWPAGE_OUTPUT_1" || nonce.empty() ||
            nonce.find_first_not_of("0123456789") != std::string::npos || count > allowed_.size())
            throw std::runtime_error("invalid output recovery journal: " + intent.u8string());
        const auto savedNonce = nonce_; nonce_ = nonce;
        std::vector<Entry> saved;
        std::set<std::string> seen;
        for (size_t i = 0; i < count; ++i) {
            Entry e; std::string path; int dir, remove, had;
            if (!(f >> std::quoted(path) >> dir >> remove >> had >> e.old.digest.size >> e.old.digest.hash >> e.fresh.size >> e.fresh.hash) ||
                (dir != 0 && dir != 1) || (remove != 0 && remove != 1) || (had != 0 && had != 1))
                throw std::runtime_error("truncated output recovery journal");
            e.path = fs::u8path(path); const auto key = Key(e.path); const auto allowed = allowed_.find(key);
            if (allowed == allowed_.end() || allowed->second.directory != bool(dir) || !seen.insert(key).second ||
                Key(Destination(e.path)) != key) throw std::runtime_error("unsafe output recovery destination");
            e.path = allowed->second.path; e.directory = dir != 0; e.remove = remove != 0; e.old.present = had != 0;
            Derive(e, i); saved.push_back(std::move(e));
        }
        f >> std::ws; if (!f.eof()) throw std::runtime_error("unexpected output recovery data");
        f.close();
        const bool ready = HasMarker("ready"), committed = HasMarker("commit");
        if (committed && !ready) throw std::runtime_error("transaction committed without prepared outputs");
        // Validate the complete set before changing any file or directory.
        for (const auto& e : saved) {
            const bool backup = Exists(e.backup), target = Exists(e.path);
            if (backup) { if (!e.old.present) throw std::runtime_error("unexpected output backup"); Match(e.backup, e.directory, e.old.digest); }
            if (committed) {
                if (e.remove) { if (target) throw std::runtime_error("deleted output changed since transaction"); }
                else Match(e.path, e.directory, e.fresh);
            } else if (backup) {
                if (target) { if (e.remove) throw std::runtime_error("deleted output changed since transaction"); Match(e.path, e.directory, e.fresh); }
            } else if (e.old.present) Match(e.path, e.directory, e.old.digest);
            else if (target) { if (e.remove) throw std::runtime_error("deleted output changed since transaction"); Match(e.path, e.directory, e.fresh); }
            if (Exists(e.stage) && ready) Match(e.stage, e.directory, e.fresh);
        }
        if (!committed) for (size_t n = saved.size(); n-- > 0;) {
            const auto& e = saved[n];
            if (Exists(e.backup)) {
                if (Exists(e.path)) {
                    Match(e.path, e.directory, e.fresh); Rename(e.path, e.stageTrash);
                    TestPoint("discarded", n);
                }
                Match(e.backup, e.directory, e.old.digest); Rename(e.backup, e.path);
            } else if (!e.old.present && Exists(e.path)) {
                Match(e.path, e.directory, e.fresh); Rename(e.path, e.stageTrash);
                TestPoint("discarded", n);
            }
            TestPoint("recovered", n);
        }
        for (size_t i = 0; i < saved.size(); ++i) {
            const auto& e = saved[i];
            // Atomically detach disposable data before recursively deleting it.
            // A second hard kill can leave partial discard trees, but never a
            // partial user target or a partial backup required for rollback.
            if (Exists(e.stage)) Rename(e.stage, e.stageTrash);
            if (Exists(e.backup)) {
                Match(e.backup, e.directory, e.old.digest); Rename(e.backup, e.backupTrash);
            }
            TestPoint("cleanup", i);
            detail::Remove(e.stageTrash, true); detail::Remove(e.backupTrash, true);
        }
        detail::Remove(work_); detail::Remove(location_ / "intent.tmp"); detail::Remove(location_ / "ready.tmp"); detail::Remove(location_ / "commit.tmp");
        // Keep the commit marker until intent is gone, so interruption during
        // cleanup never changes a committed set into an apparent rollback.
        detail::Remove(intent); detail::Remove(location_ / "ready"); detail::Remove(location_ / "commit");
        nonce_ = savedNonce;
        if (count) std::cout << (committed ? "Finalized" : "Recovered") << " output transaction (" << count << " targets)\n";
    }
};

} // namespace pulse::output
