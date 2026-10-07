// NewPageMergeMDL console branding. Keep captured logs free of terminal codes.
#pragma once
#include <cstdio>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <io.h>
#else
#include <unistd.h>
#endif

namespace newpage {
inline void PrintBanner(const char* role, const char* version, const char* format) {
#ifdef _WIN32
    HANDLE console = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO saved{};
    const bool color = _isatty(_fileno(stdout)) && GetConsoleScreenBufferInfo(console, &saved);
    if (color) SetConsoleTextAttribute(console, FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY);
#else
    const bool color = isatty(fileno(stdout));
    if (color) std::printf("\033[1;36m");
#endif
    std::printf(R"(
   .____________________________________________________________.
   |   /\    /\      N E W  P A G E                              |
   |  /  \__/  \     M E R G E  M D L                            |
   |  \  /  \  /     [ SOURCE MODEL FORGE ]                      |
   |   \/____\/      Compile ideas. Turn the page.               |
   '------------------------------------------------------------'
)");
#ifdef _WIN32
    if (color) SetConsoleTextAttribute(console, saved.wAttributes);
#else
    if (color) std::printf("\033[0m");
#endif
    std::printf("   NewPageMergeMDL | %s | v%s | MDL %s\n", role, version, format);
    std::printf("   Based on PulseModel | Community compatibility extensions\n\n");
    std::fflush(stdout);
}
} // namespace newpage
