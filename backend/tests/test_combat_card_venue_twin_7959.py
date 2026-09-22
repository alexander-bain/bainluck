"""#7959 — one fight card, minted once per venue, served as two cards.

═══ THE DEFECT ═══

Kalshi stamps a card's identity into its FIGHT ticker (`KXUFCFIGHT-26SEP22…`) and
:func:`card_token` reads a bare date token off it. Polymarket has no ticker, so
#2602's :func:`venue_card_token` keys its rows on the PAIR (promotion, venue fight
date) and mints a SCOPED token. For a NUMBERED card that function already unifies
onto the bare token and the two venues meet. For an UNNUMBERED one they never do.

What a reader got, production 2026-09-22 07:01Z, `GET /api/feed?limit=250`
(103 items) — two slots of Discover page one spent on one fight card:

    slot 79  event:ufc:26sep22danawhitescontenderseries
             "Dana White's Contender Series"          5 fights   (Polymarket)
    slot 81  event:ufc:26sep22
             "Contender Series: Novenyi Jr vs Haig"   5 fights   (Kalshi)

Fight-for-fight identical, from `/api/event/<key>` `children[]`:

    Contender Series: Quissua vs Piwowarczyk  |  Damian Piwowarczyk vs. Emilio Quissua
    Contender Series: Connor vs Guaylupo      |  Callum Connor vs. Piero Guaylupo
    Contender Series: Degli vs Moran          |  Paris Moran vs. Marcos Degli
    Contender Series: Ortega vs Dasuyev       |  Jaden Ortega vs. Alvi Dasuyev
    Contender Series: Novenyi Jr vs Haig      |  Norbert Növényi Jr. vs. Theo Haig

The same shape on 2026-09-26 (`26sep26ufcfightnight` beside `26sep26`, 11 bouts
each). The `/hub/mma` rail carried nine "upcoming cards" for roughly six events.

═══ THE RULE ═══

Neither token gives way. Bare-only re-opens #4093 (the events table carries a
different promotion on the same date and a date-only key swallows it);
scoped-only is the defect above. They are joined AFTER grouping, on evidence —
which is what :func:`token_scope`'s own docstring already specifies:

    a scoped card never folds into another promotion's night, and never into a
    bare date token — that join is a cross-source identity claim and needs BOUT
    EVIDENCE, not an adjacent date.

The evidence is a SHARED BOUT: both fighters of one fight, matched across the two
venues' spellings. One is sufficient and is the whole test — a bout cannot be on
two different cards the same night.

═══ THE CONTROL, AND WHY IT IS THE POINT ═══

Measured over every open combat market on 2026-09-22 (195 rows, both configs),
exactly three scoped tokens sit beside a bare token of the same date. Two are
twins. The third is boxing's, and it is a genuinely DIFFERENT card:

    26sep26zuffaboxing11   Pullen/Faretina, Cerda/Lewis, MacMillan/Azagier,
                           Romero/Ignat, Tapia/Ruiz, Hughes/Stephenson,
                           Allen/Mronsz                          (7 bouts)
    26sep26                Lee Cutler vs Louis Greene            (1 bout)

Zero shared bouts. That pair is #4093's hazard in live data, and it is what a
date-only join — or a promotion-NAME join — would have merged. It is reproduced
below as a control, because "the twins merged" passes just as well on a rule that
merges everything.

═══ WHY NOT THE CHEAPER SIGNALS ═══

* **The promotion name** fails on these very specimens: Kalshi writes "Contender
  Series" where Polymarket writes "Dana White's Contender Series", and "Fight
  Night" against "UFC Fight Night". Substring matching happens to join both, and
  is generic enough ("Fight Night") to join two real promotions.
* **A shared FIGHTER** is not a card — #4560 has fighters booked twice, and one
  name appears on two promotions in a week. `player_key` is doubly wrong here: it
  takes the LAST token, so "Norbert Növényi Jr." keys as `jr`.

═══ THE COUNT RIDES ALONG, BECAUSE THE FOLD WOULD HAVE SPREAD ITS DEFECT ═══

`fight_count` counted distinct `group`s, and `group` is per-venue by construction
(a Kalshi market id, a Polymarket event id). Where the two venues already met —
numbered cards — that double-counted: on 2026-09-22 the feed offered "UFC 332:
Silva vs Cong · **26 fights**" while its own page rendered **13**. This fold makes
the unnumbered cards meet too, so the counter had to stop being per-venue.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_boxing import BOXING_CONFIG, BoxingEventAdapter
from app.utils.event_combat import (
    bout_roster_key,
    bouts_are_one_fight,
    bout_sides_any,
    count_distinct_bouts,
    event_commence_token,
    fold_venue_scoped_tokens,
    list_card_concepts,
    token_scope,
    venue_card_token,
)
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter

_IDS = itertools.count(790000)


def _far(days: int, hour: int = 22) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


#: Both cards are dated from the SAME instant, so the fixture never depends on
#: which day the suite runs — the Kalshi ticker's literal date token is derived
#: from it rather than spelled, which is the only way the two halves can agree.
_DWCS_START = _far(5)
_ZUFFA_START = _far(9)
_LISTED_AT = _far(-5)


def _ticker(start: datetime, suffix: str, prefix: str = "KXUFCFIGHT") -> str:
    return f"{prefix}-{event_commence_token(start).upper()}{suffix}"


def _venue_row(name: str, start: datetime, event_id: str):
    """A Polymarket `futures_markets` row — no ticker, a `venue_game_start`."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=f"0x{next(_IDS):064x}",
        name=name,
        source="polymarket",
        status="open",
        commence_time=_LISTED_AT,  # Gamma's LISTING stamp, not the fight
        market_metadata={
            "venue_game_start": start.isoformat().replace("+00:00", "Z"),
            "polymarket_event_id": event_id,
        },
        outcomes=[],
    )


