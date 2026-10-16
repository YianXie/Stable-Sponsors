from pathlib import Path

import pytest

from stable_sponsors.data import load_cycle
from stable_sponsors.rules.context import build_ctx

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TOY_DIR = TESTS_DIR / "fixtures" / "toy_cycle"


@pytest.fixture
def toy_cycle():
    return load_cycle(TOY_DIR)


@pytest.fixture
def toy_ctx(toy_cycle):
    return build_ctx(toy_cycle)
