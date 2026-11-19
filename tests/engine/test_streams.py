"""Random streams of submits and cancels. design 4.5, the equivalence gate.

- ``test_every_step_keeps_the_spec``: per engine, every step of a random
  stream checked against design 4.1 to 4.5 (``streams.check_step``).
- ``test_the_engines_agree_exactly``: the differential test. Every
  available engine runs the same stream; fills, cancel results and books
  must be exactly equal after every op. It needs two engines, so it skips
  until the C++ engine arrives in R8.

Hypothesis shrinks a failure to a short stream itself. The final failing
stream is also written to ``.oxdaq/failures/`` as JSON lines, to replay
or shrink further with::

    uv run python -m tests.engine.replay .oxdaq/failures/<file>.jsonl

More examples: ``HYPOTHESIS_PROFILE=deep uv run pytest tests/engine``.
"""

import hashlib
import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, note, settings
from hypothesis import strategies as st
from hypothesis.control import current_build_context

from tests.engine import streams
from tests.engine.conftest import driver_or_stop, selected_engines
from tests.engine.driver import ENGINES, EngineMissingError, load
from tests.engine.streams import Cancel, StreamError, Submit

settings.register_profile(
    "default",
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.register_profile(
    "deep", parent=settings.get_profile("default"), max_examples=5000
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

FAILURES = Path(__file__).resolve().parents[2] / ".oxdaq" / "failures"

# A narrow price band and few instruments, so most orders cross something.
_submit = st.tuples(
    st.integers(1, 4),  # team
    st.integers(0, 2),  # instrument
    st.sampled_from(["bid", "ask"]),
    st.sampled_from(["limit", "limit", "limit", "ioc"]),
    st.integers(95, 105),  # price, ticks
    st.integers(1, 10),  # volume
)
_cancel = st.integers(1, 80).map(lambda target: ("cancel", target))


@st.composite
def op_streams(draw, max_ops: int = 80) -> list[streams.Op]:
    """Submits get ids 1, 2, ... in order; a cancel names any id up to 80,
    so some hit resting orders and some hit filled, cancelled or unknown ones."""
    raw = draw(
        st.lists(st.one_of(_submit, _submit, _cancel), min_size=1, max_size=max_ops)
    )
    ops: list[streams.Op] = []
    next_id = 1
    for item in raw:
        if item[0] == "cancel":
            ops.append(Cancel(item[1]))
        else:
            team, instrument, side, kind, price, volume = item
            ops.append(Submit(next_id, team, instrument, side, kind, price, volume))
            next_id += 1
    return ops


def _run_or_record(ops: list[streams.Op], engines: list[str]) -> None:
    __tracebackhide__ = True
    try:
        streams.run(ops, engines)
    except StreamError:
        if getattr(current_build_context(), "is_final", False):
            text = "".join(streams.to_json(op) + "\n" for op in ops)
            digest = hashlib.sha1(text.encode()).hexdigest()[:10]
            path = FAILURES / f"{'-'.join(engines)}-{digest}.jsonl"
            streams.dump(ops, path)
            note(f"stream saved: uv run python -m tests.engine.replay {path}")
        raise


@given(ops=op_streams())
def test_every_step_keeps_the_spec(engine_name: str, ops: list[streams.Op]) -> None:
    driver_or_stop(engine_name)  # one clear line if the engine does not exist
    _run_or_record(ops, [engine_name])


def _available(config: pytest.Config) -> list[str]:
    found = []
    for name in selected_engines(config):
        try:
            load(name)
            found.append(name)
        except EngineMissingError:
            if name == "py":
                driver_or_stop(name)
    return found


@given(ops=op_streams())
def test_the_engines_agree_exactly(request: pytest.FixtureRequest, ops) -> None:
    engines = _available(request.config)
    if len(engines) < 2:
        pytest.skip(
            f"the differential test needs two engines; have {engines or 'none'} "
            f"of {sorted(ENGINES)} (the C++ engine arrives in R8)"
        )
    _run_or_record(ops, engines)
