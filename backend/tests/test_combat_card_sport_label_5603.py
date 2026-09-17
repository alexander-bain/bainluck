"""#5603 / #2602 — a fight card's chip says what a source supports, not what our
router called it.

═══ THE DEFECT ═══

Every surface that shows an event concept prints ``domain.upper()`` — the web
`ConceptCard`, the web `EventHeader`, the native concept card. This engine's MMA
domain is ``ufc``, because that is the adapter key, the URL segment and the card
gradient. So on 2026-09-17 the production page
``/api/event/event:ufc:26sep18powerslap23`` — a card the venue itself titles
"Power Slap 23", a slap-fighting promotion — wore a **UFC** chip, and so did
every Dana White's Contender Series card and every bare sportsbook row that
arrived under the umbrella ``mma_mixed_martial_arts`` key.

``domain`` is OUR routing token. It is not a claim any source made, and it is
not a promotion. Codex's Brief 18 (2026-09-17 19:07Z) put it exactly:
*"Current namespace/domain `ufc` is routing, not evidence of UFC membership …
UFC needs source support, schedule-only MMA remains MMA, known other combat
promotion must not be mislabeled UFC/MMA just because it uses this adapter."*

═══ THE RULE ═══

:func:`app.utils.event_combat.card_sport_label` — three tiers, strongest first,
every doubt resolving DOWNWARD:

    1. venue's own fight series lists it (a `KXUFCFIGHT-…` ticker)  -> "UFC"
    2. venue TITLES every bout with the promotion                   -> "UFC"
       a venue title naming some other promotion                    -> "Combat"
    3. schedule rows only (the sport key names no promoter)         -> "MMA"

Served as ``sport_label``, on the feed concept item, the hub rail row and all
three /event envelope branches — **absent, never null**, when the sport declares
no labels, so boxing and every non-combat domain are untouched and an older
renderer's presence test is its whole question.

═══ WHAT THIS DELIBERATELY DOES NOT CLAIM ═══

The chip is a DISPLAY claim about the card's identity. It does not certify that
every bout grouped under the card belongs to the promotion it names — a bare
date-token card can still sweep in a foreign bout (#5602 / #5603's membership
half), and that is not this change's to fix. It grades what the card may be
CALLED, which is the half a reader can see.

Nor does it suppress anything. Codex refused `optional-same-card-headline.diff`
in the same note: *"no ranking/suppression policy is granted by the label
repair"*. The eligibility tripwires at the bottom of this file exist so the
withdrawn Brief 17 cross-date rule cannot return under the label repair's cover.

ALL FIXTURES ARE SYNTHETIC OR VERBATIM-PRODUCTION-SHAPED. Nothing here reaches a
network or a database.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.utils import event_combat as ec
from app.utils.event_boxing import BOXING_CONFIG
from app.utils.event_combat import card_sport_label, list_card_concepts
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter

_IDS = itertools.count(510000)


def _far(days: int, hour: int = 19) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


def _token(when: datetime) -> str:
    return ec.event_commence_token(when)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures — ORM-shaped rows, the same shapes `test_combat_card_venue_*` use.
# ═══════════════════════════════════════════════════════════════════════════


def _outcome(name: str, probability: float | None, *, yes_bid=None, yes_ask=None):
    return SimpleNamespace(
        name=name,
        current_probability=probability,
        last_updated=None,
        current_yes_bid=yes_bid,
        current_yes_ask=yes_ask,
        resolution_source=None,
    )


def _venue_row(name: str, start: datetime, event_id: str, outcomes=()):
    """A Polymarket `futures_markets` row: no card ticker, a titled matchup, and
    the venue's OWN fight start in `market_metadata` (never `commence_time`,
    which for Gamma is the listing stamp)."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=str(event_id),
        name=name,
        source="polymarket",
        status="open",
        commence_time=_far(-5, hour=22),
        market_metadata={
            "venue_game_start": start.isoformat().replace("+00:00", "Z"),
            "polymarket_event_id": str(event_id),
        },
        outcomes=list(outcomes),
    )


