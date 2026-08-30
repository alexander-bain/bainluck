"""UX-P164: the futures DETAIL page and SEARCH stop printing "Other 100%".

This is #993's own opening sentence, verbatim, still true on two surfaces on
2026-08-29. Measured on the deployed build at the same moment:

    GET /api/futures/112903            -> Democratic Party 0.855 | Republican Party 0.145 | Other 1.0
    GET /api/events/search?q=which...  -> Democratic Party 0.855 | Republican Party 0.145 | Other 1.0

That third row is a no-bid ask (measured bid 0.0000 / ask 1.0000, gotcha #17/#19)
on a market whose real book is an 85.5/14.5 two-way. It renders as "Other 100%"
underneath two real answers.

WHY DEMOTION WAS NOT ENOUGH — and why this is NOT a re-litigation of UX-P126/F5.
`display_rank_order` DEMOTES a dominant field row to the end rather than deleting
it, deliberately: "the field's share stays visible" is pinned by
`test_other_at_100_leaves_the_top_n` and MUST NOT change. Demotion keeps the row
out of a top-N slot only while the list is LONGER than N. Neither of these two
surfaces satisfies that:

  * the detail page renders the WHOLE list, so "the end" is always on the page;
  * search has already sliced to `limit`, so "the end" is inside the dropdown.

So the module's own stated rule — a dominant field outcome "must not occupy a
leader or top-N slot" — was not achieved by ordering alone on either one.

WHY THE DROP GOES AFTER NORMALIZATION, which is the load-bearing design decision
here and the one this file spends the most assertions on. `_FIELD_DOMINANT_MIN`
is documented as judging the number RENDERED, not the raw price. A field row whose
RAW price is >= 0.9 but which the #23 squeeze brings BELOW the threshold
"genuinely carries most of the probability mass" and is INFORMATION. Dropping
before normalization would delete it. Both directions are asserted below.

BOTH SURFACES MOVE IN ONE QUEUE, ON PURPOSE. They are the exact pair #993 was
about keeping in agreement; fixing one would have moved the disagreement rather
than ending it. That is UX-P162's lesson, applied before it could bite.
"""

import inspect

import pytest

from app.utils.outcome_display import (
    _FIELD_DOMINANT_MIN,
    display_rank_order,
    drop_dominant_field_outcomes,
    leader_pick_order,
    normalize_display_probs,
)

# The EXACT rows `/api/futures/112903` and `/api/events/search` both served on
# 2026-08-29. Not a plausible reconstruction — copied off the live payloads.
LIVE_112903 = [
    {"name": "Democratic Party", "probability": 0.855},
    {"name": "Republican Party", "probability": 0.145},
    {"name": "Other", "probability": 1.0},
]


def _name_of(o):
    return o.get("name")


def _prob_of(o):
    return o.get("probability")


def _pipeline_before(rows, mutually_exclusive=True):
    """The shipped pre-fix pipeline, shared by detail and search."""
    out = [dict(r) for r in rows]
    normalize_display_probs(out, mutually_exclusive=mutually_exclusive)
    leader_pick_order(out)
    return out


def _pipeline_after(rows, mutually_exclusive=True):
    """The same pipeline with the UX-P164 drop in its shipped position."""
    out = [dict(r) for r in rows]
    normalize_display_probs(out, mutually_exclusive=mutually_exclusive)
    out = drop_dominant_field_outcomes(out, _name_of, _prob_of)
    leader_pick_order(out)
    return out


class TestThePreFixOutputIsWhatItClaims:
    """Pin the DIAGNOSIS, not just the fix. If this stops reproducing, the comments
    explaining why the fix exists are describing a payload that no longer occurs."""

    def test_the_pre_fix_pipeline_reproduces_the_live_payload(self):
        got = [(o["name"], o["probability"]) for o in _pipeline_before(LIVE_112903)]
        assert got == [
            ("Democratic Party", 0.855),
            ("Republican Party", 0.145),
            ("Other", 1.0),
        ]

    def test_normalization_is_skipped_on_this_market_and_that_is_why(self):
        # Raw sum is 0.855 + 0.145 + 1.0 = 2.0, past `_FIELD_SUM_MAX` (1.60), so the
        # #1200 overround guard returns early and the prices stay raw. The no-bid
        # 1.0 is what pushes the sum over that line — which is also why the row
        # cannot be judged on a normalized number that never gets computed.
        assert sum(o["probability"] for o in LIVE_112903) == pytest.approx(2.0)
        out = [dict(r) for r in LIVE_112903]
        normalize_display_probs(out)
        assert [o["probability"] for o in out] == [0.855, 0.145, 1.0]

    def test_demotion_alone_cannot_help_a_three_row_list(self):
        # `display_rank_order` is CORRECT and unchanged — it moves the row to the
        # end. On three rows "the end" is still on the page.
        ranked = display_rank_order(LIVE_112903, _name_of, _prob_of)
        assert ranked[-1]["name"] == "Other"
        assert len(ranked) == 3


