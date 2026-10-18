#pragma once

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace vmdtool {
namespace fs = std::filesystem;

inline fs::path ExecutablePath(const char* argv0) {
#ifdef _WIN32
    std::vector<wchar_t> buffer(32768);
    const DWORD length = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (length && length < buffer.size()) return fs::path(buffer.data(), buffer.data() + length);
#else
    std::vector<char> buffer(4096);
    const auto length = readlink("/proc/self/exe", buffer.data(), buffer.size());
    if (length > 0 && static_cast<size_t>(length) < buffer.size())
        return fs::u8path(std::string(buffer.data(), static_cast<size_t>(length)));
#endif
    return fs::absolute(fs::u8path(argv0));
}

inline fs::path CompilerPath(const char* argv0) {
    const fs::path self = ExecutablePath(argv0).parent_path();
#ifdef _WIN32
    const char* name = "NewPageMergeMDL.exe";
#else
    const char* name = "NewPageMergeMDL";
#endif
    // Release layout first, then a developer's flat binary directory. Never
    // fall back to an unrelated mdlcompiler on PATH or the working directory.
    for (const fs::path& candidate : {self.parent_path() / name, self / name}) {
        std::error_code ec;
        if (fs::is_regular_file(candidate, ec) && !ec) return candidate;
    }
    throw std::runtime_error(std::string("cannot find ") + name + " beside the tool or one directory above it");
}

#ifdef _WIN32
inline std::wstring QuoteArgument(const std::wstring& value) {
    std::wstring result(1, L'"');
    size_t slashes = 0;
    for (wchar_t c : value) {
        if (c == L'\\') { ++slashes; continue; }
        result.append(slashes * (c == L'"' ? 2 : 1), L'\\');
        slashes = 0;
        if (c == L'"') result.push_back(L'\\');
        result.push_back(c);
    }
    result.append(slashes * 2, L'\\');
    result.push_back(L'"');
    return result;
}
#endif

inline int RunCompiler(const fs::path& executable, const std::vector<std::string>& arguments) {
#ifdef _WIN32
    std::wstring command = QuoteArgument(executable.native());
    for (const auto& argument : arguments)
        command += L" " + QuoteArgument(fs::u8path(argument).native());
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                        nullptr, nullptr, &startup, &process))
        throw std::runtime_error("cannot launch " + executable.u8string() +
                                 " (Windows error " + std::to_string(GetLastError()) + ")");
    CloseHandle(process.hThread);
    const DWORD waited = WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exitCode = 1;
    const bool gotExit = waited == WAIT_OBJECT_0 && GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hProcess);
    if (!gotExit) throw std::runtime_error("cannot read compiler exit status");
    return static_cast<int>(exitCode);
#else
    std::vector<std::string> owned{executable.u8string()};
    owned.insert(owned.end(), arguments.begin(), arguments.end());
    std::vector<char*> argv;
    for (auto& argument : owned) argv.push_back(argument.data());
    argv.push_back(nullptr);
    const pid_t child = fork();
    if (child < 0) throw std::runtime_error(std::string("cannot launch compiler: ") + std::strerror(errno));
    if (child == 0) {
        execv(executable.c_str(), argv.data());
        std::fprintf(stderr, "cannot launch compiler: %s\n", std::strerror(errno));
        _exit(127);
    }
    int status = 0;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited < 0) throw std::runtime_error("cannot wait for compiler");
    return WIFEXITED(status) ? WEXITSTATUS(status) : WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 1;
#endif
}
} // namespace vmdtool
