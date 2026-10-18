// Exception-safe publication of one AG2 job. This is not a crash-recovery
// journal: hard termination/power loss and concurrent writers are unsupported.
#pragma once

#include <filesystem>
#include <vector>

namespace ag2 {

class OutputTransaction {
public:
    OutputTransaction();
    ~OutputTransaction();
    OutputTransaction(const OutputTransaction&) = delete;
    OutputTransaction& operator=(const OutputTransaction&) = delete;

    const std::filesystem::path& StageRoot() const { return root_; }
    // createOnly protects the first VMDL backup, including if one appears
    // between generation and publication. Existing backups are never replaced.
    void Replace(const std::filesystem::path& staged, const std::filesystem::path& destination,
                 bool createOnly = false);
    void Remove(const std::filesystem::path& destination);
    void Commit();

private:
    struct Entry {
        std::filesystem::path staged, destination, slot;
        bool createOnly = false, hadOriginal = false, movedOriginal = false, installed = false;
    };
    void Add(Entry entry);
    void MakeParents(const std::filesystem::path& directory);
    void Cleanup() noexcept;
    std::filesystem::path root_;
    std::vector<Entry> entries_;
    std::vector<std::filesystem::path> createdDirectories_;
    bool preserve_ = false, committed_ = false;
};

} // namespace ag2
