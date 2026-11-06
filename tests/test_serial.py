import pytest
from ortools.sat.python import cp_model

from stable_sponsors import serial
from stable_sponsors.model import load_rules
from stable_sponsors.serial import random_orders, serial_dictatorship, submitters
from tests.builders import course, cycle, lex_cycle, teacher
from tests.conftest import RULES_PATH

RULES = load_rules(RULES_PATH)


def test_order_decides_the_contested_course():
    assert serial_dictatorship(lex_cycle(), RULES, ["T1", "T2"]) == {
        "T1": "X",
        "T2": "Y",
    }
    assert serial_dictatorship(lex_cycle(), RULES, ["T2", "T1"]) == {
        "T1": "Y",
        "T2": "X",
    }


def _short_cycle(extra=()):  # A needs 2 sponsors and only T1 ranks it; B seats 1
    return cycle(
        [("T1", "A", 1), ("T1", "B", 2), ("T2", "B", 1)],
        [course("A", 2, 2), course("B", 1, 1)],
        extra=extra,
    )


def test_skips_a_choice_that_cannot_be_completed():
    assert serial_dictatorship(_short_cycle(), RULES, ["T1", "T2"]) == {
        "T1": "B",
        "T2": None,
    }


def test_non_submitter_fills_a_seat():
    got = serial_dictatorship(_short_cycle((teacher("T9"),)), RULES, ["T1", "T2"])
    assert got == {"T1": "A", "T2": "B", "T9": "A"}


def test_order_must_be_the_submitters():
    with pytest.raises(ValueError, match="permutation"):
        serial_dictatorship(lex_cycle(), RULES, ["T1"])


def test_timeout_is_not_infeasible(monkeypatch):
    monkeypatch.setattr(
        serial, "_solve", lambda m, t: (cp_model.CpSolver(), cp_model.UNKNOWN)
    )
    with pytest.raises(RuntimeError, match="timed out"):
        serial_dictatorship(lex_cycle(), RULES, ["T1", "T2"])


def test_random_orders_are_reproducible_permutations():
    a = random_orders(["T3", "T1", "T2"], 5, seed=0)
    assert a == random_orders(["T1", "T2", "T3"], 5, seed=0)
    assert len(a) == 5 and all(sorted(o) == ["T1", "T2", "T3"] for o in a)


def test_toy_repeaters_stay_pinned(toy_cycle):
    got = serial_dictatorship(toy_cycle, RULES, submitters(toy_cycle))
    assert got["T1000"] == "INTL-1" and got["T1004"] == "INTL-2"
