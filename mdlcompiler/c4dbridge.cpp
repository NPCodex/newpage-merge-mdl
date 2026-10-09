#include "c4dbridge.h"
#include "pathcompat.h"
#include <chrono>
#include <cstdio>
#include <stdexcept>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif
namespace pulse::source {
namespace fs=std::filesystem;
namespace {
fs::path BridgePath() {
#ifdef _WIN32
    std::wstring path(32768,L'\0');const auto n=GetModuleFileNameW(nullptr,path.data(),static_cast<DWORD>(path.size()));
    if(!n||n>=path.size())throw std::runtime_error("cannot locate compiler executable for Cineware bridge");
    path.resize(n);return fs::path(path).parent_path()/"NewPageMergeMDL-C4D.exe";
#else
    return {};
#endif
}
#ifdef _WIN32
std::wstring Quote(const std::wstring& value) {
    std::wstring result=L"\"";size_t slashes=0;
    for(wchar_t c:value){if(c==L'\\'){++slashes;continue;}
        if(c==L'"')result.append(slashes*2+1,L'\\');else result.append(slashes,L'\\');
        slashes=0;result+=c;}
    result.append(slashes*2,L'\\');result+=L'"';return result;
}
#endif
}
TemporaryC4dScene::~TemporaryC4dScene(){if(!path.empty()){std::error_code ec;fs::remove(path,ec);fs::remove(path.parent_path(),ec);}}
bool HasC4dBridge(){auto path=BridgePath();std::error_code ec;return !path.empty()&&fs::is_regular_file(path,ec);}
void ConvertC4dScene(const std::string& input,TemporaryC4dScene& result) {
#ifdef _WIN32
    const auto helper=BridgePath();std::error_code ec;
    if(!fs::is_regular_file(helper,ec))throw std::runtime_error("C4D import requires NewPageMergeMDL-C4D.exe beside this compiler (Windows Cineware bridge)");
    const auto directory=fs::temp_directory_path()/fs::path("newpage-c4d-"+std::to_string(GetCurrentProcessId())+"-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    if(!fs::create_directory(directory))throw std::runtime_error("cannot create exclusive C4D conversion directory");
    result.path=directory/"scene.glb";
    const auto source=fs::absolute(pulse::FilePath(input));
    auto command=Quote(helper.wstring())+L" "+Quote(source.wstring())+L" "+Quote(result.path.wstring());
    STARTUPINFOW startup{};startup.cb=sizeof(startup);startup.dwFlags=STARTF_USESTDHANDLES;
    startup.hStdInput=GetStdHandle(STD_INPUT_HANDLE);startup.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);startup.hStdError=GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process{};
    if(!CreateProcessW(helper.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&process))
        throw std::runtime_error("cannot launch C4D converter (Windows error "+std::to_string(GetLastError())+")");
    CloseHandle(process.hThread);WaitForSingleObject(process.hProcess,INFINITE);DWORD code=1;
    GetExitCodeProcess(process.hProcess,&code);CloseHandle(process.hProcess);
    if(code!=0||!fs::is_regular_file(result.path))throw std::runtime_error("C4D conversion failed (exit "+std::to_string(code)+"); see the Cineware diagnostic above");
#else
    (void)input;(void)result;
    throw std::runtime_error("C4D import uses the Windows Cineware bridge; convert to GLB on Windows before compiling on this platform");
#endif
}
}
