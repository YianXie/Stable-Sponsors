import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stable_sponsors import model, review
from stable_sponsors.api import course_sort_key, create_app
from tests.conftest import RULES_PATH, make_private_root

PRIVATE_KEYS = {
    "gender",
    "male_slots",
    "female_slots",
    "qualifications",
    "requires",
    "slot_genders_ranked",
}


def make_client(tmp_path: Path, **kw) -> TestClient:
    return TestClient(create_app(make_private_root(tmp_path), RULES_PATH), **kw)


def private_root(tmp_path: Path) -> Path:
    return tmp_path / "private"


def error(res) -> dict:
    return res.json()["detail"]


@pytest.fixture
def solved(tmp_path):
    client = make_client(tmp_path)
    res = client.post("/api/allocations")
    assert res.status_code == 200, res.text
    return tmp_path, client, res, res.json()


def walk_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_keys(v)


def test_success_has_the_documented_shape(solved):
    _, _, _, body = solved
    assert set(body) == {"run", "warnings", "review", "courses", "teachers"}
    assert set(body["run"]) == {
        "file",
        "when",
        "cycle",
        "rules_file",
        "excluded",
        "objective",
    }
    assert set(body["run"]["objective"]) == {"status", "value", "primary_value"}
    assert body["courses"] and body["teachers"]
    for c in body["courses"]:
        assert set(c) == {"course_id", "course_type", "country", "model", "office"}
    for t in body["teachers"]:
        assert set(t) == {
            "teacher_id",
            "model_course",
            "office_course",
            "determined",
            "match",
            "is_repeater",
            "submitted",
            "mismatch_category",
        }


def test_success_writes_both_run_files(solved):
    tmp_path, _, _, body = solved
    runs = private_root(tmp_path) / "runs"
    run_files = list(runs.glob("*_model_run.json"))
    assert len(run_files) == 1
    assert len(list(runs.glob("*_reproduction.json"))) == 1
    assert body["run"]["file"] == run_files[0].name


def test_review_equals_the_file_it_wrote(solved):
    tmp_path, _, _, body = solved
    (repro,) = (private_root(tmp_path) / "runs").glob("*_reproduction.json")
    assert body["review"] == json.loads(repro.read_text())


def test_teacher_rows_agree_with_review_cells(solved):
    _, _, _, body = solved
    cells = body["review"]["cells"]
    rows = body["teachers"]
    for d in ("determined", "contested"):
        for m in ("match", "mismatch"):
            ids = sorted(
                t["teacher_id"]
                for t in rows
                if t["determined"] == (d == "determined")
                and t["match"] == (m == "match")
            )
            assert ids == sorted(cells[f"{d}_{m}"])
    categorised = {t["teacher_id"] for t in rows if t["mismatch_category"] is not None}
    assert categorised == set(cells["determined_mismatch"])


def test_api_agrees_with_the_clis_on_determined_results(solved, tmp_path_factory):
    _, _, _, body = solved
    cli_cfg = make_private_root(tmp_path_factory.mktemp("cli"))
    model.main(["--config", str(cli_cfg), "--rules", str(RULES_PATH), "--optimize"])
    review.main(["--config", str(cli_cfg)])
    (repro,) = (cli_cfg.parent / "private" / "runs").glob("*_reproduction.json")
    cli = json.loads(repro.read_text())
    api = body["review"]
    for key in (
        "determined_match",
        "determined_match_placed",
        "determined_match_unplaced",
        "determined_mismatch_categories",
    ):
        assert api[key] == cli[key], key
    for cell in ("determined_match", "determined_mismatch"):
        assert api["cells"][cell] == cli["cells"][cell], cell


def test_response_contains_no_private_fields(solved):
    tmp_path, _, res, body = solved
    assert not PRIVATE_KEYS & set(walk_keys(body))
    assert str(tmp_path) not in res.text
    params = private_root(tmp_path) / "params"
    secrets = set()
    for name in ("teacher_params.csv", "course_params.csv"):
        header, *lines = (params / name).read_text().splitlines()
        cols = [c.strip() for c in header.split(",")]
        for line in lines:
            row = dict(zip(cols, (c.strip() for c in line.split(","))))
            for col in ("qualifications", "requires"):
                for q in row.get(col, "").split(";"):
                    if q:
                        secrets.add(q)
    assert secrets  # the toy data does carry some
    for q in secrets:
        assert q not in res.text


