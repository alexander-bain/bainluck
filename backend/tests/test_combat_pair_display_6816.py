"""#6816: a fight's two displayed percentages agree.

WHAT A READER SAW. `GET /api/event/event%3Aufc%3A26sep19`, saved public response
2026-09-17 (`artifacts/other-model-combat-pair-display-execution/inputs/`):

    Arman Tsarukyan   74%
    Mauricio Ruffy    28%      <- 102%

and three more bouts on the same card. The quotes are 0.735 / 0.275: a half-cent
grid, so both sides of one bout sit on a rounding boundary and both round up.

WHAT THIS FILE EXECUTES. The REAL combat builder (`UFCEventAdapter.build_event`),
through all three envelopes — ticker, venue, schedule — and then the number a
consumer actually prints from the envelope it got back. `_printed` below is the
consumer rule the web and native arms implement (`servedBoutPercents.ts`,
`ConceptCardPresentation`): both served integers, or the whole pair falls back to
one independent `rendered_percent` per side. So the headline assertions are about
THE PRINTED PAIR — they were red on the unpatched builder because 74 + 28 is 102,
not because a helper was missing.

═══ SYNTHETIC ROWS, LABELLED ═══

Every `futures_markets` / `events` row in this file is SYNTHETIC: ORM-shaped
`SimpleNamespace`s, the same harness `test_concept_card_unsupported_price_6777`
uses. The PROBABILITIES and NAMES of the four named bouts are the saved public
response's, quoted rather than paraphrased. Their tickers, ids, and bid/ask books
are invented to drive the builder — the saved response carries none of them, and
nothing here is a reconstructed production fact about a book.

═══ WHAT IS NOT CLAIMED ═══

No probability moves. `probability` leaves the builder byte-identical to before,
and the saved 0.735 / 0.275 is asserted verbatim. The synthetic rows below do NOT
establish the named production rows' eligibility: that is decided at runtime
from each row's own `source` + series against `COMPLEMENTARY_BOUT_CONTRACTS`.

═══ THE PROOF A PAIR IS ONE QUESTION (Brief 22A) ═══

Shape (two rows, the titled fighters) and arithmetic (a sum inside the band) are
not the settlement contract. A fight can end in a draw or a no contest; "mutually
exclusive" is satisfied by a rule that pays NEITHER side then, under which the
draw's probability sits in the gap — possibly under a point, inside the band —
and a normalised pair would round it into a fighter's number. So a family pairs
only when its venue's published rule is on record and settles a draw as a half
to EACH side (the pair then pays the whole in every result). Kalshi `KXUFCFIGHT`
is on record (rule `UFC-RULES4`, read 2026-09-17, quoted in `event_combat`).
`KXBOXING` and every Polymarket bout are NOT, and print exactly as before #6816.
`TestTheSettlementContractIsTheProof` below drives both through the real builders.
"""

from __future__ import annotations

import itertools
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils import aggregation, event_combat
from app.utils.event_combat import (
    DISPLAY_PERCENT_FIELD,
    bout_sides_are_its_titled_fighters,
    printable_probabilities,
    ticker_bout_is_one_question,
    venue_card_token,
    with_bout_display_percents,
)
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter
from app.utils.graded_card import rendered_percent

_IDS = itertools.count(6816000)


def _far(days: int, hour: int = 19) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


_TOKEN = "26SEP19"
_CLOSE = _far(3)


def _tight_book(probability):
    """SYNTHETIC: a one-cent two-sided book around the quoted midpoint."""
    p = float(probability)
    return (round(p - 0.005, 4), round(p + 0.005, 4))


def _outcome(name, probability, book="tight"):
    if book == "tight":
        book = _tight_book(probability) if probability is not None else (None, None)
    yes_bid, yes_ask = book
    return SimpleNamespace(
        name=name,
        current_probability=probability,
        last_updated=None,
        current_yes_bid=yes_bid,
        current_yes_ask=yes_ask,
        resolution_source=None,
    )