def _kalshi_row(name: str, start: datetime, suffix: str, *, prefix="KXUFCFIGHT"):
    """A Kalshi `futures_markets` row — a fight ticker, a CLOSE stamp."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=_ticker(start, suffix, prefix),
        name=name,
        source="kalshi",
        status="open",
        commence_time=start + timedelta(hours=6),  # close, not fight (gotcha #14)
        market_metadata={"event_title": name},
        outcomes=[],
    )


def _projection(rows):
    """`COMBAT_PROJECTION` order, which is what `list_card_concepts` reads."""
    return [
        (m.id, m.external_id, m.name, m.commence_time, m.market_metadata) for m in rows
    ]


# ── The specimens, verbatim from production 2026-09-22 ────────────────────────

#: Kalshi's five, on the bare token. Names carry the promotion AND the matchup.
_DWCS_KALSHI = [
    _kalshi_row(f"Contender Series: {m}", _DWCS_START, s)
    for m, s in [
        ("Quissua vs Piwowarczyk", "QUIPIW"),
        ("Connor vs Guaylupo", "CONGUA"),
        ("Degli vs Moran", "DEGMOR"),
        ("Ortega vs Dasuyev", "ORTDAS"),
        ("Novenyi Jr vs Haig", "NOVHAI"),
    ]
]

#: Polymarket's five, on the scoped token — different spellings, reversed order,
#: diacritics, and the weight-class parenthetical. Each is published TWICE (the
#: event-level parent and its condition-id child), exactly as production has it.
_DWCS_VENUE = [
    _venue_row(f"Dana White's Contender Series: {m}", _DWCS_START, eid)
    for m, eid in [
        ("Damian Piwowarczyk vs. Emilio Quissua (Light Heavyweight, Main Card)", "1"),
        ("Callum Connor vs. Piero Guaylupo (Lightweight, Main Card)", "2"),
        ("Paris Moran vs. Marcos Degli (Flyweight, Main Card)", "3"),
        ("Jaden Ortega vs. Alvi Dasuyev (Welterweight, Main Card)", "4"),
        ("Norbert Növényi Jr. vs. Theo Haig (Middleweight, Main Card)", "5"),
    ]
    for _ in (0, 1)
]

#: THE CONTROL. Zuffa Boxing 11 (Polymarket, scoped) and a single unrelated bout
#: Kalshi lists on the same date (bare). Same date, no shared bout, two cards.
_ZUFFA_VENUE = [
    _venue_row(f"Zuffa Boxing 11: {m}", _ZUFFA_START, str(100 + i))
    for i, m in enumerate(
        [
            "Pullen vs. Faretina (Lightweight, Prelims)",
            "Cerda vs. Lewis (Featherweight, Prelims)",
            "MacMillan vs. Azagier (Super Welterweight, Prelims)",
            "Romero vs. Ignat (Cruiserweight, Prelims)",
            "Tapia vs. Ruiz (Middleweight, Main)",
            "Hughes vs. Stephenson (Light Heavyweight, Main)",
            "Allen vs. Mronsz (Women's Super Lightweight, Main)",
        ]
    )
]
_ZUFFA_KALSHI = [
    _kalshi_row(
        "Lee Cutler vs Louis Greene", _ZUFFA_START, "CUTGRE", prefix="KXBOXING"
    )
]


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    def __init__(self, events=(), markets=()):
        self._events = list(events)
        self._markets = list(markets)

    async def execute(self, statement, *_a, **_k):
        sql = str(statement)
        if "futures_outcomes" in sql:
            return _FakeResult([])
        if "futures_markets" in sql:
            return _FakeResult(self._markets)
        return _FakeResult(self._events)


def _rosters(rows, cfg=UFC_CONFIG) -> dict[str, list]:
    """`{token: [name]}` the way both callers build it."""
    from app.utils.event_combat import card_token

    out: dict[str, list] = {}
    for m in rows:
        token = card_token(cfg, m.external_id) or venue_card_token(
            cfg, m.name, m.market_metadata
        )
        if token:
            out.setdefault(token, []).append(m.name)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# The fixture is the specimen: assert the split exists before asserting it heals.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheFixtureReproducesTheDefect:
    def test_the_two_venues_really_do_mint_two_tokens(self):
        tokens = set(_rosters([*_DWCS_KALSHI, *_DWCS_VENUE]))
        assert len(tokens) == 2, tokens
        assert {bool(token_scope(t)) for t in tokens} == {True, False}, (
            "the defect is one BARE token beside one SCOPED token; if the "
            "fixture no longer produces both, every assertion below is vacuous"
        )

    def test_the_control_also_collides_on_one_date(self):
        """The control must be a real near-miss, not a trivially separate pair."""
        from app.utils.event_combat import token_date

        tokens = set(_rosters([*_ZUFFA_KALSHI, *_ZUFFA_VENUE], BOXING_CONFIG))
        assert len(tokens) == 2, tokens
        assert len({token_date(t) for t in tokens}) == 1, (
            "if the control's two tokens are not on the SAME date, it cannot "
            "discriminate — the fold would refuse them for the wrong reason"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Bout identity across two venues' spellings.
# ═══════════════════════════════════════════════════════════════════════════


class TestBoutIdentity:
    def test_a_bare_matchup_parses(self):
        """Kalshi writes a standalone fight with no promotion and no colon, and
        that row is exactly the one the control turns on."""
        assert bout_sides_any("Lee Cutler vs Louis Greene") == (
            "Lee Cutler",
            "Louis Greene",
        )

    @pytest.mark.parametrize(
        "kalshi,venue",
        [
            (
                "Contender Series: Novenyi Jr vs Haig",
                "Dana White's Contender Series: Norbert Növényi Jr. vs. Theo Haig "
                "(Middleweight, Main Card)",
            ),
            (
                "Contender Series: Quissua vs Piwowarczyk",
                "Dana White's Contender Series: Damian Piwowarczyk vs. Emilio "
                "Quissua (Light Heavyweight, Main Card)",
            ),
            (
                "Fight Night: Dumont Viana vs Perez",
                "UFC Fight Night: Norma Dumont vs. Ailin Perez "
                "(Women's Bantamweight, Prelims)",
            ),
        ],
    )
    def test_the_same_fight_across_venues_matches(self, kalshi, venue):
        """Diacritics, a reversed side order, a full name against a surname, and
        the venue's weight-class parenthetical — all four in these three rows."""
        assert bouts_are_one_fight(bout_roster_key(kalshi), bout_roster_key(venue))

    def test_two_different_fights_do_not_match(self):
        assert not bouts_are_one_fight(
            bout_roster_key("Contender Series: Degli vs Moran"),
            bout_roster_key("Zuffa Boxing 11: Tapia vs. Ruiz (Middleweight, Main)"),
        )

    def test_a_shared_surname_inside_one_bout_is_not_evidence(self):
        """"Anderson Silva vs Thiago Silva" must not match every other Silva
        bout on the strength of the one token both of its sides carry."""
        assert not bouts_are_one_fight(
            bout_roster_key("Fight Night: Anderson Silva vs Thiago Silva"),
            bout_roster_key("Fight Night: Wanderlei Silva vs Rich Franklin"),
        )

    def test_a_generational_suffix_alone_is_not_evidence(self):
        """`jr` is shared by half the roster; it is below the token floor."""
        assert not bouts_are_one_fight(
            bout_roster_key("Fight Night: Rosas Jr vs Barcelos"),
            bout_roster_key("Contender Series: Novenyi Jr vs Haig"),
        )


