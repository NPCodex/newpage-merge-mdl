#include "transaction.h"
#ifdef AG2_TRANSACTION_TESTING
#define PULSE_OUTPUT_TESTING
#endif
#include "../../libs/persistentoutput.h"
#ifdef AG2_TRANSACTION_TESTING
namespace ag2 { void TransactionTestPoint(const char*, size_t); }
namespace pulse::output {
void TestPoint(const char* point, size_t index) { ag2::TransactionTestPoint(point, index); }
}
#endif
namespace ag2 {
OutputTransaction::OutputTransaction(const std::filesystem::path& primary,
                                     const std::vector<std::filesystem::path>& destinations) {
    std::vector<pulse::output::Target> allowed;
    for (const auto& path : destinations) allowed.push_back({path, false});
    transaction_ = std::make_unique<pulse::output::Transaction>(primary, allowed);
}
OutputTransaction::~OutputTransaction() = default;
const std::filesystem::path& OutputTransaction::StageRoot() const { return transaction_->StageRoot(); }
void OutputTransaction::Replace(const std::filesystem::path& staged, const std::filesystem::path& destination,
                                bool createOnly) { transaction_->Replace(staged, destination, createOnly); }
void OutputTransaction::Remove(const std::filesystem::path& destination) { transaction_->Remove(destination); }
void OutputTransaction::Commit() { transaction_->Commit(); }
} // namespace ag2
