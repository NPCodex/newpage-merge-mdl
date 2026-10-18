// Locked, journaled publication of one AG2 job. Recover before reading inputs.
#pragma once
#include <filesystem>
#include <memory>
#include <vector>
namespace pulse::output { class Transaction; }
namespace ag2 {
class OutputTransaction {
public:
    OutputTransaction(const std::filesystem::path& primary,
                      const std::vector<std::filesystem::path>& destinations);
    ~OutputTransaction();
    OutputTransaction(const OutputTransaction&) = delete;
    OutputTransaction& operator=(const OutputTransaction&) = delete;
    const std::filesystem::path& StageRoot() const;
    void Replace(const std::filesystem::path& staged, const std::filesystem::path& destination,
                 bool createOnly = false);
    void Remove(const std::filesystem::path& destination);
    void Commit();
private:
    std::unique_ptr<pulse::output::Transaction> transaction_;
};
} // namespace ag2