# ═══════════════════════════════════════════════════════════════════════════
# The fold itself.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheFold:
    def test_the_twin_folds_onto_the_bare_token(self):
        survivor = fold_venue_scoped_tokens(_rosters([*_DWCS_KALSHI, *_DWCS_VENUE]))
        scoped = next(t for t in survivor if token_scope(t))
        bare = next(t for t in survivor if not token_scope(t))
        assert survivor[scoped] == bare
        assert survivor[bare] == bare, "the bare token survives, not the scoped one"

    def test_the_control_is_refused(self):
        """Same date, no shared bout — #4093's hazard, and it must NOT fold."""
        survivor = fold_venue_scoped_tokens(
            _rosters([*_ZUFFA_KALSHI, *_ZUFFA_VENUE], BOXING_CONFIG)
        )
        assert all(t == s for t, s in survivor.items()), survivor

    def test_a_scoped_token_with_no_bare_twin_keeps_itself(self):
        survivor = fold_venue_scoped_tokens(_rosters(_DWCS_VENUE))
        assert all(t == s for t, s in survivor.items()), survivor

    def test_the_map_is_total(self):
        rosters = _rosters([*_DWCS_KALSHI, *_DWCS_VENUE])
        assert set(fold_venue_scoped_tokens(rosters)) == set(rosters)

    def test_an_empty_roster_is_not_evidence(self):
        """A scoped token whose rows are all props must not fold on silence."""
        rosters = {
            "26sep22": ["Contender Series: Degli vs Moran"],
            "26sep22danawhitescontenderseries": ["O/U 2.5 Rounds", "Total knockouts"],
        }
        assert fold_venue_scoped_tokens(rosters)[
            "26sep22danawhitescontenderseries"
        ] == "26sep22danawhitescontenderseries"


