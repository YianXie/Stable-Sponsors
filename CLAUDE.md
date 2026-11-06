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

`pyproject.toml` uses the `uv_build` backend, so `uv sync` installs the package in editable mode and `uv run python -m stable_sponsors.<module>` works directly, e.g. `uv run python -m stable_sponsors.pseudonymize.build_crosswalk --help`. pytest also adds `src/` and `tools/` through `pythonpath`.

```sh
make api                           # uvicorn stable_sponsors.api:app on 127.0.0.1:8000
make web                           # Vite dev server for frontend/
cd frontend && npm test && npm run build   # frontend checks; not in CI or make ci-local
```

## Architecture

The code has two independent halves.

### 1. Pseudonymisation pipeline (`src/stable_sponsors/pseudonymize/`)

This turns the office's raw spreadsheets, which contain real names and emails, into pseudonymous CSVs keyed by `T###` teacher IDs and trip codes. `docs/pseudonymization.md` is the full manual. The parts that matter most:

- **Privacy boundary.** Real data lives outside the repo, under `private_root` (default `~/interim-private`: `raw/`, `key/<cycle>/`, `derived/<cycle>/`, `freetext/<cycle>/`). `idmap.py` refuses any config whose paths resolve inside the repo. `config/pseudonymize.yaml` is gitignored. Copy it from `config/pseudonymize.example.yaml`. Script console output is designed to contain only counts, row numbers, trip codes and `T###` IDs. Keep it that way: never print names, emails or free text.
- **Two stages with a human review in between, one cycle at a time.** `build_crosswalk.py` (stage 1) writes `key/<cycle>/*_draft.csv` for review, and `--accept` promotes them. `apply_pseudonymization.py` (stage 2) writes `derived/<cycle>/`. `pipeline.py` runs both for every configured cycle, oldest first, skipping a cycle whose settings or raw files are invalid; it never accepts. Confirmed rows are locks: a rerun must never renumber IDs or re-merge people who were split. IDs come from a system RNG, not a seed, via `key/issued_ids.txt`, which all cycles share. Stage 1 proposes other cycles' accepted IDs for the same email or name, so a teacher keeps one ID across cycles.
- **Per-cycle paths.** `idmap.for_cycle(cfg, cycle)` scopes a config; `out_path()` then maps `key/`, `derived/` and `freetext/` into that cycle's folder (and raises without a cycle), while `root_path()` never remaps. `layout.py` creates the folders and, once per cycle, copies that cycle's rows of an old single-folder `key/` and coding sheet in. Never delete or move existing private data: overwrite only after a dated copy (`backup()`).
- `sources.py` loads the raw files according to the config (`check_spec` refuses missing settings). `idmap.py` holds the shared normalisation, matching and config helpers. `leakcheck.py` scans a cycle's `derived/<cycle>/` for leaked tokens.
- Data principles: unknown is not "no" (missing 2026 columns stay empty rather than `False`), and nothing is imputed.
- Tests: `tests/pseudonymize/test_pipeline_synthetic.py` runs both stages end to end on fake data from `tools/make_synthetic.py` and scores them against ground truth. `test_edge_cases.py` has one small regression per defect, including the per-cycle folders. `test_leakage.py` runs against every real `derived/<cycle>/` and skips when there is no local config, as on CI.

### 2. Allocation model (`src/stable_sponsors/data.py` and `rules/`)

