# mdlcompiler - the single portable executable.

add_executable(mdlcompiler main.cpp dmxloader.cpp dmxrig.cpp smdloader.cpp
               fbxloader.cpp sceneloader.cpp gltfscene.cpp c4dbridge.cpp resources.cpp meshedit.cpp compile.cpp facemarkup.cpp
               flexreg.cpp qcloader.cpp writemdl.cpp outputfiles.cpp writevtx.cpp writephy.cpp
               surfaceproperties.cpp cloth.cpp clothadvanced.cpp clothprojection.cpp subd.cpp dmxeval.cpp)
# Each tool owns its own version; there is no project-wide one.
set(TOOL_VERSION 0.36.1)
string(REPLACE "." "," TOOL_VERSION_COMMA "${TOOL_VERSION}")
target_compile_definitions(mdlcompiler PRIVATE PULSEMODEL_VERSION="${PROJECT_VERSION}")

# Explorer's Details tab (file description, product name/version, copyright).
if(WIN32)
    target_link_libraries(mdlcompiler PRIVATE user32 advapi32 psapi)
    set(MDL_UTF8_MANIFEST_RESOURCE "")
    if(MINGW)
        # MinGW ignores .manifest target sources; embed it through windres.
        set(MDL_UTF8_MANIFEST_RESOURCE "1 24 \"${CMAKE_SOURCE_DIR}/utf8.manifest\"")
    endif()
    configure_file(version.rc.in "${CMAKE_CURRENT_BINARY_DIR}/version.rc" @ONLY)
    target_sources(mdlcompiler PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/version.rc")
    if(NOT MINGW)
        target_sources(mdlcompiler PRIVATE "${CMAKE_SOURCE_DIR}/utf8.manifest")
    endif()
endif()
# pulse_vhacd is named directly (not just via pulse_phys) because the compile
# stage calls the decomposition API for PhysicsShapeFromRender.
find_package(Threads REQUIRED)
target_include_directories(mdlcompiler PRIVATE ${CMAKE_BINARY_DIR} ${CMAKE_SOURCE_DIR}/libs/assimp/contrib/draco/src)
target_link_libraries(mdlcompiler PRIVATE pulse_libs pulse_dmx pulse_math pulse_meshopt
                                          pulse_nvtristrip pulse_phys pulse_vhacd pulse_ufbx assimp pulse_cgltf draco::draco Threads::Threads)

set_target_properties(mdlcompiler PROPERTIES OUTPUT_NAME "NewPageMergeMDL")