# ═══════════════════════════════════════════════════════════════════════════
# The count, which the fold would otherwise have doubled.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheBoutCount:
    def test_one_bout_priced_by_both_venues_counts_once(self):
        fights = [
            {"name": "Contender Series: Degli vs Moran", "group": 11},
            {
                "name": "Dana White's Contender Series: Paris Moran vs. Marcos Degli",
                "group": "pm-3",
            },
        ]
        assert count_distinct_bouts(fights) == 1

    def test_a_venue_parent_and_its_child_still_count_once(self):
        """#2602's own dedup, which keys on `group` — unchanged."""
        title = "Dana White's Contender Series: Paris Moran vs. Marcos Degli"
        assert count_distinct_bouts([{"name": title, "group": "pm-3"}] * 2) == 1

    def test_two_real_bouts_count_twice(self):
        assert (
            count_distinct_bouts(
                [
                    {"name": "Contender Series: Degli vs Moran", "group": 11},
                    {"name": "Contender Series: Ortega vs Dasuyev", "group": 12},
                ]
            )
            == 2
        )

    def test_an_unparseable_row_keeps_its_own_identity(self):
        assert (
            count_distinct_bouts(
                [
                    {"name": "O/U 2.5 Rounds", "group": 21},
                    {"name": "Total knockouts", "group": 22},
                ]
            )
            == 2
        )


