"""Local web API: POST /api/allocations runs the model and review for cycle 2027.

The response is built field by field from an allow-list. Error messages are fixed text per
code, never exception text, because an exception could carry a private path.
"""

import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from stable_sponsors import model, review
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config

CYCLE = 2027
SOLVER_LIMIT = 60.0

log = logging.getLogger("stable_sponsors.api")

STATUS_CODES = {
    "busy": 409,
    "infeasible": 422,
    "not_configured": 503,
    "data_invalid": 503,
    "solver_timeout": 504,
    "internal": 500,
}
MESSAGES = {
    "busy": "A solve is already running. Wait for it to finish, then try again.",
    "infeasible": "The hard rules cannot all be met with this data.",
    "not_configured": (
        "The config or a required data file is missing. "
        "Start the server from the repo root with `make api`, "
        "and check that the private data is in place."
    ),
    "data_invalid": "The data failed validation, or the office placed a teacher twice.",
    "solver_timeout": "The solver did not finish in time, so the result is not proven.",
    "internal": "Something unexpected went wrong. Check the server log.",
}


class ApiError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or MESSAGES[code]


# Per stage: which failures map to which code. Anything else becomes "internal".
# SystemExit is not an Exception, so it is caught by name and must never escape the route.
CONFIG = ((BaseException, "not_configured"),)
PREFLIGHT = (
    (FileNotFoundError, "not_configured"),
    ((ValueError, SystemExit), "data_invalid"),
)
SOLVE = (
    (FileNotFoundError, "not_configured"),
    (RuntimeError, "solver_timeout"),
    (SystemExit, "data_invalid"),
)
REVIEW = (
    (FileNotFoundError, "not_configured"),
    (RuntimeError, "solver_timeout"),
    ((SystemExit, ValueError), "data_invalid"),
)


def stage(mapping, fn: Callable, *args, **kwargs):
    """Call fn, turning its failures into an ApiError as ``mapping`` says."""
    try:
        return fn(*args, **kwargs)
    except ApiError:
        raise
    except (Exception, SystemExit) as e:  # noqa: BLE001  (SystemExit must not escape)
        for types, code in mapping:
            if isinstance(e, types):
                raise ApiError(code) from None
        log.error("unexpected %s", type(e).__name__)
        raise ApiError("internal") from None


def course_sort_key(course_id: str) -> list:
    """Natural order: AUST-2 before AUST-10. Odd positions are always numbers."""
    return [int(p) if i % 2 else p for i, p in enumerate(re.split(r"(\d+)", course_id))]


def conflicting_rules(report: dict) -> list[int]:
    loo = report.get("diagnose", {}).get("leave_one_out", {})
    return sorted(int(r) for r, status in loo.items() if status == "feasible")


def build_response(report: dict, run_path: Path, result: review.ReviewResult) -> dict:
    run, stats, cycle = result.run, result.stats, result.cycle
    assignment = run[model.OPTIMAL_KEY]["assignment"]
    cells = stats["cells"]
    matched = set(cells["determined_match"]) | set(cells["contested_match"])
    determined = run[model.DETERMINACY_KEY]
    category = {
        t: cat
        for cat, ids in stats["determined_mismatch_categories"].items()
        for t in ids
    }
    submitted = {p.teacher_id for p in cycle.preferences}
    repeaters = {t.teacher_id for t in cycle.teachers if t.is_repeater}

    in_cycle = {c.course_id: c for c in cycle.courses}
    course_ids = sorted(
        set(in_cycle) | set(result.office.values()), key=course_sort_key
    )
    courses = []
    for cid in course_ids:
        c = in_cycle.get(cid)
        courses.append(
            {
                "course_id": cid,
                "course_type": c.course_type if c else None,
                "country": c.country if c else None,
                "model": sorted(t for t, x in assignment.items() if x == cid),
                "office": sorted(t for t, x in result.office.items() if x == cid),
            }
        )
    teachers = [
        {
            "teacher_id": t,
            "model_course": assignment[t],
            "office_course": result.office.get(t),
            "determined": bool(determined[t]),
            "match": t in matched,
            "is_repeater": t in repeaters,
            "submitted": t in submitted,
            "mismatch_category": category.get(t),
        }
        for t in sorted(assignment)
    ]
    opt = run[model.OPTIMAL_KEY]
    return {
        "run": {
            "file": run_path.name,
            "when": run["when"],
            "cycle": run["cycle"],
            "rules_file": run["rules_file"],
            "excluded": run["excluded"],
            "objective": {
                "status": opt["status"],
                "value": opt["value"],
                "primary_value": opt["primary_value"],
            },
        },
        "warnings": result.warnings,
        "review": stats,
        "courses": courses,
        "teachers": teachers,
    }


def solve(config_path: str | Path, rules: Path) -> dict:
    config = stage(CONFIG, load_config, config_path)
    stage(PREFLIGHT, model.load_cycle_from_config, config, CYCLE)
    run_path, report = stage(
        SOLVE,
        model.run_model,
        config,
        CYCLE,
        rules,
        time_limit=SOLVER_LIMIT,
        optimize=True,
        lineage=True,
        log=lambda _: None,
    )
    if report["feasibility_result"]["status"] == "infeasible":
        ids = ", ".join(str(i) for i in conflicting_rules(report))
        raise ApiError(
            "infeasible", MESSAGES["infeasible"] + f" Rules involved: {ids or 'none'}."
        )
    if model.DETERMINACY_KEY not in report:
        raise ApiError("solver_timeout")
    result = stage(REVIEW, review.review_run, config, run_path)
    return stage((), build_response, report, run_path, result)


def create_app(
    config: str | Path = DEFAULT_CONFIG,
    rules: Path = Path("config/rules-2027.yaml"),
) -> FastAPI:
    """The config is read on each request, not here, so a missing one is an error
    response rather than a server that fails to start."""
    app = FastAPI()
    app.state.solve_lock = threading.Lock()

    @app.post("/api/allocations")
    def allocations() -> dict:
        lock = app.state.solve_lock
        if not lock.acquire(blocking=False):
            fail = ApiError("busy")
        else:
            try:
                return solve(config, rules)
            except ApiError as e:
                fail = e
            finally:
                lock.release()
        raise HTTPException(
            STATUS_CODES[fail.code],
            detail={"code": fail.code, "message": fail.message},
        )

    return app


app = create_app()