def _ticker_row(fighters: tuple[str, str], start: datetime, *, event_title=None):
    """A Kalshi `futures_markets` row whose ticker puts it in the UFC FIGHT
    series — tier 1's entire evidence."""
    tok = _token(start).upper()
    abbr = "".join(f[:3] for f in fighters).upper()
    return SimpleNamespace(
        id=next(_IDS),
        external_id=f"kalshi:KXUFCFIGHT-{tok}{abbr}",
        name=f"{fighters[0]} vs {fighters[1]}",
        source="kalshi",
        status="open",
        commence_time=start + timedelta(hours=4),  # Kalshi's CLOSE stamp
        market_metadata={"event_title": event_title} if event_title else {},
        outcomes=[_outcome(fighters[0], 0.6), _outcome(fighters[1], 0.4)],
    )


def _bout(home: str, away: str, when: datetime):
    """An `events` row — the schedule source, which names no promoter."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=None,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status="scheduled",
    )


def _projection(rows):
    """`COMBAT_PROJECTION` order — what `list_card_concepts` actually reads."""
    return [
        (m.id, m.external_id, m.name, m.commence_time, m.market_metadata) for m in rows
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


def _concepts(markets=(), events=()):
    """Run the REAL lister and key its output."""
    out = asyncio.run(
        list_card_concepts(
            UFC_CONFIG,
            _FakeDB(events=events, markets=markets),
            rows=_projection(markets),
            limit=50,
        )
    )
    return {c["key"]: c for c in out}


def _page(slug: str, markets=(), events=()):
    """Run the REAL /event adapter for one card."""
    return asyncio.run(
        UFCEventAdapter().build_event(slug, _FakeDB(events=events, markets=markets))
    )


# ── The production specimens, verbatim ────────────────────────────────────────

_POWER_SLAP_START = _far(4, hour=1)
#: The card Alex's page photographed as "UFC". One bout, published twice (the
#: event-level parent and its condition-id child), titled by the venue.
_POWER_SLAP = [
    _venue_row(
        "Power Slap 23: Wilson Pantoja vs. Ellis Hawthorne",
        _POWER_SLAP_START,
        "1041001",
    ),
    _venue_row(
        "Power Slap 23: Wilson Pantoja vs. Ellis Hawthorne",
        _POWER_SLAP_START,
        "1041001",
        [_outcome("Wilson Pantoja", 0.5), _outcome("Ellis Hawthorne", 0.495)],
    ),
]

_FIGHT_NIGHT_START = _far(9)
_FIGHT_NIGHT = [
    _venue_row(f"UFC Fight Night: {matchup}", _FIGHT_NIGHT_START, str(1013420 + i))
    for i, matchup in enumerate(
        [
            "Norma Dumont vs. Ailin Perez (Women's Bantamweight, Prelims)",
            "Ricky Simon vs. Montel Jackson (Bantamweight, Prelims)",
            "Raoni Barcelos vs. Raul Rosas Jr. (Bantamweight, Main Card)",
        ]
    )
]

_DWCS_START = _far(5, hour=23)
_DWCS = [
    _venue_row(
        "Dana White's Contender Series: Paris Moran vs. Marcos Degli",
        _DWCS_START,
        "1035320",
    )
]

_SCHEDULE_START = _far(11, hour=18)
#: The #5603 headline specimen's shape: an MMA bout the sportsbooks price and no
#: venue lists by series or title. The Odds API files these under `mma_ufc` AND
#: `mma_mixed_martial_arts` indiscriminately, so the key is not promoter evidence.
_SCHEDULE_BOUTS = [
    _bout("Jean Silva", "Jose Delgado", _SCHEDULE_START),
    _bout("Kennedy Rayomba", "Andrej Kalasnik", _SCHEDULE_START - timedelta(hours=2)),
]


# ═══════════════════════════════════════════════════════════════════════════
# A. The tiers, stated directly on the pure helper.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheEvidenceTiers:
    @pytest.mark.parametrize(
        "ticker,promos,expected,why",
        [
            (1, (), "UFC", "the venue's own fight series lists this card"),
            (13, (), "UFC", "same, at a real card's row count"),
            (
                1,
                ("Power Slap 23",),
                "UFC",
                "a series ticker outranks a stray title on the same card",
            ),
            (
                0,
                ("UFC Fight Night", "UFC Fight Night"),
                "UFC",
                "every title names the promotion",
            ),
            (0, ("UFC 331", "UFC 331"), "UFC", "a numbered card is still its say-so"),
            (
                0,
                ("UFC Fight Night", "Oktagon 77"),
                "Combat",
                "mixed provenance may not assert the stronger promotion",
            ),
            (
                0,
                ("UFCW Wrestling",),
                "Combat",
                "word boundary: 'UFCW' is not 'UFC'",
            ),
            (0, ("Power Slap 23",), "Combat", "the venue named someone else"),
            (
                0,
                ("Dana White's Contender Series",),
                "Combat",
                "a UFC property the venue does not title 'UFC' claims neither",
            ),
            (0, (), "MMA", "schedule rows name no promoter"),
            (0, (None, ""), "MMA", "empty titles are no titles"),
        ],
    )
    def test_the_label_is_the_evidence(self, ticker, promos, expected, why):
        assert (
            card_sport_label(
                UFC_CONFIG, ticker_fights=ticker, venue_promotions=promos
            )
            == expected
        ), why

    def test_every_doubt_resolves_downward(self):
        """The asymmetry that is the whole point: the strong label needs proof,
        the weak ones are what we fall back to."""
        unproven = card_sport_label(UFC_CONFIG, ticker_fights=0, venue_promotions=())
        assert unproven != UFC_CONFIG.promotion_label
        assert unproven == UFC_CONFIG.schedule_label

    def test_a_sport_with_no_labels_emits_nothing_at_all(self):
        """Boxing's domain IS its sport, so it has nothing to add and every
        renderer must behave exactly as it did before this change."""
        assert BOXING_CONFIG.promotion_label == ""
        for ticker, promos in ((1, ()), (0, ("Golden Boy",)), (0, ())):
            assert (
                card_sport_label(
                    BOXING_CONFIG, ticker_fights=ticker, venue_promotions=promos
                )
                is None
            )

    def test_the_ufc_config_declares_all_three_tiers(self):
        """The totality claim the payload contract rests on: with all three
        declared, no card of this domain can come back unlabelled, so an ABSENT
        `sport_label` on a `ufc` card means an old payload and nothing else."""
        assert UFC_CONFIG.promotion_label == "UFC"
        assert UFC_CONFIG.schedule_label == "MMA"
        assert UFC_CONFIG.generic_label == "Combat"


# ═══════════════════════════════════════════════════════════════════════════
# B. Through the REAL lister, on the real specimens.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheListerLabelsTheRealCards:
    def test_power_slap_is_not_ufc(self):
        """The photographed defect. The card keeps its name, its key, its bout
        and its page — it loses only the claim it could not support."""
        cards = _concepts(markets=_POWER_SLAP)
        (card,) = cards.values()
        assert card["sport_label"] == "Combat"
        assert card["name"] == "Power Slap 23"
        assert card["domain"] == "ufc", "the routing token is untouched"
        assert card["key"].startswith("event:ufc:"), "links must not move"
        assert card["fight_count"] == 1

    def test_a_venue_titled_ufc_card_keeps_ufc(self):
        cards = _concepts(markets=_FIGHT_NIGHT)
        (card,) = cards.values()
        assert card["sport_label"] == "UFC"
        assert card["name"] == "UFC Fight Night"

    def test_the_contender_series_claims_neither(self):
        (card,) = _concepts(markets=_DWCS).values()
        assert card["sport_label"] == "Combat"

    def test_a_schedule_only_card_is_mma(self):
        (card,) = _concepts(events=_SCHEDULE_BOUTS).values()
        assert card["sport_label"] == "MMA"

    def test_a_kalshi_series_card_is_ufc(self):
        start = _far(6, hour=22)
        rows = [
            _ticker_row(("Alexandre Pantoja", "Joshua Van"), start),
            _ticker_row(("Renato Moicano", "Brian Ortega"), start),
        ]
        (card,) = _concepts(markets=rows).values()
        assert card["sport_label"] == "UFC"

    def test_two_promotions_on_one_night_get_two_labels(self):
        """Codex's 'a foreign member accidentally attached by date' check, from
        the reader's side: the Power Slap card and a UFC card on the SAME night
        stay two cards, and neither borrows the other's chip."""
        same_night = _far(7, hour=22)
        ufc = [_ticker_row(("Ann Alpha", "Bea Bravo"), same_night)]
        slap = [
            _venue_row("Power Slap 24: Cy Charlie vs. Dee Delta", same_night, "2001")
        ]
        labels = {
            c["name"]: c["sport_label"] for c in _concepts(markets=ufc + slap).values()
        }
        assert len(labels) == 2, labels
        assert labels["Power Slap 24"] == "Combat"
        assert set(labels.values()) == {"UFC", "Combat"}

    def test_a_ufc_card_and_a_foreign_schedule_bout_on_its_date(self):
        """The bare date-token card still sweeps in a same-day schedule bout
        from another promotion (#5602, NOT fixed here). The chip is a claim
        about the card's IDENTITY, which is taken from the ticker rows that
        also named it — so it reads UFC, and this test exists so the next reader
        knows that is deliberate rather than an oversight."""
        night = _far(8, hour=22)
        ufc = [_ticker_row(("Ann Alpha", "Bea Bravo"), night, event_title="UFC 340")]
        foreign = [_bout("Oktagon Fighter", "Regional Opponent", night)]
        (card,) = _concepts(markets=ufc, events=foreign).values()
        assert card["sport_label"] == "UFC"
        assert card["name"].startswith("UFC 340")

    def test_every_card_of_this_domain_carries_a_label(self):
        """Totality, measured on the union of every specimen above — the
        contract the clients' fallback rule depends on."""
        cards = _concepts(
            markets=[*_POWER_SLAP, *_FIGHT_NIGHT, *_DWCS], events=_SCHEDULE_BOUTS
        )
        assert cards, "the fixture produced no cards at all"
        missing = [k for k, c in cards.items() if not c.get("sport_label")]
        assert missing == [], (
            f"{len(missing)} `ufc`-domain card(s) came back with no `sport_label`, "
            f"so a renderer cannot tell them from an old payload: {missing}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# C. Through the REAL /event adapter — all three envelope branches.
# ═══════════════════════════════════════════════════════════════════════════


class TestThePageAgreesWithTheCard:
    def test_the_power_slap_page_stops_saying_ufc(self):
        """The venue-envelope branch, and the exact URL the BEFORE screenshot
        was taken of."""
        token = f"{_token(_POWER_SLAP_START)}powerslap23"
        env = _page(token, markets=_POWER_SLAP)
        assert env is not None, "the page must not 404 — it keeps its bout"
        assert env["event"]["sport_label"] == "Combat"
        assert env["event"]["domain"] == "ufc"
        assert env["event"]["name"] == "Power Slap 23"
        names = [o["name"] for o in env["primary"]["competitors"]]
        assert names == ["Wilson Pantoja", "Ellis Hawthorne"]

    def test_the_ticker_page_says_ufc(self):
        start = _far(6, hour=22)
        rows = [_ticker_row(("Alexandre Pantoja", "Joshua Van"), start)]
        env = _page(_token(start), markets=rows)
        assert env["event"]["sport_label"] == "UFC"

    def test_the_schedule_only_page_says_mma(self):
        env = _page(_token(_SCHEDULE_START), events=_SCHEDULE_BOUTS)
        assert env is not None
        assert env["event"]["sport_label"] == "MMA"

    def test_the_page_and_the_card_never_disagree(self):
        """One helper, two callers. A card whose chip and whose page chip
        differed would be the #4555 class in a new place."""
        for markets, events in (
            (_POWER_SLAP, ()),
            (_FIGHT_NIGHT, ()),
            (_DWCS, ()),
            ((), _SCHEDULE_BOUTS),
        ):
            for card in _concepts(markets=markets, events=events).values():
                token = card["key"].split(":", 2)[2]
                env = _page(token, markets=markets, events=events)
                assert env is not None, f"{token} listed but has no page"
                assert env["event"]["sport_label"] == card["sport_label"], (
                    f"{token}: the card says {card['sport_label']!r} and the page "
                    f"behind it says {env['event']['sport_label']!r}"
                )

    def test_a_boxing_envelope_gains_no_key(self):
        from app.utils.event_boxing import BoxingEventAdapter

        start = _far(12, hour=21)
        tok = _token(start).upper()
        row = SimpleNamespace(
            id=next(_IDS),
            external_id=f"KXBOXING-{tok}MASBEL",
            name="Mason Bell vs Carl Frame",
            source="kalshi",
            status="open",
            commence_time=start,
            market_metadata={},
            outcomes=[_outcome("Mason Bell", 0.55), _outcome("Carl Frame", 0.45)],
        )
        env = asyncio.run(
            BoxingEventAdapter().build_event(
                _token(start), _FakeDB(markets=[row])
            )
        )
        assert env is not None
        assert "sport_label" not in env["event"], (
            "boxing declares no labels, so its envelope must be byte-identical "
            "to the one it served before this change"
        )


# ═══════════════════════════════════════════════════════════════════════════
# D. The payload contract — fresh, missing-field, and the allowlisted rail.
# ═══════════════════════════════════════════════════════════════════════════


def _feed_harness(now, concepts):
    """The `_score_event_concepts` harness from `test_feed_concept_empty_gate`:
    a warm leader for every concept so the empty-concept gate admits them, and
    the OTHER listers emptied so only these cards can reach the output."""
    from app.utils.event_concept_cache import stamp_envelope

    warm = {
        c["key"]: json.dumps(
            stamp_envelope(
                {
                    "primary": {
                        "kind": "winner_field",
                        "competitors": [
                            {"name": "Ann Alpha", "probability": 0.55},
                            {"name": "Bea Bravo", "probability": 0.45},
                        ],
                    }
                },
                created_at=now,
                lifecycle_watermark=None,
            ),
            default=str,
        )
        for c in concepts
    }

    async def ufc(db, statuses=None, limit=None):
        return [dict(c) for c in concepts]

    async def empty(db, statuses=None, limit=None):
        return []

    class _Client:
        def _lookup(self, k):
            base = k[: -len(":stale")] if k.endswith(":stale") else k
            for key, raw in warm.items():
                if base.endswith(key):
                    return raw
            return None

        async def get(self, k):
            return self._lookup(k)

        async def mget(self, keys):
            return [self._lookup(k) for k in keys]

    async def _shared():
        return _Client()

    async def _bounded(fn):
        class _R:
            is_ok = True

        _R.value = await fn()
        return _R

    return ufc, empty, _shared, _bounded


async def _feed(concepts):
    from app.routes import feed as feed_mod
    import app.utils.request_cache as rc

    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    ufc, empty, _shared, _bounded = _feed_harness(now, concepts)
    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", ufc),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", empty),
        patch.object(rc, "get_shared_async_redis", _shared),
        patch.object(rc, "bounded_redis_call", _bounded),
    ):
        return {
            c["data"]["key"]: c["data"]
            for c in await feed_mod._score_event_concepts(None, now, None)
        }


