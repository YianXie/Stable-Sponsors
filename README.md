# Stable-Sponsors

Stable Sponsors — a constraint-based reallocation of the SAS Interim Semester faculty sponsor matching process. Encodes the current procedure as rules, reproduces real placements, then compares CP-SAT/OR-Tools objectives (utilitarian, leximin, coverage) and deferred acceptance for a more transparent, explainable allocation.

The project has three steps:

1. **Encode** the current procedure, partly unwritten, as explicit rules (hard constraints, priorities, tie-breaks).
2. **Reproduce**: check that those rules reproduce the office's real placements.
3. **Compare** alternative allocations: CP-SAT objectives (utilitarian, leximin, coverage) and deferred acceptance.

**Status:** step 2 is in progress. Reproduction v1 for the 2027 cycle is written up in [`docs/reproduction-report-v1.md`](docs/reproduction-report-v1.md).

---

## Privacy first

The office's spreadsheets contain real names and emails. None of that data is in this repository.

- Real data lives outside the repo, under `private_root` (default `~/interim-private`): `raw/` (office spreadsheets), `key/<cycle>/` (identity crosswalk), `derived/<cycle>/` (pseudonymous CSVs), `freetext/<cycle>/`, `params/` and `runs/`.
- The scripts refuse any config whose paths resolve inside the repository.
- Teachers appear only as `T###` IDs and courses as trip codes. Console output is limited to counts, row numbers, trip codes and `T###` IDs.
- `config/pseudonymize.yaml` and the two source documents (the office's procedure document and interview notes) are gitignored.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
cp config/pseudonymize.example.yaml config/pseudonymize.yaml   # then set private_root
```

## Workflow

Run in this order. The scripts read `config/pseudonymize.yaml` by default; most accept `--config` to use another file.

| Step | Command                                                                               | What it does                                                                                                                                                                                                                                                                                                                                                         |
| ---- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | `uv run python -m stable_sponsors.pseudonymize.pipeline`                              | For every cycle in the config: creates `key/<cycle>/`, `derived/<cycle>/` and `freetext/<cycle>/`, skips the cycle (with the reason) if its settings or raw files are not valid, runs stage 1 (drafts `key/<cycle>/*_draft.csv` for human review) and, once the cycle's key is accepted, stage 2 (writes `derived/<cycle>/`). `--cycle 2027` limits it to one cycle. |
| 2    | `uv run python -m stable_sponsors.pseudonymize.build_crosswalk --cycle 2027 --accept` | Promotes a cycle's fully confirmed drafts to its final key, then rerun step 1. Confirmed rows are never renumbered or re-merged, and a teacher keeps one ID across cycles.                                                                                                                                                                                           |
| 3    | `uv run pytest tests/pseudonymize/test_leakage.py`                                    | Scans every `derived/<cycle>/` for names or emails that leaked through.                                                                                                                                                                                                                                                                                              |
| 4    | `uv run python -m stable_sponsors.params --cycle 2027`                                | Drafts `params/course_params.csv` and `params/teacher_params.csv` from input tables only (never from placements). Edit them by hand as the office confirms values.                                                                                                                                                                                                   |
| 5    | `uv run python -m stable_sponsors.model --cycle 2027 --optimize`                      | Checks the hard rules are feasible, solves, checks determinacy, and writes `runs/*_model_run.json`. `--exclude 10` drops a rule; `--no-lineage` matches repeaters' prior course by code.                                                                                                                                                                             |
| 6    | `uv run python -m stable_sponsors.review`                                             | Compares the latest run with the office's placements: which teachers are determined, and which match. `--list` adds `T###` IDs.                                                                                                                                                                                                                                      |
| 7    | `uv run python -m stable_sponsors.rq2 --determinacy`                                  | Allocates the cycle under the four objectives (utilitarian, leximin, coverage, Round-2) and by random serial dictatorship (`--orders`, default 20), compares each with the office in one table of counts (plus a rank histogram), and writes `runs/<when>_rq2_run.json`. `--determinacy` adds determined and determined-and-match counts.                            |

Diagnostics:

- `uv run python -m stable_sponsors.compare` counts rule violations in the office's own placements.
- `uv run python -m stable_sponsors.interview_checks` counts how far the data agree with the 2026-10-28 office interview. The interview notes (`docs/interview-*.md`) are kept local and gitignored, like the other meeting notes.
- `uv run python -m stable_sponsors.course_set_check --cycle 2027` tests whether the course set was fixed before sponsors were allocated (rule 10).

Stage 1 and stage 2 can also be run by hand (`build_crosswalk`, `apply_pseudonymization`, both with `--cycle`). See [`docs/pseudonymization.md`](docs/pseudonymization.md) for the full pipeline manual, including how IDs carry across cycles and how a pre-existing single-folder `key/`, `derived/` and `freetext/` is copied, never moved, into the per-cycle folders.

## Web UI

A local page that runs the model and shows the allocation next to the office's placements. Use two terminals from the repo root:

```sh
make api    # FastAPI on 127.0.0.1:8000
make web    # Vite dev server for frontend/ (needs `npm install` in frontend/ once)
```

It is local only; it reads the private data through `config/pseudonymize.yaml`. Each click on "Generate allocation" takes about a minute and writes the usual run and reproduction files to `runs/`, so `review` treats a web run as the latest. The browser receives only `T###` IDs, trip codes, course type, country and review results.

## Repository layout

```text
src/stable_sponsors/
  pseudonymize/      raw spreadsheets -> pseudonymous CSVs, per cycle (pipeline, stages 1 and 2, leak check)
  data.py            Teacher / Course / Preference / Cycle dataclasses, load_cycle()
  rules/             CP-SAT encoders: hard.py, priority.py, tiebreak.py, registry
  params.py          draft course/teacher parameter CSVs
  model.py           build and solve the model, write run reports
  review.py          score a run against the office's placements
  objectives.py      RQ2 objectives (utilitarian, leximin, coverage, Round-2), solved in stages
  serial.py          random serial dictatorship baseline
  metrics.py         metrics of one allocation, and agreement between two
  rq2.py             compare the objectives and serial dictatorship with the office
  compare.py         rule violations in the observed placements
  interview_checks.py
  course_set_check.py
  api.py             local web API: POST /api/allocations (uses model.run_model and review.review_run)
frontend/            Vite React TypeScript page for the web UI
config/              rules-2027.yaml (rule spec), *.example.yaml templates
docs/                procedure diff, encoding decisions, reports
tests/               pytest suite; fixtures/toy_cycle is a small fake cycle
tools/               make_synthetic.py (fake raw data), inspect_structure.py
```

## The rules model

`config/rules-2027.yaml` is the rule specification. Each rule has an `id`, a `class` (`hard`, `priority` or `tiebreak`), a `status` (`documented`, `reported`, `assumed`, `deferred` or `contradicted`) and a `source` that points to an entry in the procedure diff. Every non-deferred rule has a matching encoder in `src/stable_sponsors/rules/`, registered with `@register(rule_id)`. The model uses booleans `x[(teacher, course)]` for assignments and `y[course]` for whether a course runs.

Every modelling assumption is recorded in [`docs/encoding-decisions.md`](docs/encoding-decisions.md).

## Documentation

| Document                                                           | Contents                                                                     |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| [`docs/pseudonymization.md`](docs/pseudonymization.md)             | Pipeline manual: config, review steps, data principles                       |
| [`docs/procedure-diff-v1.1.md`](docs/procedure-diff-v1.1.md)       | The office's written procedure compared with interview notes, categories A–E |
| [`docs/encoding-decisions.md`](docs/encoding-decisions.md)         | Modelling assumptions made while encoding the rules                          |
| [`docs/reproduction-report-v1.md`](docs/reproduction-report-v1.md) | Reproduction v1: do the rules reproduce the 2027 placements?                 |

`docs/procedure-doc-rules-v1.0.md` (office document) and `docs/my-understanding-of-rules-v2.0.md` (interview notes) exist only locally.

## Development

```sh
make ci-local       # uv sync --locked, ruff check, ruff format --check, pytest -v
uv run ruff check . && uv run ruff format .
uv run pytest tests/rules/test_hard_rules.py -v
```

CI runs the same checks on GitHub Actions. Tests that need real data, such as `test_leakage.py`, skip when there is no local config. The end-to-end pipeline test runs on synthetic data from `tools/make_synthetic.py`.

## License

[MIT](LICENSE) © 2026 Yian Xie
