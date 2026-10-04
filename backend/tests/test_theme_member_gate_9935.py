"""#9925 / #9935 P3 — an awards question is asked of awards markets.

THE DEFECT, from #9925's audit: `_story_key` mints
`story:major_entertainment_events` from the name alone (`\\boscars?\\b`), so
`61082201` "Sandoval vs Oscar Collazo" (boxing) and `63448382` / `63448383`
"Oscar Brown vs …" (an M15 Baku tennis match) key into Awards Season and sit
under "Who wins awards season?" beside Best Picture (`6173044`). The awards
`group_id` bundler already requires entertainment; the story-theme bundler had
no such gate on either of its two admission sites.

Also here: the public `theme_member_withhold_reason(...)` helper a collection
page imports to decide membership by the same rule the feed folds by, and the
pin that it and `_theme_member_eligible` are one predicate.

Tennis opponent names are elided in the audit; the fixtures below keep the
part the bug keys on ("Oscar") and the category the gate reads.
"""

import ast
import inspect

import pytest

import app.utils.discover_bundles as discover_bundles
from app.utils.discover_bundles import (
    _member_fits_story,
    _theme_member_eligible,
    _theme_story_key,
    _theme_withhold_reason_for,
    assemble_story_theme_bundles,
    theme_member_withhold_reason,
)

AWARDS = "story:major_entertainment_events"


def _member(
    market_id: int,
    name: str,
    llm_sport_category: str,
    score: float = 72.0,
    **extra,
) -> dict:
    item = {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "_sort_time": 0.0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": llm_sport_category,
            "canonical_market_key": None,
            "discover_card": {},
        },
    }
    item.update(extra)
    return item


BEST_PICTURE = _member(
    6173044, "Oscars 2027: Best Picture Winner", "entertainment", 90.0
)
ALBUM_OF_YEAR = _member(
    9935001, "Grammys 2027: Album of the Year", "entertainment", 85.0
)
BOXER = _member(61082201, "Sandoval vs Oscar Collazo", "boxing", 88.0)
TENNIS_A = _member(63448382, "Oscar Brown vs Ivan Petrov", "tennis", 87.0)
TENNIS_B = _member(63448383, "Oscar Brown vs Ivan Petrov: Set 1 Winner", "tennis", 86.0)
NEAR_MISSES = [BOXER, TENNIS_A, TENNIS_B]


def _bundles(out: list[dict]) -> list[dict]:
    return [item for item in out if item.get("type") == "bundle"]


def _standalone_ids(out: list[dict]) -> set:
    return {item["data"]["id"] for item in out if item.get("type") == "futures"}


# ── Preconditions: the specimens really do key into Awards Season ───────────


@pytest.mark.parametrize("item", [BEST_PICTURE, ALBUM_OF_YEAR, *NEAR_MISSES])
def test_every_specimen_keys_into_awards_season(item):
    """Without this the refusals below could pass because the near-misses
    never reached the family at all."""
    assert _theme_story_key(item) == AWARDS


# ── The gate ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("item", NEAR_MISSES, ids=lambda i: str(i["data"]["id"]))
def test_a_non_entertainment_oscar_does_not_fit_awards_season(item):
    assert _member_fits_story(AWARDS, item) is False


@pytest.mark.parametrize("item", [BEST_PICTURE, ALBUM_OF_YEAR])
def test_an_entertainment_awards_market_fits(item):
    assert _member_fits_story(AWARDS, item) is True


def test_a_family_with_no_category_claim_is_unchanged():
    """The gate is one key's claim, not a general relevance test."""
    tennis = _member(1, "Wimbledon 2027 Winner", "tennis")
    assert _theme_story_key(tennis) == "story:grand_slam_tennis"
    assert _member_fits_story("story:grand_slam_tennis", tennis) is True
    assert _member_fits_story("story:grand_slam_tennis", BOXER) is True


# ── Admission site 1: the main loop ─────────────────────────────────────────


def test_main_loop_refuses_the_near_misses_and_keeps_best_picture():
    out = assemble_story_theme_bundles([BEST_PICTURE, *NEAR_MISSES, ALBUM_OF_YEAR])

    bundles = _bundles(out)
    assert len(bundles) == 1
    assert bundles[0]["data"]["member_ids"] == [6173044, 9935001]


def test_a_refused_member_still_emits_as_its_own_card():
    out = assemble_story_theme_bundles([BEST_PICTURE, *NEAR_MISSES, ALBUM_OF_YEAR])
    assert _standalone_ids(out) == {61082201, 63448382, 63448383}


