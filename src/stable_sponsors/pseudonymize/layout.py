"""Per-cycle folders under private_root, and the one-time copy of the old flat layout.

Each cycle has its own key/<cycle>/, derived/<cycle>/ and freetext/<cycle>/.
Earlier versions wrote every cycle into key/, derived/ and freetext/ directly.
Those flat files are never deleted, moved or changed. The first time a cycle's
key folder is prepared, the rows of the flat key and coding sheet that belong
to that cycle are copied in, so its confirmed IDs and hand coding carry over.
key/issued_ids.txt stays where it is: it is shared by every cycle, so an ID is
never handed out twice.

Console output names files and counts only.
"""

from __future__ import annotations

import json
import shutil

import pandas as pd

from stable_sponsors.pseudonymize.idmap import (
    CYCLE_AREAS,
    for_cycle,
    out_path,
    root_path,
)

# the stage-1 key files; a cycle folder holding any of them is never seeded again
KEY_CSVS = (
    "identity.csv",
    "identity_draft.csv",
    "course_alias.csv",
    "course_alias_draft.csv",
    "course_catalogue.csv",
    "course_catalogue_draft.csv",
)


def ensure_cycle_dirs(cfg, cycle) -> dict:
    """Create key/, derived/ and freetext/ for the cycle if missing; return the scoped cfg."""
    ccfg = for_cycle(cfg, cycle)
    for area in CYCLE_AREAS:
        out_path(ccfg, area).mkdir(parents=True, exist_ok=True)
    return ccfg


def _copy_rows(src, dst, keep) -> int:
    """Copy the rows of CSV src for which keep(row) is true to dst; return how many.

    When every row is kept the file is copied byte for byte, so a draft and its
    accepted twin stay identical (stage 2 compares their hashes).
    """
    df = pd.read_csv(src, dtype=str).fillna("")
    mask = df.apply(keep, axis=1) if len(df) else pd.Series(dtype=bool)
    if not mask.any():
        return 0
    if mask.all():
        shutil.copy2(src, dst)
    else:
        df[mask].to_csv(dst, index=False)
    return int(mask.sum())


def _in_cycle(key):
    return lambda r: str(r["cycle"]) == key


def _seen_in_cycle(key):
    # seen_in is empty for accepted rows absent from that build: unknown, so kept
    return lambda r: (
        not r["seen_in"]
        or any(s.split(":", 1)[0] == key for s in r["seen_in"].split("|"))
    )


def flat_layout_cycles(cfg) -> set:
    """Cycles that the old flat key/ has course rows for."""
    out = set()
    for name in ("course_alias.csv", "course_alias_draft.csv"):
        p = root_path(cfg, f"key/{name}")
        if p.exists():
            df = pd.read_csv(p, dtype=str).fillna("")
            if "cycle" in df.columns:
                out |= set(df["cycle"])
    return out


def seed_from_flat_layout(cfg, cycle) -> list[str]:
    """Copy this cycle's share of the flat key/ and coding sheet into its own folders.

    Does nothing for a file whose target already exists, and nothing at all to the
    key if the cycle's key folder already holds a key file or the flat key has no
    rows for the cycle. Returns the copied paths, relative to private_root.
    """
    key = str(cycle)
    ccfg = for_cycle(cfg, key)
    copied = []

    def copy(name, area, keep):
        src, dst = root_path(cfg, f"{area}/{name}"), out_path(ccfg, f"{area}/{name}")
        if src.is_file() and not dst.exists() and _copy_rows(src, dst, keep):
            copied.append(f"{area}/{key}/{name}")

    key_dir = out_path(ccfg, "key")
    if key in flat_layout_cycles(cfg) and not any(
        (key_dir / n).exists() for n in KEY_CSVS
    ):
        for name in ("identity.csv", "identity_draft.csv"):
            copy(name, "key", _seen_in_cycle(key))
        for name in KEY_CSVS[2:]:
            copy(name, "key", _in_cycle(key))
        src = root_path(cfg, "key/draft_inputs.json")
        dst = out_path(ccfg, "key/draft_inputs.json")
        if src.is_file() and not dst.exists():
            inputs = json.loads(src.read_text())
            if key in inputs:
                dst.write_text(json.dumps({key: inputs[key]}, indent=2, sort_keys=True))
                copied.append(f"key/{key}/draft_inputs.json")
        src = root_path(cfg, "key/leakage_allowlist.txt")
        dst = out_path(ccfg, "key/leakage_allowlist.txt")
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            copied.append(f"key/{key}/leakage_allowlist.txt")
    # lineage maps last cycle's courses onto this cycle's, so it belongs to this cycle
    copy("course_lineage.csv", "key", _in_cycle(key))
    copy("coding_sheet.csv", "freetext", _in_cycle(key))
    return copied


def prepare_cycle(cfg, cycle, quiet=False) -> dict:
    """Folders for the cycle, seeded from the flat layout once; return the scoped cfg."""
    ccfg = ensure_cycle_dirs(cfg, cycle)
    copied = seed_from_flat_layout(cfg, cycle)
    if copied and not quiet:
        print(f"copied from the old flat layout (originals left in place): {copied}")
    return ccfg


def selected_cycles(cfg, wanted) -> list[str]:
    """The cycles named on the command line, or every configured cycle, in order."""
    if not wanted:
        return sorted(cfg["cycles"])
    unknown = sorted({str(c) for c in wanted} - set(cfg["cycles"]))
    if unknown:
        raise SystemExit(f"not in the config: {', '.join(unknown)}")
    return sorted({str(c) for c in wanted})


def run_step(step, ccfg) -> str:
    """step(ccfg); '' if it finished, else why it stopped.

    Stages stop with SystemExit: a message, or exit code 1 after printing the
    reasons themselves.
    """
    try:
        step(ccfg)
    except SystemExit as exc:
        if exc.code in (None, 0):
            return ""
        return "see above" if exc.code == 1 else str(exc.code)
    return ""


def for_each_cycle(cfg, wanted, step) -> None:
    """Run step on each selected cycle's scoped cfg; one cycle failing does not stop the rest."""
    failed = []
    for key in selected_cycles(cfg, wanted):
        print(f"\n##### cycle {key}")
        why = run_step(step, prepare_cycle(cfg, key))
        if why:
            if why != "see above":
                print(f"  ! {why}")
            failed.append(key)
    if failed:
        raise SystemExit(f"not done for cycle(s): {', '.join(failed)}")
