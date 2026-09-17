"""#2602 — a card the VENUE lists is a card, and its identity is not a date.

═══ THE DEFECT ═══

`event_combat` keys a fight card on a date-token it reads out of a Kalshi FIGHT
ticker (`KXUFCFIGHT-26SEP19…`). Polymarket has no ticker. So `card_token`
returned `None` for every Polymarket row and `list_card_concepts` dropped it at
the top of its loop — **no venue-only card could form at all.**

Censused on production 2026-09-17 (`futures_markets`, `llm_sport_category='mma'`,
`status='open'`):

    polymarket  115 rows   0 with a card ticker   28 with `venue_game_start`
    kalshi       34 rows  13 with a card ticker    0 with `venue_game_start`

Three real cards were invisible behind that zero, every row already in our DB:

    UFC Fight Night                2026-09-26   11 bouts
    Dana White's Contender Series  2026-09-22    5 bouts (6 rows)
    Power Slap 23                  2026-09-18    1 bout  (2 rows)

═══ THE RULE ═══

Card identity is the PAIR — the promotion the venue's own title names, and the
venue's own fight date (`market_metadata->>'venue_game_start'`). Each half alone
is measurably wrong:

* **The date alone** merges promotions. The events table carries "Darren Till vs
  Yoel Romero" on 2026-09-26; a date-only key swallows it into the UFC Fight
  Night card. That is #4093, already proved insufficient.
* **The promotion alone** merges nights. "UFC Fight Night" recurs every few weeks.

And the date must come from `venue_game_start`, never `commence_time`: for a
Polymarket row the latter is Gamma's `startDate`, the LISTING stamp. All 28 open
MMA rows carrying both disagree — the 26 Sep card's eleven bouts are stamped
`commence_time 2026-09-12 22:00`, a fortnight early.

═══ WHAT THIS DELIBERATELY DOES NOT CLAIM ═══

A venue bout row is two-sided far more often than it is a moneyline, so counting
outcomes is not a test for a fight. Production row `61241597` is titled "Dana
White's Contender Series: Norbert Növényi Jr. vs. Theo Haig" and its two
outcomes are **props** — "Haig in Round 3" and "Növényi Jr. in Round 2". A bout
shows prices only when its outcomes ARE the two fighters its title names, and
otherwise shows the fighters with no numbers.

Most of these bouts have no price for a second reason, which is not this change's
to fix: the Polymarket scan cannot currently reach any event listed before today
(#6758), so the moneyline the venue publishes for them never lands. The venue's
own API carries `0xf4cf69164b08` — `["Norma Dumont","Ailin Perez"]`,
`["0.54","0.46"]`, `closed=false` — and we hold no row for it.
"""

from __future__ import annotations

import itertools
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import (
    _DATE_TOKEN_RE,
    card_slug,
    list_card_concepts,
    title_bout_sides,
    venue_bout_group,
    venue_bout_is_priced,
    venue_card_promotion,
    venue_card_token,
)
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter

_IDS = itertools.count(70000)


def _far(days: int, hour: int = 19) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


#: The card's real fight time, and the LISTING stamp the venue also carries. The
#: gap is the defect: production's 26 Sep card was listed on 12 Sep.
_FIGHT_START = _far(9)
_LISTED_AT = _far(-5, hour=22)


def _vmeta(start: datetime, event_id: str) -> dict:
    return {
        "venue_game_start": start.isoformat().replace("+00:00", "Z"),
        "polymarket_event_id": event_id,
    }


def _outcome(name: str, probability: float | None):
    return SimpleNamespace(
        name=name, current_probability=probability, last_updated=None
    )


def _venue_row(name, start, event_id, outcomes=(), *, listed=None, external=None):
    """A Polymarket `futures_markets` row, ORM-shaped for the adapter."""
    market_id = next(_IDS)
    return SimpleNamespace(
        id=market_id,
        external_id=external or str(event_id),
        name=name,
        source="polymarket",
        status="open",
        commence_time=listed or _LISTED_AT,
        market_metadata=_vmeta(start, event_id),
        outcomes=list(outcomes),
    )


