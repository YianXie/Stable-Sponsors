"""Run both stages for every cycle, each in its own folders.

    uv run python -m stable_sponsors.pseudonymize.pipeline              # every cycle
    uv run python -m stable_sponsors.pseudonymize.pipeline --cycle 2027

For each cycle in the config, oldest first:
    1. create key/<cycle>/, derived/<cycle>/ and freetext/<cycle>/ if missing; the
       first time, copy in that cycle's share of an old flat key/ and coding sheet
       (the originals stay where they are);
    2. check the cycle's settings and raw files; a cycle that fails is skipped,
       with the reason, and the other cycles still run;
    3. stage 1: rebuild the drafts under key/<cycle>/ (confirmed rows are kept);
    4. stage 2: if the cycle has an accepted, fully confirmed key, write
       derived/<cycle>/ and freetext/<cycle>/.

The drafts are never accepted here: confirming the key is the human step. After
reviewing a cycle's drafts, run build_crosswalk --cycle <cycle> --accept, then run
this again. Oldest first means stage 2 compares a cycle's repeaters with the
previous cycle's placements as just rebuilt.

Console output is the stages' own (counts, rows, trip codes and T### IDs only).
"""

from __future__ import annotations

import argparse

import stable_sponsors.pseudonymize.apply_pseudonymization as stage2
import stable_sponsors.pseudonymize.build_crosswalk as stage1
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config
from stable_sponsors.pseudonymize.layout import (
    prepare_cycle,
    run_step,
    selected_cycles,
)
from stable_sponsors.pseudonymize.sources import load_cycle


def run_cycle(cfg, key, quiet=False) -> str:
    """Both stages for one cycle; returns a one-line outcome for the summary."""
    ccfg = prepare_cycle(cfg, key, quiet=quiet)
    why = run_step(lambda c: load_cycle(c, key), ccfg)
    if why:
        return f"skipped, config or raw files not valid: {why}"
    why = run_step(lambda c: stage1.run(c, quiet=quiet), ccfg)
    if why:
        return f"stage 1 stopped: {why}"
    why = run_step(lambda c: stage2.run(c, quiet=quiet), ccfg)
    if why:
        return f"drafts rebuilt in key/{key}/; not applied: {why}"
    return f"drafts rebuilt in key/{key}/; derived/{key}/ and freetext/{key}/ written"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument(
        "--cycle",
        action="append",
        help="cycle to process (repeatable; default: every cycle in the config)",
    )
    args = ap.parse_args()
    cfg = load_config(args.config)
    outcomes = {}
    for key in selected_cycles(cfg, args.cycle):
        print(f"\n##### cycle {key}")
        outcomes[key] = run_cycle(cfg, key)
    print("\n" + "=" * 70)
    for key, outcome in outcomes.items():
        print(f"{key}: {outcome}")


if __name__ == "__main__":
    main()
