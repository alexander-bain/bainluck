"""TYPING A TEAM'S NAME LEADS WITH THE TEAM CARD. #4551 / D107, ship #4461.

Third sibling. `test_typeahead_leads_with_the_entity_4411.py` owns a query that
is a PLAYER's name (no team row exists, so the match is the entity);
`test_typeahead_yank_leads_with_the_team_4519.py` owns the keystroke BEFORE a
name is finished (MC0 has not arrived and MC1B is the missing rung); this one
owns the query that IS a team's name and ties on class anyway.

MEASURED ON PRODUCTION, 2026-09-10 00:1xZ, `GET /api/events/typeahead?q=yankee`:

    0  futures  Colorado Rockies vs. New York Yankees - First 5 Innings Winner
    1  futures  Colorado Rockies vs. New York Yankees - 6th Inning Winner
    2  futures  Colorado Rockies vs. New York Yankees - 3rd Inning Winner
    3  futures  Colorado Rockies vs. New York Yankees - 5th Inning Winner
    4  futures  Colorado Rockies vs. New York Yankees - 4th Inning Winner
    5  event    Colorado Rockies at New York Yankees
    6  event    Colorado Rockies at New York Yankees

No `type: team` row in the seven slots.

THE CAUSE IS NOT A DEFECT, WHICH IS WHY THIS NEEDED A RULING AND NOT A PATCH.
`_fold_token` strips one trailing plural, so `tokens("New York Yankees")` is
`("new","york","yankee")` and the query token `yankee` is PRESENT — the team is
an honest MC1. Every inning prop carries the same token and is MC1 too. The
class ties, and ruling 041 / Q325's ratified `market > event > team` floor then
hands slot 0 to the props. Nothing malfunctioned: the ratified relation and
Alex's rule ("a team or player name leads with the entity", #4411) genuinely
disagreed on this one keystroke. D107 resolved it in favour of the entity, for
the entity-name class only; ruling 041 still governs every other query.

THE SEAM MATTERS MORE THAN THE SCORER HERE, AND THAT IS WHY THIS FILE RANKS
THROUGH `_typeahead_evidence`. Nothing in `match_class` or `rank_key` moved for
`yankee` — both candidates are MC1 before this ship and after it. The whole
change is that the ROUTE now tells the scorer the team is an entity. A test that
built `Evidence(kind="team")` by hand would therefore pass identically before
and after and measure nothing at all — which is exactly what happened to
#4519's `yankee` guard, and is recorded there.
"""

from __future__ import annotations

import pytest

from app.routes.events import _typeahead_evidence
from app.utils import search_match_class as smc
from app.utils.search_match_class import (
    ENTITY_EVENT_KIND,
    ENTITY_TEAM_KIND,
    KIND_ORDER,
    query_is_entity_name,
    rank,
)


# --- the shared harness ----------------------------------------------------
#
# Pool items in, ranked labels out, through the REAL route converter and the
# REAL `rank`. A test here cannot pass by re-implementing either one.


def _team(name, aliases=(), abbreviation=None, sport_key="baseball_mlb"):
    return {
        "type": "team",
        "text": name,
        "abbreviation": abbreviation,
        "sport_key": sport_key,
        "_aliases": list(aliases),
    }


def _futures(name, sport_key="baseball"):
    return {"type": "futures", "text": name, "sport_key": sport_key}


def _event(name, participants, sport_key="baseball_mlb"):
    return {
        "type": "event",
        "text": name,
        "sport_key": sport_key,
        "_participants": list(participants),
    }


def _ranked(q, pool):
    return rank(
        q,
        [
            (_typeahead_evidence(item, q), f'{item["type"]}|{item["text"]}')
            for item in pool
        ],
    )


#: The measured `yankee` pool, row for row. Aliases are the real ones
#: (`teams.alternate_names` for id 6610: `['New York', 'Yankees']`) because
#: "Yankees" is the string the promotion matches — a specimen without them would
#: pass this file while production failed, which is LAT-P050's exact defect.
_YANKEES = _team("New York Yankees", ("New York", "Yankees"), "NYY")
_INNING_PROPS = [
    _futures(f"Colorado Rockies vs. New York Yankees - {n} Winner")
    for n in ("First 5 Innings", "6th Inning", "3rd Inning", "5th Inning",
              "4th Inning")
]
_FIXTURES = [
    _event("Colorado Rockies at New York Yankees",
           ["New York Yankees", "Colorado Rockies"])
    for _ in range(2)
]
_YANKEE_POOL = [*_INNING_PROPS, *_FIXTURES, _YANKEES]


