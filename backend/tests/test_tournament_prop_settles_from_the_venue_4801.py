"""#4801 — the loader must SERVE the settlement the slate rule reads.

THE DEFECT, MEASURED ON PRODUCTION 2026-09-10 (`d29c068a`, ~06:50 PT)
---------------------------------------------------------------------
Four of the five curated props on `/tournaments/us-open` printed a live
probability for a question our own database had already answered:

    second-major (Alcaraz)        KXGRANDSLAM-CALC26    resolved 9/9 16:50Z
                                  is_winner=False       page printed  1% live
    second-major (Sinner)         KXGRANDSLAM-JSIN26    resolved 9/8 12:51Z
                                  is_winner=False       page printed  1%
    usa-men-final-berth           KXATPNATSTAGE-26FIN   resolved 9/9 16:51Z
                                  is_winner=True        page printed 99% live
    usa-women-quarterfinal-count  KXWTANATSTAGE-26QF    resolved 9/8 02:51Z
                                  is_winner=True        page printed 99% live

`sabalenka-title-defence` was the fifth and was honestly live at 41.5%.

WHY THIS FILE EXISTS SEPARATELY FROM `test_tournament_slate.py`
----------------------------------------------------------------
The fix has two halves in two modules and either one is inert alone:

* `tournament_slate._ingested_settlement` READS `market_status`,
  `market_settled_at` and `is_winner` off a price row;
* `routes.tournaments._load_prices` is the only thing that WRITES them.

A rule reading a key the loader never serves is a green unit test over a dead
feature, and a near-miss on a key NAME ships exactly that. So the tests below
drive the real loader and feed its real output into the real builder — the two
sides agree by composition here, not by two files each asserting its own half.

THE ORDER OF THE TWO COLUMNS IS THE WHOLE RULE
-----------------------------------------------
`is_winner` is written `False` when a leg is BORN, not when it loses (#4788).
Measured the same morning: `KXWTAGRANDSLAM-26` is `open` and already carries
`is_winner = False` while Sabalenka plays a semi-final. `status` is read first,
and `TestTheOpenMarketTrap` is the test that costs the most if it goes.

...AND THE GRADE IS A THIRD COLUMN, NOT THE SECOND ONE (CERT-2526)
-------------------------------------------------------------------
`status` says the MARKET closed; it cannot say whether anyone graded the ROW.
`futures_outcomes.is_winner` is `boolean NULL DEFAULT false`, so "ungraded" and
"graded a loser" are the same stored value and only `resolution_source` tells
them apart. `TestTheUngradedDefault` is that guard.

WHERE THE REAL-POSTGRES HALF OF THAT CLAIM LIVES
--------------------------------------------------
It is already a committed, CI-run gate and is deliberately not duplicated here:
`tests/integration/test_futures_outcome_grade_schema_parity_pg.py` proves on a
real database that a raw INSERT omitting `is_winner` stores `False`
(`test_a_raw_insert_that_omits_is_winner_stores_false`), and it is registered
both in `test_pg_gate_seed_completeness.py`'s `COVERED` tuple and as its own CI
step, so it cannot silently not run. Its own header carries the production
census this file's fakes are built to match: **778,306** outcomes with
`is_winner NOT NULL` and `resolution_source NULL` (2026-08-31). Re-measured for
this repair on 2026-09-10 over markets `settled_at` within 21 days, **1,752**
are `resolved` as well as ungraded — the rows that would have rendered a
fabricated verdict.

So the chain is: that gate pins the column's real shape -> `_Row` below encodes
that shape as its DEFAULT -> the tests here prove what the page does with it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import tournaments
from app.utils.tournament_slate import build_props

NOW = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)
SETTLED_AT = datetime(2026, 9, 9, 16, 51, 9, 516502, tzinfo=timezone.utc)
# The measured disagreement (gotcha #14): a close time five weeks off the real
# settlement. Present on every row below so any test that started serving it
# would be visibly wrong rather than plausibly wrong.
RESOLUTION_DATE = datetime(2026, 8, 31, 15, 7, 35, tzinfo=timezone.utc)
# What a real graded row carries. Both of production's US Open values are real
# strings (`api_settlement`, `all_losers`); the rule is presence, not value.
SOURCED = "api_settlement"


class _Row:
    """One joined `futures_outcomes` × `futures_markets` row, as the loader
    reads it. Attribute names are the ORM's, so a column renamed upstream
    breaks this fake rather than silently serving `None`."""

    # ⚠ THE DEFAULTS BELOW ARE PRODUCTION'S OWN SERVER DEFAULTS, NOT
    # CONVENIENCE (CERT-2526). `futures_outcomes.is_winner` is
    # `boolean NULL DEFAULT false` and `resolution_source` is nullable with no
    # default, so a row nobody has graded arrives here as `False` + `None` —
    # NOT as `None`. This fake used to default `is_winner=None`, which is a
    # shape production never produces, and that single wrong default is what
    # let a rule that reads `is_winner` alone pass every test in this file
    # while rendering a fabricated `No` on 1,752 live rows.
    def __init__(self, *, id, probability=0.99, status="open",
                 settled_at=None, is_winner=False, resolution_source=None):
        self.id = id
        self.name = f"outcome-{id}"
        self.current_probability = probability
        self.opening_probability = 0.2
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.volume_24h = None
        self.volume_updated_at = None
        self.last_updated = NOW - timedelta(minutes=5)
        self.status = status
        self.settled_at = settled_at
        self.is_winner = is_winner
        self.resolution_source = resolution_source
        self.resolution_date = RESOLUTION_DATE


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rows)


@pytest.fixture(autouse=True)
def _no_history(monkeypatch):
    """The observation-history probe is a second query and not this subject."""

    async def fake_loader(session, outcome_ids):
        return {}

    monkeypatch.setattr(tournaments, "load_latest_observed_at", fake_loader)


def _register(props):
    return {
        "schema_version": 2,
        "tournament": "us-open",
        "season": "2026",
        "version": 2,
        "sides": {},
        "props": props,
    }


def _yes_no_prop():
    """`usa-men-final-berth` — one market, one answering row."""
    return {
        "key": "usa-men-final-berth",
        "title": "Will an American reach the men's final?",
        "hook": "The market asks about the American men as a group.",
        "draw": "mens-singles",
        "source": "kalshi",
        "markets": [{"market_id": 59694147,
                     "market_external_id": "KXATPNATSTAGE-26FIN"}],
        "outcomes": [{
            "entity_key": "usa-men-final-berth:yes",
            "display_name": "Yes",
            "outcome_id": 222299660,
            "is_answer": True,
            "market_id": 59694147,
            "market_external_id": "KXATPNATSTAGE-26FIN",
        }],
    }


def _comparison_prop():
    """`second-major` — two subjects, two markets, no answering row, so the
    verdict is a claim about EVERY leg (`Neither`). The real register entry."""
    return {
        "key": "second-major",
        "title": "A second major in 2026?",
        "hook": "Two men, one question.",
        "draw": "mens-singles",
        "source": "kalshi",
        "markets": [{"market_id": 53796,
                     "market_external_id": "KXGRANDSLAM-CALC26"},
                    {"market_id": 53795,
                     "market_external_id": "KXGRANDSLAM-JSIN26"}],
        "outcomes": [
            {
                "entity_key": "second-major:alcaraz",
                "display_name": "Carlos Alcaraz",
                "outcome_id": 848773,
                "is_answer": False,
                "market_id": 53796,
                "market_external_id": "KXGRANDSLAM-CALC26",
            },
            {
                "entity_key": "second-major:sinner",
                "display_name": "Jannik Sinner",
                "outcome_id": 848769,
                "is_answer": False,
                "market_id": 53795,
                "market_external_id": "KXGRANDSLAM-JSIN26",
            },
        ],
    }


async def _load(rows):
    session = _Session(rows)
    return await tournaments._load_prices(
        session, [r.id for r in rows], now=NOW
    )


class TestTheLoaderServesTheResult:
    """The payload half, by name."""

    async def test_the_four_result_keys_travel_off_a_real_row(self):
        loaded = await _load([_Row(
            id=222299660, status="resolved",
            settled_at=SETTLED_AT, is_winner=True, resolution_source=SOURCED,
        )])
        row = loaded[222299660]
        assert row["market_status"] == "resolved"
        assert row["market_settled_at"] == SETTLED_AT
        assert row["is_winner"] is True
        # The fourth, and the one whose absence made the other three lie.
        assert row["resolution_source"] == SOURCED

    async def test_resolution_date_is_not_among_them(self):
        """It is on the row and it must not be served: it is a close time and
        the measured one is eight days off the real settlement."""
        loaded = await _load([_Row(
            id=222299660, status="resolved",
            settled_at=SETTLED_AT, is_winner=True,
        )])
        assert RESOLUTION_DATE not in loaded[222299660].values()

    async def test_it_is_still_one_statement(self):
        """The columns ride the join the loader already issues for
        `volume_24h`. A second round trip on the hub's hottest query would be a
        real cost for a fact that was already in reach."""
        session = _Session([_Row(id=222299660)])
        await tournaments._load_prices(session, [222299660], now=NOW)
        assert len(session.statements) == 1

    async def test_an_open_row_serves_its_state_rather_than_nothing(self):
        """`None` and `"open"` are different answers and the difference is
        load-bearing downstream — absence is not a settlement (gotcha #53)."""
        loaded = await _load([_Row(id=222299660, status="open")])
        assert loaded[222299660]["market_status"] == "open"
        assert loaded[222299660]["market_settled_at"] is None
        # `False`, not `None` — this is the server default an ungraded row
        # really carries, and serving it faithfully is what lets the reader
        # notice that `resolution_source` is the only honest grade.
        assert loaded[222299660]["is_winner"] is False
        assert loaded[222299660]["resolution_source"] is None


class TestTheLoaderAndTheBuilderMeet:
    """THE COMPOSITION. Real loader output, real builder, no hand-written dict
    in between — which is the only arrangement a key-name near-miss cannot
    survive."""

    async def test_a_resolved_graded_market_reaches_the_card_as_settled(self):
        prices = await _load([_Row(
            id=222299660, probability=0.99, status="resolved",
            settled_at=SETTLED_AT, is_winner=True, resolution_source=SOURCED,
        )])
        card = build_props(_register([_yes_no_prop()]), prices=prices, now=NOW)[0]
        assert card["settled"] is True
        assert card["settled_answer"] == "Yes"
        assert card["settled_at"] == SETTLED_AT.isoformat()

    async def test_a_live_market_reaches_the_card_as_a_question(self):
        """The other direction, through the same rails: the fix must not settle
        the section. `sabalenka-title-defence`'s shape keeps its number."""
        prices = await _load([_Row(id=222299660, probability=0.415, status="open")])
        card = build_props(_register([_yes_no_prop()]), prices=prices, now=NOW)[0]
        assert card["settled"] is False
        assert card["outcomes"][0]["probability"] == pytest.approx(0.415)


class TestTheOpenMarketTrap:
    """🔴 The most expensive test in this file.

    Production, 2026-09-10: `KXWTAGRANDSLAM-26` reads `status='open'` with
    `is_winner=False` on its outcome, because a born leg is written `False`
    rather than left NULL (#4788). Sabalenka was playing a semi-final that
    afternoon. A settlement rule keyed on the grade would have printed her
    match as decided, and decided the wrong way.
    """

    async def test_a_false_grade_on_an_open_market_settles_nothing(self):
        prices = await _load([_Row(
            id=222299660, probability=0.415, status="open",
            settled_at=None, is_winner=False,
        )])
        card = build_props(_register([_yes_no_prop()]), prices=prices, now=NOW)[0]
        assert card["settled"] is False
        assert card["settled_answer"] is None
        # And it is still a card a reader can use, not a blank.
        assert card["outcomes"][0]["probability"] == pytest.approx(0.415)

    async def test_a_true_grade_on_an_open_market_settles_nothing_either(self):
        """Stated in both directions so the guard is about the STATUS GATE and
        not about the value `False` happening to be falsy."""
        prices = await _load([_Row(
            id=222299660, probability=0.99, status="open", is_winner=True,
            resolution_source=SOURCED,
        )])
        card = build_props(_register([_yes_no_prop()]), prices=prices, now=NOW)[0]
        assert card["settled"] is False


class TestTheUngradedDefault:
    """🔴 THE SECOND-MOST EXPENSIVE TEST IN THIS FILE, and the one that was
    missing (CERT-2526).

    `TestTheOpenMarketTrap` above guards the *status* half: a graded-looking
    row on a market still in play. This class guards the *grade* half, which is
    strictly harder, because the two states it separates are the same value.

    `futures_outcomes.is_winner` is `boolean NULL DEFAULT false`. So:

        nobody has graded this row yet   ->  is_winner = False
        the venue graded this row a loss ->  is_winner = False

    and only `resolution_source` tells them apart. Resolved-before-graded is
    not an edge case — measured on production 2026-09-10 across markets
    `settled_at` within 21 days, **1,752** outcomes are `resolved` with
    `is_winner = false` and no `resolution_source`. Reading the grade alone
    prints a definitive `No`/`Neither` on all of them that no source wrote,
    which is the exact fabrication this ship exists to delete.
    """

    async def test_resolved_server_default_false_without_resolution_source_is_withheld(
        self,
    ):
        """The BLOCK's own repro, through the real loader into the real
        builder: resolved market, `is_winner` never written, so it reads
        `False`, and nothing graded it."""
        prices = await _load([_Row(
            id=222299660, probability=0.99, status="resolved",
            settled_at=SETTLED_AT, is_winner=False, resolution_source=None,
        )])
        cards = build_props(_register([_yes_no_prop()]), prices=prices, now=NOW)
        # WITHHELD, not answered `No`. A question we can prove is closed but
        # whose answer we do not hold must not be printed either way.
        assert cards == []

    async def test_the_same_row_with_a_source_answers_no(self):
        """The discriminator. Identical row, one column added — so this pair
        proves the rule keys on `resolution_source` and not on `is_winner`
        being falsy, and proves the withhold above is not simply the fallback
        going dead."""
        prices = await _load([_Row(
            id=222299660, probability=0.99, status="resolved",
            settled_at=SETTLED_AT, is_winner=False, resolution_source="all_losers",
        )])
        card = build_props(_register([_yes_no_prop()]), prices=prices, now=NOW)[0]
        assert card["settled"] is True
        assert card["settled_answer"] == "No"

    async def test_one_unsourced_leg_withholds_the_whole_comparison_card(self):
        """`Neither` asserts about EVERY leg, so a single ungraded leg makes it
        unsayable — even though the other leg is properly graded a loss."""
        prices = await _load([
            _Row(id=848773, status="resolved", settled_at=SETTLED_AT,
                 is_winner=False, resolution_source="all_losers"),
            _Row(id=848769, status="resolved", settled_at=SETTLED_AT,
                 is_winner=False, resolution_source=None),
        ])
        assert build_props(
            _register([_comparison_prop()]), prices=prices, now=NOW
        ) == []

    async def test_both_legs_sourced_still_says_neither(self):
        """The control for the test above: the ship's real `second-major`
        behaviour must survive the repair."""
        prices = await _load([
            _Row(id=848773, status="resolved", settled_at=SETTLED_AT,
                 is_winner=False, resolution_source="all_losers"),
            _Row(id=848769, status="resolved", settled_at=SETTLED_AT,
                 is_winner=False, resolution_source=SOURCED),
        ])
        card = build_props(
            _register([_comparison_prop()]), prices=prices, now=NOW
        )[0]
        assert card["settled"] is True
        assert card["settled_answer"] == "Neither"

    async def test_an_empty_string_source_is_not_a_grade(self):
        """`resolution_source` is a nullable varchar, so blank is reachable and
        is an absence wearing a value (gotcha #53)."""
        prices = await _load([_Row(
            id=222299660, probability=0.99, status="resolved",
            settled_at=SETTLED_AT, is_winner=False, resolution_source="   ",
        )])
        assert build_props(_register([_yes_no_prop()]), prices=prices, now=NOW) == []