def _ticker_fight(code, title, outcomes, *, close=_CLOSE, **extra):
    """SYNTHETIC Kalshi fight row, ORM-shaped for the adapter."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=f"kalshi:KXUFCFIGHT-{_TOKEN}{code}",
        name=title,
        source="kalshi",
        status="open",
        commence_time=close,
        market_metadata={},
        outcomes=list(outcomes),
        **extra,
    )


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def scalars(self):
        return self

    def unique(self):
        return self


class _FakeDB:
    """Dispatch on the statement text, and COUNT — the scan guard below reads it."""

    def __init__(self, markets=(), events=()):
        self._markets = list(markets)
        self._events = list(events)
        self.statements: list[str] = []

    async def execute(self, statement, *_a, **_k):
        sql = str(statement)
        self.statements.append(sql)
        if "futures_markets" in sql:
            return _FakeResult(self._markets)
        if "FROM events" in sql:
            return _FakeResult(self._events)
        return _FakeResult([])


async def _page(markets=(), events=(), token=None):
    db = _FakeDB(markets=markets, events=events)
    envelope = await UFCEventAdapter().build_event(token or _TOKEN.lower(), db)
    return envelope, db


def _child(envelope, title):
    return next(c for c in envelope["children"] if c["market_name"] == title)


def _printed(rows):
    """The integers a consumer prints for a bout's rows.

    BOTH served, or the pair falls back whole to one `rendered_percent` per
    side — the rule `frontend/lib/servedBoutPercents.ts` and the native
    `ConceptCardPresentation` implement. On an envelope that carries no served
    field at all (the unpatched builder) this is exactly what a reader saw.
    """
    served = [row.get(DISPLAY_PERCENT_FIELD) for row in rows]
    if len(served) == 2 and all(isinstance(p, int) for p in served):
        return served
    return [rendered_percent(row["probability"]) for row in rows]


# ═══════════════════════════════════════════════════════════════════════════
# The four named bouts, through the real builder
# ═══════════════════════════════════════════════════════════════════════════

#: (title, favourite, quote, underdog, quote, what a reader SAW, what prints now).
#: Names and quotes: the saved public response. Everything else: synthetic.
NAMED = [
    (
        "331: Tsarukyan vs Ruffy",
        "Arman Tsarukyan",
        0.735,
        "Mauricio Ruffy",
        0.275,
        [74, 28],
        [73, 27],
    ),
    (
        "331: Chikadze vs Brito",
        "Joanderson Brito",
        0.785,
        "Giga Chikadze",
        0.225,
        [79, 23],
        [78, 22],
    ),
    (
        "331: Pitbull vs Choi",
        "Doo Ho Choi",
        0.725,
        "Patricio Pitbull",
        0.285,
        [73, 29],
        [72, 28],
    ),
    (
        "331: Aswell vs Yoo",
        "Joo Sang Yoo",
        0.665,
        "Michael Aswell",
        0.325,
        [67, 33],
        [67, 33],
    ),
]


def _named_card():
    rows = [
        _ticker_fight(f"N{i}", title, [_outcome(fav, p_fav), _outcome(dog, p_dog)])
        for i, (title, fav, p_fav, dog, p_dog, _saw, _now) in enumerate(NAMED)
    ]
    # The main event closes last (`fights[-1]`), and is a healthy pair.
    rows.append(
        _ticker_fight(
            "VANPAN",
            "331: Van vs Pantoja",
            [_outcome("Joshua van", 0.565), _outcome("Alexandre Pantoja", 0.435)],
            close=_CLOSE + timedelta(hours=1),
        )
    )
    return rows


class TestTheFourNamedBoutsPrintOneHundred:
    async def test_the_specimen_really_did_print_what_the_issue_says(self):
        """The defect is in the ARITHMETIC, reproduced from the saved quotes."""
        for _t, _f, p_fav, _d, p_dog, saw, _now in NAMED:
            assert [rendered_percent(p_fav), rendered_percent(p_dog)] == saw
        assert sum(NAMED[0][5]) == 102

    @pytest.mark.parametrize("named", NAMED, ids=[n[0] for n in NAMED])
    async def test_each_named_bout_prints_a_pair_that_agrees(self, named):
        title, fav, p_fav, dog, p_dog, _saw, now = named
        envelope, _db = await _page(_named_card())
        rows = _child(envelope, title)["outcomes"]
        printed = _printed(rows)
        assert sum(printed) == 100, f"{title} prints {printed}"
        assert printed == now
        # …and no probability moved to get there.
        assert [(r["name"], r["probability"]) for r in rows] == [
            (fav, p_fav),
            (dog, p_dog),
        ]

    async def test_the_hero_prints_the_same_pair_as_its_rail_row(self):
        rows = _named_card()
        # Make a NAMED bout the main event, so the hero carries a boundary pair.
        rows[0].commence_time = _CLOSE + timedelta(hours=2)
        envelope, _db = await _page(rows)
        hero = envelope["primary"]["competitors"]
        assert _printed(hero) == [73, 27]
        assert _printed(hero) == _printed(_child(envelope, NAMED[0][0])["outcomes"])
        assert [c["probability"] for c in hero] == [0.735, 0.275]

    async def test_a_pair_that_already_sums_to_one_stops_printing_101(self):
        """The issue's "other 8" sum to 1.000 on the wire and are NOT healthy on
        screen: 0.565 / 0.435 is a half-cent pair, so under the shared contract
        both round up — 57 / 44. Every bout in the saved response is on that grid.
        """
        envelope, _db = await _page(_named_card())
        rows = _child(envelope, "331: Van vs Pantoja")["outcomes"]
        assert [rendered_percent(r["probability"]) for r in rows] == [57, 44]
        assert _printed(rows) == [57, 43]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [57, 43]


# ═══════════════════════════════════════════════════════════════════════════
# Controls — through the builder wherever a builder branch decides
# ═══════════════════════════════════════════════════════════════════════════


def _solo(title, outcomes, **extra):
    return [_ticker_fight("SOLO", title, outcomes, **extra)]


async def _solo_rows(title, outcomes, **extra):
    envelope, _db = await _page(_solo(title, outcomes, **extra))
    return _child(envelope, title)["outcomes"]


class TestControls:
    async def test_a_half_point_tie_prints_fifty_fifty(self):
        rows = await _solo_rows(
            "331: Alpha vs Beta",
            [_outcome("Ann Alpha", 0.505), _outcome("Bea Beta", 0.505)],
        )
        assert _printed(rows) == [50, 50]

    async def test_a_genuine_even_bout_keeps_its_fifty(self):
        rows = await _solo_rows(
            "331: Alpha vs Beta",
            [_outcome("Ann Alpha", 0.5), _outcome("Bea Beta", 0.5)],
        )
        assert _printed(rows) == [50, 50]
        assert [r["probability"] for r in rows] == [0.5, 0.5]

    async def test_the_boundary_pair_gives_the_point_to_the_underdog(self):
        rows = await _solo_rows(
            "331: Alpha vs Beta",
            [_outcome("Ann Alpha", 0.505), _outcome("Bea Beta", 0.495)],
        )
        assert _printed(rows) == [51, 49]

    async def test_stored_order_does_not_move_a_number_onto_the_wrong_fighter(self):
        """REVERSED ORDER: the underdog row stored first."""
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [_outcome("Mauricio Ruffy", 0.275), _outcome("Arman Tsarukyan", 0.735)],
        )
        assert [(r["name"], r[DISPLAY_PERCENT_FIELD]) for r in rows] == [
            ("Arman Tsarukyan", 73),
            ("Mauricio Ruffy", 27),
        ]

    async def test_a_decimal_price_is_served_like_a_float(self):
        """Numeric(7,6) arrives as Decimal — the production type, not float."""
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [
                _outcome("Arman Tsarukyan", Decimal("0.735000")),
                _outcome("Mauricio Ruffy", Decimal("0.275000")),
            ],
        )
        assert _printed(rows) == [73, 27]
        assert all(type(r["probability"]) is float for r in rows)
        assert all(type(r[DISPLAY_PERCENT_FIELD]) is int for r in rows)

    async def test_a_missing_side_serves_no_percent_on_either_row(self):
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [_outcome("Arman Tsarukyan", 0.735), _outcome("Mauricio Ruffy", None)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]
        assert [r["probability"] for r in rows] == [0.735, None]

    async def test_price_support_comes_first_and_nothing_is_resurrected(self):
        """#6777's empty book refuses the PAIR; no complement brings a leg back."""
        rows = await _solo_rows(
            "331: Wilson vs Ellis",
            [
                _outcome("Brandon Wilson", 0.500000, (0.0200, 0.9900)),
                _outcome("Brian Ellis", 0.495000, (0.0100, 0.9800)),
            ],
        )
        assert [r["probability"] for r in rows] == [None, None]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_one_refused_side_still_refuses_both_percents(self):
        rows = await _solo_rows(
            "331: Wilson vs Ellis",
            [
                _outcome("Brandon Wilson", 0.500000, (0.0200, 0.9900)),
                _outcome("Brian Ellis", 0.495000),
            ],
        )
        assert [r["probability"] for r in rows] == [None, None]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_an_out_of_band_pair_is_not_normalised(self):
        """A third result priced at five points leaves the pair alone."""
        rows = await _solo_rows(
            "331: Alpha vs Beta",
            [_outcome("Ann Alpha", 0.70), _outcome("Bea Beta", 0.25)],
        )
        assert _printed(rows) == [70, 25]

    async def test_independent_binaries_under_a_fight_ticker_are_refused(self):
        """Two Yes/No-shaped rows that happen to sum near one are not a bout."""
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy", [_outcome("Yes", 0.735), _outcome("No", 0.275)]
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]
        assert _printed(rows) == [74, 28]  # exactly as before: no claim is made

    async def test_a_draw_leg_is_refused(self):
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [_outcome("Arman Tsarukyan", 0.735), _outcome("Draw", 0.275)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_a_no_contest_leg_is_refused(self):
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [_outcome("Arman Tsarukyan", 0.735), _outcome("No Contest", 0.275)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_two_props_under_a_matchup_title_are_refused(self):
        """`venue_bout_is_priced`'s specimen shape, on the ticker path."""
        rows = await _solo_rows(
            "331: Noveny vs Haig",
            [_outcome("Haig in Round 3", 0.735), _outcome("Noveny in Round 2", 0.275)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_a_row_flagged_non_exclusive_is_refused(self):
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [_outcome("Arman Tsarukyan", 0.735), _outcome("Mauricio Ruffy", 0.275)],
            mutually_exclusive=False,
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_a_row_shaped_as_something_other_than_a_duel_is_refused(self):
        rows = await _solo_rows(
            "331: Tsarukyan vs Ruffy",
            [_outcome("Arman Tsarukyan", 0.735), _outcome("Mauricio Ruffy", 0.275)],
            market_type="claim",
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]

    async def test_a_prop_ladder_gets_no_field_and_no_pairing(self):
        """MORE THAN TWO, and a PROP of two: neither is ever paired."""
        method = SimpleNamespace(
            id=next(_IDS),
            external_id=f"kalshi:KXUFCMOV-{_TOKEN}TSARUF",
            name="Tsarukyan: Method of Victory",
            source="kalshi",
            status="open",
            commence_time=_CLOSE,
            market_metadata={},
            outcomes=[
                _outcome("Tsarukyan by KO/TKO", 0.335),
                _outcome("Tsarukyan by decision", 0.335),
                _outcome("Ruffy by KO/TKO", 0.335),
            ],
        )
        distance = SimpleNamespace(
            id=next(_IDS),
            external_id=f"kalshi:KXUFCDISTANCE-{_TOKEN}TSARUF",
            name="Will Tsarukyan and Ruffy go the distance?",
            source="kalshi",
            status="open",
            commence_time=_CLOSE,
            market_metadata={},
            outcomes=[_outcome("Yes", 0.735), _outcome("No", 0.275)],
        )
        envelope, _db = await _page(_named_card() + [method, distance])
        props = [c for c in envelope["children"] if c["kind"] == "prop"]
        assert {p["prop_type"] for p in props} == {"method", "distance"}
        for prop in props:
            assert all(DISPLAY_PERCENT_FIELD not in o for o in prop["outcomes"])
        ladder = next(p for p in props if p["prop_type"] == "method")
        assert [o["probability"] for o in ladder["outcomes"]] == [0.335, 0.335, 0.335]

    async def test_a_settled_result_is_served_as_the_result(self):
        """Genuine 1 / 0 stays 100 / 0 — and nobody is crowned from integers."""
        rows_in = [
            _outcome("Arman Tsarukyan", 1.0, (None, None)),
            _outcome("Mauricio Ruffy", 0.0, (None, None)),
        ]
        envelope, _db = await _page(_solo("331: Tsarukyan vs Ruffy", rows_in))
        child = _child(envelope, "331: Tsarukyan vs Ruffy")
        assert [r[DISPLAY_PERCENT_FIELD] for r in child["outcomes"]] == [100, 0]
        assert [r["probability"] for r in child["outcomes"]] == [1.0, 0.0]
        assert all(
            set(r) == {"name", "probability", DISPLAY_PERCENT_FIELD}
            for r in child["outcomes"]
        )
        assert "graded_winner" not in child and child["settled"] is True

    async def test_a_near_certain_live_price_keeps_its_boundary_material(self):
        """The served 100 rides beside 0.995, so a consumer can still say `>99%`."""
        rows = await _solo_rows(
            "331: Alpha vs Beta",
            [_outcome("Ann Alpha", 0.995), _outcome("Bea Beta", 0.005)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [100, 0]
        assert [r["probability"] for r in rows] == [0.995, 0.005]


# ═══════════════════════════════════════════════════════════════════════════
# The other two envelopes
# ═══════════════════════════════════════════════════════════════════════════

_FIGHT_START = _far(1, hour=23)


def _venue_row(name, outcomes):
    """SYNTHETIC Polymarket bout row (the #6777 harness shape)."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=f"0x{next(_IDS):x}",
        name=name,
        source="polymarket",
        status="open",
        commence_time=_far(-6, hour=22),
        market_metadata={
            "venue_game_start": _FIGHT_START.isoformat().replace("+00:00", "Z"),
            "polymarket_event_id": str(next(_IDS)),
        },
        outcomes=list(outcomes),
    )


class TestTheVenueEnvelope:
    async def _page(self, rows):
        token = venue_card_token(UFC_CONFIG, rows[0].name, rows[0].market_metadata)
        assert token, "the harness must produce a real card token"
        return (await _page(rows, token=token))[0]

    async def test_a_priced_venue_bout_stays_on_independent_display(self):
        """Brief 22A: `venue_bout_is_priced` maps participants; it is not the
        venue's draw / no-contest rule, and no Polymarket rule is on record. So
        the pair is served with no claim and prints what it printed before
        #6816 — 74 / 28, the honest independent rounding — until that rule is
        read and recorded in `COMPLEMENTARY_BOUT_CONTRACTS`.
        """
        title = "Power Slap 23: Brandon Wilson vs. Brian Ellis"
        envelope = await self._page(
            [
                _venue_row(
                    title,
                    [_outcome("Brian Ellis", 0.275), _outcome("Brandon Wilson", 0.735)],
                )
            ]
        )
        rows = envelope["children"][0]["outcomes"]
        assert [(r["name"], r["probability"]) for r in rows] == [
            ("Brandon Wilson", 0.735),
            ("Brian Ellis", 0.275),
        ]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]
        assert _printed(rows) == [74, 28]
        assert _printed(envelope["primary"]["competitors"]) == [74, 28]

    async def test_two_props_under_a_venue_title_stay_unpriced_and_unpaired(self):
        title = "Dana White's Contender Series: Norbert Noveny vs. Theo Haig"
        envelope = await self._page(
            [
                _venue_row(
                    title,
                    [
                        _outcome("Haig in Round 3", 0.735),
                        _outcome("Noveny in Round 2", 0.275),
                    ],
                )
            ]
        )
        rows = envelope["children"][0]["outcomes"]
        assert [r["probability"] for r in rows] == [None, None]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]


def _event(home, away, home_prob):
    return SimpleNamespace(
        id=next(_IDS),
        home_team_name=home,
        away_team_name=away,
        commence_time=_far(2, hour=23),
        status="scheduled",
        _home_prob=home_prob,
    )


class TestTheScheduleEnvelope:
    async def test_a_built_complement_no_longer_rounds_both_sides_up(self, monkeypatch):
        """`round(1 - p, 4)` sums to one and STILL printed 74 / 27."""
        monkeypatch.setattr(
            aggregation,
            "compute_aggregate_probability",
            lambda ev, _status: ev._home_prob,
        )
        ev = _event("Arman Tsarukyan", "Mauricio Ruffy", 0.735)
        token = event_combat.event_commence_token(ev.commence_time)
        envelope, _db = await _page(events=[ev], token=token)
        rows = envelope["children"][0]["outcomes"]
        assert [r["probability"] for r in rows] == [0.735, 0.265]
        assert [rendered_percent(r["probability"]) for r in rows] == [
            74,
            27,
        ]  # what it printed
        assert _printed(rows) == [74, 26]
        assert _printed(envelope["primary"]["competitors"]) == [74, 26]

    async def test_an_unpriced_schedule_bout_serves_no_percent(self, monkeypatch):
        monkeypatch.setattr(
            aggregation, "compute_aggregate_probability", lambda ev, _status: None
        )
        ev = _event("Arman Tsarukyan", "Mauricio Ruffy", None)
        token = event_combat.event_commence_token(ev.commence_time)
        envelope, _db = await _page(events=[ev], token=token)
        rows = envelope["children"][0]["outcomes"]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]


# ═══════════════════════════════════════════════════════════════════════════
# What did NOT change
# ═══════════════════════════════════════════════════════════════════════════


class TestNothingElseMoved:
    def test_printable_probabilities_is_still_not_a_normaliser(self):
        """The shared helper owns price support and nothing else."""
        assert printable_probabilities([(0.735, 0.73, 0.74), (0.275, 0.27, 0.28)]) == [
            0.735,
            0.275,
        ]
        assert printable_probabilities([(0.335, None, None)] * 3) == [0.335] * 3

    async def test_identity_order_keys_and_sections_are_untouched(self):
        envelope, _db = await _page(_named_card())
        fights = [c for c in envelope["children"] if c["kind"] == "fight"]
        assert envelope["sections"][0]["market_ids"] == [c["market_id"] for c in fights]
        assert fights[-1]["market_name"] == "331: Van vs Pantoja"  # main event last
        assert envelope["primary"]["evolution_market_id"] == fights[-1]["market_id"]
        for child in fights:
            assert set(child) == {
                "market_id",
                "market_name",
                "source",
                "kind",
                "settled",
                "probability",
                "outcomes",
            }
            # The lead number is still the favourite's QUOTE, not a display integer.
            assert child["probability"] == child["outcomes"][0]["probability"]
        assert envelope["event"]["key"] == "event:ufc:26sep19"

    async def test_the_builder_reads_nothing_it_did_not_read_before(self):
        """No added scan, no per-bout call: one markets read, one schedule read."""
        _envelope, db = await _page(_named_card())
        assert len(db.statements) == 2
        assert sum("futures_markets" in s for s in db.statements) == 1

    def test_the_input_rows_are_not_mutated(self):
        outs = [
            {"name": "A", "probability": 0.735},
            {"name": "B", "probability": 0.275},
        ]
        served = with_bout_display_percents(outs, one_question=True)
        assert outs == [
            {"name": "A", "probability": 0.735},
            {"name": "B", "probability": 0.275},
        ]
        assert [o[DISPLAY_PERCENT_FIELD] for o in served] == [73, 27]


class TestTheSemanticGate:
    """`ticker_bout_is_one_question` — every term, one refusal each."""

    def _row(self, **over):
        base = {
            "external_id": "kalshi:KXUFCFIGHT-26SEP19TSARUF",
            "source": "kalshi",
            "name": "331: Tsarukyan vs Ruffy",
            "outcomes": [
                SimpleNamespace(name="Arman Tsarukyan"),
                SimpleNamespace(name="Mauricio Ruffy"),
            ],
        }
        base.update(over)
        return SimpleNamespace(**base)

    def test_the_specimen_is_admitted(self):
        assert ticker_bout_is_one_question(UFC_CONFIG, self._row()) is True

    def test_a_bare_title_and_a_rematch_ordinal_are_admitted(self):
        row = self._row(
            name="McGregor vs Holloway 2",
            outcomes=[
                SimpleNamespace(name="Conor McGregor"),
                SimpleNamespace(name="Max Holloway"),
            ],
        )
        assert ticker_bout_is_one_question(UFC_CONFIG, row) is True

    @pytest.mark.parametrize(
        "over",
        [
            {"external_id": "kalshi:KXUFCMOV-26SEP19TSARUF"},  # a prop series
            {"external_id": None},
            {"outcomes": [SimpleNamespace(name="Arman Tsarukyan")]},
            {
                "outcomes": [
                    SimpleNamespace(name=n)
                    for n in ("Arman Tsarukyan", "Mauricio Ruffy", "Draw")
                ]
            },
            {"mutually_exclusive": False},
            {"market_type": "field"},
            {"name": "UFC 331"},  # no matchup to map onto
            {"name": "331: Tsarukyan vs Oliveira"},  # a side no row names
            {"source": "polymarket"},  # the rule on record is Kalshi's
            {"source": None},
        ],
    )
    def test_each_term_refuses_on_its_own(self, over):
        assert ticker_bout_is_one_question(UFC_CONFIG, self._row(**over)) is False

    def test_the_bare_event_ticker_the_ingest_writes_is_admitted(self):
        """`kalshi.py` stores `external_id=event.event_ticker` — no prefix."""
        row = self._row(external_id="KXUFCFIGHT-26SEP19TSARUF")
        assert ticker_bout_is_one_question(UFC_CONFIG, row) is True

    def test_a_flag_that_is_true_or_absent_is_not_evidence_for(self):
        """`mutually_exclusive` is default-true at ingest; only an affirmative
        False refuses. The admission above comes from the contract, not the flag
        — shown by the boxing arm, where the same flag admits nothing."""
        assert ticker_bout_is_one_question(
            UFC_CONFIG, self._row(mutually_exclusive=True)
        )
        assert ticker_bout_is_one_question(UFC_CONFIG, self._row())  # absent

    def test_a_shared_surname_is_ambiguous_and_refused(self):
        assert not bout_sides_are_its_titled_fighters(
            "331: Nurmagomedov vs Silva", ["Usman Nurmagomedov", "Umar Nurmagomedov"]
        )

    def test_diacritics_and_apostrophes_fold(self):
        assert bout_sides_are_its_titled_fighters(
            "331: O'Neill vs Novenyi", ["Casey O'Neill", "Norbert Növényi"]
        )


# ═══════════════════════════════════════════════════════════════════════════
# The cross-runtime fixture is THIS builder's output, not a hand-typed payload
# ═══════════════════════════════════════════════════════════════════════════

_REPO = Path(__file__).resolve().parents[2]
_SAVED = (
    _REPO / "frontend/__tests__/fixtures/eventConceptUfc26sep19.native209.20260917.json"
)
_SERVED_WEB = (
    _REPO
    / "frontend/__tests__/fixtures/eventConceptUfc26sep19.served6816.SYNTHETIC.json"
)
_SERVED_IOS = (
    _REPO
    / "ios/Bain Luck/BainLuckTests/Fixtures/event-ufc-26sep19.served6816.SYNTHETIC.json"
)


def _rows_from_saved_response(saved):
    """SYNTHETIC rows carrying the saved response's names, ids and quotes.

    The response is what production SERVED; it holds no ticker, book or market
    type. Those are invented here (a fight-series ticker, a tight book) so the
    real builder can be driven — this is not a reconstruction of stored rows.
    """
    rows = []
    for index, child in enumerate(saved["children"]):
        outcomes = [_outcome(o["name"], o["probability"]) for o in child["outcomes"]]
        if child["kind"] == "fight":
            row = _ticker_fight(
                f"F{index:02d}",
                child["market_name"],
                outcomes,
                close=_CLOSE + timedelta(minutes=index),
            )
        else:
            row = SimpleNamespace(
                external_id=f"0xsynthetic{index}",
                name=child["market_name"],
                source=child["source"],
                status="open",
                commence_time=_CLOSE,
                market_metadata={},
                outcomes=outcomes,
            )
        row.id = child["market_id"]
        rows.append(row)
    return rows


class TestTheSharedFixtureIsTheBuildersOwnOutput:
    """Web and native tests read ONE served payload; this pins it to the builder.

    Without this the consumer tests would prove they can print integers somebody
    typed. With it, a change to the builder's decision fails HERE, naming the
    fixture, until it is regenerated:

        REGENERATE_6816_FIXTURE=1 python3 -m pytest tests/test_combat_pair_display_6816.py -k fixture
    """

    async def _built(self):
        saved = json.loads(_SAVED.read_text())
        envelope, _db = await _page(_rows_from_saved_response(saved))
        # Clock-dependent fields are taken from the saved response, so the
        # fixture is byte-stable across runs. Nothing a consumer prints is here.
        envelope["event"]["start_date"] = saved["event"]["start_date"]
        envelope["event"]["status"] = saved["event"]["status"]
        envelope["primary"]["price_observed_at"] = saved["primary"]["price_observed_at"]
        return saved, envelope

    async def test_the_fixture_is_byte_for_byte_what_the_builder_serves(self):
        _saved, envelope = await self._built()
        text = json.dumps(envelope, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
        if os.environ.get("REGENERATE_6816_FIXTURE") == "1":
            _SERVED_WEB.write_text(text)
            _SERVED_IOS.write_text(text)
        assert _SERVED_WEB.read_text() == text
        assert _SERVED_IOS.read_text() == text

    async def test_the_builder_reproduces_the_saved_response_apart_from_the_new_field(
        self,
    ):
        """Same ids, same order, same names, same quotes — plus one field."""
        saved, envelope = await self._built()
        for was, now in zip(saved["children"], envelope["children"], strict=True):
            stripped = [
                {k: v for k, v in o.items() if k != DISPLAY_PERCENT_FIELD}
                for o in now["outcomes"]
            ]
            assert stripped == was["outcomes"]
            assert {k: v for k, v in now.items() if k != "outcomes"} == {
                k: v for k, v in was.items() if k != "outcomes"
            }
        assert envelope["sections"] == saved["sections"]
        assert envelope["event"] == saved["event"]

    async def test_all_twelve_bouts_print_one_hundred(self):
        _saved, envelope = await self._built()
        fights = [c for c in envelope["children"] if c["kind"] == "fight"]
        assert len(fights) == 12
        before = [
            sum(rendered_percent(o["probability"]) for o in c["outcomes"])
            for c in fights
        ]
        after = [sum(_printed(c["outcomes"])) for c in fights]
        # What the contract rounding printed off the saved quotes: NONE was 100.
        assert sorted(before) == [100] * 1 + [101] * 8 + [102] * 3
        assert after == [100] * 12


# ═══════════════════════════════════════════════════════════════════════════
# Brief 22A — the settlement contract is the proof, through the real builders
# ═══════════════════════════════════════════════════════════════════════════
#
# The new names (`bout_settlement_contract`, `COMPLEMENTARY_BOUT_CONTRACTS`,
# `BoutSettlementContract`, `ticker_series`) are imported INSIDE the tests that
# need them, so this file still loads against the Brief 22 candidate and the
# builder-level controls below run there — red, behaviourally, on the old guard.


def _boxing_fight(code, title, outcomes, **extra):
    """SYNTHETIC Kalshi BOXING fight row — a family with NO rule on record."""
    fields = dict(
        id=next(_IDS),
        external_id=f"KXBOXING-{_TOKEN}{code}",  # the bare ticker the ingest writes
        name=title,
        source="kalshi",
        status="open",
        commence_time=_CLOSE,
        market_metadata={},
        outcomes=list(outcomes),
    )
    fields.update(extra)
    return SimpleNamespace(**fields)


async def _boxing_rows(title, outcomes, **extra):
    from app.utils.event_boxing import BoxingEventAdapter

    db = _FakeDB(markets=[_boxing_fight("SOLO", title, outcomes, **extra)])
    envelope = await BoxingEventAdapter().build_event(_TOKEN.lower(), db)
    return _child(envelope, title)["outcomes"]


class TestTheSettlementContractIsTheProof:
    """Same quotes, two families: the one with a venue rule on record pairs; the
    one without prints independently. Names here are invented; nothing about a
    real boxing card is asserted."""

    async def test_a_ufc_bout_that_can_draw_still_prints_one_decision(self):
        """0.70 / 0.29 leaves a point unquoted. Under `UFC-RULES4` a draw or no
        contest pays EACH side 0.50, so the two contracts sum to the whole in
        every result and that point is vig or staleness, not a third result —
        the band removes it symmetrically, as it does on every complement pair.
        """
        rows = await _solo_rows(
            "331: Alpha vs Beta",
            [_outcome("Ann Alpha", 0.70), _outcome("Bea Beta", 0.29)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [71, 29]
        assert _printed(rows) == [71, 29]
        assert [r["probability"] for r in rows] == [0.70, 0.29]

    async def test_the_same_quotes_with_no_rule_on_record_print_independently(self):
        """THE SEMANTIC CONTROL. A boxing draw is live and Kalshi's `KXBOXING`
        rule has not been read. The missing point here MAY be a draw priced
        under one point — inside the band — and normalising would round it onto
        the favourite. The old guard served 71 / 29 for this row (a point
        invented from an unread rule); the revision makes no claim and the
        row prints the honest independent 70 / 29.
        """
        rows = await _boxing_rows(
            "Alpha vs Beta", [_outcome("Ann Alpha", 0.70), _outcome("Bea Beta", 0.29)]
        )
        assert [r["probability"] for r in rows] == [0.70, 0.29]
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]
        assert _printed(rows) == [70, 29]

    async def test_an_unproved_pair_inside_the_band_is_not_paired(self):
        """The named specimen's quotes on the unproved family: shape says
        fighters, arithmetic says 1.010, and neither is the rule. Old guard:
        73 / 27. Revision: 74 / 28 — exactly what it printed before #6816."""
        rows = await _boxing_rows(
            "Alpha vs Beta",
            [_outcome("Ann Alpha", 0.735), _outcome("Bea Beta", 0.275)],
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]
        assert _printed(rows) == [74, 28]

    async def test_missing_provenance_is_not_proof(self):
        """Everything a row can carry that LOOKS like proof — the default-true
        flag set explicitly, an assigned `duel` shape, the classifier's own
        `exhaustive: true` (which is that flag read back) — and still no rule on
        record: refused. Only the venue's published rule admits a family."""
        rows = await _boxing_rows(
            "Alpha vs Beta",
            [_outcome("Ann Alpha", 0.735), _outcome("Bea Beta", 0.275)],
            mutually_exclusive=True,
            market_type="duel",
            market_metadata={
                "shape": {
                    "outcome_relation": "competitors",
                    "exhaustive": True,
                    "expected_winners": 1,
                }
            },
        )
        assert [r[DISPLAY_PERCENT_FIELD] for r in rows] == [None, None]
        assert _printed(rows) == [74, 28]

    def test_the_boxing_gate_refuses_on_the_contract_term_alone(self):
        """Through the gate directly: every OTHER term satisfied, one refusal."""
        from app.utils.event_boxing import BOXING_CONFIG
        from app.utils.event_combat import bout_settlement_contract

        row = _boxing_fight(
            "SOLO",
            "Alpha vs Beta",
            [SimpleNamespace(name="Ann Alpha"), SimpleNamespace(name="Bea Beta")],
            mutually_exclusive=True,
            market_type="duel",
        )
        assert event_combat.card_token(BOXING_CONFIG, row.external_id) == "26sep19"
        assert bout_sides_are_its_titled_fighters(row.name, ["Ann Alpha", "Bea Beta"])
        assert bout_settlement_contract(row) is None
        assert ticker_bout_is_one_question(BOXING_CONFIG, row) is False

    def test_the_rule_on_record_quotes_the_venue(self):
        """The registry entry is the venue's words, with where and when they
        were read — never an inference from a row."""
        from app.utils.event_combat import COMPLEMENTARY_BOUT_CONTRACTS

        contract = COMPLEMENTARY_BOUT_CONTRACTS[("kalshi", "KXUFCFIGHT")]
        assert contract.rule_id == "UFC-RULES4"
        assert contract.pair_sums_to_one is True
        assert all(
            "resolve to 50/50" in sentence and "no contest" in sentence
            for sentence in contract.verbatim
        )
        assert all(
            url.startswith("https://api.elections.kalshi.com/trade-api/v2/")
            for url in contract.endpoints
        )
        # Held pending their rules — on the fallback, not silently authorised.
        assert ("kalshi", "KXBOXING") not in COMPLEMENTARY_BOUT_CONTRACTS
        assert not any(src == "polymarket" for src, _ in COMPLEMENTARY_BOUT_CONTRACTS)

    def test_a_void_or_refund_rule_is_recorded_but_never_pairs(self, monkeypatch):
        """`tournament_match.threshold_labels`'s convention: a pair whose tie is
        a push does not sum to the whole and is not normalised into a split.
        A family whose draw rule is a refund can be put on record and still
        refuses — no third win probability is invented for it."""
        from app.utils.event_combat import (
            COMPLEMENTARY_BOUT_CONTRACTS,
            BoutSettlementContract,
        )

        refund = BoutSettlementContract(
            source="kalshi",
            series="KXUFCFIGHT",
            draw_rule="void: both contracts are refunded on a draw / no contest",
            rule_id="SYNTHETIC",
            read_at="2026-09-17T00:00:00Z",
            endpoints=(),
            verbatim=(),
        )
        assert refund.pair_sums_to_one is False
        monkeypatch.setitem(
            COMPLEMENTARY_BOUT_CONTRACTS, ("kalshi", "KXUFCFIGHT"), refund
        )
        row = _ticker_fight(
            "SOLO",
            "331: Alpha vs Beta",
            [SimpleNamespace(name="Ann Alpha"), SimpleNamespace(name="Bea Beta")],
        )
        assert ticker_bout_is_one_question(UFC_CONFIG, row) is False

    async def test_with_no_rule_on_record_the_named_card_prints_as_before(
        self, monkeypatch
    ):
        """Take the UFC rule off the record and the four named bouts go back to
        74 / 28 — the fix is the contract, not the arithmetic."""
        from app.utils.event_combat import COMPLEMENTARY_BOUT_CONTRACTS

        monkeypatch.delitem(COMPLEMENTARY_BOUT_CONTRACTS, ("kalshi", "KXUFCFIGHT"))
        envelope, _db = await _page(_named_card())
        printed = [_printed(_child(envelope, n[0])["outcomes"]) for n in NAMED]
        assert printed == [n[5] for n in NAMED]  # what a reader SAW

    def test_ticker_series_reads_both_spellings_and_nothing_else(self):
        from app.utils.event_combat import ticker_series

        assert ticker_series("kalshi:KXUFCFIGHT-26SEP19TSARUF") == "KXUFCFIGHT"
        assert ticker_series("KXUFCFIGHT-26SEP19TSARUF") == "KXUFCFIGHT"
        assert ticker_series("KXUFCMOV-26SEP19TSARUF") == "KXUFCMOV"  # a prop series
        assert ticker_series("0x1a2b3c") is None
        assert ticker_series("331: Tsarukyan vs Ruffy") is None
        assert ticker_series(None) is None
