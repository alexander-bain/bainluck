"""#9937: the export tool can copy grouping grades into the grades store.

Fable, Nov 11: Alex's 20 held-out exam grades sit in ``ranking_grades`` under
``surface="grouping"``, and ``tools/ranking/grades.py export`` read only the
Discover grades endpoint. So Atlas could not score the exam from the repo.

What must hold:
* ``export --surface grouping`` reads ``GET /api/admin/ranking/grouping-grades``
  for the named slate; with no ``--surface`` it reads the Discover endpoint as
  before;
* ``--adults-only`` leaves every kid's row out of the files entirely;
* each exported row keeps its position, item key, grade, note and graded-at;
* a grouping file validates on the grouping grades (amazing, fine, no), and a
  Discover file still only on shareable, interesting, neither.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLATE = "new-kinds-exam-test-2026-11"


def _tool():
    spec = importlib.util.spec_from_file_location("grades_9937", REPO / "tools" / "ranking" / "grades.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(position, grade, grader="Alex Bain", expert=True, note=""):
    return {"slate_id": SLATE, "surface": "grouping", "grader": grader, "expert": expert,
            "position": position, "item_key": f"proposal:{position}", "grade": grade, "note": note,
            "graded_at": "2026-11-11T05:10:00+00:00"}


def test_adults_only_leaves_every_kid_row_out():
    gr = _tool()
    rows = [_row(1, "amazing"), _row(2, "no", note="too busy"), _row(1, "fine", grader="Sam", expert=False)]
    (doc,) = gr.export_documents(rows, adults_only=True)
    assert doc["grader"] == "Alex Bain" and doc["expert"] is True and doc["surface"] == "grouping"
    assert "Sam" not in json.dumps(doc) and "kid" not in json.dumps(doc)
    assert doc["items"] == [
        {"position": 1, "item_key": "proposal:1", "grade": "amazing", "note": "",
         "graded_at": "2026-11-11T05:10:00+00:00"},
        {"position": 2, "item_key": "proposal:2", "grade": "no", "note": "too busy",
         "graded_at": "2026-11-11T05:10:00+00:00"},
    ]
    # 05:10Z Nov 11 is still Nov 10 in Pacific time.
    assert doc["date"] == "2026-11-10"


def test_without_adults_only_a_kid_is_still_a_pseudonym():
    gr = _tool()
    docs = gr.export_documents([_row(1, "amazing"), _row(1, "fine", grader="Sam", expert=False)])
    kid = next(d for d in docs if d["expert"] is False)
    assert gr.KID_ID.match(kid["grader"]) and "Sam" not in json.dumps(kid)


def test_grades_validate_against_their_own_surface():
    gr = _tool()
    grouping = {"slate_id": SLATE, "surface": "grouping", "grader": "Alex Bain", "expert": True,
                "items": [{"position": 1, "grade": "amazing"}, {"position": 2, "grade": "Fine"},
                          {"position": 3, "grade": "no"}]}
    assert gr.validate_grades(grouping) == []
    assert gr.validate_grades({**grouping, "items": [{"position": 1, "grade": "shareable"}]})
    discover = {**grouping, "surface": "discover", "items": [{"position": 1, "grade": "interesting"}]}
    assert gr.validate_grades(discover) == []
    assert gr.validate_grades({**discover, "items": [{"position": 1, "grade": "amazing"}]})
    # A file with no surface is a Discover file, as before.
    assert gr.validate_grades({k: v for k, v in discover.items() if k != "surface"}) == []


def _run_export(gr, monkeypatch, tmp_path, argv, rows):
    seen = []

    def fake_get(path):
        seen.append(path)
        return {"grades": rows}

    monkeypatch.setattr(gr, "_admin_get", fake_get)
    assert gr.main(["export", *argv, "--out", str(tmp_path)]) == 0
    return seen


def test_export_surface_grouping_reads_the_grouping_endpoint(monkeypatch, tmp_path):
    gr = _tool()
    rows = [_row(n, "fine") for n in range(1, 21)] + [_row(1, "no", grader="Sam", expert=False)]
    seen = _run_export(gr, monkeypatch, tmp_path,
                       ["--surface", "grouping", "--slate", SLATE, "--days", "30", "--adults-only"], rows)
    assert seen == [f"/api/admin/ranking/grouping-grades?days=30&slate_id={SLATE}"]
    (path,) = tmp_path.iterdir()
    assert path.name == f"2026-11-10-grouping-{SLATE}-alex-bain.json"
    doc = json.loads(path.read_text())
    assert len(doc["items"]) == 20 and gr.validate_grades(doc) == []


def test_export_with_no_surface_reads_the_discover_endpoint_as_before(monkeypatch, tmp_path):
    gr = _tool()
    row = {**_row(1, "interesting"), "surface": "discover", "slate_id": "s"}
    seen = _run_export(gr, monkeypatch, tmp_path, ["--slate", "s"], [row])
    assert seen == ["/api/admin/ranking/grades?days=14&slate_id=s"]