class TestTheReportedScreen:
    def test_yankee_leads_with_the_yankees(self):
        """The production screen above, in one assertion."""
        out = _ranked("yankee", _YANKEE_POOL)
        assert out[0] == "team|New York Yankees", out[:3]

    def test_every_prop_sorts_below_the_team(self):
        """Not just the top slot — the partition holds all the way down.

        Leading with the card while rows 1-4 are still props is the complaint
        half-fixed. Alex's sentence is "the ENTITY leads … then its games, then
        props", so the card must clear the whole prop block, not one slot.
        """
        out = _ranked("yankee", _YANKEE_POOL)
        assert out.index("team|New York Yankees") == 0, out

    def test_the_pre_ship_ordering_is_still_reproducible(self):
        """The bug, on demand. If this stops failing, the file stopped measuring.

        Withholding `q` is how the route spells "do not promote" (#4411's
        boundary arm), so this reproduces exactly the screen production served:
        five props, then the fixtures, then the card — nowhere in the top 7.
        """
        unpromoted = rank(
            "yankee",
            [
                (_typeahead_evidence(item), f'{item["type"]}|{item["text"]}')
                for item in _YANKEE_POOL
            ],
        )
        assert unpromoted[0].startswith("futures|"), unpromoted[:3]
        assert unpromoted[-1] == "team|New York Yankees", unpromoted


class TestTheKeystrokeSweepIsNowWhole:
    """`yan` through `yankees` — #4519 closed six of seven, D107 closes the last.

    #4519's own sweep had to omit `yankee` and pin it as broken. The hole is the
    thing worth guarding: a fix that merely moves it one character left passes
    any test that checks a single keystroke.
    """

    @pytest.mark.parametrize("q", ["yan", "yank", "yanke", "yankee", "yankees"])
    def test_the_team_leads_on_every_keystroke(self, q):
        out = _ranked(q, _YANKEE_POOL)
        assert out[0] == "team|New York Yankees", f"{q!r} -> {out[:3]}"

    def test_only_the_finished_names_are_promoted(self):
        """The sweep is green for two DIFFERENT reasons and they must not merge.

        `yan`/`yank`/`yanke` lead on MC1B — a better class, ruling 041 intact,
        no promotion anywhere. `yankee`/`yankees` lead because the route calls
        them the entity. Asserting only the sweep above would let someone
        "simplify" the promotion to a prefix test, which reverses the ratified
        relation for every unfinished query in the product and still passes.
        """
        promoted = {
            q
            for q in ("yan", "yank", "yanke", "yankee", "yankees")
            if _typeahead_evidence(_YANKEES, q).kind == ENTITY_TEAM_KIND
        }
        assert promoted == {"yankee", "yankees"}, promoted


