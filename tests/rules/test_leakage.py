"""Leakage checks against YOUR derived data. Run after every rebuild:  pytest -q

Skips when there is no local config (e.g. on GitHub). Failure messages list
the leaked tokens, which are names: read them locally, do not paste them.
If a token is a genuine collision (a surname that is also a country), add it
to key/leakage_allowlist.txt rather than weakening this test.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from stable_sponsors.pseudonymize.idmap import REPO_ROOT, load_config, out_path  # noqa: E402
from stable_sponsors.pseudonymize.leakcheck import find_leaks  # noqa: E402

CONFIG = Path(os.environ.get("PSEUDO_CONFIG", ROOT / "config/pseudonymize.yaml"))


@pytest.fixture(scope="module")
def cfg():
    if not CONFIG.exists():
        pytest.skip("no local config")
    c = load_config(CONFIG)
    if not out_path(c, "derived/teachers.csv").exists():
        pytest.skip("derived/ not built yet")
    return c


@pytest.fixture(scope="module")
def leaks(cfg):
    return find_leaks(cfg)


def test_no_email_addresses(leaks):
    assert not leaks["emails"], (
        f"{len(leaks['emails'])} email-shaped strings in derived/"
    )


def test_no_email_domain(leaks):
    assert not leaks["domains"]


def test_no_name_tokens(leaks):
    assert not leaks["tokens"], (
        f"{len(leaks['tokens'])} name tokens in derived/: {leaks['tokens'][:10]}"
    )


def test_no_free_text_in_derived(leaks):
    assert not leaks["stray_text_files"]


def test_teacher_ids_are_opaque(cfg):
    for name in ("teachers", "preferences"):
        df = pd.read_csv(out_path(cfg, f"derived/{name}.csv"), dtype=str)
        assert df["teacher_id"].str.fullmatch(r"T\d{3}").all()


def test_private_tree_is_outside_repo(cfg):
    for p in (cfg["_private_root"], cfg["_raw_root"]):
        assert p != REPO_ROOT and REPO_ROOT not in p.parents
