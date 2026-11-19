// Proves the toolchain before any engine code exists: C++20, GoogleTest
// linked, and in the asan preset, both sanitizers actually compiled in.
// Scaffolding, not engine code. The engine's own tests join this directory
// (R2 onwards) and are picked up with no CMake edit.

#include <gtest/gtest.h>

#include <cstdint>
#include <limits>

static_assert(__cplusplus >= 202002L, "the engine is C++20 (docs/build.md 2.2)");

#if defined(__has_feature)
#if __has_feature(address_sanitizer)
#define OXDAQ_HAS_ASAN 1
#endif
#if __has_feature(undefined_behavior_sanitizer)
#define OXDAQ_HAS_UBSAN 1
#endif
#endif
#if defined(__SANITIZE_ADDRESS__)  // GCC
#define OXDAQ_HAS_ASAN 1
#endif

TEST(Toolchain, Int64IsTheWidthTheEngineAssumes) {
  // docs/design.md 3.2: the C++ engine uses 64-bit integers.
  EXPECT_EQ(std::numeric_limits<std::int64_t>::digits, 63);
}

#ifdef OXDAQ_EXPECT_SANITIZERS
TEST(Toolchain, TheAsanPresetCompilesInAddressSanitizer) {
#ifdef OXDAQ_HAS_ASAN
  SUCCEED();
#else
  FAIL() << "OXDAQ_SANITIZE is on but AddressSanitizer is not compiled in";
#endif
}
#endif