class TestTheNineControlsAlexNamed:
    """D107's position-preserving list, verbatim: `yank`, `yankees`, `red sox`,
    `shelton`, `nba mvp`, `british open`, `us open`, `ai`, `ipo`.

    `yank` and `yankees` are swept above. The other seven are here, and each one
    is a query the promotion must NOT fire on — six because no team owns the
    name, and `red sox` because it fires and the ordering is unchanged anyway
    (the card already won on MC0).
    """

    def test_red_sox_still_gives_card_then_game_then_props(self):
        """Fires, and moves nothing. The card was already MC0 on its alias.

        Worth pinning precisely because it is a no-op: if the promotion ever
        starts changing this ordering, something has reached above the class
        term, which is the one guarantee `rank_key` makes.
        """
        out = _ranked("red sox", [
            _futures("Boston Red Sox - Player Props"),
            _event("New York Yankees at Boston Red Sox",
                   ["Boston Red Sox", "New York Yankees"]),
            _team("Boston Red Sox", ("Red Sox",), "BOS"),
        ])
        assert out == [
            "team|Boston Red Sox",
            "event|New York Yankees at Boston Red Sox",
            "futures|Boston Red Sox - Player Props",
        ], out

    @pytest.mark.parametrize("q", ["shelton", "nba mvp", "british open",
                                   "us open", "ai", "ipo"])
    def test_the_query_names_no_team_so_nothing_is_promoted(self, q):
        """`ai` and `ipo` are measured failure family #2 in the scorer's own
        docstring (`ai` -> "1. FC Kaiserslautern", `ipo` -> "Asteras Tripolis").
        They came back once through MC1B's door and #4519 floored that; this is
        the third door, and equality closes it without needing a floor — no team
        is NAMED "ai", whatever it is a fragment of.
        """
        candidates = [
            _team("Aizawl FC", ("Aizawl",), "AIZ", "soccer_india"),
            _team("Asteras Tripolis", ("Asteras",), "AST", "soccer_greece"),
            _team("New York Yankees", ("New York", "Yankees"), "NYY"),
            _team("Boston Red Sox", ("Red Sox",), "BOS"),
        ]
        for item in candidates:
            assert _typeahead_evidence(item, q).kind == "team", (
                f"{q!r} promoted {item['text']!r}"
            )

    def test_us_open_keeps_answering_with_the_tournament(self):
        """The seven gold probes behind the concept slot, unmoved.

        `entity_team` sits BELOW `hub`/`concept` for this reason, exactly as
        `entity_event` does — a promoted entity must never outrank the
        tournament a reader typed.
        """
        assert KIND_ORDER["event_concept"] < KIND_ORDER[ENTITY_TEAM_KIND]
        assert KIND_ORDER["hub"] < KIND_ORDER[ENTITY_TEAM_KIND]

    def test_nba_mvp_still_answers_with_the_award(self):
        out = _ranked("nba mvp", [
            _futures("NBA MVP Winner"),
            _event("Boston Celtics at Los Angeles Lakers",
                   ["Los Angeles Lakers", "Boston Celtics"]),
            _team("Los Angeles Lakers", ("Lakers",), "LAL", "basketball_nba"),
        ])
        assert out[0] == "futures|NBA MVP Winner", out


class TestEqualityNotSubset:
    """THE MUTATION THIS FILE EXISTS FOR.

    `query_names_participant` (#4411) is a SUBSET test, and reusing it here is
    the obvious implementation. It passes every test above. It also promotes the
    Yankees on `new` and on `york`, which reverses ruling 041 for two of the
    commonest tokens in American sport, and nothing else in the repo notices.
    """

    @pytest.mark.parametrize("q", ["new", "york", "boston", "los", "angeles",
                                   "red", "sox"])
    def test_a_token_inside_a_name_is_not_the_name(self, q):
        assert not query_is_entity_name(
            q, ["New York Yankees", "New York", "Yankees", "NYY"]
        ) or q in {"yankees"}, q

    def test_new_still_answers_with_the_market(self):
        """#4519's `test_a_complete_word_still_beats_an_unfinished_one`, through
        the seam this ship added. That test builds `Evidence` by hand and so
        cannot see a route-level promotion at all — this is the arm that can.
        """
        out = _ranked("new", [
            _team("New York Yankees", ("New York", "Yankees"), "NYY"),
            _futures("New York Yankees vs. Boston Red Sox - Winner"),
        ])
        assert out[0].startswith("futures|"), out

    def test_the_whole_name_and_the_abbreviation_both_promote(self):
        """Three spellings a reader actually types, one entity."""
        for q in ("new york yankees", "yankees", "nyy"):
            assert _typeahead_evidence(_YANKEES, q).kind == ENTITY_TEAM_KIND, q

    def test_case_and_accents_fold_but_the_comparison_is_on_tokens(self):
        koln = _team("1. FC Köln", ("Köln", "FC Koeln"), "KOE", "soccer_germany")
        assert _typeahead_evidence(koln, "koln").kind == ENTITY_TEAM_KIND
        assert _typeahead_evidence(koln, "KÖLN").kind == ENTITY_TEAM_KIND
        # Punctuation is not compared at all — `1. FC Köln` tokenises to three
        # tokens, and a query supplying them in that order is the same name.
        assert _typeahead_evidence(koln, "1 fc koln").kind == ENTITY_TEAM_KIND
        # ...but a strict subset of them is not.
        assert _typeahead_evidence(koln, "fc").kind == "team"


