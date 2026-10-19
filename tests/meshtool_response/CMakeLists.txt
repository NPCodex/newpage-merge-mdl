cmake_minimum_required(VERSION 3.20)
project(MeshToolResponseTests LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(meshtool_response_test
    ../meshtool_response_test.cpp
    ../../subtools/meshtool/response_writer.cpp
)
target_compile_definitions(meshtool_response_test PRIVATE PULSE_MESHTOOL_RESPONSE_TESTING)
if(MSVC)
  target_compile_options(meshtool_response_test PRIVATE /utf-8)
endif()
enable_testing()
add_test(NAME meshtool_response
    COMMAND meshtool_response_test "${CMAKE_CURRENT_BINARY_DIR}/response-test-work")