class TestTheFix:
    def test_the_dominant_field_row_is_gone(self):
        got = [(o["name"], o["probability"]) for o in _pipeline_after(LIVE_112903)]
        assert got == [("Democratic Party", 0.855), ("Republican Party", 0.145)]

    def test_the_two_real_answers_keep_their_book_prices(self):
        # The drop must narrow WHAT IS SHOWN without restating either number. 0.855
        # is what the book says and what the market page has been serving all along.
        after = _pipeline_after(LIVE_112903)
        assert after[0]["probability"] == 0.855
        assert after[1]["probability"] == 0.145

    def test_no_field_outcome_survives_at_or_above_the_threshold(self):
        for o in _pipeline_after(LIVE_112903):
            assert not (o["name"] == "Other" and o["probability"] >= _FIELD_DOMINANT_MIN)


class TestTheInformationCarveOutSurvives:
    """THE REVERSE DIRECTION, and the reason the drop sits AFTER normalization.
    Only the ~100% artifact is suppressed; a field that genuinely holds mass stays."""

    def test_a_field_normalization_pulls_under_the_threshold_is_kept(self):
        # RAW "Other" is 0.95 — at first glance a drop candidate. The field sums to
        # 1.45, inside the normalizable band, so the #23 squeeze renders it at
        # ~0.655. That is a wide-open race, not an artifact, and it must survive.
        rows = [
            {"name": "Candidate X", "probability": 0.30},
            {"name": "Candidate Y", "probability": 0.20},
            {"name": "Other", "probability": 0.95},
        ]
        after = _pipeline_after(rows)
        names = [o["name"] for o in after]
        assert "Other" in names, "a field carrying real mass is INFORMATION"
        other = next(o for o in after if o["name"] == "Other")
        assert other["probability"] < _FIELD_DOMINANT_MIN
        assert other["probability"] == pytest.approx(0.655, abs=1e-3)

    def test_dropping_before_normalization_would_have_deleted_it(self):
        # The counterfactual, asserted rather than argued: judged on the RAW price
        # the same row disappears. This is what the ordering buys.
        rows = [
            {"name": "Candidate X", "probability": 0.30},
            {"name": "Candidate Y", "probability": 0.20},
            {"name": "Other", "probability": 0.95},
        ]
        premature = drop_dominant_field_outcomes(
            [dict(r) for r in rows], _name_of, _prob_of
        )
        assert [o["name"] for o in premature] == ["Candidate X", "Candidate Y"]

    def test_a_plurality_field_is_untouched(self):
        rows = [
            {"name": "Other", "probability": 0.55},
            {"name": "Gavin Newsom", "probability": 0.22},
        ]
        assert "Other" in [o["name"] for o in _pipeline_after(rows)]

    def test_threshold_boundary_is_inclusive_and_unmoved(self):
        # Judged post-normalization, so use an overrounded field (sum > 1.60) where
        # the raw price IS the rendered one.
        below = [
            {"name": "Other", "probability": 0.89},
            {"name": "Real", "probability": 0.85},
        ]
        at = [
            {"name": "Other", "probability": 0.90},
            {"name": "Real", "probability": 0.85},
        ]
        assert "Other" in [o["name"] for o in _pipeline_after(below)]
        assert "Other" not in [o["name"] for o in _pipeline_after(at)]


class TestNeverEmpties:
    def test_an_all_field_market_still_renders(self):
        rows = [
            {"name": "Other", "probability": 1.0},
            {"name": "The Field", "probability": 0.99},
        ]
        after = _pipeline_after(rows)
        assert len(after) == 2, "an honest-empty decision belongs to the surface"

    def test_a_single_dominant_field_row_is_not_wiped(self):
        rows = [{"name": "Other", "probability": 1.0}]
        assert len(_pipeline_after(rows)) == 1

    def test_missing_probabilities_do_not_crash(self):
        rows = [
            {"name": "Real", "probability": None},
            {"name": "Other", "probability": None},
        ]
        assert len(_pipeline_after(rows)) == 2


