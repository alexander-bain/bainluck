"""#8278 — the pinned game-1 score repair decides exactly what it was read to decide."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "repair_8278_doubleheader_game1_scores.py"
_spec = importlib.util.spec_from_file_location("repair_8278_scores", _PATH)
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)

NYY, BAL = 14788069, 15316846
TAG = "provenance:duplicate-of:15316824"


def _prod_state():
    scores = {NYY: (1, 6), BAL: (4, 0)}
    tags = {NYY: ["narrative:rivalry", TAG]}
    return scores, tags, set()


def test_the_pins_are_mlbs_finals():
    # MLB 823543: TB 0 @ NYY 2. MLB 824785: TOR 2 @ BAL 4. Home first.
    assert repair.PINNED_SCORES[NYY][1] == (2, 0)
    assert repair.PINNED_SCORES[BAL][1] == (4, 2)


def test_apply_on_the_production_read_writes_both_scores_and_the_tag():
    out = repair.plan(*_prod_state(), restore=False)
    assert out["scores"] == [(NYY, (1, 6), (2, 0)), (BAL, (4, 0), (4, 2))]
    assert out["tags"] == [(NYY, TAG)]
    assert out["skip"] == []


def test_restore_is_the_exact_inverse():
    scores = {NYY: (2, 0), BAL: (4, 2)}
    tags = {NYY: ["narrative:rivalry"]}
    out = repair.plan(scores, tags, set(), restore=True)
    assert out["scores"] == [(NYY, (2, 0), (1, 6)), (BAL, (4, 2), (4, 0))]
    assert out["tags"] == [(NYY, TAG)]


def test_a_second_apply_writes_nothing():
    scores = {NYY: (2, 0), BAL: (4, 2)}
    tags = {NYY: ["narrative:rivalry"]}
    out = repair.plan(scores, tags, set(), restore=False)
    assert out["scores"] == [] and out["tags"] == []
    assert len(out["skip"]) == 3


@pytest.mark.parametrize("drifted", [(9, 9), (None, None), (0, 2)])
def test_a_row_that_moved_since_it_was_read_refuses_the_whole_run(drifted):
    scores, tags, live = _prod_state()
    scores[BAL] = drifted
    with pytest.raises(repair.Refused):
        repair.plan(scores, tags, live, restore=False)


def test_a_live_tag_target_refuses():
    scores, tags, _ = _prod_state()
    with pytest.raises(repair.Refused):
        repair.plan(scores, tags, {15316824}, restore=False)


def test_a_missing_row_is_skipped_not_invented():
    scores, tags, live = _prod_state()
    del scores[BAL]
    out = repair.plan(scores, tags, live, restore=False)
    assert (BAL, "row missing") in out["skip"]
    assert [w[0] for w in out["scores"]] == [NYY]


@pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
def test_off_production_refuses(app):
    with pytest.raises(repair.Refused):
        repair.refuse_unless_production({"HEROKU_APP_NAME": app})


@pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
def test_production_apps_pass(app):
    repair.refuse_unless_production({"HEROKU_APP_NAME": app})
