# oxdaq-core: where it stands

**As of:** 2026-11-19 · **State:** live, in build (Phase 1)

## Now
- Milestone 1, the wire protocol, is done and frozen at protocol v1 (2026-08-28). Protocol v2 is specified, not implemented.
- The spec moved here from `planning/` and was rewritten as spec 3.0 in `docs/` (2026-11-19). No engine code yet.

## Decided
- 2026-11-19: only the matching engine moves to C++ (C++20, in process via nanobind, `packages/oxdaq-engine`); the Python reference engine stays as oracle and fallback, behind an equivalence gate (D19 to D24).
- 2026-11-19: integer arrival sequence for time priority; integer engine ids mapped by the session manager (D25, D26).
- 2026-11-19: participants use a synchronous Optibook-style `Exchange` over `oqts.aio`; protocol v2 adds IOC, cancel on disconnect, a rate limit and `trade_tick` (D27 to D31).
- Engine (Python and C++, bindings included), accounting, price maths and all async are Alec's to write by hand.

## Next
- Claude: protocol v2 in the schema, codec and golden corpus.
- Claude: shared `OrderBook` correctness suite and the differential harness.
- Alec: milestone 2, the Python reference engine. Then Claude scaffolds `packages/oxdaq-engine`.

## Open
- Dashboard stack, before milestone 9 (`docs/build.md` 2.3).
- Bot runner contract with `oxdaq-ops`, before milestone 7.
- Practice exchange parameters, before milestone 11.
- An unmerged `alec/milestone-1-protocol` branch on compute-node, probably superseded.