class TestBothSerializersMoved:
    """Source-level, because both are big DB-shaped functions the endpoints prove
    end-to-end. Anchored on the CALL SITE rather than the bare name: UX-P163 paid
    for a `src.index("<name>")` assertion that matched the mention inside the
    comment written directly above the fix and failed on a correct file."""

    def test_detail_serializer_drops_before_leader_pick(self):
        from app.routes import futures

        src = inspect.getsource(futures._format_market_detail)
        drop_at = src.index("outcomes = drop_dominant_field_outcomes(")
        norm_at = src.index("normalize_display_probs(\n")
        pick_at = src.index("leader_pick_order(outcomes)")
        assert norm_at < drop_at < pick_at, (
            "the drop must judge the RENDERED number (after normalization) and "
            "agree with the demotion (before leader-pick)"
        )

    def test_search_serializer_drops_before_leader_pick(self):
        from app.routes import events

        src = inspect.getsource(events._build_search_top_outcomes)
        drop_at = src.index("out = _drop_dominant_field_outcomes(")
        norm_at = src.index("_normalize_search_outcome_probs(")
        pick_at = src.index("return _leader_pick_order(out)")
        assert norm_at < drop_at < pick_at

    def test_search_and_detail_cannot_diverge_on_this_market(self):
        # #993's actual requirement: the click-through MATCHES the answer search
        # gave. Search slices to `limit` first; on this market that changes nothing
        # (three rows), and both surfaces must land on the same two.
        search_side = _pipeline_after(LIVE_112903[:5])
        detail_side = _pipeline_after(LIVE_112903)
        assert [o["name"] for o in search_side] == [o["name"] for o in detail_side]


class TestTheApiContract:
    """Dropping a row changes `outcome_count`, which has real consumers. Each one
    was checked; these pin the answers so a later reader does not have to re-derive
    them."""

    def test_outcome_count_goes_three_to_two_on_this_market(self):
        # `outcome_count` on the detail payload is `len(outcomes)` — ALREADY the
        # placeholder-filtered count, never the raw 9 this market holds. So it keeps
        # meaning "how many rows are on the page", which is the honest reading.
        assert len(_pipeline_before(LIVE_112903)) == 3
        assert len(_pipeline_after(LIVE_112903)) == 2

    def test_concept_derivation_is_decoupled_from_the_display_drop(self):
        # `derive_market_concept_key` forwards its outcome count to the combat
        # adapters, which gate on `n_outcomes == 2` (event_combat.py:245, :356). A
        # DISPLAY rule feeding that could flip a 3-outcome market into a
        # fight-shaped one and invent a breadcrumb. The serializer must therefore
        # pass a count captured BEFORE the drop.
        from app.routes import futures

        src = inspect.getsource(futures._format_market_detail)
        capture_at = src.index("concept_outcome_count = len(outcomes)")
        drop_at = src.index("outcomes = drop_dominant_field_outcomes(")
        assert capture_at < drop_at, "the count must be captured pre-drop"
        # Anchor on the CALL, not the token. `"outcome_count": len(outcomes)` in the
        # response dict is a DIFFERENT and correct use of the post-drop length — it
        # reports how many rows the page shows. Only the derive call must be pre-drop.
        call = src[src.index("derive_market_concept_key(") :]
        call = call[: call.index(")")]
        assert "concept_outcome_count" in call
        assert "len(outcomes)" not in call, "the pre-drop count must be the one passed"

    def test_the_combat_gate_this_protects_is_real(self):
        # Not asserted from memory — read the predicate back.
        from app.utils import event_combat

        assert "n_outcomes == 2" in inspect.getsource(event_combat)


class TestTheDemotionContractIsUntouched:
    """UX-P164 adds a caller; it must not have edited the rule UX-P126/F5 pinned."""

    def test_display_rank_order_still_demotes_rather_than_deletes(self):
        outs = [
            {"name": "Byrum Brown", "probability": 0.475},
            {"name": "Other", "probability": 1.0},
            {"name": "Duce Robinson", "probability": 0.475},
            {"name": "Brendan Sorsby", "probability": 0.465},
        ]
        ranked = display_rank_order(outs, _name_of, _prob_of)
        assert ranked[-1]["name"] == "Other"
        assert len(ranked) == 4, "demote-not-delete is deliberate and still pinned"

    def test_the_drop_and_the_demotion_share_one_threshold(self):
        # They can never disagree about which rows they mean.
        src = inspect.getsource(drop_dominant_field_outcomes)
        assert "_FIELD_DOMINANT_MIN" in src
        assert "_FIELD_DOMINANT_MIN" in inspect.getsource(display_rank_order)
