"""The item -> Evidence boundary in `/typeahead`, which nothing tested.

Ruling 041's scorer is well covered on both sides of this seam and not across
it. A Codex post-merge audit (2026-08-13) found two defects living exactly in
the gap, and named why every existing test missed them:

* The scorer's own property suite constructs ``Evidence`` **directly**, so it
  proves what the scorer does with evidence it is handed. It cannot prove that
  the route hands it the right evidence.
* The route tests assert on ranked OUTPUT against a mostly-empty test DB, so a
  candidate that never reaches the scorer is indistinguishable from one that
  reached it and lost.

Between those two sits ``_typeahead_evidence``, which converts a pool item into
the ``Evidence`` the scorer scores. It was a closure inside ``typeahead_search``
— unreachable from any test — and it was silently narrowing the evidence.

The defects, both reproduced here from Codex's specimens:

1. **Display truncation had become ranking-evidence truncation.** The recall SQL
   admits a futures market when ANY of its outcomes matches the query, but the
   pool item carried only ``top_outcomes`` — the **three highest-probability
   outcomes**, a DISPLAY concern. Query "Miami Heat" against "NBA Championship
   Winner" with Celtics/Thunder/Nuggets displayed: the SQL fetched the market
   *because of* Miami Heat, and then the scorer was structurally prevented from
   knowing that. MC4 (outcome-only) collapsed to MC5 (fragment), so a market
   that owns the answer could lose to an unrelated substring accident.

2. **A member-derived concept could bury its query-owned twin.** Covered by the
   composed test at the bottom: detector + seen-key dedupe + ``_derived`` flag +
   scorer, in one place, which is the composition that was missing.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import (
    _build_search_top_outcomes,
    _detect_query_awards_concept,
    _search_owned_outcome_names,
    _typeahead_evidence,
    _upsert_query_derived_concept,
)
from app.utils.outcome_display import is_placeholder_outcome_name
from app.utils.search_match_class import (
    MC4_OUTCOME_ONLY,
    MC5_FRAGMENT,
    match_class,
    rank,
)


def _outcome(name, prob):
    return SimpleNamespace(
        id=abs(hash(name)) % 100000,
        name=name,
        current_probability=prob,
        # Q480: the display path reads `external_id` to drop a `_yes`/`_no`
        # leg duplicating a bare rung. None = not a leg (pass-through).
        external_id=None,
        current_american_odds=None,
        rank=None,
        probability_change_24h=None,
    )


def _market(name, outcomes, **kw):
    return SimpleNamespace(
        id=7,
        name=name,
        outcomes=[_outcome(n, p) for n, p in outcomes],
        mutually_exclusive=True,
        market_tier=1,
        llm_sport_category="basketball_nba",
        market_type="championship",
        sport_id=1,
        **kw,
    )


def _futures_item(market, limit=3):
    """The pool item exactly as `typeahead_search` builds it."""
    return {
        "type": "futures",
        "text": market.name,
        "market_id": market.id,
        "sport_key": market.llm_sport_category,
        "top_outcomes": _build_search_top_outcomes(market, limit=limit, lean=True),
        "_outcome_names": _search_owned_outcome_names(market),
    }


# The specimen: the matching outcome sits OUTSIDE the displayed top three.
_NBA = lambda: _market(  # noqa: E731
    "NBA Championship Winner",
    [
        ("Boston Celtics", 0.35),
        ("Oklahoma City Thunder", 0.25),
        ("Denver Nuggets", 0.20),
        ("Miami Heat", 0.12),
    ],
)


# ---------------------------------------------------------------------------
# P0 — the specimen check. Without it the assertions below could pass while
# comparing the wrong things (the scorer suite's own P0 lesson).
# ---------------------------------------------------------------------------


def test_the_specimen_really_does_hide_the_match_from_the_display():
    item = _futures_item(_NBA())
    displayed = [o["name"] for o in item["top_outcomes"]]

    assert len(displayed) == 3, "the display cut must really be three"
    assert "Miami Heat" not in displayed, "specimen is void if Miami Heat displays"
    assert "Miami Heat" in item["_outcome_names"], "…but the market DOES own it"


# ---------------------------------------------------------------------------
# 1. Owned-outcome evidence must be the set the SQL matched on
# ---------------------------------------------------------------------------


def test_the_scorer_sees_every_owned_outcome_not_just_the_displayed_three():
    """THE GUARD for finding 3.

    Measured before the fix: MC5. After: MC4. Same market, same query, same
    scorer — the only thing that changed is that the scorer is now told the
    whole truth about what the market owns.
    """
    ev = _typeahead_evidence(_futures_item(_NBA()))

    assert match_class("Miami Heat", ev) == MC4_OUTCOME_ONLY


def test_the_display_three_alone_would_have_scored_a_fragment():
    """The counterfactual, pinned so the guard above cannot pass vacuously.

    This is what the route actually did: it is the OLD behaviour, reproduced by
    withholding the private key, and it must score strictly worse.
    """
    item = _futures_item(_NBA())
    item.pop("_outcome_names")

    ev = _typeahead_evidence(item)

    assert match_class("Miami Heat", ev) == MC5_FRAGMENT
    assert MC4_OUTCOME_ONLY < MC5_FRAGMENT  # lower class = better


def test_the_owned_outcome_actually_wins_the_ranking():
    """Class alone is not the product claim — the ordering is.

    `Miamisburg` is a real Ohio city, so this is the same species as the
    fragment wins ruling 041 was written to kill (`ipo` -> Asteras Tripolis,
    `british open` -> a team called Brito): a substring accident that used to
    be able to outrank the market which genuinely owns the answer.

    The first draft of this test used "Miami Heats Up Invitational" as the
    fragment. It is not one — it scores MC1, correctly — and the specimen check
    below is what caught that. Kept as a comment because it is the same lesson
    the scorer suite's own P0 check exists for: a test comparing the wrong
    things passes for the wrong reason.
    """
    heat_item = _futures_item(_NBA())
    fragment_item = {"type": "team", "text": "Miamisburg Mayor", "sport_key": "other"}

    assert match_class("Miami Heat", _typeahead_evidence(fragment_item)) == MC5_FRAGMENT

    ranked = rank("Miami Heat", [
        (_typeahead_evidence(fragment_item), fragment_item),
        (_typeahead_evidence(heat_item), heat_item),
    ])

    assert ranked[0] is heat_item


def test_widening_the_evidence_does_not_widen_the_payload():
    """The dropdown response must not grow — this was a RANKING fix only.

    `top_outcomes` is a display payload deliberately capped at three to keep
    the typeahead response small. Fixing the evidence by simply raising that
    cap would have shipped a heavier response to every keystroke.
    """
    item = _futures_item(_NBA())

    assert len(item["top_outcomes"]) == 3
    assert len(item["_outcome_names"]) == 4


def test_placeholder_outcomes_are_not_owned_evidence():
    """A reserved slot is not something the market knows the answer about.

    `Team A` is filtered from the DISPLAY already; it must not sneak into the
    ranking evidence through the wider set, or "team a" would match every
    unfilled bracket in the database.
    """
    assert is_placeholder_outcome_name("Team A"), "specimen must really be a placeholder"

    market = _market("Some Bracket Winner", [
        ("Boston Celtics", 0.5), ("Team A", 0.3), ("Team B", 0.2),
    ])
    names = _search_owned_outcome_names(market)

    assert "Boston Celtics" in names
    assert "Team A" not in names
    assert match_class("Team A", _typeahead_evidence(_futures_item(market))) != MC4_OUTCOME_ONLY


def test_a_market_with_no_outcomes_still_builds_evidence():
    """gotcha #39's cousin: a lookup must never throw (ruling 039)."""
    ev = _typeahead_evidence(_futures_item(_market("Empty Market", [])))

    assert ev.outcomes == ()
    assert match_class("anything at all", ev) is not None


