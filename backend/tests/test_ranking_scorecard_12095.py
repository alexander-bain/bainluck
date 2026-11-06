"""#12095 Decide 37-B: every scorecard metric, the UNKNOWN cases, and replay.

``tools/ranking/scorecard.py`` and ``tools/ranking/grades.py`` are stdlib-only
scripts; they are loaded by path so the tests read exactly what Alex runs.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / "ranking" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sc = _load("scorecard")
gr = _load("grades")


def cand(i, *, cat="politics", ents=("X",), prob=0.5, age=600.0, move=0.0, pos=None, **flags):
    return {
        "item_key": f"futures:{i}",
        "title": f"Card {i}",
        "category": cat,
        "entities": list(ents),
        "probability": prob,
        "price_age_s": age,
        "movement_24h": move,
        "served_position": pos,
        "settled": flags.get("settled", False),
        "settled_without_result": flags.get("settled_without_result", False),
        "stale": flags.get("stale", False),
        "blend_missing": flags.get("blend_missing", False),
    }


def slate(n=12, slate_id="s1", captured="2026-11-06T12:15:00+00:00", **kw):
    cands = [cand(i, pos=i, ents=(f"E{i}",), **kw) for i in range(1, n + 1)]
    return {
        "slate_id": slate_id,
        "surface": "discover",
        "captured_at": captured,
        "ranker_version": "abc",
        "served_order": [c["item_key"] for c in cands],
        "candidates": cands,
    }


def grades(items, *, grader="alex", expert=True, slate_id="s1"):
    return {
        "slate_id": slate_id,
        "surface": "discover",
        "grader": grader,
        "expert": expert,
        "items": [{"item_key": k, "grade": g} for k, g in items.items()],
    }


ORDER = [f"futures:{i}" for i in range(1, 11)]


class TestNDCG:
    def test_no_grades_is_unknown_never_zero(self):
        out = sc.ndcg_at(ORDER, {})
        assert out["value"] is None and out["reason"] == "no grades"
        assert sc._fmt_ndcg(out).startswith("UNKNOWN")

    def test_a_perfect_order_is_one(self):
        ladder = {f"futures:{i}": ("shareable" if i <= 3 else "interesting" if i <= 6 else "neither") for i in range(1, 11)}
        gains = sc.item_gains([grades(ladder)], expert=True)
        out = sc.ndcg_at(ORDER, gains)
        assert out["value"] == pytest.approx(1.0) and out["ungraded"] == 0
        assert sc._fmt_ndcg(out) == "1.000"

    def test_a_reversed_order_scores_the_textbook_value(self):
        gains = {f"futures:{i}": 0 for i in range(1, 11)} | {"futures:9": 1, "futures:10": 2}
        dcg = 1 / math.log2(10) + 2 / math.log2(11)
        idcg = 2 / math.log2(2) + 1 / math.log2(3)
        assert sc.ndcg_at(ORDER, gains)["value"] == pytest.approx(dcg / idcg)

    def test_founders_average_and_kids_stay_separate(self):
        docs = [
            grades({"futures:1": "shareable"}, grader="alex"),
            grades({"futures:1": "neither"}, grader="bain"),
            grades({"futures:1": "interesting", "futures:2": "shareable"}, grader="kid1", expert=False),
        ]
        assert sc.item_gains(docs, expert=True) == {"futures:1": 1.0}
        assert sc.item_gains(docs, expert=False) == {"futures:1": 1.0, "futures:2": 2.0}

    def test_one_graded_card_is_unknown_not_one(self):
        # Fable 8: with ungraded = 0, one graded card alone scores 1.000 — an
        # overstatement, not a bound. More than three ungraded is UNKNOWN.
        out = sc.ndcg_at(ORDER, {"futures:2": 2})
        assert out["value"] is None and out["ungraded"] == 9
        assert sc._fmt_ndcg(out) == "UNKNOWN (9 of the top 10 ungraded (more than 3))"

    def test_up_to_three_ungraded_is_a_labelled_partial(self):
        gains = {f"futures:{i}": 1 for i in range(1, 8)}
        out = sc.ndcg_at(ORDER, gains)
        assert out["value"] is not None and out["ungraded"] == 3
        assert sc._fmt_ndcg(out).endswith("**3 ungraded** (partial; ungraded = 0)")
        assert "lower bound" not in sc._fmt_ndcg(out)
        assert sc.ndcg_at(ORDER, {f"futures:{i}": 1 for i in range(1, 7)})["value"] is None  # 4 ungraded

    def test_no_graded_card_in_the_top_ten_and_all_neither_are_unknown(self):
        assert sc.ndcg_at(ORDER, {"futures:99": 2})["value"] is None
        assert sc.ndcg_at(ORDER, {f"futures:{i}": 0 for i in range(1, 11)})["reason"] == "every graded card is 'neither'"

    def test_grades_are_normalized_and_a_file_without_an_explicit_expert_is_skipped(self, tmp_path, capsys):
        good = grades({"futures:1": "  Shareable "})
        no_flag = {k: v for k, v in grades({"futures:2": "shareable"}, grader="who").items() if k != "expert"}
        bad = grades({"futures:3": "cool"}, grader="typo")
        for name, doc in (("a.json", good), ("b.json", no_flag), ("c.json", bad)):
            (tmp_path / name).write_text(json.dumps(doc))
        docs = sc.load_grades(tmp_path, "s1")
        assert [d["grader"] for d in docs] == ["alex"]
        assert docs[0]["items"][0]["grade"] == "shareable"
        err = capsys.readouterr().err
        assert "b.json" in err and "`expert` must be true or false" in err and "c.json" in err


class TestShapeMetrics:
    def test_entropy(self):
        assert sc.category_entropy([cand(i, cat="a") for i in range(10)]) == 0
        two = [cand(i, cat="a" if i < 5 else "b") for i in range(10)]
        assert sc.category_entropy(two) == pytest.approx(1.0)
        assert sc.category_entropy([cand(i, cat=str(i)) for i in range(10)]) == pytest.approx(math.log2(10))
        assert sc.category_entropy([]) is None

    def test_max_entity_repeats_counts_each_card_once(self):
        cards = [cand(1, ents=("Dodgers", "Dodgers")), cand(2, ents=("Dodgers", "Yankees")), cand(3, ents=("Yankees",)), cand(4, ents=("Dodgers",))]
        assert sc.max_entity_repeats(cards) == (3, ["Dodgers"])
        assert sc.max_entity_repeats([cand(1, ents=())]) == (None, [])

    def test_sameness_against_the_previous_day(self):
        prev = {"served_order": ORDER[5:] + [f"futures:{i}" for i in range(20, 25)]}
        assert sc.sameness(ORDER, prev) == 5
        assert sc.sameness(ORDER, None) is None

    def test_freshness_median_age_and_moved_share_over_known_values(self):
        cards = [cand(1, age=60), cand(2, age=180, move=0.02), cand(3, age=None, move=None), cand(4, age=600, move=-0.05)]
        f = sc.freshness(cards)
        assert f["median_age_s"] == 180 and f["ages_known"] == 3
        assert f["moved_count"] == 2 and f["moves_known"] == 3 and f["moved_share"] == pytest.approx(2 / 3)
        empty = sc.freshness([cand(1, age=None, move=None)])
        assert empty["median_age_s"] is None and empty["moved_share"] is None

    def test_truth_gate_counts_only_recorded_true(self):
        cards = [
            cand(1, settled=True, settled_without_result=True),
            cand(2, stale=True, blend_missing=True),
            cand(3, settled=None, settled_without_result=None),
            cand(4),
        ]
        t = sc.truth_gate(cards)
        assert t["failures"] == 2 and t["settled_without_result"] == 1 and t["stale"] == 1 and t["blend_missing"] == 1
        assert t["settled_without_result_unknown"] == 1

    def test_a_finished_game_shown_with_its_result_is_counted_but_never_a_failure(self):
        cards = [cand(1, settled=True, settled_without_result=False), cand(2, settled=True, settled_without_result=True)]
        t = sc.truth_gate(cards)
        assert t["failures"] == 1 and t["settled_with_result"] == 1


class TestReplay:
    def test_movement_replay_reorders_the_pool_and_scores_against_the_same_grades(self):
        s = slate(12)
        for c in s["candidates"]:
            c["movement_24h"] = 0.0
        s["candidates"][11]["movement_24h"] = 0.09  # futures:12, unserved in the top ten
        s["candidates"][10]["movement_24h"] = None  # futures:11, unknown goes last
        order = sc.replay(s, sc.resolve_ranker("movement"))
        assert order[0] == "futures:12" and order[-1] == "futures:11"
        g = [grades({f"futures:{i}": "neither" for i in range(1, 13)} | {"futures:12": "shareable", "futures:10": "shareable"})]
        served = sc.score_ranking(s["served_order"], s, g, None)
        replayed = sc.score_ranking(order, s, g, None)
        assert served["ndcg_founder"]["value"] < replayed["ndcg_founder"]["value"]
        assert replayed["ndcg_founder"]["ungraded"] == 0

    def test_a_module_function_ranker_and_a_bad_spec(self):
        ranker = sc.resolve_ranker("builtins:list")  # module:function, returns candidates
        assert sc.replay(slate(2), ranker) == ["futures:1", "futures:2"]
        with pytest.raises(SystemExit):
            sc.resolve_ranker("not-a-builtin")
        s = slate(3)
        assert sc.replay(s, lambda cands: [c["item_key"] for c in reversed(cands)]) == ["futures:3", "futures:2", "futures:1"]


class TestEndToEnd:
    def test_main_prints_unknown_ndcg_and_computed_metrics_without_grades(self, tmp_path, capsys):
        path = tmp_path / "slate.json"
        path.write_text(json.dumps(slate(12)))
        assert sc.main(["--slate", str(path), "--grades-dir", str(tmp_path / "none"), "--replay", "movement"]) == 0
        out = capsys.readouterr().out
        assert "| NDCG@10 (founder) | UNKNOWN (no grades) | UNKNOWN (no grades) |" in out
        assert "| Sameness vs previous day | UNKNOWN | UNKNOWN |" in out
        assert "| Truth-gate failures (target 0) | 0 — settled without its result 0, stale 0, blend missing 0 |" in out
        assert "| Settled, shown with result (info) | 0 | 0 |" in out
        assert "replay: movement" in out

    def test_grades_and_previous_slate_are_found_on_disk(self, tmp_path, capsys):
        slates, gdir = tmp_path / "slates", tmp_path / "grades"
        slates.mkdir(), gdir.mkdir()
        today = slate(12)
        yesterday = slate(12, slate_id="s0", captured="2026-11-05T12:15:00+00:00")
        (slates / "a.json").write_text(json.dumps(today))
        (slates / "b.json").write_text(json.dumps(yesterday))
        full = {f"futures:{i}": "neither" for i in range(1, 11)} | {"futures:1": "shareable"}
        (gdir / "2026-11-06-discover-s1-alex.json").write_text(json.dumps(grades(full)))
        (gdir / "other.json").write_text(json.dumps(grades({"futures:1": "neither"}, slate_id="zzz")))
        sc.main(["--slate", str(slates / "a.json"), "--slates-dir", str(slates), "--grades-dir", str(gdir)])
        out = capsys.readouterr().out
        assert "| NDCG@10 (founder) | 1.000 |" in out
        assert "| Sameness vs previous day | 10 of 10 |" in out
        assert "founder graders: alex" in out


class TestGradingSheet:
    def test_sheet_has_the_opening_ten_and_writes_a_file_once(self, tmp_path, capsys):
        path = tmp_path / "slate.json"
        path.write_text(json.dumps(slate(12)))
        out = tmp_path / "grades"
        assert gr.main(["sheet", "--slate", str(path), "--grader", "kid1", "--kid", "--out", str(out)]) == 0
        # Named by the PT date and the slate id (two captures a day never collide).
        written = out / "2026-11-06-discover-s1-kid1.json"
        doc = json.loads(written.read_text())
        assert doc["expert"] is False and doc["grader"] == "kid1"
        assert [i["position"] for i in doc["items"]] == list(range(1, 11))
        assert all(i["grade"] is None for i in doc["items"])
        printed = capsys.readouterr().out
        assert "| 1 | Card 1 | 50% |" in printed and "Captured Fri Nov 6, 4:15 AM PT." in printed
        with pytest.raises(SystemExit):
            gr.main(["sheet", "--slate", str(path), "--grader", "kid1", "--kid", "--out", str(out)])

    def test_a_kid_grader_must_be_a_pseudonym(self, tmp_path):
        path = tmp_path / "slate.json"
        path.write_text(json.dumps(slate(12)))
        with pytest.raises(SystemExit, match="pseudonym"):
            gr.main(["sheet", "--slate", str(path), "--grader", "A Real Name", "--kid", "--out", str(tmp_path / "g")])
        assert not (tmp_path / "g").exists()

    def test_check_flags_a_grade_outside_the_three(self, tmp_path):
        bad = tmp_path / "g.json"
        bad.write_text(json.dumps({"slate_id": "s1", "grader": "a", "expert": True, "items": [{"position": 1, "grade": "cool"}]}))
        assert gr.main(["check", str(bad)]) == 1
        no_flag = tmp_path / "nf.json"
        no_flag.write_text(json.dumps({"slate_id": "s1", "grader": "a", "items": []}))
        assert gr.main(["check", str(no_flag)]) == 1
        named_kid = tmp_path / "nk.json"
        named_kid.write_text(json.dumps(grades({}, grader="A Real Name", expert=False)))
        assert gr.main(["check", str(named_kid)]) == 1
        good = tmp_path / "ok.json"
        good.write_text(json.dumps(grades({"futures:1": " Interesting "})))
        assert gr.main(["check", str(good)]) == 0
