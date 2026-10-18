// Standalone fault-injection harness; no hooks are enabled in shipped tools.
#define NEWPAGE_SUBTOOL_TRANSACTION_TESTING
#include "../subtools/vmd2valvebiped/output_transaction.h"
#include "../subtools/vmd2valvebiped/compiler_process.h"
#include <iostream>
#include <iterator>
#include <cstdint>
#ifdef _WIN32
#include <io.h>
#endif

namespace fs = std::filesystem;
static std::string failPoint;
static size_t failIndex = 1;
static fs::path corruptRollback;

void subtool::TransactionTestPoint(const char* point, size_t index) {
    if (failPoint == point && failIndex == index) {
        if (!corruptRollback.empty()) {
            fs::remove(corruptRollback);
            fs::create_directory(corruptRollback);
            std::ofstream(corruptRollback / "foreign-file") << "concurrent change";
        }
        throw std::runtime_error("injected " + failPoint);
    }
}

static void Require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
static void Write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    std::ofstream file(path, std::ios::binary);
    file << text;
    file.close();
    Require(bool(file), "test fixture write failed");
}
static std::string Read(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
static void Record(const fs::path& path, const std::vector<std::string>& arguments) {
    std::ofstream file(path, std::ios::binary);
    for (const auto& argument : arguments) {
        const uint32_t size = static_cast<uint32_t>(argument.size());
        file.write(reinterpret_cast<const char*>(&size), sizeof(size));
        file.write(argument.data(), size);
    }
    file.close();
    Require(bool(file), "argument recording failed");
}
static int Run(const std::vector<std::string>& arguments) {
    // A fake NewPageMergeMDL used by the Python integration test to verify
    // exact child argv, failure status and no accidental use of mdlcompiler.
    if (arguments.size() > 1 && arguments[1] == "-game") {
        const char* record = std::getenv("NEWPAGE_TEST_CHILD_RECORD");
        if (record) Record(fs::u8path(record), arguments);
        const char* failure = std::getenv("NEWPAGE_TEST_CHILD_EXIT");
        if (failure && std::atoi(failure)) return std::atoi(failure);
        fs::path output;
        for (size_t i = 1; i + 1 < arguments.size(); ++i)
            if (arguments[i] == "-OutDir") output = fs::u8path(arguments[++i]);
        Require(!output.empty(), "missing staged -OutDir");
        const char* model = std::getenv("NEWPAGE_TEST_CHILD_MODEL");
        Write(output / "models" / fs::u8path(model ? model : "fixture.mdl"), "compiled fixture");
        return 0;
    }
    if (arguments.size() > 1 && arguments[1] == "--argument-probe") {
        Record(fs::u8path(arguments.at(2)), {arguments.begin() + 4, arguments.end()});
        return std::stoi(arguments.at(3));
    }
    Require(arguments.size() == 2, "usage: subtool_transaction_test <isolated test directory>");
    const fs::path root = fs::u8path(arguments[1]);
    Require(!fs::exists(root), "test directory must not already exist");
    fs::create_directories(root);
    size_t passed = 0;
    for (const std::string point : {"stage", "prepared", "backed_up", "published"}) {
        for (bool existing : {false, true}) {
            const fs::path work = root / (point + (existing ? "-existing" : "-new"));
            fs::create_directory(work);
            const fs::path a = work / "a.dmx", b = work / "b.smd", c = work / "old.ani";
            if (existing) { Write(a, "old a"); Write(b, "old b"); }
            Write(c, "old companion");
            failPoint = point;
            bool rejected = false;
            fs::path staging;
            try {
                subtool::OutputTransaction output;
                staging = output.Root();
                Write(fs::u8path(output.Stage(a.u8string())), "new a");
                Write(fs::u8path(output.Stage(b.u8string())), "new b");
                output.Remove(c);
                output.Commit();
            } catch (const std::exception&) { rejected = true; }
            failPoint.clear();
            Require(rejected, "fault not raised: " + point);
            Require(existing ? Read(a) == "old a" && Read(b) == "old b" : !fs::exists(a) && !fs::exists(b),
                    "partial output after " + point);
            Require(Read(c) == "old companion", "companion changed during failure");
            Require(!fs::exists(staging), "staging leaked after ordinary failure");
            ++passed;
        }
    }
    for (const std::string point : {"backed_up", "published"}) {
        const fs::path work = root / (point + "-after-removal");
        Write(work / "a", "old a"); Write(work / "b", "old b"); Write(work / "old.ani", "old companion");
        failPoint = point; failIndex = 2;
        bool rejected = false;
        try {
            subtool::OutputTransaction output;
            Write(fs::u8path(output.Stage((work / "a").u8string())), "new a");
            Write(fs::u8path(output.Stage((work / "b").u8string())), "new b");
            output.Remove(work / "old.ani");
            output.Commit();
        } catch (const std::exception&) { rejected = true; }
        failPoint.clear(); failIndex = 1;
        Require(rejected && Read(work / "a") == "old a" && Read(work / "b") == "old b" &&
                Read(work / "old.ani") == "old companion", "removed companion not restored");
        ++passed;
    }
    {
        const fs::path work = root / "success";
        Write(work / "a", "old"); Write(work / "old.ani", "stale");
        subtool::OutputTransaction output;
        Write(fs::u8path(output.Stage((work / "a").u8string())), "new");
        Write(fs::u8path(output.Stage((work / "nested" / "b").u8string())), "new b");
        output.Remove(work / "old.ani");
        output.Commit();
        Require(Read(work / "a") == "new" && Read(work / "nested" / "b") == "new b" &&
                !fs::exists(work / "old.ani"), "success did not publish the complete set");
        ++passed;
    }
    {
        const fs::path work = root / "rollback-incomplete";
        Write(work / "a", "old a"); Write(work / "b", "old b");
        fs::path staging;
        std::string error;
        failPoint = "published"; corruptRollback = work / "a";
        try {
            subtool::OutputTransaction output;
            staging = output.Root();
            Write(fs::u8path(output.Stage((work / "a").u8string())), "new a");
            Write(fs::u8path(output.Stage((work / "b").u8string())), "new b");
            output.Commit();
        } catch (const std::exception& e) { error = e.what(); }
        failPoint.clear(); corruptRollback.clear();
        Require(error.find("rollback incomplete") != std::string::npos &&
                fs::is_regular_file(staging / "RECOVERY.txt"), "recovery evidence not retained");
        Require(Read(work / "b") == "old b", "unblocked output was not restored");
        ++passed;
    }
    {
        // fwrite failure must not disappear merely because fclose succeeds.
        const fs::path path = root / "read-only-stream";
        Write(path, "original");
#ifdef _WIN32
        std::FILE* file = _wfopen(path.c_str(), L"rb");
#else
        std::FILE* file = std::fopen(path.c_str(), "rb");
#endif
        Require(file && std::fwrite("x", 1, 1, file) == 0, "failed-write fixture did not fail");
        Require(!subtool::CloseFile(file), "failed write incorrectly reported as success");
        ++passed;
    }
    {
        // No buffered data: the native handle is closed underneath stdio so
        // fclose itself fails, independently of the prior-write case above.
        const fs::path path = root / "close-failure";
#ifdef _WIN32
        std::FILE* file = _wfopen(path.c_str(), L"wb");
        Require(file != nullptr, "cannot create close-failure fixture");
        Require(CloseHandle(reinterpret_cast<HANDLE>(_get_osfhandle(_fileno(file)))), "cannot close native handle");
#else
        std::FILE* file = std::fopen(path.c_str(), "wb");
        Require(file != nullptr, "cannot create close-failure fixture");
        Require(close(fileno(file)) == 0, "cannot close native handle");
#endif
        Require(!subtool::CloseFile(file), "fclose failure incorrectly reported as success");
        ++passed;
    }
#ifdef _WIN32
    {
        const fs::path work = root / "real-rename-failure";
        Write(work / "a", "old a"); Write(work / "b", "old b");
        HANDLE locked = CreateFileW((work / "b").c_str(), GENERIC_READ, FILE_SHARE_READ,
                                    nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        Require(locked != INVALID_HANDLE_VALUE, "cannot lock second destination");
        bool rejected = false;
        try {
            subtool::OutputTransaction output;
            Write(fs::u8path(output.Stage((work / "a").u8string())), "new a");
            Write(fs::u8path(output.Stage((work / "b").u8string())), "new b");
            output.Commit();
        } catch (const std::exception&) { rejected = true; }
        CloseHandle(locked);
        Require(rejected && Read(work / "a") == "old a" && Read(work / "b") == "old b",
                "actual later rename failure did not restore earlier output");
        ++passed;
    }
#endif
    {
        const fs::path record = root / "arguments.bin";
        const std::vector<std::string> values{"", "space path", u8"中文目录", "shell&|<>$();%literal%", "a\"b", "ending\\"};
        std::vector<std::string> child{"--argument-probe", record.u8string(), "17"};
        child.insert(child.end(), values.begin(), values.end());
        const int code = vmdtool::RunCompiler(vmdtool::ExecutablePath(arguments[0].c_str()), child);
        Require(code == 17, "compiler exit code was not propagated");
        const fs::path expected = root / "expected-arguments.bin";
        Record(expected, values);
        Require(Read(record) == Read(expected), "child arguments were altered");
        ++passed;
    }
    std::cout << passed << " transaction/process checks passed\n";
    return 0;
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
    std::vector<std::string> arguments;
    for (int i = 0; i < argc; ++i) {
        const int size = WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, nullptr, 0, nullptr, nullptr);
        std::string value(static_cast<size_t>(size), '\0');
        WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, value.data(), size, nullptr, nullptr);
        value.pop_back(); arguments.push_back(std::move(value));
    }
#else
int main(int argc, char** argv) {
    const std::vector<std::string> arguments(argv, argv + argc);
#endif
    try { return Run(arguments); }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