def test_courses_are_in_natural_order():
    ids = ["SING-10", "NR-3ce91a", "AUST-10", "NR-3", "AUST-2"]
    assert sorted(ids, key=course_sort_key) == [
        "AUST-2",
        "AUST-10",
        "NR-3",
        "NR-3ce91a",
        "SING-10",
    ]


def test_missing_config_is_not_configured(tmp_path):
    client = TestClient(create_app(tmp_path / "nope.yaml", RULES_PATH))
    res = client.post("/api/allocations")
    assert res.status_code == 503
    assert error(res)["code"] == "not_configured"


def test_wrong_working_directory_is_not_configured(tmp_path, monkeypatch):
    cfg = make_private_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = TestClient(create_app(cfg)).post("/api/allocations")
    assert res.status_code == 503
    assert error(res)["code"] == "not_configured"
    assert "make api" in error(res)["message"]


def test_invalid_data_is_data_invalid(tmp_path):
    client = make_client(tmp_path)
    p = private_root(tmp_path) / "derived" / "2027" / "teachers.csv"
    p.write_text(p.read_text().replace("True", "maybe", 1))
    res = client.post("/api/allocations")
    assert res.status_code == 503
    assert error(res)["code"] == "data_invalid"


def test_double_placement_is_data_invalid(tmp_path, monkeypatch):
    def twice(*_):
        raise SystemExit("office has 1 teacher(s) placed twice")

    monkeypatch.setattr(review, "load_office", twice)
    res = make_client(tmp_path, raise_server_exceptions=False).post("/api/allocations")
    assert res.status_code == 503
    assert error(res)["code"] == "data_invalid"


def test_infeasible_names_conflicting_rules(tmp_path):
    client = make_client(tmp_path)
    p = private_root(tmp_path) / "params" / "course_params.csv"
    p.write_text(
        "\n".join(
            "2027,INTL-1,,0,0,0,0,,assumed"
            if line.strip().startswith("2027, INTL-1")
            else line
            for line in p.read_text().splitlines()
        )
        + "\n"
    )
    res = client.post("/api/allocations")
    assert res.status_code == 422
    assert error(res)["code"] == "infeasible"
    ids = re.findall(r"\d+", error(res)["message"])
    assert "0" in ids


def test_timeout_is_solver_timeout(tmp_path, monkeypatch):
    def timeout(*_, **__):
        raise RuntimeError("timed out checking T1000")

    monkeypatch.setattr(model, "determinacy", timeout)
    res = make_client(tmp_path).post("/api/allocations")
    assert res.status_code == 504
    assert error(res)["code"] == "solver_timeout"
    assert "T1000" not in res.text


def test_unexpected_error_hides_its_message(tmp_path, monkeypatch):
    def boom(*_, **__):
        raise KeyError(str(tmp_path))

    monkeypatch.setattr(review, "review_run", boom)
    res = make_client(tmp_path, raise_server_exceptions=False).post("/api/allocations")
    assert res.status_code == 500
    assert error(res)["code"] == "internal"
    assert str(tmp_path) not in res.text


def test_busy_while_lock_is_held(tmp_path):
    app = create_app(make_private_root(tmp_path), RULES_PATH)
    client = TestClient(app)
    assert app.state.solve_lock.acquire(blocking=False)
    try:
        res = client.post("/api/allocations")
        assert res.status_code == 409
        assert error(res)["code"] == "busy"
    finally:
        app.state.solve_lock.release()
    assert client.post("/api/allocations").status_code == 200


def test_lock_is_released_after_failure(tmp_path):
    app = create_app(tmp_path / "nope.yaml", RULES_PATH)
    res = TestClient(app).post("/api/allocations")
    assert res.status_code == 503
    assert not app.state.solve_lock.locked()


def test_importing_the_module_does_not_read_the_config():
    # the module-level app exists although config/pseudonymize.yaml may be absent
    from stable_sponsors import api

    assert api.app.state.solve_lock is not None