class TestThePluralNamesakeStillWins:
    """CERT-2392's Sinner/Sinners boundary, re-asked of the team promotion.

    `query_is_entity_name` folds the plural — that is the whole of #4551, since
    `yankee` reaches no MC0. `query_names_participant` deliberately does NOT,
    because `sinner` must not name the Counter-Strike roster "Sinners". So the
    two predicates disagree about the plural ON PURPOSE, and the argument that
    this is safe is not "teams are different": it is that `rank`'s namesake gate
    is a property of the RESULT SET and outranks kind in the key.

    If that argument is wrong, this class is where it fails.
    """

    _POOL = [
        _futures("Jannik Sinner: Total Games", "tennis"),
        _futures("US Open ATP: Jannik Sinner vs Felix Auger-Aliassime", "tennis"),
        _team("Sinners", ("SNRS",), "SNR", "esports_csgo"),
    ]

    def test_the_roster_is_promoted_and_still_loses(self):
        """Promoted, penalised, last. Both halves asserted.

        Asserting only the ordering would pass if the promotion silently stopped
        firing for some unrelated reason, and the file would stop measuring the
        thing that makes it safe.
        """
        roster = self._POOL[-1]
        assert _typeahead_evidence(roster, "sinner").kind == ENTITY_TEAM_KIND
        out = _ranked("sinner", self._POOL)
        assert out[-1] == "team|Sinners", out
        assert out[0].startswith("futures|Jannik Sinner"), out

    def test_the_gate_is_what_does_it_not_the_kind(self):
        """Remove the strictly-landing candidate and the roster leads again.

        That is correct — with no Jannik row in the set, "Sinners" is the only
        thing the query can mean — and it proves the penalty is the set-level
        gate rather than something accidental about esports sport keys.
        """
        out = _ranked("sinner", [
            _futures("Counter-Strike: NIP vs Sinners - Map 1 Winner", "esports_csgo"),
            self._POOL[-1],
        ])
        assert out[0] == "team|Sinners", out

    def test_yankee_keeps_working_because_its_gate_is_closed(self):
        """The other half of the same rule, stated as the reason it is safe.

        Nothing in the `yankee` pool carries `yankee` unfolded, so the gate
        never opens, no candidate is penalised, and the promotion decides. A
        change that opened the gate more eagerly would break the ship without
        touching a line of it.
        """
        assert not any(
            smc._query_lands_strictly("yankee", _typeahead_evidence(item, "yankee"))
            for item in _YANKEE_POOL
        )


