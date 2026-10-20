// Durable, all-output publication for VMD conversion and L4D animation swaps.
// One authoritative manifest makes the commit decision for the entire batch.
// Locks coordinate cooperating writers; non-cooperating edits are detected by
// fingerprints. Filesystem flushes cannot promise survival of every power loss.
#pragma once
#include "../libs/persistentoutput.h"
#include <random>

namespace subtool {
namespace fs = std::filesystem;
namespace txdetail = pulse::output::detail;
#ifdef NEWPAGE_SUBTOOL_TRANSACTION_TESTING
void TransactionTestPoint(const char*, size_t);
#else
inline void TransactionTestPoint(const char*, size_t) {}
#endif

class DurableOutputTransaction {
    struct Entry {
        fs::path staged, destination, slot;
        bool original = false;
        txdetail::Digest old, fresh;
    };
    struct Data {
        fs::path root;
        // 0: generation, 1: copying, 2: publication, 3: rolled back, 4: committed.
        int phase = 0;
        std::vector<Entry> entries;
    } data_;
    std::map<std::string, size_t> destinations_;
    std::map<fs::path, fs::path> directories_;
    std::map<std::string, std::unique_ptr<txdetail::Lock>> locks_;
    std::vector<fs::path> created_;
    bool done_ = false, preserve_ = false;

