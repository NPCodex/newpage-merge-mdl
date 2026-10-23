#pragma once
#include "dependencies.h"
#include "pathcompat.h"
#include "persistentoutput.h"

namespace pulse::reports {
inline bool Aliases(const std::filesystem::path& a, const std::filesystem::path& b) {
    namespace fs = std::filesystem;
    std::error_code ec;
    if (fs::equivalent(a, b, ec) && !ec) return true; // Includes hard links.
    return output::detail::Key(fs::weakly_canonical(fs::absolute(a))) ==
           output::detail::Key(fs::weakly_canonical(fs::absolute(b)));
}
inline void Validate(const std::filesystem::path& destination,
                     const std::vector<std::filesystem::path>& outputs) {
    // Reject symlink/reparse targets and resolve short Windows spellings.
    const auto target = output::detail::Destination(destination);
    const auto targetKey = output::detail::Key(std::filesystem::weakly_canonical(target));
    const auto aliasesTarget = [&](const std::filesystem::path& file) {
        std::error_code ec;
        if (std::filesystem::equivalent(target, file, ec) && !ec) return true;
        return targetKey == output::detail::Key(
            std::filesystem::weakly_canonical(std::filesystem::absolute(file)));
    };
    for (const auto& input : dependencies::Paths())
        if (aliasesTarget(FilePath(input)))
            throw std::runtime_error("report output aliases an input: " + input);
    for (const auto& file : outputs)
        if (aliasesTarget(file))
            throw std::runtime_error("report output aliases a model output: " + file.u8string());
    for (const auto& component : target)
        if (component == ".newpage-output-locks" || component == ".newpage-output-transactions")
            throw std::runtime_error("report output overlaps transaction storage");
}
// Own the lock and snapshot before model publication. Staging/flush failures
// leave an existing report intact; an interrupted commit recovers on retry.
class Report {
public:
    Report(const std::filesystem::path& destination,
           const std::vector<std::filesystem::path>& outputs) : path_(destination) {
        Validate(path_, outputs);
        transaction_ = std::make_unique<output::Transaction>(path_,
            std::vector<output::Target>{{path_, false}});
    }
    void Write(const std::string& text) {
        const auto staged = transaction_->StageRoot() / "report.json";
        // This is only Commit's copy source, never a recovery target. Commit
        // copies and flushes the publication stage before its durable ready
        // marker. Flushing this scratch copy as well doubles data sync work
        // without strengthening recovery. Still check both writing and close.
        FILE* file = output::detail::Open(staged, true);
        if (!file) throw std::runtime_error("cannot write staged report: " + staged.u8string());
        bool complete = std::fwrite(text.data(), 1, text.size(), file) == text.size();
        if (std::fclose(file)) complete = false;
        if (!complete) throw std::runtime_error("cannot finish staged report: " + staged.u8string());
        transaction_->Replace(staged, path_);
        transaction_->Commit();
    }
private:
    std::filesystem::path path_;
    std::unique_ptr<output::Transaction> transaction_;
};
}
