from pathlib import Path

import pytest

from stable_sponsors.data import Cycle, load_cycle
from stable_sponsors.rules.context import Ctx, build_ctx

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TOY_DIR = TESTS_DIR / "fixtures" / "toy_cycle"


@pytest.fixture
def toy_cycle() -> Cycle:
    """Load the toy cycle

    Returns:
        Cycle: The loaded toy cycle.
    """

    return load_cycle(TOY_DIR)


@pytest.fixture
def ctx(toy_cycle: Cycle) -> Ctx:
    """Build a context for the toy cycle.

    Args:
        toy_cycle (Cycle): The toy cycle for which to build the context.

    Returns:
        Ctx: The built context.
    """

    return build_ctx(toy_cycle)