# ═══════════════════════════════════════════════════════════════════════════
# The lister — what Discover is offered.
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestTheCardReachesDiscoverOnce:
    async def test_one_card_not_two(self):
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection([*_DWCS_KALSHI, *_DWCS_VENUE])
        )
        assert len(concepts) == 1, [c["name"] for c in concepts]

    async def test_the_surviving_card_counts_five_fights_not_ten(self):
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection([*_DWCS_KALSHI, *_DWCS_VENUE])
        )
        assert concepts[0]["fight_count"] == 5, (
            "five bouts, priced by two venues and published by one of them twice "
            "— fifteen rows"
        )

    async def test_the_surviving_card_keeps_the_bare_key(self):
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection([*_DWCS_KALSHI, *_DWCS_VENUE])
        )
        assert not token_scope(concepts[0]["key"].rsplit(":", 1)[-1])

    async def test_the_surviving_card_names_the_event_and_the_main_bout(self):
        """The Kalshi label wins, and it is the better of the two: the venue-only
        card was "Dana White's Contender Series" with no bout in its name."""
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection([*_DWCS_KALSHI, *_DWCS_VENUE])
        )
        assert "Contender Series" in concepts[0]["name"]
        assert " vs " in concepts[0]["name"]

    async def test_the_control_stays_two_cards(self):
        concepts = await list_card_concepts(
            BOXING_CONFIG,
            _FakeDB(),
            rows=_projection([*_ZUFFA_KALSHI, *_ZUFFA_VENUE]),
        )
        assert len(concepts) == 2, [c["name"] for c in concepts]


# ═══════════════════════════════════════════════════════════════════════════
# The page must fold IDENTICALLY, or the feed offers a card whose page holds
# half of it — the invariant `_folded_card_tokens` exists to maintain.
# ═══════════════════════════════════════════════════════════════════════════


class TestThePageFoldsTheSameWay:
    def _tokens(self, target, rows, adapter=UFCEventAdapter):
        return adapter()._folded_card_tokens(target, rows, {})

    def test_the_bare_target_reaches_the_venue_rows(self):
        rows = [*_DWCS_KALSHI, *_DWCS_VENUE]
        bare = next(t for t in _rosters(rows) if not token_scope(t))
        assert set(_rosters(rows)) <= self._tokens(bare, rows)

    def test_a_stale_link_to_the_scoped_key_resolves_onto_the_whole_card(self):
        rows = [*_DWCS_KALSHI, *_DWCS_VENUE]
        scoped = next(t for t in _rosters(rows) if token_scope(t))
        assert set(_rosters(rows)) <= self._tokens(scoped, rows)

    def test_the_control_does_not_bleed_across(self):
        rows = [*_ZUFFA_KALSHI, *_ZUFFA_VENUE]
        bare = next(t for t in _rosters(rows, BOXING_CONFIG) if not token_scope(t))
        scoped = next(t for t in _rosters(rows, BOXING_CONFIG) if token_scope(t))
        assert scoped not in self._tokens(bare, rows, BoxingEventAdapter)