def test_near_misses_alone_cannot_form_an_awards_bundle():
    """Before the gate, three Oscars-by-name rows folded into a bundle
    headed "Who wins awards season?" with no award in it."""
    out = assemble_story_theme_bundles(list(NEAR_MISSES))
    assert _bundles(out) == []
    assert _standalone_ids(out) == {61082201, 63448382, 63448383}


# ── Admission site 2: the story-cap overflow top-up ─────────────────────────


def test_overflow_top_up_refuses_the_near_misses():
    reserve = [
        *NEAR_MISSES,
        _member(9935002, "Emmys 2027: Best Drama Series", "entertainment"),
    ]
    carrier_a = dict(BEST_PICTURE, _story_overflow_members=reserve)
    carrier_b = dict(ALBUM_OF_YEAR, _story_overflow_members=reserve)

    out = assemble_story_theme_bundles([carrier_a, carrier_b])

    bundles = _bundles(out)
    assert len(bundles) == 1
    assert bundles[0]["data"]["member_ids"] == [6173044, 9935001, 9935002]
    served = repr(bundles[0])
    assert "Collazo" not in served
    assert "Oscar Brown" not in served


# ── Set-pin: the gate sits beside #7552's guard at BOTH sites ───────────────


def _calls_by_function(callee: str) -> list[str]:
    tree = ast.parse(inspect.getsource(discover_bundles))
    sites = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == callee
            ):
                sites.append(fn.name)
    return sorted(sites)


def test_member_fits_story_is_called_exactly_where_the_question_guard_is():
    fits = _calls_by_function("_member_fits_story")
    answers = _calls_by_function("_member_answers_story_question")
    assert fits == ["_with_story_overflow", "assemble_story_theme_bundles"]
    assert fits == answers


# ── The public helper and the one predicate ─────────────────────────────────


@pytest.mark.parametrize(
    ("quality_class", "disagreement", "expected"),
    [
        ("suppress", False, "suppressed"),
        ("suppress", True, "suppressed"),
        ("low_quality", False, "low_quality"),
        ("low_quality", True, "low_quality"),
        ("normal", True, "public_source_disagreement"),
        ("compelling", True, "public_source_disagreement"),
        ("normal", False, None),
        ("compelling", False, None),
        (None, False, None),
    ],
)
def test_withhold_reason_truth_table(quality_class, disagreement, expected):
    assert _theme_withhold_reason_for(quality_class, disagreement) == expected


@pytest.mark.parametrize(
    ("quality_class", "disagreement"),
    [
        (qc, d)
        for qc in (None, "compelling", "normal", "low_quality", "suppress")
        for d in (False, True)
    ],
)
def test_feed_eligibility_and_the_helper_are_one_predicate(quality_class, disagreement):
    item = _member(1, "x", "entertainment")
    item["_quality_class"] = quality_class
    item["data"]["discover_card"]["public_source_disagreement"] = disagreement
    assert _theme_member_eligible(item) is (
        _theme_withhold_reason_for(quality_class, disagreement) is None
    )


def test_public_helper_classifies_then_applies_the_same_predicate(monkeypatch):
    seen = {}

    class _Quality:
        quality_class = "low_quality"

    def _fake_classify(**kwargs):
        seen.update(kwargs)
        return _Quality()

    monkeypatch.setattr(discover_bundles, "classify_market_quality", _fake_classify)
    reason = theme_member_withhold_reason(
        market_name="Oscars 2027: Best Picture Winner",
        sport_category="entertainment",
        outcome_names=["Film A", "Film B"],
        external_id="KXOSCARPIC-27",
        status="open",
    )
    assert reason == "low_quality"
    assert seen == {
        "market_name": "Oscars 2027: Best Picture Winner",
        "sport_category": "entertainment",
        "outcome_names": ["Film A", "Film B"],
        "external_id": "KXOSCARPIC-27",
        "status": "open",
    }


def test_public_helper_reports_disagreement_on_a_clean_market():
    reason = theme_member_withhold_reason(
        market_name="Oscars 2027: Best Picture Winner",
        sport_category="entertainment",
        public_source_disagreement=True,
    )
    clean = theme_member_withhold_reason(
        market_name="Oscars 2027: Best Picture Winner",
        sport_category="entertainment",
    )
    assert clean is None
    assert reason == "public_source_disagreement"


def test_public_helper_signature_is_keyword_only():
    params = inspect.signature(theme_member_withhold_reason).parameters
    assert list(params) == [
        "market_name",
        "sport_category",
        "outcome_names",
        "external_id",
        "status",
        "public_source_disagreement",
    ]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())