def _projection(rows):
    """`COMBAT_PROJECTION` order, which is what `list_card_concepts` reads."""
    return [
        (m.id, m.external_id, m.name, m.commence_time, m.market_metadata) for m in rows
    ]


# ── The three real cards, verbatim from production ─────────────────────────────

_FIGHT_NIGHT = [
    _venue_row(f"UFC Fight Night: {matchup}", _FIGHT_START, str(1013420 + i))
    for i, matchup in enumerate(
        [
            "Norma Dumont vs. Ailin Perez (Women's Bantamweight, Prelims)",
            "Vanessa Demopoulos vs. Yazmin Jauregui (Women's Strawweight, Prelims)",
            "Alatengheili vs. John Castaneda (Bantamweight, Prelims)",
            "Ricky Simon vs. Montel Jackson (Bantamweight, Prelims)",
            "Christian Edwards vs. Rodolfo Bellato (Light Heavyweight, Prelims)",
            "Elves Brener vs. Josiah Harrell (Lightweight, Main Card)",
            "Valesca Machado vs. Melissa Amaya (Women's Strawweight, Main Card)",
            "Ilimbek Akylbek Uulu vs. Mehemmedeli Osmanli (Bantamweight, Main Card)",
            "Brady Hiestand vs. Rinya Nakamura (Bantamweight, Main Card)",
            "Robert Bryczek vs. Rodolfo Vieira (Middleweight, Main Card)",
            "Raoni Barcelos vs. Raul Rosas Jr. (Bantamweight, Main Card)",
        ]
    )
]

_DWCS_START = _far(5, hour=23)
_DWCS_TITLE = "Dana White's Contender Series: Paris Moran vs. Marcos Degli"
#: The same bout twice — the event-level parent and its condition-id child. Only
#: the child carries the moneyline. Both are named as the matchup.
_DWCS_PARENT = _venue_row(_DWCS_TITLE, _DWCS_START, "1035320", [])
_DWCS_CHILD = _venue_row(
    _DWCS_TITLE,
    _DWCS_START,
    "1035320",
    [_outcome("Paris Moran", 0.5), _outcome("Marcos Degli", 0.5)],
    external="0x11146d202cffc0a0757efb80b708",
)
#: A matchup title whose two outcomes are PROPS, not fighters.
_DWCS_PROPS = _venue_row(
    "Dana White's Contender Series: Norbert Növényi Jr. vs. Theo Haig",
    _DWCS_START,
    "1035313",
    [_outcome("Haig in Round 3", 0.505), _outcome("Növényi Jr. in Round 2", 0.5)],
)
#: The card's own props, which carry no colon and must never become bouts.
_DWCS_NOISE = [
    _venue_row("O/U 2.5 Rounds", _DWCS_START, "1035321", []),
    _venue_row("Will Theo Haig win in Round 3?", _DWCS_START, "1035313", []),
    _venue_row("Will the fight end before Round 3?", _DWCS_START, "1035317", []),
]

_DWCS = [_DWCS_PARENT, _DWCS_CHILD, _DWCS_PROPS, *_DWCS_NOISE]


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
    """Dispatch on the statement text, never one shared list — feeding market
    rows to the Event reader makes an arm pass for the wrong reason."""

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


def _resolve(slug: str) -> str:
    """What `build_event` reduces a URL slug to."""
    target = re.sub(r"[^a-z0-9]", "", slug.lower())
    match = _DATE_TOKEN_RE.search(target)
    return target[match.start() :] if match else target


