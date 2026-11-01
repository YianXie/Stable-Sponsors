# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Stable Sponsors models how SAS Interim Semester faculty sponsors are allocated to courses. The plan has three steps: encode the current (partly unwritten) procedure as rules, check that those rules reproduce the real placements, then compare CP-SAT objectives (utilitarian, leximin, coverage) and deferred acceptance as alternative ways to allocate.

## Commands

Python 3.12, managed with `uv`. CI (`.github/workflows/ci.yml`) runs ruff and pytest; `make ci-local` runs the same checks locally.

```sh
make ci-local                      # uv sync --locked, ruff check, ruff format --check, pytest -v
uv run ruff check . && uv run ruff format .
uv run pytest tests/rules/test_hard_rules.py::test_repeater_cannot_be_moved_out -v   # single test
```

`pyproject.toml` uses the `uv_build` backend, so `uv sync` installs the package in editable mode and `uv run python -m stable_sponsors.<module>` works directly, e.g. `uv run python -m stable_sponsors.pseudonymize.build_crosswalk --help`. pytest also adds `src/` and `tools/` through `pythonpath`. The `python src/build_crosswalk.py` paths in `docs/pseudonymization.md` are out of date. The scripts now live under `src/stable_sponsors/pseudonymize/`.

## Architecture

The code has two independent halves.

### 1. Pseudonymisation pipeline (`src/stable_sponsors/pseudonymize/`)

This turns the office's raw spreadsheets, which contain real names and emails, into pseudonymous CSVs keyed by `T###` teacher IDs and trip codes. `docs/pseudonymization.md` is the full manual. The parts that matter most:

- **Privacy boundary.** Real data lives outside the repo, under `private_root` (default `~/interim-private`: `raw/`, `key/`, `derived/`, `freetext/`). `idmap.py` refuses any config whose paths resolve inside the repo. `config/pseudonymize.yaml` is gitignored. Copy it from `config/pseudonymize.example.yaml`. Script console output is designed to contain only counts, row numbers, trip codes and `T###` IDs. Keep it that way: never print names, emails or free text.
- **Two stages with a human review in between.** `build_crosswalk.py` (stage 1) writes `key/*_draft.csv` for review, and `--accept` promotes them. `apply_pseudonymization.py` (stage 2) writes `derived/`. Confirmed rows are locks: a rerun must never renumber IDs or re-merge people who were split. IDs come from a system RNG, not a seed.
- `sources.py` loads the raw files according to the config. `idmap.py` holds the shared normalisation, matching and config helpers. `leakcheck.py` scans `derived/` for leaked tokens.
- Data principles: unknown is not "no" (missing 2026 columns stay empty rather than `False`), and nothing is imputed.
- Tests: `tests/pseudonymize/test_pipeline_synthetic.py` runs both stages end to end on fake data from `tools/make_synthetic.py` and scores them against ground truth. `test_leakage.py` runs against the real `derived/` and skips when there is no local config, as on CI.

### 2. Allocation model (`src/stable_sponsors/data.py` and `rules/`)

- `data.py` defines frozen dataclasses (`Teacher`, `Course`, `Preference`, `Cycle`, `ObservedPlacement`). `load_cycle(dir)` reads `teachers.csv`, `courses.csv` and `preferences.csv`, which come from `derived/`, and enriches them with hand-maintained `teacher_params.csv` (qualifications separated by `;`, gender) and `course_params.csv` (`requires`, `min_sponsors`, `max_sponsors`, `female_slots`). It then runs `validate_cycle`. CSV cells are whitespace-padded, and `read_csv` strips that padding (`params.py` and `review.py` reuse it). In real runs the params CSVs come from `private_root/params/`, drafted by `params.py` from input tables only (never from `placements.csv`).
- `rules/context.py`: `build_ctx(cycle)` creates a CP-SAT model with booleans `x[(teacher_id, course_id)]` (assignment) and `y[course_id]` (course runs).
- `rules/registry.py`: `@register(rule_id)` adds an encoder `fn(ctx, params)` to `ENCODERS`. Registration happens on import, so `hard`, `priority` and `tiebreak` must be imported for the registry to be filled.
- Rule IDs, classes (hard/priority/tiebreak), params and status (`documented`/`reported`/`assumed`/`deferred`/`contradicted`) come from `config/rules-2027.yaml`. That file is tracked (it holds no personal data); `rules-2027.example.yaml` is currently empty. Every encoder ID must match an entry there. `tests/rules/test_registry.py` calls every non-deferred encoder and marks it xfail while it raises `NotImplementedError`. Priority rules 1 (`rank_preference`) and 6 (`round_precedence`) are implemented; 2 (`past_experience`, deferred) and the tiebreak encoder 7 are still stubs. `model.py` builds the model from the YAML rules and checks feasibility, the optimum and determinacy; with `--optimize` it writes `private_root/runs/<when>_model_run.json`.
- Analysis CLIs: `review.py` reads a run JSON and scores it against the office's `derived/placements.csv` (only "determined and match" counts as reproduction; determined mismatches are classified). `compare.py` counts rule violations in the observed placements. `course_set_check.py` tests whether the course set was fixed before allocation (rule 10). `interview_checks.py` counts how far the data agree with the 2026-10-28 interview. Frozen rule sets (`config/rules-2027-v2.3.yaml`, `-v3.0.yaml`) replay old runs; only `deferred` and `contradicted` rules are inactive. `review.py` replaces the old `reproduction.py`. `README.md` lists the full run order.
- Where the rules come from: `docs/procedure-doc-rules-v1.0.md` (the office's document, D-xxx), `docs/my-understanding-of-rules-v2.0.md` (interview notes, M-xxx), and `docs/procedure-diff-v1.1.md` (comparison categories A–E). The YAML `source` fields refer to these diff entries. `docs/encoding-decisions.md` records modelling assumptions. Add any new assumption there.
- The test fixture is `tests/fixtures/toy_cycle/`, exposed as the `toy_cycle` and `ctx` fixtures in `tests/conftest.py`.
