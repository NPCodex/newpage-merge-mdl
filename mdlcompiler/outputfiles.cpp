#include "outputfiles.h"
#include <chrono>
#include <cstdio>
#include <set>

namespace {
struct Entry {
    PendingOutput output;
    std::filesystem::path stage, backup;
    bool staged = false, backed = false, installed = false;
};
struct Transaction {
    std::vector<Entry> entries;
    bool committed = false;
    std::string rollback() {
        std::string failures;
        for (auto it = entries.rbegin(); it != entries.rend(); ++it) {
            std::error_code ec;
            if (it->installed) {
                std::filesystem::remove(it->output.path, ec);
                if (!ec) it->installed = false;
            }
            if (it->backed && !it->installed) {
                ec.clear();
                std::filesystem::rename(it->backup, it->output.path, ec);
                if (!ec) it->backed = false;
            }
            if (it->backed) failures += " recovery backup: " + it->backup.string();
            if (it->staged) {
                ec.clear();
                std::filesystem::remove(it->stage, ec);
                if (!ec) it->staged = false;
            }
        }
        return failures;
    }
    ~Transaction() {
        if (!committed) { try { rollback(); } catch (...) {} }
    }
};
}

bool SaveOutputSet(const std::vector<PendingOutput>& outputs, std::string* error) {
    Transaction transaction;
    auto fail = [&](const std::string& message) {
        auto recovery = transaction.rollback();
        if (error) *error = message + recovery;
        return false;
    };
    try {
        std::set<std::filesystem::path> paths;
        const auto nonce = std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        for (const auto& output : outputs) {
            if (!paths.insert(std::filesystem::absolute(output.path).lexically_normal()).second)
                return fail("duplicate output path: " + output.path.string());
            std::error_code ec;
            if (!output.path.parent_path().empty())
                std::filesystem::create_directories(output.path.parent_path(), ec);
            if (ec) return fail("cannot create output directory: " + ec.message());
            const auto status = std::filesystem::symlink_status(output.path, ec);
            if (ec && ec != std::errc::no_such_file_or_directory)
                return fail("cannot inspect output: " + output.path.string() + ": " + ec.message());
            if (std::filesystem::exists(status)) {
                if (!std::filesystem::is_regular_file(status))
                    return fail("output is not a regular file: " + output.path.string());
                auto writes = std::filesystem::perms::owner_write | std::filesystem::perms::group_write | std::filesystem::perms::others_write;
                if ((status.permissions() & writes) == std::filesystem::perms::none)
                    return fail("output is read-only: " + output.path.string());
            }
            const auto suffix = ".npmdl-" + nonce + "-" + std::to_string(transaction.entries.size());
            Entry entry{output, output.path.string() + suffix + ".stage", output.path.string() + suffix + ".backup"};
            ec.clear();
            if (std::filesystem::exists(entry.backup, ec) || ec)
                return fail("cannot reserve output backup: " + entry.backup.string());
            transaction.entries.push_back(std::move(entry));
        }
        for (auto& entry : transaction.entries) {
            FILE* file = nullptr;
#ifdef _WIN32
            _wfopen_s(&file, entry.stage.c_str(), L"wbx");
#else
            file = std::fopen(entry.stage.c_str(), "wbx");
#endif
            if (!file) return fail("cannot stage output: " + entry.output.path.string());
            entry.staged = true;
            bool ok = std::fwrite(entry.output.data, 1, entry.output.size, file) == entry.output.size;
            if (std::fflush(file) != 0) ok = false;
            if (std::fclose(file) != 0) ok = false;
            if (!ok) return fail("incomplete output write: " + entry.output.path.string());
        }
        for (auto& entry : transaction.entries) {
            std::error_code ec;
            if (!std::filesystem::exists(entry.output.path, ec)) {
                if (ec) return fail("cannot inspect output: " + ec.message());
                continue;
            }
            std::filesystem::rename(entry.output.path, entry.backup, ec);
            if (ec) return fail("cannot preserve existing output: " + entry.output.path.string() + ": " + ec.message());
            entry.backed = true;
        }
        // Publish the MDL last so its companion files are installed first.
        for (int pass = 0; pass < 2; ++pass) for (auto& entry : transaction.entries) {
            if ((entry.output.path.extension() == ".mdl") != (pass == 1)) continue;
            std::error_code ec;
            std::filesystem::rename(entry.stage, entry.output.path, ec);
            if (ec) return fail("cannot install output: " + entry.output.path.string() + ": " + ec.message());
            entry.staged = false;
            entry.installed = true;
        }
        transaction.committed = true;
        for (auto& entry : transaction.entries) if (entry.backed) {
            std::error_code ec;
            std::filesystem::remove(entry.backup, ec);
            if (ec) std::fprintf(stderr, "warning: retained output backup %s: %s\n", entry.backup.string().c_str(), ec.message().c_str());
        }
        return true;
    } catch (const std::exception& exception) {
        return fail(std::string("output transaction: ") + exception.what());
    }
}
