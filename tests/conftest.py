import shutil
from pathlib import Path

import pytest
import yaml

from stable_sponsors.data import Cycle, load_cycle
from stable_sponsors.rules.context import Ctx, build_ctx

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TOY_DIR = TESTS_DIR / "fixtures" / "toy_cycle"
RULES_PATH = REPO_ROOT / "config" / "rules-2027.yaml"


def make_private_root(tmp_path: Path, lineage: bool = True) -> Path:
    """Lay out the toy cycle as a throwaway private_root, like the real one.

    Args:
        tmp_path (Path): where to put private/ and the config.
        lineage (bool, optional): copy key/course_lineage.csv. Defaults to True.

    Returns:
        Path: the config file pointing at it.
    """

    root = tmp_path / "private"
    for sub, names in {
        "derived": ("teachers", "courses", "preferences", "placements"),
        "params": ("teacher_params", "course_params"),
        "key": ("course_lineage",) if lineage else (),
    }.items():
        (root / sub).mkdir(parents=True)
        for name in names:
            shutil.copy(TOY_DIR / f"{name}.csv", root / sub)
    (root / "raw").mkdir()
    cfg = tmp_path / "pseudonymize.yaml"
    cfg.write_text(yaml.safe_dump({"private_root": str(root), "cycles": {2027: {}}}))
    return cfg


@pytest.fixture(scope="session")
def toy_cycle() -> Cycle:
    """Load the toy cycle once; Cycle is frozen, so tests share it safely.

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
