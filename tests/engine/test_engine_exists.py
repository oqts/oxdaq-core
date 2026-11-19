"""Step 0 of the ladder: the reference engine imports. design 4.5.

While this fails, the rest of the engine suite skips (``conftest.py``).
"""

import pytest

from tests.engine.driver import EngineMissingError, load


def test_the_reference_engine_exists() -> None:
    try:
        load("py")
    except EngineMissingError as exc:
        message = str(exc)
    else:
        return
    pytest.fail(message, pytrace=False)
