# OXDAQ specification

Spec 3.0, 2026-11-19. The authoritative design of OXDAQ. Code that
disagrees with these documents is wrong, or the documents change in the
same pull request.

Read in this order:

1. [`design.md`](design.md): what the exchange is and how it works. The
   order loop and why validation lives in the gateway, integer prices,
   the matching engine and its two implementations (Python and C++),
   accounting, the price process, bots, and the invariants that must
   never break. Start here.
2. [`protocol.md`](protocol.md): the wire protocol, message by message,
   including the admin protocol and the things that surprise people. The
   reference for anyone writing a client.
3. [`client.md`](client.md): `oqts-client`, the synchronous `Exchange`
   object participants write strategies with, and how it works inside.
4. [`operations.md`](operations.md): scoring, the trade tape, tokens,
   dashboards, the practice exchange, and the checklist before a live
   round.
5. [`build.md`](build.md): repositories, the Python and C++ toolchains,
   who writes what, the build order and what waits for Phase 2.
6. [`decisions.md`](decisions.md): every design decision so far, with
   the problem it solved. History lives here and nowhere else.

References between documents use `file section`, for example
`design 2.4`.