class TestTheEvidenceSeam:
    """Promotion needs the query AND the team's own aliases."""

    def test_the_query_is_required(self):
        """Called without `q`, a team can never be promoted — #4411's arm."""
        assert _typeahead_evidence(_YANKEES).kind == "team"
        assert _typeahead_evidence(_YANKEES, "yankee").kind == ENTITY_TEAM_KIND

    def test_a_team_whose_aliases_are_withheld_cannot_be_promoted(self):
        """LAT-P050, arriving in a third place.

        "New York Yankees" does not equal `yankee`; the ALIAS does. So a pool
        that forgets `_aliases` degrades to the pre-ship screen rather than
        promoting on the display name — and the offline harness, which strips
        exactly these fields, would report a fix that production does not have.
        """
        bare = _team("New York Yankees")
        assert _typeahead_evidence(bare, "yankee").kind == "team"
        assert _typeahead_evidence(bare, "new york yankees").kind == ENTITY_TEAM_KIND

    def test_the_abbreviation_reaches_the_promotion(self):
        """It is appended to `aliases`, and the promotion reads `aliases`.

        Assembling the aliases AFTER the kind decision — the order the route
        used before this ship — leaves this green for the wrong reason on every
        team whose display name a reader might type in full, and red only here.
        """
        no_abbrev = dict(_YANKEES, abbreviation=None)
        assert _typeahead_evidence(no_abbrev, "nyy").kind == "team"
        assert _typeahead_evidence(_YANKEES, "nyy").kind == ENTITY_TEAM_KIND

    def test_only_a_team_is_promoted_to_the_team_kind(self):
        """A futures row named exactly like a team must not become an entity."""
        assert _typeahead_evidence(
            _futures("Yankees"), "yankees"
        ).kind == "futures"
        assert _typeahead_evidence(
            _event("Yankees", ["New York Yankees"]), "yankees"
        ).kind == ENTITY_EVENT_KIND

    def test_an_event_is_never_promoted_to_the_TEAM_kind(self):
        """The team arm is gated on `kind == "team"`, and that gate is the point.

        An event's `text` is the assembled "A at B" string, so an unguarded
        team arm would treat it as an owned NAME: a reader typing the fixture
        exactly as rendered would get `entity_team`, which sorts the game above
        the actual team card and inverts Alex's order. Asserted on the query
        that equals that string, which is the only one that could reach it.
        """
        item = _event("Colorado Rockies at New York Yankees",
                      ["New York Yankees", "Colorado Rockies"])
        assert query_is_entity_name(
            "colorado rockies at new york yankees", [item["text"]]
        ), "the specimen no longer equals the event's own text"
        assert _typeahead_evidence(
            item, "colorado rockies at new york yankees"
        ).kind != ENTITY_TEAM_KIND
        # ...and the #4411 arm still owns the query that names a participant.
        assert _typeahead_evidence(item, "new york yankees").kind == ENTITY_EVENT_KIND


class TestKindOrderRelations:
    """Asserted as relations, never as literals — the numbers are free."""

    def test_the_ratified_relation_survives(self):
        assert KIND_ORDER["market"] < KIND_ORDER["event"] < KIND_ORDER["team"]
        assert KIND_ORDER["futures"] == KIND_ORDER["market"]

    def test_the_card_leads_its_own_game_which_leads_the_props(self):
        """Alex's sentence, as one chain of relations."""
        assert (
            KIND_ORDER[ENTITY_TEAM_KIND]
            < KIND_ORDER[ENTITY_EVENT_KIND]
            < KIND_ORDER["market"]
        )

    def test_a_promoted_team_still_sits_under_the_tournament(self):
        assert KIND_ORDER["hub"] < KIND_ORDER[ENTITY_TEAM_KIND]
        assert KIND_ORDER["concept"] < KIND_ORDER[ENTITY_TEAM_KIND]

    def test_the_promoted_kind_is_actually_in_the_table(self):
        """An unknown kind takes `_KIND_ORDER_FALLBACK` and sorts LAST, so a
        typo would invert the ship silently rather than raise."""
        assert smc.kind_rank(ENTITY_TEAM_KIND) != smc._KIND_ORDER_FALLBACK

    def test_the_renumber_moved_nothing_that_was_not_promoted(self, monkeypatch):
        """#4551's blast radius, asserted rather than reasoned about.

        Inserting `entity_team` at slot 2 pushed four kinds down one. If any
        PAIRWISE relation had changed, every query in the product would have
        moved — and no other test in this file would notice, because they all
        rank a set that contains a promotion.
        """
        pre_4551 = {
            "event_concept": 0, "concept": 0, "hub": 1, "entity_event": 2,
            "futures": 3, "market": 3, "event": 4, "team": 5,
        }
        pool = [
            {"type": "concept", "text": "US Open"},
            {"type": "hub", "text": "Tennis"},
            _futures("US Open Men's Singles Winner"),
            _event("Baltimore Orioles at New York Yankees", []),
            _team("New York Yankees", ("New York", "Yankees"), "NYY"),
        ]
        queries = ["yank", "us open", "nba mvp", "tennis", "winner", "new"]

        after = {q: _ranked(q, pool) for q in queries}
        monkeypatch.setattr(smc, "KIND_ORDER", pre_4551)
        before = {q: _ranked(q, pool) for q in queries}

        assert before == after, (
            "the renumber changed an ordering for a query that promotes "
            "nothing — a pairwise relation moved"
        )
