"""TYPING A TEAM'S NICKNAME LEADS WITH THE GAME, NOT WITH FIVE OF ITS OWN PROPS. #4986.

Sibling of `test_typeahead_leads_with_the_entity_4411.py`. That file owns the
promotion when the query names a participant **in their own name** (`alcaraz`,
`shelton`). This one owns the case that predicate cannot see: a curated
NICKNAME. `niners` is nowhere inside "San Francisco 49ers"; `pats` is nowhere
inside "New England Patriots".

MEASURED ON PRODUCTION, 2026-09-10 23:46Z, backend `575867fc`, three minutes
after #4847 went live, forty-eight minutes before that very game kicked off:

    q=niners   1 team, then 5 props, then the game       <- SF@LAR was row 7 of 7
    q=pats     1 team, then 5 props, then the game

The five rows above the game are markets DERIVED FROM IT: `2nd Quarter Winner`,
`1st Half Total`, `1st Half Spread`, `Team Total`, and a playoff future.

WHY IT COULD NOT HAVE BEEN SEEN BEFORE TODAY. Until #4847 shipped, a nickname
query returned **no game at all** — `pats` and `niners` were 1 team + 5 futures
and nothing else. #4847 made the arm resolve, and the latent ranking defect
became reachable in the same release. It is not a regression in #4847; it is the
next rung, and #4847's own cert routed it here rather than widening that ship.

THE MECHANISM, measured rather than reasoned (`rank_key` on the production
evidence echo, `?debug_evidence=1`):

    row                                        match_class   kind_rank
    San Francisco 49ers (team)                      0            2      entity_team
    SF 49ers vs LA Rams: 2nd Quarter Winner         5            4      futures
    ...four more futures...                         5            4      futures
    San Francisco 49ers at Los Angeles Rams         5            5      event

**Every candidate but the team ties at MC5.** `rank_key` is
`(mc, kind_rank, prominence, fragment, *within_tier)`, so with the class term
tied, `KIND_ORDER` alone decides — and a plain `event` sits BELOW `futures`, by
design and correctly (ruling 041 / Q325, the ratified market > event > team).

So this is not a class problem and must not be fixed as one. The event is in the
right class; it is the wrong KIND. #4411 already built the promotion that fixes
exactly this (`event` -> `entity_event`, kind 3, above futures at 4) — it simply
could not fire, because `query_names_participant` reads the participants' own
DISPLAY names and a nickname is not in them.

THE SEAM, which is the whole of the fix. The route already knows: it decides
admission with `_ta_names_participant`, whose nickname half is
`_nickname_names_participant` (#4847), sport scope and all. The scorer did not,
because the only thing crossing the boundary was `_participants` — two display
names. The route now carries its own verdict across as `_names_participant`, and
`_typeahead_evidence` prefers it. One authority, not two.

WHAT THIS FILE MUST NOT BE READ AS: a reversal of market > event > team. That
relation governs every query that names no participant, and the survival
controls below fail if it is flipped wholesale. `us open`, `nba mvp` and
`british open` are untouched — they name no participant under either half of the
test.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes.events import _typeahead_evidence, typeahead_search
from app.utils.search_match_class import (
    ENTITY_EVENT_KIND,
    ENTITY_TEAM_KIND,
    Evidence,
    KIND_ORDER,
    match_class,
    query_names_participant,
    rank,
    rank_key,
)

#: The 49ers' fixture, exactly as production names it. `niners` appears in
#: NEITHER participant, which is the entire point of the specimen.
_SF = "San Francisco 49ers"
_LAR = "Los Angeles Rams"
_GAME = f"{_SF} at {_LAR}"


def _event_item(names_participant=None, participants=(_SF, _LAR), text=_GAME):
    item = {
        "type": "event",
        "text": text,
        "event_id": 1,
        "sport_key": "americanfootball_nfl",
        "_participants": list(participants),
    }
    if names_participant is not None:
        item["_names_participant"] = names_participant
    return item


# ---------------------------------------------------------------------------
# 1. The specimen is real: `niners` names neither participant
# ---------------------------------------------------------------------------


class TestTheSpecimenIsNotVacuous:
    """If these pass trivially, every assertion below is meaningless."""

    def test_the_nickname_is_in_neither_participants_own_name(self):
        assert not query_names_participant("niners", (_SF, _LAR)), (
            "if #4411's predicate already saw this, #4986 would not exist"
        )
        assert not query_names_participant("pats", ("New England Patriots", "Seattle Seahawks"))

    def test_the_canonical_token_still_is(self):
        """The control: the same predicate, the same row, the name a nickname
        stands in for. #4411 is untouched by anything here."""
        assert query_names_participant("49ers", (_SF, _LAR))
        assert query_names_participant("patriots", ("New England Patriots", "Seattle Seahawks"))

    def test_a_plain_event_really_does_sort_below_a_market(self):
        """The ratified relation, which is why the fix is a promotion and not a
        reordering of `KIND_ORDER`."""
        assert KIND_ORDER["event"] > KIND_ORDER["futures"]
        assert KIND_ORDER[ENTITY_EVENT_KIND] < KIND_ORDER["futures"]
        assert KIND_ORDER[ENTITY_TEAM_KIND] < KIND_ORDER[ENTITY_EVENT_KIND]


