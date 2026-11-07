import copy

from stable_sponsors.metrics import agreement, allocation_metrics, summarise
from stable_sponsors.model import load_rules
from stable_sponsors.objectives import leximin_population, preference_scores
from tests.builders import course, cycle, lex_cycle, teacher
from tests.conftest import RULES_PATH

RULES = load_rules(RULES_PATH)


def _m(assignment, c=None, rules=RULES):
    c = c or lex_cycle()
    return allocation_metrics(
        c,
        assignment,
        preference_scores(c, rules),
        leximin_population(c),
        rules=rules,
    )


def _equal_round_bonus(rules):
    """rules with intl_r1 = intl_r2 = 10, as in rules-2027-v3.1-round-order.yaml."""
    out = copy.deepcopy(rules)
    rule6 = next(r for r in out if r["id"] == 6)
    rule6["params"]["bonus"].update(intl_r1=10, intl_r2=10)
    return out


def test_metrics_of_the_utilitarian_lex_allocation():
    m = _m({"T1": "X", "T2": "Y"})
    assert (
        m["score"],
        m["placed"],
        m["courses_run"],
        m["worst_score"],
        m["at_worst"],
    ) == (48, 2, 2, 21, 1)
    assert (
        m["rank_hist"] == {"intl_r1:1": 1, "intl_r1:7": 1} and m["round1_placed"] == 2
    )


def test_unplaced_submitter_is_the_worst_off():
    m = _m({"T1": "X", "T2": None})
    assert (m["submitters_unplaced"], m["worst_score"], m["courses_run"]) == (1, 0, 1)
    assert m["rank_hist"]["unplaced"] == 1


def test_unranked_placement_is_counted():
    c = cycle([("T1", "X", 1), ("T2", "X", 2)], [course("X", 1, 1), course("Z", 1, 1)])
    m = _m({"T1": "X", "T2": "Z"}, c)
    assert m["unranked_placements"] == 1 and m["rank_hist"]["unranked"] == 1


def test_incumbent_course_is_not_unranked():
    c = cycle(
        [("T5", "Y", 1)],
        [course("X", 1, 1), course("Y", 1, 1)],
        extra=(teacher("T5", repeater=True, incumbent="X"),),
    )
    assert _m({"T5": "X"}, c)["unranked_placements"] == 0


def test_course_ranked_in_two_rounds_is_labelled_by_its_best_row():
    # intl_r1 rank 5 = 3 + 20 = 23 beats intl_r2 rank 1 = 7 + 10 = 17; sg course counted apart
    c = cycle(
        [("T1", "X", 5, "intl_r1"), ("T1", "X", 1, "intl_r2"), ("T2", "S", 1, "sg")],
        [course("X", 1, 1), course("S", 1, 1, kind="sg")],
    )
    m = _m({"T1": "X", "T2": "S"}, c)
    assert m["rank_hist"] == {"intl_r1:5": 1, "sg:1": 1}
    assert (m["courses_run_intl"], m["courses_run_sg"]) == (1, 1)


def test_equal_round_bonus_labels_by_bonus_plus_weight():
    # intl_r1 rank 5 = 3 + 10 = 13 loses to intl_r2 rank 1 = 7 + 10 = 17
    c = cycle(
        [("T1", "X", 5, "intl_r1"), ("T1", "X", 1, "intl_r2")],
        [course("X", 1, 1)],
    )
    m = _m({"T1": "X"}, c, rules=_equal_round_bonus(RULES))
    assert m["rank_hist"] == {"intl_r2:1": 1}


def test_equal_row_value_goes_to_the_earlier_round():
    # intl_r1 rank 2 = 6 + 10 = 16 ties intl_r2 rank 2 = 16: intl_r1 comes first in ROUNDS
    c = cycle(
        [("T1", "X", 2, "intl_r2"), ("T1", "X", 2, "intl_r1")],
        [course("X", 1, 1)],
    )
    m = _m({"T1": "X"}, c, rules=_equal_round_bonus(RULES))
    assert m["rank_hist"] == {"intl_r1:2": 1}


def test_agreement_counts_both_unplaced_as_same():
    got = agreement({"T1": "X", "T2": "Y", "T3": None}, {"T1": "X", "T2": "X"})
    assert got == {
        "same_placement": 2,
        "courses_both": 1,
        "courses_only_a": 1,
        "courses_only_b": 0,
    }


def test_summarise_fills_missing_labels_with_zero():
    s = summarise(
        [{"score": 10, "rank_hist": {"a": 1}}, {"score": 20, "rank_hist": {}}]
    )
    assert s["score"] == {"mean": 15, "min": 10, "max": 20}
    assert s["rank_hist"]["a"] == {"mean": 0.5, "min": 0, "max": 1}