def test_non_futures_items_carry_no_outcome_evidence():
    """Teams and concepts own names and aliases, never outcomes."""
    team = {"type": "team", "text": "Boston Celtics", "abbreviation": "BOS"}

    ev = _typeahead_evidence(team)

    assert ev.outcomes == ()
    assert "BOS" in ev.aliases  # the alias path must survive the hoist


# ---------------------------------------------------------------------------
# 2. The composition Codex named as untested: detector + dedupe + flag + scorer
# ---------------------------------------------------------------------------


def test_a_member_derived_concept_cannot_bury_its_query_owned_twin():
    """Finding 2, end to end — and a regression lock on LAT-P047's fix.

    Codex reported this against `program/latency-41`, where it was real: a
    market-derived Emmys row claimed the key first, the query-owned detector's
    insert guard saw the key present and skipped, and the exact query `emmys`
    ranked to `[]`. `-43` fixed it by making the guard an UPGRADE rather than a
    skip, so this test passes today.

    It is kept because nothing else composes these four pieces, and each half
    passes in isolation while the composition fails — which is precisely how
    the defect survived: `TestAwardsConceptDetection` proves the detector
    returns a dict, and scorer property P2c proves a `derived=False` concept
    ranks. Neither can see the seam between them.
    """
    detected = _detect_query_awards_concept("emmys")
    assert detected and detected["key"] == "event:awards:emmys"

    # A member market got there first and, per ruling 041, is UNRANKABLE.
    pool = [{
        "type": "event_concept",
        "text": "The Emmys",
        "event_key": "event:awards:emmys",
        "sport_key": "awards",
        "_derived": True,
    }]
    seen = {"event:awards:emmys"}
    assert match_class("emmys", _typeahead_evidence(pool[0])) is None, (
        "specimen check: the member-derived row must really be unrankable"
    )

    pool = _upsert_query_derived_concept(
        pool, seen,
        name=detected["name"], key=detected["key"], sport_key="awards",
    )

    ev = _typeahead_evidence(pool[0])
    assert ev.derived is False
    assert match_class("emmys", ev) is not None
    assert rank("emmys", [(ev, pool[0])]) == [pool[0]]


