cmake_minimum_required(VERSION 3.22)
# Distributed tools share the NewPageMergeMDL project version.
# Upstream TOOL_VERSION declarations remain as merge context only.
# C is enabled only for vendored dependencies; toolkit code is C++.
project(NewPageMergeMDL VERSION 1.2.39 LANGUAGES CXX C)

option(NEWPAGE_REPRODUCIBLE "Normalize source paths and deterministic executable identity" ON)
option(NEWPAGE_SEPARATE_SYMBOLS "Produce matching separate native debug symbols" OFF)
set(NEWPAGE_SANITIZERS "" CACHE STRING "Developer sanitizers: address,undefined (GCC/Clang); address (MSVC)")
include(cmake/BuildQuality.cmake)

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
        add_link_options("$<$<CONFIG:Release,MinSizeRel>:-Wl,--gc-sections>")
        if(NOT NEWPAGE_SEPARATE_SYMBOLS AND NOT NEWPAGE_SANITIZERS)
            add_link_options("$<$<CONFIG:Release,MinSizeRel>:-s>")
        endif()
    endif()
endif()

# Distribution builds use MinSizeRel with LTO (the x64-compact preset).
# Ordinary Release remains available for development without LTO's link cost.
if(CMAKE_INTERPROCEDURAL_OPTIMIZATION)
    # CheckIPOSupported uses project-mode try_compile. Propagate the selected
    # toolchain and its flags instead of probing the host's default compiler.
    cmake_policy(PUSH)
    if(POLICY CMP0137)
        cmake_policy(SET CMP0137 NEW)
    endif()
    if(POLICY CMP0138)
        cmake_policy(SET CMP0138 NEW)
    endif()
    include(CheckIPOSupported)
    # Probe each language separately: some CMake versions can let a successful
    # language check mask a later failed check in the same invocation.
    check_ipo_supported(RESULT NEWPAGE_C_IPO_SUPPORTED OUTPUT NEWPAGE_C_IPO_ERROR
                        LANGUAGES C)
    check_ipo_supported(RESULT NEWPAGE_CXX_IPO_SUPPORTED OUTPUT NEWPAGE_CXX_IPO_ERROR
                        LANGUAGES CXX)
    cmake_policy(POP)
    if(NOT NEWPAGE_C_IPO_SUPPORTED OR NOT NEWPAGE_CXX_IPO_SUPPORTED)
        message(WARNING "IPO is unavailable; building without LTO: ${NEWPAGE_C_IPO_ERROR}${NEWPAGE_CXX_IPO_ERROR}")
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF CACHE BOOL
            "Enable interprocedural optimization when the toolchain supports it" FORCE)
    endif()
endif()
message(STATUS "NewPage IPO enabled: ${CMAKE_INTERPROCEDURAL_OPTIMIZATION}")
# Visual Studio generators do not cache CMAKE_<LANG>_COMPILER themselves.
# Keep the actual compiler identity available to the package manifest writer.
set(NEWPAGE_BUILD_C_COMPILER "${CMAKE_C_COMPILER}" CACHE INTERNAL "Configured C compiler" FORCE)
set(NEWPAGE_BUILD_CXX_COMPILER "${CMAKE_CXX_COMPILER}" CACHE INTERNAL "Configured C++ compiler" FORCE)
set(NEWPAGE_BUILD_CXX_COMPILER_ID "${CMAKE_CXX_COMPILER_ID}" CACHE INTERNAL "Configured C++ compiler family" FORCE)
set(NEWPAGE_BUILD_CXX_COMPILER_VERSION "${CMAKE_CXX_COMPILER_VERSION}" CACHE INTERNAL "Configured C++ compiler version" FORCE)

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