# ---------------------------------------------------------------------------
# 2. The seam: the route's verdict reaches the scorer
# ---------------------------------------------------------------------------


class TestTheRoutesVerdictCrossesTheBoundary:
    """Drives the REAL `_typeahead_evidence`, which is where the defect lived."""

    def test_the_nickname_verdict_promotes_the_game(self):
        """THE SHIP. Fails on the pre-#4986 code, which reads `_participants`
        only and returns a plain `event`."""
        ev = _typeahead_evidence(_event_item(names_participant=True), "niners")
        assert ev.kind == ENTITY_EVENT_KIND

    def test_without_the_verdict_the_row_is_not_promoted(self):
        """The before-state, pinned: this is what production served at 23:46Z."""
        ev = _typeahead_evidence(_event_item(), "niners")
        assert ev.kind == "event"

    def test_a_route_that_supplies_no_verdict_keeps_4411(self):
        """The fallback is a fallback, not a replacement. The fuzzy pool and the
        offline harness supply no verdict and must keep the older rule."""
        ev = _typeahead_evidence(_event_item(), "49ers")
        assert ev.kind == ENTITY_EVENT_KIND

    def test_a_false_verdict_cannot_demote_what_4411_would_promote(self):
        """The verdict is a SUPERSET of `query_names_participant`, never a
        replacement for it, so the two are combined with OR and not with the
        route's answer alone. Pinned because the tempting simplification —
        trusting the flag when present — would silently make #4986's key a
        regression risk for #4411 the first time a pool sets it wrong."""
        ev = _typeahead_evidence(_event_item(names_participant=False), "49ers")
        assert ev.kind == ENTITY_EVENT_KIND

    def test_a_withheld_query_still_withholds_the_promotion(self):
        """`_typeahead_evidence`'s documented invariant: no query, no promotion.
        A verdict computed by the route does not buy an exemption from it — the
        promotion is a statement ABOUT the query."""
        ev = _typeahead_evidence(_event_item(names_participant=True))
        assert ev.kind == "event"

    @pytest.mark.parametrize("kind", ["futures", "team", "concept", "hub"])
    def test_the_verdict_promotes_nothing_that_is_not_an_event(self, kind):
        """A stray key on a non-event item must not reach the event branch."""
        item = {"type": kind, "text": "SF 49ers vs LA Rams: Team Total",
                "sport_key": "football", "_names_participant": True}
        assert _typeahead_evidence(item, "niners").kind == kind


# ---------------------------------------------------------------------------
# 3. The reader-visible ordering, through the REAL scorer
# ---------------------------------------------------------------------------
#
# The exact seven rows production served for `niners` at 23:46Z, with the
# aliases and outcomes from the `?debug_evidence=1` echo, so the classes here
# are the classes that were actually computed on the box.

_TEAM_ALIASES = ("niners", "9ers", "49ers", "SF")

_PROPS = [
    ("SF 49ers vs LA Rams: 2nd Quarter Winner",
     ("Tie 2nd Quarter", "San Francisco wins 2nd Quarter", "Los Angeles R wins 2nd Quarter")),
    ("Will the San Francisco 49ers make the 2027 NFL Playoffs?", ("No", "Yes")),
    ("SF 49ers vs LA Rams: 1st Half Total",
     ("Over 3.5 1H points scored", "Over 20.5 1H points scored")),
    ("SF 49ers vs LA Rams: 1st Half Spread",
     ("LA Rams wins 1H by over 10.5 points", "SF 49ers wins 1H by over 3.5 points")),
    ("SF 49ers vs LA Rams: Team Total",
     ("LA Rams over 10.5 points scored", "SF 49ers over 20.5 points scored")),
]


def _production_pool(promote):
    """The seven candidates, in the order production ranked them."""
    rows = [(
        Evidence(name=_SF, kind=ENTITY_TEAM_KIND, aliases=_TEAM_ALIASES,
                 sport_key="americanfootball_nfl"),
        _SF,
    )]
    for name, outcomes in _PROPS:
        rows.append((
            Evidence(name=name, kind="futures", outcomes=outcomes, sport_key="football"),
            name,
        ))
    rows.append((
        Evidence(name=_GAME, kind=ENTITY_EVENT_KIND if promote else "event",
                 sport_key="americanfootball_nfl"),
        _GAME,
    ))
    return rows


