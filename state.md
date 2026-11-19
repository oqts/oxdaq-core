# oxdaq-core: where it stands

**As of:** 2026-11-19 · **State:** live, in build (Phase 1)

## Now
- Milestone 1 is done at protocol v2 (2026-11-19): `order_type`, `trade_tick`, `rate_limited`, no admin seed; golden corpus regenerated.
- Ready for R1: the shared engine suite (`tests/engine`, 52 tests on the Python engine), the Hypothesis stream checks and differential test, and the replay and shrink tool. Checked against a throwaway engine and seven broken variants, then deleted. `uv run pytest tests/engine -q` shows where the engine stands.
- Ready for R2: `packages/oxdaq-engine` scaffold (CMake presets dev, asan, release; GoogleTest; clang-format, clang-tidy; scikit-build-core in the workspace; CI matrix). Green locally on Apple clang; the GitHub matrix has not yet run.

## Decided
- 2026-11-19: only the matching engine moves to C++, in process via nanobind; the Python reference engine stays as oracle and fallback (D19 to D24).
- 2026-11-19: integer arrival sequence and integer engine ids (D25, D26); synchronous `Exchange` client and protocol v2 (D27 to D32).
- 2026-11-19: engine interface pinned in design 4.5 (D34); snapshots list resting orders (D35); bad engine input raises `ValueError` (D36).
- Engine (Python and C++, bindings included), accounting, price maths and all async are Alec's to write by hand.

## Next
- Alec: R1 build sessions from 28 Nov (`CLAUDE.md`, "A build session"). Milestone 2 is done when `tests/engine` passes on `py`; then drop `continue-on-error` on the CI engine step.
- Alec: install the C++ toolchain before 4 Dec (README, Development).
- Claude, before R2's build (11 Dec): GoogleTest for Ticks, Volume, Side and reject codes, once their signatures are agreed.
- Claude, before R4: the M3 accounting suite.

## Open
- Dashboard stack, before milestone 9 (`docs/build.md` 2.3).
- Bot runner contract with `oxdaq-ops`, before milestone 7.
- Practice exchange parameters, before milestone 11.
- An unmerged `alec/milestone-1-protocol` branch on compute-node, probably superseded.