    static fs::path Marker(const fs::path& path) {
        return fs::u8path(path.u8string() + ".newpage-subtool-journal");
    }
    static bool File(const fs::path& path) {
        txdetail::CheckParents(path);
        const auto status = txdetail::Status(path);
        if (!fs::exists(status)) return false;
        if (!fs::is_regular_file(status))
            throw std::runtime_error("transaction output is not a regular file: " + path.u8string());
        return true;
    }
    static bool Same(const fs::path& path, const txdetail::Digest& digest) {
        return File(path) && txdetail::Fingerprint(path, false) == digest;
    }
    static fs::path UniqueRoot() {
        const auto parent = fs::canonical(fs::temp_directory_path());
        std::random_device random;
        for (int i = 0; i < 32; ++i) {
            const auto path = parent / ("newpage-subtool-stage-" + std::to_string(random()) + "-" +
                std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
            if (fs::create_directory(path)) { txdetail::SyncDirectory(parent); return path; }
        }
        throw std::runtime_error("cannot create output staging directory");
    }
    static fs::path Slot(const Data& data, const Entry& entry, size_t index) {
        return entry.destination.parent_path() /
            (".newpage-subtool-publish-" + data.root.filename().u8string().substr(22) + "-" + std::to_string(index));
    }
    static void AtomicText(const fs::path& path, const std::string& text) {
        txdetail::CheckParents(path);
        const auto pending = fs::u8path(path.u8string() + ".tmp");
        txdetail::Remove(pending);
        txdetail::Write(pending, text);
        txdetail::Rename(pending, path, true);
    }
    static std::string MarkerText(const fs::path& root, const fs::path& destination) {
        std::ostringstream text;
        text << "NPSUB_PTR_3 " << std::quoted(root.u8string()) << ' ' << std::quoted(destination.u8string()) << '\n';
        return text.str();
    }
    static void Save(const Data& data) {
        std::ostringstream text;
        text << "NPSUB_TXN_3 " << std::quoted(data.root.u8string()) << ' ' << data.phase << ' ' << data.entries.size() << '\n';
        for (const auto& e : data.entries)
            text << std::quoted(e.destination.u8string()) << ' ' << std::quoted(e.staged.u8string()) << ' '
                 << std::quoted(e.slot.u8string()) << ' ' << e.original << ' '
                 << e.old.size << ' ' << e.old.hash << ' ' << e.fresh.size << ' ' << e.fresh.hash << '\n';
        const std::string body = text.str();
        if (body.size() > 4 * 1024 * 1024 - 64) throw std::runtime_error("output transaction journal is too large");
        txdetail::Digest checksum; txdetail::Hash(checksum, body);
        AtomicText(data.root / "journal", body + "CHECKSUM " + txdetail::Hex(checksum.hash) + "\n");
    }
    static std::string ReadText(const fs::path& path) {
        if (!File(path) || fs::file_size(path) > 4 * 1024 * 1024)
            throw std::runtime_error("invalid subtool output journal: " + path.u8string());
        std::ifstream input(path, std::ios::binary);
        std::ostringstream contents; contents << input.rdbuf();
        if (input.bad()) throw std::runtime_error("cannot read subtool output journal");
        return contents.str();
    }
    static fs::path ReadMarker(const fs::path& destination) {
        std::istringstream input(ReadText(Marker(destination)));
        std::string magic, root, target;
        if (!(input >> magic >> std::quoted(root) >> std::quoted(target)) || magic != "NPSUB_PTR_3" ||
            fs::u8path(target) != destination)
            throw std::runtime_error("invalid subtool output marker: " + Marker(destination).u8string());
        input >> std::ws;
        if (!input.eof()) throw std::runtime_error("unexpected subtool marker data");
        return fs::u8path(root);
    }
    static void CheckRoot(const fs::path& root) {
        if (!root.is_absolute() || root != root.lexically_normal() ||
            root.parent_path() != fs::canonical(fs::temp_directory_path()) ||
            root.filename().u8string().rfind("newpage-subtool-stage-", 0) != 0)
            throw std::runtime_error("unsafe output recovery staging path: " + root.u8string());
        txdetail::CheckParents(root);
        if (!fs::is_directory(txdetail::Status(root))) throw std::runtime_error("missing output recovery staging directory");
    }
    static Data Load(const fs::path& root) {
        CheckRoot(root);
        const auto contents = ReadText(root / "journal");
        const auto end = contents.rfind("CHECKSUM ");
        if (end == std::string::npos) throw std::runtime_error("missing journal checksum");
        txdetail::Digest checksum; txdetail::Hash(checksum, contents.substr(0, end));
        if (contents.substr(end) != "CHECKSUM " + txdetail::Hex(checksum.hash) + "\n")
            throw std::runtime_error("invalid journal checksum");
        std::istringstream input(contents.substr(0, end));
        Data data; data.root = root;
        std::string magic, storedRoot; size_t count = 0;
        if (!(input >> magic >> std::quoted(storedRoot) >> data.phase >> count) || magic != "NPSUB_TXN_3" ||
            fs::u8path(storedRoot) != root || data.phase < 0 || data.phase > 4 || !count || count > 4096)
            throw std::runtime_error("invalid subtool output journal");
        std::set<std::string> paths;
        for (size_t i = 0; i < count; ++i) {
            Entry e; std::string destination, staged, slot; int original;
            if (!(input >> std::quoted(destination) >> std::quoted(staged) >> std::quoted(slot) >> original >>
                  e.old.size >> e.old.hash >> e.fresh.size >> e.fresh.hash) || (original != 0 && original != 1))
                throw std::runtime_error("truncated subtool output journal");
            e.destination = fs::u8path(destination); e.staged = fs::u8path(staged); e.slot = fs::u8path(slot); e.original = original != 0;
            if (!e.destination.is_absolute() || e.destination != txdetail::Destination(e.destination) ||
                !paths.insert(txdetail::Key(e.destination)).second ||
                e.destination.u8string().find(".newpage-subtool-") != std::string::npos)
                throw std::runtime_error("unsafe or duplicate output recovery destination");
            if (!e.staged.empty()) {
                if (!e.staged.is_absolute() || e.staged != e.staged.lexically_normal())
                    throw std::runtime_error("unsafe staged output path");
                const auto relative = e.staged.lexically_relative(root);
                if (relative.empty() || *relative.begin() == "..") throw std::runtime_error("staged output outside transaction");
            }
            if ((data.phase == 0 && !e.slot.empty()) || (data.phase != 0 && e.slot != Slot(data, e, i)))
                throw std::runtime_error("invalid output recovery slot");
            if ((!e.original && !(e.old == txdetail::Digest{})) ||
                (e.staged.empty() && !(e.fresh == txdetail::Digest{})))
                throw std::runtime_error("invalid output recovery fingerprint");
            data.entries.push_back(std::move(e));
        }
        input >> std::ws;
        if (!input.eof()) throw std::runtime_error("unexpected subtool output journal data");
        for (const auto& e : data.entries) {
            if (paths.count(txdetail::Key(Marker(e.destination)))) throw std::runtime_error("output overlaps journal marker");
        }
        return data;
    }
    static void CheckSlot(const Data& data, const Entry& e) {
        if (e.slot.empty()) return;
        txdetail::CheckParents(e.slot);
        if (!txdetail::Exists(e.slot)) return;
        if (!fs::is_directory(txdetail::Status(e.slot))) throw std::runtime_error("invalid recovery slot object");
        if (!File(e.slot / "owner")) {
            // A kill immediately after mkdir, or just before rmdir during
            // completed cleanup, can leave an empty slot without its marker.
            if (!fs::is_empty(e.slot) || data.phase == 2)
                throw std::runtime_error("missing recovery slot owner");
        } else if (ReadText(e.slot / "owner") != MarkerText(data.root, e.destination)) {
            throw std::runtime_error("mismatched recovery slot owner");
        }
        for (const auto& item : fs::directory_iterator(e.slot)) {
            if ((item.path().filename() != "previous" && item.path().filename() != "replacement" &&
                 item.path().filename() != "owner") || !File(item.path()))
                throw std::runtime_error("unexpected recovery slot contents");
        }
    }
    static void Preflight(const Data& data, bool markers) {
        CheckRoot(data.root);
        txdetail::Tree(data.root); // Reject links/special files before any recovery mutation.
        // Validate every marker/slot and every destination before restoring one.
        // A later conflict therefore cannot cause a partially restored batch.
        for (const auto& e : data.entries) {
            txdetail::CheckParents(e.destination);
            if (File(Marker(e.destination))) {
                if (ReadMarker(e.destination) != data.root) throw std::runtime_error("mismatched output recovery marker");
            } else if (markers && data.phase == 2) throw std::runtime_error("missing output recovery marker");
            CheckSlot(data, e);
            if (data.phase < 2) continue; // Generation/copying never touched outputs.
            const bool dest = File(e.destination);
            const auto backup = e.slot / "previous", replacement = e.slot / "replacement";
            const bool saved = File(backup);
            if (saved && (!e.original || !Same(backup, e.old))) throw std::runtime_error("changed transaction backup: " + backup.u8string());
            if (File(replacement) && (e.staged.empty() || !Same(replacement, e.fresh)))
                throw std::runtime_error("changed transaction replacement: " + replacement.u8string());
            if (data.phase == 4) {
                if (e.staged.empty() ? dest : !Same(e.destination, e.fresh))
                    throw std::runtime_error("committed output changed since transaction: " + e.destination.u8string());
            } else if (data.phase == 3) {
                if (e.original ? !Same(e.destination, e.old) : dest)
                    throw std::runtime_error("restored output changed since transaction: " + e.destination.u8string());
            } else {
                const bool oldHere = dest && e.original && Same(e.destination, e.old);
                const bool newHere = dest && !e.staged.empty() && Same(e.destination, e.fresh);
                if ((dest && !oldHere && !newHere) || (e.original && !saved && !oldHere))
                    throw std::runtime_error("output changed since transaction: " + e.destination.u8string());
            }
        }
    }
    static void Cleanup(Data& data) {
        // The durable completed decision precedes removing any backup or marker.
        // Slot deletion is restartable; removing the root always comes last.
        for (size_t i = 0; i < data.entries.size(); ++i) {
            const auto& e = data.entries[i];
            if (e.slot.empty() || !txdetail::Exists(e.slot)) continue;
            // Delete the owner last, explicitly. A kill at any boundary must
            // leave an owned slot, or an empty slot safe to remove on restart.
            txdetail::Remove(e.slot / "previous");
            TransactionTestPoint("cleanup_previous", i);
            txdetail::Remove(e.slot / "replacement");
            TransactionTestPoint("cleanup_replacement", i);
            txdetail::Remove(e.slot / "owner");
            TransactionTestPoint("cleanup_owner", i);
            if (!fs::is_empty(e.slot)) throw std::runtime_error("recovery slot changed during cleanup");
            fs::remove(e.slot); txdetail::SyncDirectory(e.slot.parent_path());
            TransactionTestPoint("cleanup_slot", i);
        }
        for (size_t i = 0; i < data.entries.size(); ++i) {
            txdetail::Remove(Marker(data.entries[i].destination));
            txdetail::Remove(fs::u8path(Marker(data.entries[i].destination).u8string() + ".tmp"));
            TransactionTestPoint("cleanup_marker", i);
        }
        txdetail::Remove(data.root);
    }
    static void RecoverData(Data& data) {
        Preflight(data, true);
        TransactionTestPoint("recovery_preflight", 0);
        if (data.phase == 2) {
            for (size_t i = 0; i < data.entries.size(); ++i) {
                const auto& e = data.entries[i];
                const auto backup = e.slot / "previous";
                if (e.original && File(backup)) {
                    // Atomic replacement leaves either the new file + backup,
                    // or the restored original; both are recognized on restart.
                    if (File(e.destination) && !Same(e.destination, e.old) && !Same(e.destination, e.fresh))
                        throw std::runtime_error("output changed during recovery");
                    txdetail::Match(backup, false, e.old);
                    txdetail::Rename(backup, e.destination, true);
                } else if (!e.original && File(e.destination)) {
                    txdetail::Match(e.destination, false, e.fresh);
                    txdetail::Remove(e.destination);
                }
                TransactionTestPoint("recovered", i);
            }
            data.phase = 3; Save(data);
        }
        Cleanup(data);
    }
    static std::unique_ptr<txdetail::Lock> Lock(const fs::path& destination) {
        txdetail::Digest identity; txdetail::Hash(identity, txdetail::Key(destination));
        const auto path = fs::canonical(fs::temp_directory_path()) /
            ("newpage-subtool-lock-" + txdetail::Hex(identity.hash) + ".lock");
        txdetail::Status(path);
        return std::make_unique<txdetail::Lock>(path);
    }
    void Acquire(const fs::path& destination) {
        const auto key = txdetail::Key(destination);
        if (locks_.count(key)) return;
        auto lock = Lock(destination);
        if (File(Marker(destination))) {
            Data old = Load(ReadMarker(destination));
            bool found = false;
            std::map<std::string, fs::path> others;
            for (const auto& e : old.entries) {
                const auto other = txdetail::Key(e.destination);
                if (other == key) found = true;
                else if (!locks_.count(other)) others.emplace(other, e.destination);
            }
            if (!found) throw std::runtime_error("output recovery journal does not contain target");
            std::vector<std::unique_ptr<txdetail::Lock>> held;
            for (const auto& other : others) held.push_back(Lock(other.second));
            RecoverData(old);
        }
        locks_.emplace(key, std::move(lock));
    }
    void Parents(const fs::path& parent) {
        txdetail::CheckParents(parent);
        if (fs::is_directory(parent)) return;
        Parents(parent.parent_path());
        if (fs::create_directory(parent)) { created_.push_back(parent); txdetail::SyncDirectory(parent.parent_path()); }
    }
    void Add(const fs::path& staged, const fs::path& destination) {
        if (done_ || data_.phase != 0) throw std::runtime_error("output transaction already finished");
        if (data_.entries.size() >= 4096) throw std::runtime_error("too many outputs in one transaction");
        const auto key = txdetail::Key(destination);
        if (destinations_.count(key)) throw std::runtime_error("duplicate output: " + destination.u8string());
        if (destination.u8string().find(".newpage-subtool-") != std::string::npos)
            throw std::runtime_error("output uses reserved transaction name");
        Entry e; e.staged = staged; e.destination = destination; e.original = File(destination);
        if (e.original) e.old = txdetail::Fingerprint(destination, false);
        Parents(destination.parent_path());
        data_.entries.push_back(std::move(e)); destinations_[key] = data_.entries.size() - 1;
        Save(data_);
        AtomicText(Marker(destination), MarkerText(data_.root, destination));
    }
public:
    DurableOutputTransaction() { data_.root = UniqueRoot(); }
    DurableOutputTransaction(const DurableOutputTransaction&) = delete;
    DurableOutputTransaction& operator=(const DurableOutputTransaction&) = delete;
    ~DurableOutputTransaction() {
        if (preserve_ || done_) return;
        try {
            if (data_.entries.empty()) txdetail::Remove(data_.root);
            else RecoverData(data_);
            for (auto it = created_.rbegin(); it != created_.rend(); ++it) {
                std::error_code ec; fs::remove(*it, ec);
            }
        } catch (const std::exception& error) {
            std::fprintf(stderr, "warning: output recovery retained at %s: %s\n", data_.root.u8string().c_str(), error.what());
        }
    }
    const fs::path& Root() const { return data_.root; }
    std::string Stage(const std::string& destination) {
        if (done_ || data_.phase != 0) throw std::runtime_error("output transaction already finished");
        const auto final = txdetail::Destination(fs::u8path(destination));
        const auto found = destinations_.find(txdetail::Key(final));
        if (found != destinations_.end()) return data_.entries[found->second].staged.u8string();
        Acquire(final);
        const auto parent = final.parent_path();
        auto directory = directories_.find(parent);
        if (directory == directories_.end()) {
            const auto path = data_.root / ("directory-" + std::to_string(directories_.size()));
            fs::create_directory(path); directory = directories_.emplace(parent, path).first;
        }
        const auto staged = directory->second / final.filename();
        Add(staged, final);
        TransactionTestPoint("stage", data_.entries.size() - 1);
        return staged.u8string();
    }
    void Replace(const fs::path& staged, const fs::path& destination) {
        if (done_ || data_.phase != 0) throw std::runtime_error("output transaction already finished");
        const auto final = txdetail::Destination(destination); Acquire(final);
        const auto source = txdetail::Destination(staged);
        const auto relative = source.lexically_relative(data_.root);
        if (relative.empty() || *relative.begin() == "..") throw std::runtime_error("replacement is outside transaction staging");
        Add(source, final);
    }
    void Remove(const fs::path& destination) {
        if (done_ || data_.phase != 0) throw std::runtime_error("output transaction already finished");
        const auto final = txdetail::Destination(destination); Acquire(final); Add({}, final);
    }
    void Commit() {
        if (done_ || data_.phase != 0) throw std::runtime_error("output transaction already finished");
        if (data_.entries.empty()) { txdetail::Remove(data_.root); done_ = true; return; }
        try {
            for (size_t i = 0; i < data_.entries.size(); ++i) {
                auto& e = data_.entries[i];
                e.slot = Slot(data_, e, i);
                if (!e.staged.empty()) e.fresh = txdetail::Fingerprint(e.staged, false);
            }
            data_.phase = 1; Save(data_);
            AtomicText(data_.root / "RECOVERY.txt", "Recovery manifest: " + (data_.root / "journal").u8string() + "\n");
            for (size_t i = 0; i < data_.entries.size(); ++i) {
                const auto& e = data_.entries[i];
                if (!fs::create_directory(e.slot)) throw std::runtime_error("output slot already exists");
                txdetail::SyncDirectory(e.slot.parent_path());
                txdetail::Write(e.slot / "owner", MarkerText(data_.root, e.destination));
                if (!e.staged.empty()) {
                    txdetail::CopyFile(e.staged, e.slot / "replacement");
                    txdetail::Match(e.slot / "replacement", false, e.fresh);
                }
                TransactionTestPoint("prepared", i);
            }
            for (const auto& e : data_.entries)
                if (e.original ? !Same(e.destination, e.old) : File(e.destination))
                    throw std::runtime_error("output changed during generation: " + e.destination.u8string());
            data_.phase = 2; Save(data_);
            TransactionTestPoint("journal", 0);
            for (size_t i = 0; i < data_.entries.size(); ++i) {
                const auto& e = data_.entries[i];
                if (e.original ? !Same(e.destination, e.old) : File(e.destination))
                    throw std::runtime_error("output changed during publication: " + e.destination.u8string());
                if (e.original) txdetail::Rename(e.destination, e.slot / "previous");
                TransactionTestPoint("backed_up", i);
                if (!e.staged.empty()) {
                    txdetail::Match(e.slot / "replacement", false, e.fresh);
                    txdetail::Rename(e.slot / "replacement", e.destination);
                }
                TransactionTestPoint("published", i);
            }
            TransactionTestPoint("before_commit", 0);
            data_.phase = 4; Save(data_);
            TransactionTestPoint("committed", 0);
            Preflight(data_, true); Cleanup(data_); done_ = true;
        } catch (const std::exception& failure) {
            if (data_.phase == 4) {
                preserve_ = true;
                throw std::runtime_error(std::string(failure.what()) + "\npublication completed; recovery retained at " + data_.root.u8string());
            }
            try { RecoverData(data_); done_ = true; }
            catch (const std::exception& recovery) {
                preserve_ = true;
                throw std::runtime_error(std::string(failure.what()) + "\noutput rollback incomplete: " + recovery.what() +
                    "\nStaging and backups retained; see " + (data_.root / "RECOVERY.txt").u8string());
            }
            throw;
        }
    }
};
} // namespace subtool