class TestWhatTheReaderSees:

    def test_the_reported_bug_reproduces(self):
        """Non-vacuity for the whole file: without the promotion the game is
        LAST, under all five of its own props. This is the screenshot."""
        assert list(rank("niners", _production_pool(promote=False)))[-1] == _GAME

    def test_the_game_leads_the_props_once_promoted(self):
        ranked = list(rank("niners", _production_pool(promote=True)))
        assert ranked[0] == _SF, "the team card still leads — ruling 041's floor"
        assert ranked[1] == _GAME, f"the game must sit directly under the team; got {ranked[1]!r}"
        assert ranked[2:] == [name for name, _ in _PROPS], (
            "the props keep their own order below it"
        )

    def test_every_prop_sorts_below_the_game(self):
        ranked = list(rank("niners", _production_pool(promote=True)))
        game_at = ranked.index(_GAME)
        for name, _ in _PROPS:
            assert ranked.index(name) > game_at, f"{name!r} still outranks the game"

    def test_the_class_term_really_is_tied_so_kind_alone_decides(self):
        """The measurement the fix rests on. If a future change makes the props
        outrank the game on CLASS, promoting the kind stops working and this
        test says so directly instead of the ordering tests failing obscurely."""
        game = Evidence(name=_GAME, kind="event", sport_key="americanfootball_nfl")
        for name, outcomes in _PROPS:
            prop = Evidence(name=name, kind="futures", outcomes=outcomes, sport_key="football")
            assert match_class("niners", prop) == match_class("niners", game), (
                f"{name!r} no longer ties the game on class — re-derive #4986"
            )

    def test_the_whole_chain_from_pool_ITEM_to_ranked_order(self):
        """The composed test, and the only one here that fails if the ROUTE
        stops carrying its verdict.

        Every other test in this class builds `Evidence` directly, so it proves
        what the scorer does once the promotion has happened — which is exactly
        the gap `test_typeahead_evidence_boundary.py` was written for. This one
        starts from pool ITEMS, goes through the real `_typeahead_evidence`, and
        ends at the real `rank`.

        It is still not the whole ship: nothing here proves the route SETS
        `_names_participant` correctly against a live pool, because that needs a
        populated database. That control is #4922, and this is the second ship
        on this cut to want it."""
        items = [
            {"type": "team", "text": _SF, "_aliases": list(_TEAM_ALIASES),
             "sport_key": "americanfootball_nfl"},
            *[
                {"type": "futures", "text": name, "_outcome_names": list(outcomes),
                 "sport_key": "football"}
                for name, outcomes in _PROPS
            ],
            _event_item(names_participant=True),
        ]
        ranked = list(rank("niners", [(_typeahead_evidence(i, "niners"), i["text"]) for i in items]))
        assert ranked[0] == _SF
        assert ranked[1] == _GAME, (
            f"the game must sit directly under the team card; got {ranked[1]!r}"
        )

    def test_the_kind_term_is_what_moves_the_row(self):
        """Same two rows, one field different, opposite order."""
        plain = Evidence(name=_GAME, kind="event", sport_key="americanfootball_nfl")
        promoted = Evidence(name=_GAME, kind=ENTITY_EVENT_KIND, sport_key="americanfootball_nfl")
        prop = Evidence(name=_PROPS[0][0], kind="futures", outcomes=_PROPS[0][1],
                        sport_key="football")
        assert rank_key("niners", plain) > rank_key("niners", prop)
        assert rank_key("niners", promoted) < rank_key("niners", prop)


# ---------------------------------------------------------------------------
# 4. The survival controls — the ratified relation is untouched
# ---------------------------------------------------------------------------


class TestTheRatifiedRelationSurvives:
    """A query that names no participant must be ordered exactly as before."""

    @pytest.mark.parametrize("q", ["us open", "nba mvp", "british open", "ai", "ipo"])
    def test_a_non_participant_query_promotes_nothing(self, q):
        assert _typeahead_evidence(_event_item(), q).kind == "event"

    def test_the_market_still_leads_a_tournament_query(self):
        pool = [
            (Evidence(name="US Open Men's Singles Winner", kind="futures", sport_key="tennis"),
             "market"),
            (Evidence(name="Ben Shelton at Frances Tiafoe", kind="event", sport_key="tennis"),
             "game"),
        ]
        assert list(rank("us open", pool))[0] == "market"


# ---------------------------------------------------------------------------
# 5. The sport scope, and the payload
# ---------------------------------------------------------------------------


class TestTheScopeAndThePayload:

    def test_the_wrong_sports_namesake_is_not_promoted_by_the_fallback(self):
        """`pats` rewrites to `Patriots`, and `St Kitts & Nevis Patriots` is a
        real Caribbean Premier League side that production really does return
        for `patriots`. The route's verdict is False for it (the sport scope
        lives in `_nickname_names_participant`, and #4847's suite owns that
        half); what THIS file has to prove is that the fallback does not let it
        through anyway — `pats` is not a token of the cricket side's name."""
        cricket = _event_item(
            names_participant=False,
            participants=("Barbados Tridents", "St Kitts & Nevis Patriots"),
            text="St Kitts & Nevis Patriots at Barbados Tridents",
        )
        assert _typeahead_evidence(cricket, "pats").kind == "event"

    def test_the_verdict_never_reaches_the_reader(self):
        """Private ranking evidence, like `_participants` beside it. Asserted
        against the route's own strip block rather than a re-implementation of
        it, because a test that pops the key itself proves only that popping
        works."""
        source = inspect.getsource(typeahead_search)
        assert '_s.pop("_names_participant", None)' in source, (
            "the route must strip the verdict before returning suggestions"
        )