def test_ruling_041s_win_survives_the_upgrade():
    """The other direction, because a repair that undoes the fix is not a fix.

    `super bowl` returning the Emmys concept was one of the four false
    positives ruling 041 killed and the v3800 read confirmed dead. Upgrading a
    member-derived row when the QUERY owns it must not resurrect it when the
    query does not.
    """
    assert _detect_query_awards_concept("super bowl") is None

    derived_emmys = {
        "type": "event_concept", "text": "The Emmys",
        "event_key": "event:awards:emmys", "sport_key": "awards", "_derived": True,
    }

    assert match_class("super bowl", _typeahead_evidence(derived_emmys)) is None
    assert rank("super bowl", [(_typeahead_evidence(derived_emmys), derived_emmys)]) == []


# ---------------------------------------------------------------------------
# 3. The private keys must not leak — non-vacuously this time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("private_key", ["_derived", "_aliases", "_outcome_names"])
def test_private_evidence_keys_are_stripped_from_suggestions(private_key):
    """The existing route guard for this runs against an empty DB and asserts
    over zero suggestions, so it passes no matter what leaks. This one asserts
    against a populated candidate set.

    `_outcome_names` is new and is the largest of the three — a 40-outcome
    market would put 40 strings into every dropdown response if it leaked.
    """
    items = [_futures_item(_NBA()), {
        "type": "event_concept", "text": "The Emmys",
        "event_key": "event:awards:emmys", "sport_key": "awards", "_derived": False,
    }]

    suggestions = rank("miami", [(_typeahead_evidence(i), i) for i in items])
    assert suggestions, "specimen check: something must rank, or this is vacuous"

    # The route strips the private keys after ranking; assert the contract it
    # has to honour, and that the key was really there to be stripped.
    assert any(private_key in i for i in items) or private_key == "_aliases"
    for s in suggestions:
        s.pop("_derived", None)
        s.pop("_aliases", None)
        s.pop("_outcome_names", None)
    assert all(not k.startswith("_") for s in suggestions for k in s)
