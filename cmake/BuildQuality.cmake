if(NEWPAGE_REPRODUCIBLE)
    if(MSVC)
        add_compile_options(/experimental:deterministic "/pathmap:${CMAKE_SOURCE_DIR}=src" "/pathmap:${CMAKE_BINARY_DIR}=build" /Brepro)
        add_link_options(/Brepro /INCREMENTAL:NO)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        add_compile_options("-ffile-prefix-map=${CMAKE_SOURCE_DIR}=src"
                            "-fdebug-prefix-map=${CMAKE_BINARY_DIR}=build")
        # LTO compiles code again during linking. Its generated DWARF compilation
        # unit must receive the same maps or its working directory changes the
        # debug file, ELF build ID and debuglink CRC in every runtime binary.
        add_link_options("-ffile-prefix-map=${CMAKE_SOURCE_DIR}=src"
                         "-fdebug-prefix-map=${CMAKE_BINARY_DIR}=build")
        if(UNIX AND NOT APPLE)
            add_link_options(-Wl,--build-id=sha1)
        endif()
    endif()
endif()

if(NEWPAGE_SANITIZERS)
    if(MSVC)
        if(NOT NEWPAGE_SANITIZERS STREQUAL "address")
            message(FATAL_ERROR "MSVC supports NEWPAGE_SANITIZERS=address; use Linux Clang for undefined")
        endif()
        add_compile_options(/fsanitize=address /Zi)
        add_link_options(/INCREMENTAL:NO /DEBUG)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        if(NOT NEWPAGE_SANITIZERS MATCHES "^(address|undefined|address,undefined)$")
            message(FATAL_ERROR "Unsupported sanitizer selection")
        endif()
        add_compile_options("-fsanitize=${NEWPAGE_SANITIZERS}" -fno-omit-frame-pointer -fno-sanitize-recover=all -g)
        add_link_options("-fsanitize=${NEWPAGE_SANITIZERS}" -fno-sanitize-recover=all)
    else()
        message(FATAL_ERROR "Sanitizers require MSVC, GCC or Clang")
    endif()
    if(CMAKE_INTERPROCEDURAL_OPTIMIZATION)
        message(FATAL_ERROR "Use CMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF for sanitizer validation")
    endif()
endif()

if(NEWPAGE_SEPARATE_SYMBOLS)
    if(MSVC)
        # Embed CodeView in objects, including vendored object libraries. /Zi
        # leaves compile-PDB paths that can be lost when Draco aggregates its
        # object libraries, producing incomplete final symbols (LNK4099).
        add_compile_options("$<$<CONFIG:Release,MinSizeRel>:/Z7>")
        add_link_options("$<$<CONFIG:Release,MinSizeRel>:/DEBUG:FULL>" /INCREMENTAL:NO)
    else()
        add_compile_options("$<$<CONFIG:Release,MinSizeRel>:-g1>")
        if(NOT CMAKE_OBJCOPY OR NOT CMAKE_STRIP)
            message(FATAL_ERROR "Separate symbols require objcopy and strip")
        endif()
    endif()
endif()

function(newpage_separate_symbols target)
    if(MSVC AND NEWPAGE_REPRODUCIBLE)
        # A literal %_PDB% is escaped repeatedly by the Visual Studio generator.
        # Resolve the target's filename in CMake instead of invoking LINK macros.
        target_link_options(${target} PRIVATE "/PDBALTPATH:$<TARGET_PDB_FILE_NAME:${target}>")
    endif()
    if(NEWPAGE_SEPARATE_SYMBOLS AND NOT MSVC)
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND "${CMAKE_OBJCOPY}" --only-keep-debug "$<TARGET_FILE:${target}>" "$<TARGET_FILE:${target}>.debug"
            COMMAND "${CMAKE_STRIP}" --strip-unneeded "$<TARGET_FILE:${target}>"
            COMMAND "${CMAKE_OBJCOPY}" "--add-gnu-debuglink=$<TARGET_FILE:${target}>.debug" "$<TARGET_FILE:${target}>"
            VERBATIM)
    endif()
endfunction()
