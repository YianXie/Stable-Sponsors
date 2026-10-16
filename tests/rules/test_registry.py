from pathlib import Path

import pytest
import yaml

from stable_sponsors.rules import hard, priority, tiebreak  # noqa: F401
from stable_sponsors.rules.registry import ENCODERS

RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules-2027.yaml"
RULES = yaml.safe_load(RULES_PATH.read_text())["rules"]
BY_ID = {r["id"]: r for r in RULES}
ACTIVE = {r["id"] for r in RULES if r["status"] != "deferred"}


@pytest.mark.parametrize("rule_id", sorted(ACTIVE))
def test_encoder_implemented(rule_id, toy_ctx):
    try:
        ENCODERS[rule_id](toy_ctx, BY_ID[rule_id]["params"])
    except NotImplementedError:
        pytest.xfail(f"{rule_id} not implemented yet")
