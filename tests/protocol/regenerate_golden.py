"""Rewrite the frozen golden corpus. Spec 15.2.

Run this **only** as a deliberate act, alongside a ``PROTOCOL_VERSION``
bump and a matching change to ``planning/OXDAQ-PLAN.md``::

    uv run python tests/protocol/regenerate_golden.py

If you are running it to make a failing test pass, stop: the failure is
the freeze working.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from oqts.protocol.codec import encode
from tests.protocol.samples import SAMPLES

GOLDEN_DIR = pathlib.Path(__file__).resolve().parents[1] / "golden"


def main() -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    written = set()
    for name, message in sorted(SAMPLES.items()):
        path = GOLDEN_DIR / f"{name}.json"
        # Pretty-printed so a review diff is readable, one field per line.
        path.write_text(
            json.dumps(json.loads(encode(message)), indent=2, sort_keys=False) + "\n"
        )
        written.add(path.name)
    for stale in GOLDEN_DIR.glob("*.json"):
        if stale.name not in written:
            stale.unlink()
            print(f"removed stale {stale.name}")
    print(f"wrote {len(written)} golden frames to {GOLDEN_DIR}")


if __name__ == "__main__":
    main()
