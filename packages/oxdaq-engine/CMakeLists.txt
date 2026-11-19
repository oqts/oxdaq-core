# The OXDAQ C++ engine. docs/build.md 2.2, design.md 4.5.
#
# cpp/ is Alec's: the engine, headers in cpp/include/oxdaq/, sources in
# cpp/src/. Everything else here is scaffolding. A new file under cpp/src/
# or tests/cpp/ is picked up at the next build, with no edit to this file.
#
#   cmake --workflow --preset dev      configure, build, test (also: asan, release)

cmake_minimum_required(VERSION 3.25)
project(oxdaq_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG") # build 2.2: -O2, never -march=native

option(OXDAQ_SANITIZE "Build everything with ASan and UBSan" OFF)
option(OXDAQ_TESTS "Build the GoogleTest suite" ON)

# Sanitizers apply to every target, GoogleTest included, so instrumented
# and uninstrumented code never share a container.
if(OXDAQ_SANITIZE)
  add_compile_options(-fsanitize=address,undefined -fno-sanitize-recover=all
                      -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()

# Warnings as errors, for our targets only: never for fetched dependencies.
add_library(oxdaq_warnings INTERFACE)
target_compile_options(oxdaq_warnings INTERFACE
  -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror)

# --- the engine library ------------------------------------------------------
# A static library once cpp/src/ has a source file; until then (or while the
# engine is header-only) an interface target carrying the include path.
file(GLOB_RECURSE OXDAQ_ENGINE_SOURCES CONFIGURE_DEPENDS cpp/src/*.cpp)
if(OXDAQ_ENGINE_SOURCES)
  add_library(oxdaq_engine_core STATIC ${OXDAQ_ENGINE_SOURCES})
  target_include_directories(oxdaq_engine_core PUBLIC cpp/include)
  target_link_libraries(oxdaq_engine_core PRIVATE oxdaq_warnings)
  set_target_properties(oxdaq_engine_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
else()
  add_library(oxdaq_engine_core INTERFACE)
  target_include_directories(oxdaq_engine_core INTERFACE cpp/include)
endif()
add_library(oxdaq::engine ALIAS oxdaq_engine_core)

# --- the Python module (R8, E1) ---------------------------------------------
# scikit-build-core sets SKBUILD when uv builds this package. The nanobind
# module oxdaq_engine is added here in R8; until then the wheel is empty and
# the shared Python suite skips the cpp engine.

# --- tests ---------------------------------------------------------------------
if(OXDAQ_TESTS)
  enable_testing()
  include(FetchContent)
  FetchContent_Declare(googletest
    URL https://github.com/google/googletest/releases/download/v1.17.0/googletest-1.17.0.tar.gz
    URL_HASH SHA256=65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c
    SYSTEM)
  set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  file(GLOB_RECURSE OXDAQ_ENGINE_TESTS CONFIGURE_DEPENDS tests/cpp/*.cpp)
  add_executable(oxdaq_engine_tests ${OXDAQ_ENGINE_TESTS})
  target_link_libraries(oxdaq_engine_tests PRIVATE
    oxdaq::engine oxdaq_warnings GTest::gtest_main)
  if(OXDAQ_SANITIZE)
    target_compile_definitions(oxdaq_engine_tests PRIVATE OXDAQ_EXPECT_SANITIZERS=1)
  endif()

  include(GoogleTest)
  gtest_discover_tests(oxdaq_engine_tests DISCOVERY_MODE PRE_TEST)
endif()
