cmake_minimum_required(VERSION 3.22)
# Distributed tools share the NewPageMergeMDL project version.
# Upstream TOOL_VERSION declarations remain as merge context only.
# C is enabled only for vendored dependencies; toolkit code is C++.
project(NewPageMergeMDL VERSION 1.2.34 LANGUAGES CXX C)

# Keep all Windows tools portable, including helpers without Assimp's runtime
# link settings. MSVC distribution builds select MultiThreaded in their preset.
if(MINGW)
    add_link_options(-static)
endif()

# Keep every importer, but omit unused code and development symbols from release
# executables. Debug/RelWithDebInfo and compilation optimization levels stay intact.
option(NEWPAGE_COMPACT_RELEASE "Remove unused code and symbols from release tools" ON)
if(NEWPAGE_COMPACT_RELEASE)
    if(MSVC)
        add_compile_options("$<$<CONFIG:Release,MinSizeRel>:/Gy>"
                            "$<$<CONFIG:Release,MinSizeRel>:/Gw>")
        add_link_options("$<$<CONFIG:Release,MinSizeRel>:/OPT:REF>")
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang" AND (WIN32 OR UNIX AND NOT APPLE))
        add_compile_options("$<$<AND:$<COMPILE_LANGUAGE:C,CXX>,$<CONFIG:Release,MinSizeRel>>:-ffunction-sections>"
                            "$<$<AND:$<COMPILE_LANGUAGE:C,CXX>,$<CONFIG:Release,MinSizeRel>>:-fdata-sections>")
        add_link_options("$<$<CONFIG:Release,MinSizeRel>:-Wl,--gc-sections>"
                         "$<$<CONFIG:Release,MinSizeRel>:-s>")
    endif()
endif()

# Distribution builds use MinSizeRel with LTO (the x64-compact preset).
# Ordinary Release remains available for development without LTO's link cost.

# C++17: inline constexpr + nested namespaces (used by libs/pulselimits.h).
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Single portable executable; no external package manager (vcpkg/conan).
# Linux build is a near-completion goal - avoid Windows-only imports in code.
if(CMAKE_SYSTEM_NAME STREQUAL "Windows")
    if(CMAKE_SIZEOF_VOID_P EQUAL 8)
        set(PLATFORM_DEFINES COMPILER_MSVC64 COMPILER_MSVC _AMD64_)
    else()
        message(FATAL_ERROR "NewPageMergeMDL targets 64-bit only.")
    endif()
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(PLATFORM_DEFINES LINUX COMPILER_GCC POSIX _AMD64_)
endif()

add_compile_definitions(${PLATFORM_DEFINES} _CRT_SECURE_NO_WARNINGS)

# Both tools ship side by side in one PulseModel/ folder. Guarded so a -D on
# the command line (the CI workflows) still wins.
if(NOT DEFINED CMAKE_RUNTIME_OUTPUT_DIRECTORY)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/NewPageMergeMDL")
endif()

# Layout (kept shallow):
#   libs/           - C++ libraries (pulselimits.h lives here), vendored OSS
#   mdlcompiler/    - the app: .pulseqc loader, compile stage, writers, main()
#   mdldecompiler/  - the reverse tool: .mdl -> .pulseqc
#   subtools/       - standalone helpers
add_subdirectory(libs)
add_subdirectory(subtools)
add_subdirectory(mdlcompiler)
add_subdirectory(mdldecompiler)
