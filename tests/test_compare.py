from dataclasses import replace

import pytest

from stable_sponsors.compare import explain, main, violations
from stable_sponsors.data import ObservedPlacement
from tests.conftest import RULES_PATH, make_private_root


def _placed(*pairs: tuple[str, str]) -> tuple[ObservedPlacement, ...]:
    return tuple(ObservedPlacement(2027, c, i, t) for i, (t, c) in enumerate(pairs))


def test_violations_flags_same_gender_pair(toy_cycle):
    # toy: T1000 and T1002 are both female; INTL-2 is 1M/1F
    v = violations(toy_cycle, _placed(("T1000", "INTL-2"), ("T1002", "INTL-2")))
    assert v["5 slot_gender"] == [("INTL-2", 0, 2)]


def test_violations_accepts_mixed_pair(toy_cycle):
    v = violations(toy_cycle, _placed(("T1001", "INTL-2"), ("T1003", "INTL-2")))
    assert v["5 slot_gender"] == []


def test_violations_does_not_count_unknown_gender(toy_cycle):
    teachers = tuple(
        replace(t, gender=None) if t.teacher_id == "T1002" else t
        for t in toy_cycle.teachers
    )
    cycle = replace(toy_cycle, teachers=teachers)
    v = violations(cycle, _placed(("T1000", "INTL-2"), ("T1002", "INTL-2")))
    assert v["5 slot_gender"] == []


def test_violations_uses_the_course_maximum(toy_cycle):
    courses = tuple(
        replace(c, min_sponsors=3, max_sponsors=3) if c.course_id == "INTL-2" else c
        for c in toy_cycle.courses
    )
    cycle = replace(toy_cycle, courses=courses)
    two_females = _placed(("T1000", "INTL-2"), ("T1002", "INTL-2"), ("T1001", "INTL-2"))
    assert violations(cycle, two_females)["5 slot_gender"] == []


def test_explain_prints_origin_of_unranked_placement(toy_cycle, capsys):
    # toy: T1001 ranked INTL-1 and SING-1, both ran
    placed = _placed(("T1001", "INTL-2"))
    explain(toy_cycle, placed, violations(toy_cycle, placed))
    assert "origin=none_unrun" in capsys.readouterr().out


def test_main_reads_the_rules_and_config_it_is_given(tmp_path, capsys):
    cfg = make_private_root(tmp_path)
    main(["--config", str(cfg), "--rules", str(RULES_PATH)])
    assert "observed teachers matched to cycle: 5 of 5" in capsys.readouterr().out


def test_main_uses_the_given_rule_weights(tmp_path, capsys):
    cfg = make_private_root(tmp_path)
    rules = tmp_path / "broken.yaml"
    rules.write_text("rules: []\n")
    # no rule 1 to take weights from: proves the file was read rather than the default
    with pytest.raises(StopIteration):
        main(["--config", str(cfg), "--rules", str(rules)])