# ═══════════════════════════════════════════════════════════════════════════
# The key itself.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheIdentityIsThePair:
    def test_a_venue_bout_gets_a_card_token_at_all(self):
        """The defect, stated directly: every one of these was `None`."""
        assert venue_card_token(
            UFC_CONFIG, _FIGHT_NIGHT[0].name, _FIGHT_NIGHT[0].market_metadata
        )

    def test_every_bout_of_one_card_shares_one_token(self):
        tokens = {
            venue_card_token(UFC_CONFIG, m.name, m.market_metadata)
            for m in _FIGHT_NIGHT
        }
        assert len(tokens) == 1, tokens

    def test_two_promotions_on_ONE_date_are_two_cards(self):
        """The half a date-only key gets wrong (#4093). Same instant, and the
        promotions must not merge."""
        same_day = _FIGHT_START
        a = venue_card_token(
            UFC_CONFIG,
            "UFC Fight Night: A Fighter vs. B Fighter",
            _vmeta(same_day, "1"),
        )
        b = venue_card_token(
            UFC_CONFIG, "Power Slap 23: C Slapper vs. D Slapper", _vmeta(same_day, "2")
        )
        assert a and b and a != b

    def test_one_promotion_on_TWO_dates_is_two_cards(self):
        """The half a promotion-only key gets wrong — Fight Night recurs."""
        a = venue_card_token(
            UFC_CONFIG, _FIGHT_NIGHT[0].name, _vmeta(_FIGHT_START, "1")
        )
        b = venue_card_token(
            UFC_CONFIG,
            _FIGHT_NIGHT[0].name,
            _vmeta(_FIGHT_START + timedelta(days=14), "2"),
        )
        assert a and b and a != b

    def test_the_LISTING_stamp_is_never_the_card_date(self):
        """`commence_time` is Gamma's `startDate`. A token built from it dates the
        26 Sep card to 12 Sep and the card never forms."""
        from app.utils.event_combat import event_commence_token

        token = venue_card_token(
            UFC_CONFIG, _FIGHT_NIGHT[0].name, _FIGHT_NIGHT[0].market_metadata
        )
        assert event_commence_token(_FIGHT_START) in token
        assert event_commence_token(_LISTED_AT) not in token

    def test_a_row_the_venue_gives_no_fixture_time_for_mints_nothing(self):
        assert venue_card_token(UFC_CONFIG, _FIGHT_NIGHT[0].name, {"a": 1}) is None
        assert venue_card_token(UFC_CONFIG, _FIGHT_NIGHT[0].name, None) is None

    @pytest.mark.parametrize(
        "name",
        [
            "O/U 2.5 Rounds",
            "Will Theo Haig win in Round 3?",
            "Will the fight end before Round 3?",
            "Who will be UFC Flyweight champion at the end of 2026?",
            "Will Trump attend UFC 331?",
        ],
    )
    def test_a_prop_is_not_a_card(self, name):
        """Cards are keyed by FIGHTS. A title with no matchup mints no token,
        however good its `venue_game_start` is."""
        assert venue_card_token(UFC_CONFIG, name, _vmeta(_FIGHT_START, "1")) is None
        assert venue_card_promotion(name) is None

    def test_a_NUMBERED_card_unifies_onto_the_ticker_token(self):
        """ "UFC 331" is globally unique on its date and is what the Kalshi path
        already keys, so the venue rows must join that card rather than mint a
        second one beside it."""
        from app.utils.event_combat import card_token, event_commence_token

        ticker = card_token(
            UFC_CONFIG,
            f"kalshi:KXUFCFIGHT-{event_commence_token(_FIGHT_START).upper()}PANVAN",
        )
        venue = venue_card_token(
            UFC_CONFIG,
            "UFC 331: Alexandre Pantoja vs. Joshua Van (Flyweight, Main Card)",
            _vmeta(_FIGHT_START, "1"),
        )
        assert venue == ticker


