"""The shared engine suite runs once per engine. design 4.5.

``engine`` is a fresh :class:`Driver` per test, parametrised over every
engine: ``py`` (the reference, ``oxdaq.engine``) and ``cpp``
(``oxdaq_engine``, from R8). Choose with ``--engine py`` or
``--engine cpp``; the default is both.

Until the reference engine exists, ``test_engine_exists.py`` fails with
one line saying what to write and everything else here skips. Until the
C++ engine exists (R8), its runs skip with the reason. Never an import
traceback.
"""

from pathlib import Path

import pytest

from tests.engine.driver import ENGINES, Driver, EngineMissingError, load

HERE = Path(__file__).parent


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--engine",
        action="append",
        choices=sorted(ENGINES),
        help="engine to run the shared suite against (repeatable; default all)",
    )


def selected_engines(config: pytest.Config) -> list[str]:
    return config.getoption("--engine") or list(ENGINES)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "engine_name" in metafunc.fixturenames:
        metafunc.parametrize("engine_name", selected_engines(metafunc.config))


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """With no reference engine, one test fails saying what to write
    (``test_the_reference_engine_exists``) and the rest of the suite skips,
    instead of fifty copies of the same message."""
    try:
        load("py")
    except EngineMissingError:
        skip = pytest.mark.skip(reason="no engine yet: see test_engine_exists.py")
        for item in items:
            if item.path.parent == HERE and item.path.name != "test_engine_exists.py":
                item.add_marker(skip)


def driver_or_stop(name: str) -> Driver:
    """A fresh engine, or a one-line failure (py) or skip (cpp) if absent."""
    try:
        return Driver(name)
    except EngineMissingError as exc:
        message = str(exc)
    if name == "cpp":
        pytest.skip(message)
    pytest.fail(message, pytrace=False)


@pytest.fixture
def engine(engine_name: str) -> Driver:
    return driver_or_stop(engine_name)
