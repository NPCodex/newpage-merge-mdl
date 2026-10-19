#include "response_writer.h"

#include <atomic>
#include <cerrno>
#include <cstdint>
#include <filesystem>
#include <string>
#include <system_error>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/types.h>
#include <unistd.h>
#endif

namespace pulse::tool::detail {
namespace {

namespace fs = std::filesystem;
std::atomic<std::uint64_t> nextTemporary{0};

void SetError(std::string* err, const std::string& message) {
    if (err)
        *err = message;
}

std::string SystemError() {
#ifdef _WIN32
    return std::system_category().message(static_cast<int>(GetLastError()));
#else
    return std::system_category().message(errno);
#endif
}

struct TempFile {
#ifdef _WIN32
    HANDLE handle = INVALID_HANDLE_VALUE;
#else
    int handle = -1;
#endif
    fs::path path;

    bool Open(const fs::path& destination) {
        const fs::path parent = destination.has_parent_path() ? destination.parent_path() : fs::path(".");
        const std::string filename = destination.filename().u8string();
        for (unsigned attempt = 0; attempt < 64; ++attempt) {
            const auto serial = nextTemporary.fetch_add(1, std::memory_order_relaxed);
#ifdef _WIN32
            const auto process = static_cast<unsigned long long>(GetCurrentProcessId());
#else
            const auto process = static_cast<unsigned long long>(getpid());
#endif
            path = parent / fs::u8path(filename + ".meshtool-" + std::to_string(process) + "-" +
                                      std::to_string(serial) + ".tmp");
#ifdef _WIN32
            handle = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                                 FILE_ATTRIBUTE_TEMPORARY, nullptr);
            if (handle != INVALID_HANDLE_VALUE)
                return true;
            if (GetLastError() != ERROR_FILE_EXISTS && GetLastError() != ERROR_ALREADY_EXISTS)
                return false;
#else
            handle = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL
#ifdef O_CLOEXEC
                          | O_CLOEXEC
#endif
                          , 0666);
            if (handle >= 0)
                return true;
            if (errno != EEXIST)
                return false;
#endif
        }
        errno = EEXIST;
        return false;
    }

    bool Write(const unsigned char* bytes, std::size_t size) {
        while (size > 0) {
#ifdef _WIN32
            const DWORD chunk = static_cast<DWORD>(size > 0x7fffffffu ? 0x7fffffffu : size);
            DWORD written = 0;
            if (!WriteFile(handle, bytes, chunk, &written, nullptr) || written == 0)
                return false;
            bytes += written;
            size -= written;
#else
            const ssize_t written = ::write(handle, bytes, size);
            if (written < 0) {
                if (errno == EINTR)
                    continue;
                return false;
            }
            if (written == 0) {
                errno = EIO;
                return false;
            }
            bytes += written;
            size -= static_cast<std::size_t>(written);
#endif
        }
        return true;
    }

    bool Flush() {
#ifdef _WIN32
        return FlushFileBuffers(handle) != 0;
#else
        int result;
        do {
            result = fsync(handle);
        } while (result != 0 && errno == EINTR);
        return result == 0;
#endif
    }

    bool Close() {
#ifdef _WIN32
        HANDLE current = handle;
        handle = INVALID_HANDLE_VALUE;
        return CloseHandle(current) != 0;
#else
        const int current = handle;
        handle = -1;
        return ::close(current) == 0;
#endif
    }

    bool Replace(const fs::path& destination) {
#ifdef _WIN32
        return MoveFileExW(path.c_str(), destination.c_str(),
                           MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
        return ::rename(path.c_str(), destination.c_str()) == 0;
#endif
    }

    void Remove() {
        if (path.empty())
            return;
#ifdef _WIN32
        DeleteFileW(path.c_str());
#else
        ::unlink(path.c_str());
#endif
    }

    ~TempFile() {
#ifdef _WIN32
        if (handle != INVALID_HANDLE_VALUE)
            CloseHandle(handle);
#else
        if (handle >= 0)
            ::close(handle);
#endif
        Remove();
    }
};

} // namespace

bool WriteResponseAtomically(const std::string& responsePath, const void* data,
                             std::size_t size, std::string* err) {
    const fs::path destination = fs::u8path(responsePath);
    TempFile temporary;
    if (!temporary.Open(destination)) {
        SetError(err, "cannot create a temporary response file: " + SystemError());
        return false;
    }

    const auto* bytes = static_cast<const unsigned char*>(data);
    if (!temporary.Write(bytes, size) || ResponseWriteTestFail("write")) {
        const std::string reason = SystemError();
        temporary.Close();
        temporary.Remove();
        SetError(err, "cannot write the temporary response file: " + reason);
        return false;
    }
    if (!temporary.Flush() || ResponseWriteTestFail("flush")) {
        const std::string reason = SystemError();
        temporary.Close();
        temporary.Remove();
        SetError(err, "cannot flush the temporary response file: " + reason);
        return false;
    }
    const bool closed = temporary.Close();
    if (!closed || ResponseWriteTestFail("close")) {
        const std::string reason = SystemError();
        temporary.Remove();
        SetError(err, "cannot close the temporary response file: " + reason);
        return false;
    }
    if (ResponseWriteTestFail("replace") || !temporary.Replace(destination)) {
        const std::string reason = SystemError();
        temporary.Remove();
        SetError(err, "cannot replace the response file: " + reason);
        return false;
    }
    temporary.path.clear();
    return true;
}

} // namespace pulse::tool::detail