class TestOutcomesAreNotEvidenceOfABout:
    def test_a_matchup_title_over_two_PROPS_is_not_priced(self):
        """Production `61241597`. Counting outcomes renders these two props as
        the fighters' win probabilities."""
        assert not venue_bout_is_priced(
            _DWCS_PROPS.name, [o.name for o in _DWCS_PROPS.outcomes]
        )

    def test_a_real_moneyline_is_priced(self):
        assert venue_bout_is_priced(
            _DWCS_CHILD.name, [o.name for o in _DWCS_CHILD.outcomes]
        )

    def test_a_surname_match_is_not_enough(self):
        """`player_key` matches both props to both fighters, which is why the
        test is exact folded-name equality and not containment."""
        assert not venue_bout_is_priced(
            "Power Slap 23: Brandon Wilson vs. Brian Ellis (Fight 1)",
            ["Wilson by KO", "Ellis by KO"],
        )

    @pytest.mark.parametrize("outs", [[], ["Only One Side"], ["A", "B", "C"]])
    def test_a_bout_that_is_not_two_sided_is_not_priced(self, outs):
        assert not venue_bout_is_priced(_DWCS_CHILD.name, outs)

    def test_the_title_gives_the_two_fighters_without_the_annotation(self):
        assert title_bout_sides(_FIGHT_NIGHT[0].name) == ("Norma Dumont", "Ailin Perez")

    def test_the_venue_event_id_is_the_dedupe_key(self):
        assert venue_bout_group(_DWCS_PARENT.market_metadata) == venue_bout_group(
            _DWCS_CHILD.market_metadata
        )


# ═══════════════════════════════════════════════════════════════════════════
# The lister — what Discover is offered.
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestTheCardReachesDiscover:
    async def test_the_eleven_bout_card_appears_once(self):
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection(_FIGHT_NIGHT)
        )
        assert len(concepts) == 1, concepts
        assert concepts[0]["name"] == "UFC Fight Night"
        assert concepts[0]["fight_count"] == 11

    async def test_the_card_is_dated_by_the_fight_not_the_listing(self):
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection(_FIGHT_NIGHT)
        )
        assert concepts[0]["start_date"] == _FIGHT_START.isoformat()
        assert concepts[0]["status"] == "upcoming"

    async def test_one_bout_published_twice_counts_once(self):
        """The venue publishes a bout as a parent row AND a condition-id child."""
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection(_DWCS)
        )
        assert len(concepts) == 1, concepts
        assert concepts[0]["name"] == "Dana White's Contender Series"
        assert concepts[0]["fight_count"] == 2, (
            "Moran/Degli is ONE bout across two rows, plus Növényi/Haig — the "
            "card's four prop rows are not bouts at all"
        )

    async def test_two_promotions_on_one_slate_stay_two_cards(self):
        concepts = await list_card_concepts(
            UFC_CONFIG, _FakeDB(), rows=_projection([*_FIGHT_NIGHT, *_DWCS])
        )
        assert {c["name"] for c in concepts} == {
            "UFC Fight Night",
            "Dana White's Contender Series",
        }

    async def test_a_ticker_card_is_untouched(self):
        """The Kalshi path keeps its key, its name and its count."""
        from app.utils.event_combat import event_commence_token

        token = event_commence_token(_FIGHT_START).upper()
        rows = [
            (
                901,
                f"kalshi:KXUFCFIGHT-{token}PANVAN",
                "Alexandre Pantoja vs. Joshua Van",
                _FIGHT_START,
                {"event_title": "UFC 331: Pantoja vs Van"},
            )
        ]
        concepts = await list_card_concepts(UFC_CONFIG, _FakeDB(), rows=rows)
        assert len(concepts) == 1
        assert concepts[0]["key"] == f"event:ufc:{token.lower()}"
        assert concepts[0]["is_major"] is True
        assert concepts[0]["main_event_id"] == 901