def _lister_dict(key, **extra):
    base = {
        "key": key,
        "name": key,
        "domain": "ufc",
        "status": "upcoming",
        "start_date": "2026-09-19",
        "is_major": False,
        "fight_count": 5,
        "latest_commence": datetime(2026, 9, 19, 22, tzinfo=timezone.utc),
    }
    base.update(extra)
    return base


class TestThePayloadContract:
    @pytest.mark.asyncio
    async def test_the_feed_card_carries_the_label(self):
        data = await _feed(
            [
                _lister_dict("event:ufc:26sep19", sport_label="UFC"),
                _lister_dict("event:ufc:26sep18powerslap23", sport_label="Combat"),
            ]
        )
        assert data["event:ufc:26sep19"]["sport_label"] == "UFC"
        assert data["event:ufc:26sep18powerslap23"]["sport_label"] == "Combat"

    @pytest.mark.asyncio
    async def test_a_lister_that_says_nothing_serves_no_key(self):
        """The MISSING-FIELD contract, which is what every other domain is: the
        key is ABSENT, not null, so a renderer's presence test is its whole
        question and an older client is untouched."""
        data = await _feed([_lister_dict("event:cycling:vuelta-2026", domain="cycling")])
        (item,) = data.values()
        assert "sport_label" not in item
        assert item["domain"] == "cycling"

    @pytest.mark.asyncio
    async def test_an_empty_label_is_never_served_as_a_chip(self):
        """A blank is not a label. It must not reach a client that would then
        print an empty chip, and it must not reach one that would fall back to
        the domain having been told the server HAD something to say."""
        data = await _feed([_lister_dict("event:ufc:26sep19", sport_label="")])
        (item,) = data.values()
        assert "sport_label" not in item

    def test_the_hub_rail_does_not_silently_drop_it(self):
        """`_serialize_concept` is an ALLOWLIST (UX-P178): a key the lister emits
        and it does not name vanishes while the route still returns 200. The
        combat listers emit this one, so the rail must name it."""
        from app.routes.hub import _serialize_concept

        row = _serialize_concept(_lister_dict("event:ufc:26sep18ps", sport_label="Combat"))
        assert row["sport_label"] == "Combat"
        assert "sport_label" not in _serialize_concept(_lister_dict("event:ufc:x"))


