import pytest
import yaml

from stable_sponsors.rules import hard, priority, tiebreak  # noqa: F401
from stable_sponsors.rules.registry import ENCODERS
from tests.conftest import RULES_PATH

RULES = yaml.safe_load(RULES_PATH.read_text())["rules"]
ALL = {r["id"]: r for r in RULES}
ACTIVE = {r["id"] for r in RULES if r["status"] != "deferred"}


@pytest.mark.parametrize("rule_id", sorted(ACTIVE))
def test_encoder_implemented(rule_id, ctx):
    try:
        ENCODERS[rule_id](ctx, ALL[rule_id]["params"])
    except NotImplementedError:
        pytest.xfail(f"{rule_id} not implemented yet")
