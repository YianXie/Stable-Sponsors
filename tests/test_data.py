from pathlib import Path

from stable_sponsors.data import load_cycle, load_observed_placements


def test_load_cycle() -> None:
    base = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "toy_cycle"

    cycle = load_cycle(base)
    load_observed_placements(base / "placements.csv", cycle)