- `data.py` defines frozen dataclasses (`Teacher`, `Course`, `Preference`, `Cycle`, `ObservedPlacement`). `load_cycle(dir)` reads `teachers.csv`, `courses.csv` and `preferences.csv`, which come from `derived/<cycle>/`, and enriches them with hand-maintained `teacher_params.csv` (qualifications separated by `;`, gender) and `course_params.csv` (`requires`, `min_sponsors`, `max_sponsors`, `female_slots`). It then runs `validate_cycle`. CSV cells are whitespace-padded, and `read_csv` strips that padding (`params.py` and `review.py` reuse it). In real runs the params CSVs come from `private_root/params/`, drafted by `params.py` from input tables only (never from `placements.csv`).
- `rules/context.py`: `build_ctx(cycle)` creates a CP-SAT model with booleans `x[(teacher_id, course_id)]` (assignment) and `y[course_id]` (course runs).
- `rules/registry.py`: `@register(rule_id)` adds an encoder `fn(ctx, params)` to `ENCODERS`. Registration happens on import, so `hard`, `priority` and `tiebreak` must be imported for the registry to be filled.
- Rule IDs, classes (hard/priority/tiebreak), params and status (`documented`/`reported`/`assumed`/`deferred`/`contradicted`) come from `config/rules-2027.yaml`. That file is tracked (it holds no personal data); `rules-2027.example.yaml` is currently empty. Every encoder ID must match an entry there. `tests/rules/test_registry.py` calls every non-deferred encoder and marks it xfail while it raises `NotImplementedError`. Priority rules 1 (`rank_preference`), 6 (`round_precedence`) and 11 (`unranked_fallback`, a secondary term in `objective_expr`) are implemented; 2 (`past_experience`, deferred) and the tiebreak encoder 7 are still stubs. `model.py` builds the model from the YAML rules and checks feasibility, the optimum and determinacy; with `--optimize` it writes `private_root/runs/<when>_model_run.json`.
- Analysis CLIs: `review.py` reads a run JSON and scores it against the office's `derived/<cycle>/placements.csv` (only "determined and match" counts as reproduction; determined mismatches are classified). `compare.py` counts rule violations in the observed placements. `course_set_check.py` tests whether the course set was fixed before allocation (rule 10). `interview_checks.py` counts how far the data agree with the 2026-10-28 interview. Frozen rule sets (`config/rules-2027-v2.3.yaml`, `-v3.0.yaml`) replay old runs; only `deferred` and `contradicted` rules are inactive. `review.py` replaces the old `reproduction.py`. `README.md` lists the full run order.
- `objectives.py` (RQ2): `solve_objective` maximises an objective's stages in order on the hard rules, pinning each stage at its optimum before the next; the last stage is always the utilitarian preference score, so every `StagedResult.score` is comparable with `model`'s primary value. Objectives are `utilitarian`, `leximin` (counts of `leximin_population` teachers above each score level), `coverage` (courses running, each needing a sponsor) and `round2` (teachers placed from `intl_r1` or `sg`). `preference_scores` is rules 1 and 6 via `review.claim_scores`; rule 11 is ignored. A stage not proven optimal gives no assignment. `objective_determinacy` runs `model.determinacy_on` on the final staged model, so the earlier pins stay in force.
- `serial.py`: feasibility-preserving random serial dictatorship. Submitters pick in order, each taking their best-scoring ranked course that keeps the hard rules satisfiable (else unplaced, else free); one last solve seats non-submitters at score 0. `random_orders` shuffles from one `random.Random(seed)`. A solver timeout raises rather than counting as infeasible.
- `metrics.py`: `allocation_metrics` (score, placed, courses run, worst-off, `rank_hist`, …) and `agreement` are computed from an assignment dict only, never from the model's `y` or from files; `summarise` gives mean/min/max over RSD orders.
- `rq2.py`: CLI that runs every objective and `--orders` RSD orders against the office, prints two tables of counts and the path, and writes `private_root/runs/<when>_rq2_run.json` with keys `when`, `cycle`, `rules_file`, `excluded`, `lineage`, `provenance` (commit, dirty tree, `inputs_sha256`), `office`, `objectives` (per objective `result`, `metrics`, `agreement_with_office`, and with `--determinacy` `determinacy` and `review`) and `rsd`. Default rules are the frozen `rules-2027-v3.1.yaml`; it refuses `--exclude 1` or `6`. The JSON may hold `T###` IDs; the console never does.
- Where the rules come from: `docs/procedure-doc-rules-v1.0.md` (the office's document, D-xxx), `docs/my-understanding-of-rules-v2.0.md` (interview notes, M-xxx), and `docs/procedure-diff-v1.1.md` (comparison categories A–E). The YAML `source` fields refer to these diff entries. `docs/encoding-decisions.md` records modelling assumptions. Add any new assumption there.
- `api.py`: `create_app()` / `app` serve `POST /api/allocations` for cycle 2027. It calls the same `model.run_model` and `review.review_run` as the CLIs, so a web run writes the usual `runs/*_model_run.json` and `_reproduction.json` and counts as the latest run for `review`. One solve at a time (409 otherwise). The response is built from an allow-list (`T###` IDs, trip codes, course type, country, review stats), and errors are fixed text per code, never exception text. `frontend/` is the Vite React TypeScript page that calls it.
- The test fixture is `tests/fixtures/toy_cycle/`, exposed as the `toy_cycle` and `ctx` fixtures in `tests/conftest.py`.
