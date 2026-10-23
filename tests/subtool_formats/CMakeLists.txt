cmake_minimum_required(VERSION 3.22)
project(NewPageSubtoolFormatTests LANGUAGES CXX C)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_executable(ag2_vpk_test ../ag2_vpk_test.cpp)
add_executable(ag2_view_pose_test ../ag2_view_pose_test.cpp
    ../../subtools/ag2proportions/rig.cpp
    ../../libs/math/math.cpp ../../libs/dmx/dmx.cpp
    ../../libs/dmx/dmx_keyvalues2.cpp ../../libs/dmx/dmx_binary.cpp
    ../../libs/keyvalues3/kv3.cpp ../../libs/keyvalues3/kv3_binary.cpp
    ../../libs/zstd/common/debug.c ../../libs/zstd/common/entropy_common.c
    ../../libs/zstd/common/error_private.c ../../libs/zstd/common/fse_decompress.c
    ../../libs/zstd/common/zstd_common.c ../../libs/zstd/common/xxhash.c
    ../../libs/zstd/decompress/huf_decompress.c ../../libs/zstd/decompress/zstd_ddict.c
    ../../libs/zstd/decompress/zstd_decompress.c ../../libs/zstd/decompress/zstd_decompress_block.c)
target_include_directories(ag2_view_pose_test PRIVATE ../../libs)
target_compile_definitions(ag2_view_pose_test PRIVATE ZSTD_LEGACY_SUPPORT=0 ZSTD_DISABLE_ASM=1)
enable_testing()
add_test(NAME ag2_vpk_crc COMMAND ag2_vpk_test)
add_test(NAME ag2_view_pose COMMAND ag2_view_pose_test)