# ═══════════════════════════════════════════════════════════════════════════
# The page — "its actual bouts remain reachable".
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestTheCardHasAPage:
    async def _page(self, rows):
        token = venue_card_token(UFC_CONFIG, rows[0].name, rows[0].market_metadata)
        return await UFCEventAdapter().build_event(token, _FakeDB(markets=rows))

    async def test_the_card_the_feed_offers_resolves(self):
        built = await self._page(_FIGHT_NIGHT)
        assert built is not None
        assert built["event"]["name"] == "UFC Fight Night"

    async def test_every_bout_is_reachable_on_it(self):
        built = await self._page(_FIGHT_NIGHT)
        assert len(built["children"]) == 11
        assert len(built["sections"][0]["market_ids"]) == 11

    async def test_a_bout_we_cannot_price_shows_the_fighters_and_no_number(self):
        """#6758 — the venue publishes a moneyline for these and our scan cannot
        reach it. The honest answer is the two names and an empty space."""
        built = await self._page(_FIGHT_NIGHT)
        child = built["children"][0]
        assert [o["name"] for o in child["outcomes"]]
        assert all(o["probability"] is None for o in child["outcomes"])
        assert child["probability"] is None

    async def test_a_prop_pair_never_renders_as_the_fighters(self):
        built = await self._page(_DWCS)
        by_name = {c["market_name"]: c for c in built["children"]}
        props = by_name["Norbert Növényi Jr. vs. Theo Haig"]
        assert {o["name"] for o in props["outcomes"]} == {
            "Norbert Növényi Jr.",
            "Theo Haig",
        }, "the two PROPS must never be served as the two fighters"
        assert all(o["probability"] is None for o in props["outcomes"])

    async def test_the_bout_we_can_price_keeps_its_prices(self):
        built = await self._page(_DWCS)
        by_name = {c["market_name"]: c for c in built["children"]}
        moran = by_name["Paris Moran vs. Marcos Degli"]
        assert {o["name"] for o in moran["outcomes"]} == {"Paris Moran", "Marcos Degli"}
        assert all(o["probability"] is not None for o in moran["outcomes"])

    async def test_one_bout_published_twice_is_one_row_on_the_page(self):
        built = await self._page(_DWCS)
        assert len(built["children"]) == 2, [
            c["market_name"] for c in built["children"]
        ]

    async def test_the_pretty_slug_resolves_back_to_the_card(self):
        built = await self._page(_FIGHT_NIGHT)
        token = venue_card_token(
            UFC_CONFIG, _FIGHT_NIGHT[0].name, _FIGHT_NIGHT[0].market_metadata
        )
        assert _resolve(built["event"]["slug"]) == token
        again = await UFCEventAdapter().build_event(
            built["event"]["slug"], _FakeDB(markets=_FIGHT_NIGHT)
        )
        assert again is not None and again["event"]["key"] == built["event"]["key"]

    async def test_an_unrelated_card_is_not_on_this_page(self):
        built = await self._page(_FIGHT_NIGHT)
        assert not any(
            "Moran" in c["market_name"] or "Haig" in c["market_name"]
            for c in built["children"]
        )

    async def test_no_price_means_no_chart_and_no_stamp(self):
        built = await self._page(_FIGHT_NIGHT)
        assert built["primary"]["evolution_market_id"] is None
        assert built["primary"]["price_observed_at"] is None


class TestLegacyLinksAreUnmoved:
    @pytest.mark.parametrize(
        "slug,expected",
        [
            ("26jul18", "26jul18"),
            ("ufc-329-mcgregor-vs-holloway-2-26jul18", "26jul18"),
            ("event:ufc:26sep19", "26sep19"),
        ],
    )
    def test_a_bare_or_pretty_ticker_slug_still_resolves_to_its_date(
        self, slug, expected
    ):
        """The resolver now keeps the tail after the date token. For every slug
        `card_slug` has ever produced the token is last, so the tail IS the
        match and this is a no-op."""
        assert _resolve(slug) == expected

    def test_a_venue_slug_keeps_its_promotion(self):
        # Derived, never a hardcoded copy — so the round-trip is asserted against
        # the token the code actually mints and cannot drift from it. (It also
        # keeps gitleaks out of the way: its generic-api-key rule reads any
        # key-ish variable assigned a high-entropy literal as a credential, and
        # failed this gate twice on a card date-token that is not a secret.)
        minted = venue_card_token(
            UFC_CONFIG, _FIGHT_NIGHT[0].name, _FIGHT_NIGHT[0].market_metadata
        )
        assert _resolve(card_slug("UFC Fight Night", minted)) == minted
