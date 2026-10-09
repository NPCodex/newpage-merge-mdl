# This GPL executable is isolated from all compiler/Assimp targets. The only
# common dependency is permissively licensed pugixml, compiled separately here.
cmake_minimum_required(VERSION 3.16)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(NewPageVRMLtoX3D LANGUAGES CXX)
endif()
get_filename_component(VRML_REPOSITORY_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
add_executable(NewPageVRMLtoX3D main.cpp meshlab/Parser.cpp meshlab/Scanner.cpp
    ${VRML_REPOSITORY_ROOT}/libs/assimp/contrib/pugixml/src/pugixml.cpp)
target_include_directories(NewPageVRMLtoX3D PRIVATE meshlab ${VRML_REPOSITORY_ROOT}/libs/assimp)
target_compile_features(NewPageVRMLtoX3D PRIVATE cxx_std_17)
if(MINGW)
    target_link_options(NewPageVRMLtoX3D PRIVATE -static -municode)
endif()