# ═══════════════════════════════════════════════════════════════════════════
# E. Tripwires — the label repair grants no suppression policy.
# ═══════════════════════════════════════════════════════════════════════════


class TestNoFightLosesItsCard:
    """Codex, Brief 18: *"Brief17 cross-date rule remains withdrawn … Preserve
    current price eligibility and all real questions/pages/search."* The premise
    that rule rested on — nobody holds two bookings — is false: champions are
    booked twice a year and the sportsbooks list both."""

    def test_the_withdrawn_cross_date_rule_has_not_returned(self):
        assert not hasattr(ec, "contradicted_schedule_bouts")
        for card in _concepts(events=_SCHEDULE_BOUTS).values():
            assert "schedule_contradicted" not in card

    def test_two_fights_six_months_apart_both_keep_their_card(self):
        a = _bout("Ann Alpha", "Bea Bravo", _far(20))
        b = _bout("Ann Alpha", "Cyd Charlie", _far(200))
        cards = _concepts(events=[a, b])
        assert f"event:ufc:{_token(a.commence_time)}" in cards
        assert f"event:ufc:{_token(b.commence_time)}" in cards

    def test_a_later_rematch_keeps_both_cards(self):
        a = _bout("Ann Alpha", "Bea Bravo", _far(21))
        b = _bout("Ann Alpha", "Bea Bravo", _far(201))
        assert len(_concepts(events=[a, b])) == 2

    def test_labelling_a_card_never_removes_one(self):
        """The whole population, before/after the only thing this change adds."""
        markets = [*_POWER_SLAP, *_FIGHT_NIGHT, *_DWCS]
        cards = _concepts(markets=markets, events=_SCHEDULE_BOUTS)
        assert len(cards) == 4, sorted(cards)
        for card in cards.values():
            assert card["fight_count"] >= 1
            assert card["key"] and card["name"]

    def test_the_simultaneous_double_booking_gate_is_untouched(self):
        """The one contradiction the rows themselves prove (#4485) still fires —
        nobody is in two cages at one instant."""
        when = _far(150)
        pile = [
            _bout("Ann Alpha", "Bea Bravo", when),
            _bout("Ann Alpha", "Cyd Charlie", when),
        ]
        assert ec.card_rows_are_not_a_schedule(pile) is True
        assert f"event:ufc:{_token(when)}" not in _concepts(events=pile)
