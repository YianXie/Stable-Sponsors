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

- Real data lives outside the repo, under `private_root` (default `~/interim-private`): `raw/` (office spreadsheets), `key/` (identity crosswalk), `derived/` (pseudonymous CSVs), `freetext/`, `params/` and `runs/`.
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

| Step | Command                                                                  | What it does                                                                                                                                                                             |
| ---- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | `uv run python -m stable_sponsors.pseudonymize.build_crosswalk`          | Stage 1: proposes the identity key and course mapping as `key/*_draft.csv` for human review.                                                                                             |
| 2    | `uv run python -m stable_sponsors.pseudonymize.build_crosswalk --accept` | Promotes fully confirmed drafts to the final key. Confirmed rows are never renumbered or re-merged.                                                                                      |
| 3    | `uv run python -m stable_sponsors.pseudonymize.apply_pseudonymization`   | Stage 2: applies the key and writes `derived/`.                                                                                                                                          |
| 4    | `uv run pytest tests/pseudonymize/test_leakage.py`                       | Scans `derived/` for names or emails that leaked through.                                                                                                                                |
| 5    | `uv run python -m stable_sponsors.params --cycle 2027`                   | Drafts `params/course_params.csv` and `params/teacher_params.csv` from input tables only (never from placements). Edit them by hand as the office confirms values.                       |
| 6    | `uv run python -m stable_sponsors.model --cycle 2027 --optimize`         | Checks the hard rules are feasible, solves, checks determinacy, and writes `runs/*_model_run.json`. `--exclude 10` drops a rule; `--no-lineage` matches repeaters' prior course by code. |
| 7    | `uv run python -m stable_sponsors.review`                                | Compares the latest run with the office's placements: which teachers are determined, and which match. `--list` adds `T###` IDs.                                                          |

Diagnostics:

- `uv run python -m stable_sponsors.compare` counts rule violations in the office's own placements.
- `uv run python -m stable_sponsors.course_set_check --cycle 2027` tests whether the course set was fixed before sponsors were allocated (rule 10).

See [`docs/pseudonymization.md`](docs/pseudonymization.md) for the full pipeline manual. Some script paths in it are out of date: the scripts now live under `src/stable_sponsors/pseudonymize/`.

## Repository layout

```text
src/stable_sponsors/
  pseudonymize/      raw spreadsheets -> pseudonymous CSVs (stages 1 and 2, leak check)
  data.py            Teacher / Course / Preference / Cycle dataclasses, load_cycle()
  rules/             CP-SAT encoders: hard.py, priority.py, tiebreak.py, registry
  params.py          draft course/teacher parameter CSVs
  model.py           build and solve the model, write run reports
  review.py          score a run against the office's placements
  compare.py         rule violations in the observed placements
  course_set_check.py
config/              rules-2027.yaml (rule spec), *.example.yaml templates
docs/                procedure diff, encoding decisions, reports
tests/               pytest suite; fixtures/toy_cycle is a small fake cycle
tools/               make_synthetic.py (fake raw data), inspect_structure.py
```

## The rules model

`config/rules-2027.yaml` is the rule specification. Each rule has an `id`, a `class` (`hard`, `priority` or `tiebreak`), a `status` (`documented`, `assumed` or `deferred`) and a `source` that points to an entry in the procedure diff. Every non-deferred rule has a matching encoder in `src/stable_sponsors/rules/`, registered with `@register(rule_id)`. The model uses booleans `x[(teacher, course)]` for assignments and `y[course]` for whether a course runs.

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
