"""Describe the raw spreadsheets without revealing their contents.

    python tools/inspect_structure.py ~/interim-private/raw

Prints, per file and sheet: headers, row counts, merged cells, and for each
column the number of non-blank values, distinct values, and the most common
value *shapes* (letters -> a/A, digits -> 9). Email columns report domains
only. Nothing printed identifies a person, so the output is safe to share.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import openpyxl


def shape(v) -> str:
    s = str(v)
    s = re.sub(r"[A-Z]+", "A", s)
    s = re.sub(r"[a-z]+", "a", s)
    s = re.sub(r"(?:Aa)+", "Aa", s)
    s = re.sub(r"[0-9]+", lambda m: "9" * min(len(m.group()), 4), s)
    return s[:40]


def describe(root: Path) -> None:
    for f in sorted(root.rglob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        wb = openpyxl.load_workbook(f, data_only=True)
        print("=" * 72)
        print(f.relative_to(root))
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            filled = [r for r in rows if any(c not in (None, "") for c in r)]
            print(
                f"  sheet {ws.title!r} ({ws.sheet_state}) rows={len(rows)} "
                f"non-empty={len(filled)} merged={len(ws.merged_cells.ranges)}"
            )
            if ws.merged_cells.ranges:
                print(
                    "    merged:", [str(m) for m in list(ws.merged_cells.ranges)[:10]]
                )
            if not filled:
                continue
            h = next(
                i
                for i, r in enumerate(rows)
                if sum(c not in (None, "") for c in r) >= 2
            )
            if h:
                print(
                    f"    header is on row {h + 1}; rows above it are ignored by pandas!"
                )
            for j, name in enumerate(rows[h]):
                vals = [
                    r[j] for r in rows[h + 1 :] if j < len(r) and r[j] not in (None, "")
                ]
                shown = "<has @>" if name and "@" in str(name) else name
                extra = ""
                if any("@" in str(v) for v in vals):
                    extra = " domains=" + str(
                        dict(
                            Counter(
                                str(v).rsplit("@", 1)[-1].strip().lower()
                                for v in vals
                                if "@" in str(v)
                            )
                        )
                    )
                pad = sum(1 for v in vals if isinstance(v, str) and v != v.strip())
                print(
                    f"    [{j}] {shown!r}: non-blank={len(vals)} distinct={len(set(map(str, vals)))} "
                    f"shapes={Counter(shape(v) for v in vals).most_common(3)}{extra}"
                    + (f" padded={pad}" if pad else "")
                )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    describe(Path(sys.argv[1]).expanduser())
