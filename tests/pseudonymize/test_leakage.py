"""Leakage checks against YOUR derived data. Run after every rebuild:  pytest -q

Checks derived/<cycle>/ for every configured cycle that has been built. Skips
when there is no local config (e.g. on GitHub). Failure messages list the
leaked tokens, which are names: read them locally, do not paste them.
If a token is a genuine collision (a surname that is also a country), add it
to key/<cycle>/leakage_allowlist.txt rather than weakening this test.
"""

import os
from pathlib import Path

import pandas as pd
import pytest

from stable_sponsors.pseudonymize.idmap import (
    DEFAULT_CONFIG,
    REPO_ROOT,
    for_cycle,
    load_config,
    out_path,
)
from stable_sponsors.pseudonymize.leakcheck import find_leaks

CONFIG = Path(os.environ.get("PSEUDO_CONFIG", REPO_ROOT / DEFAULT_CONFIG))


@pytest.fixture(scope="module")
def cfg():
    if not CONFIG.exists():
        pytest.skip("no local config")
    return load_config(CONFIG)


@pytest.fixture(scope="module")
def built(cfg):
    """One scoped config per cycle whose derived/<cycle>/ exists."""
    out = [for_cycle(cfg, c) for c in sorted(cfg["cycles"])]
    out = [c for c in out if out_path(c, "derived/teachers.csv").exists()]
    if not out:
        pytest.skip("no cycle's derived/ is built yet")
    return out


@pytest.fixture(scope="module")
def leaks(built):
    return {c["_cycle"]: find_leaks(c) for c in built}


def test_no_email_addresses(leaks):
    found = {k: len(v["emails"]) for k, v in leaks.items() if v["emails"]}
    assert not found, f"email-shaped strings in derived/<cycle>/: {found}"


def test_no_email_domain(leaks):
    assert not any(v["domains"] for v in leaks.values())


def test_no_name_tokens(leaks):
    found = {k: v["tokens"][:10] for k, v in leaks.items() if v["tokens"]}
    assert not found, f"name tokens in derived/<cycle>/: {found}"


def test_no_free_text_in_derived(leaks):
    assert not any(v["stray_text_files"] for v in leaks.values())


def test_teacher_ids_are_opaque(built):
    for c in built:
        for name in ("teachers", "preferences"):
            df = pd.read_csv(out_path(c, f"derived/{name}.csv"), dtype=str)
            assert df["teacher_id"].str.fullmatch(r"T\d{3}").all()


def test_private_tree_is_outside_repo(cfg):
    for p in (cfg["_private_root"], cfg["_raw_root"]):
        assert p != REPO_ROOT and REPO_ROOT not in p.parents
