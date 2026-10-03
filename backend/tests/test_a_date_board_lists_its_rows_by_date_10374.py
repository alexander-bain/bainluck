"""#10374 — a question whose outcomes are dates lists them by date.

Alex, iPhone rage shake 170 (build 1.0.2, 2026-10-03 18:25Z): "These date
oriented cards should be shown in chronological order because showing them out
of chronological order is confusing, even if that is the true descending order
of the probabilities." The `Next Claude Haiku (4.6+) released on...?` card read

    1  October 27  14%  ·  2  October 12  14%  ·  3  October 28  13%
    4  October 13  12%  ·  5  Field and remaining outcomes  +26

The backend owes the two things a renderer cannot work out on its own: that the
board IS a date question, and which calendar day each row is (the venue writes
`October 27` with no year). It does not re-order the list: which four rows
survive the cut is still the leader-first slice both clients make (#1526), and
a re-ordered list would hand every shipped iPhone build — which draws row 0 as
the leader — a leader bar on whichever drawn date came first.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.personalization import PersonalizationContext

#: Production `/api/futures/63522622`, 2026-10-03 19:50Z, as served: probability
#: order, the residual row inside the first eight.
HAIKU_BOARD = [
    ("October 27", 0.14),
    ("October 12", 0.138),
    ("October 14", 0.13),
    ("October 28", 0.125),
    ("October 13", 0.12),
    ("October 5", 0.102),
    ("October 6", 0.1),
    ("No release by October 31", 0.095),
]
HAIKU_RESOLVES = "2026-11-01T03:59:00+00:00"


def _card(board, resolution_date=HAIKU_RESOLVES, **kwargs):
    return classify_discover_card_archetype(
        name=kwargs.pop("name", "Next Claude Haiku (4.6+) released?"),
        category="tech",
        outcomes=[{"name": n, "probability": p} for n, p in board],
        outcome_count=kwargs.pop("outcome_count", 30),
        resolution_date=resolution_date,
        **kwargs,
    )


class TestTheSpecimen:
    def test_the_haiku_board_is_a_date_question(self):
        card = _card(HAIKU_BOARD)
        assert card["suggested_format"] == "outcome_distribution"
        assert card["distribution_order"] == "chronological"

    def test_each_row_says_its_day(self):
        rows = _card(HAIKU_BOARD)["distribution_outcomes"]
        assert {r["label"]: r["date"] for r in rows} == {
            "October 27": "2026-10-27",
            "October 12": "2026-10-12",
            "October 14": "2026-10-14",
            "October 28": "2026-10-28",
            "October 13": "2026-10-13",
            "October 5": "2026-10-05",
            "October 6": "2026-10-06",
            "No release by October 31": None,
        }

    def test_the_list_itself_is_not_reordered(self):
        """Same rows, same order, same numbers — the field is additive."""
        rows = _card(HAIKU_BOARD)["distribution_outcomes"]
        assert [(r["label"], r["probability"]) for r in rows] == HAIKU_BOARD

    def test_the_drawn_four_read_earliest_first(self):
        """What the renderer is being asked to do, done here once on the wire.

        Leader-first cut of four, then by date: October 12 · 14 · 27 · 28 (by
        19:50Z October 14 had overtaken the 13th the phone drew). The leader
        (October 27, 14%) is still drawn — third, not first.
        """
        rows = _card(HAIKU_BOARD)["distribution_outcomes"]
        drawn = sorted(rows, key=lambda r: -r["probability"])[:4]
        listed = sorted(drawn, key=lambda r: (r["date"] is None, r["date"] or ""))
        assert [r["label"] for r in listed] == [
            "October 12",
            "October 14",
            "October 27",
            "October 28",
        ]

    def test_the_residual_sorts_after_every_date(self):
        board = [("No release by October 31", 0.5), ("October 12", 0.3), ("October 5", 0.2)]
        rows = _card(board, outcome_count=3)["distribution_outcomes"]
        listed = sorted(rows, key=lambda r: (r["date"] is None, r["date"] or ""))
        assert [r["label"] for r in listed] == [
            "October 5",
            "October 12",
            "No release by October 31",
        ]


class TestTheYearIsPlacedNotGuessed:
    def test_a_board_across_new_year_puts_december_first(self):
        board = [("January 5", 0.4), ("December 28", 0.35), ("January 12", 0.25)]
        card = _card(board, resolution_date="2027-01-15T05:00:00+00:00", outcome_count=3)
        assert card["distribution_order"] == "chronological"
        assert {r["label"]: r["date"] for r in card["distribution_outcomes"]} == {
            "January 5": "2027-01-05",
            "December 28": "2026-12-28",
            "January 12": "2027-01-12",
        }

    def test_the_resolution_day_itself_is_this_year(self):
        board = [("October 31", 0.6), ("October 1", 0.4)]
        card = _card(board, resolution_date="2026-10-31T23:00:00+00:00", outcome_count=2)
        dates = [r["date"] for r in card["distribution_outcomes"]]
        assert dates == ["2026-10-31", "2026-10-01"]

    def test_a_datetime_anchor_reads_the_same_as_its_string(self):
        board = [("January 5", 0.6), ("December 28", 0.4)]
        anchor = datetime(2027, 1, 15, 5, tzinfo=timezone.utc)
        assert _card(board, resolution_date=anchor, outcome_count=2) == _card(
            board, resolution_date=anchor.isoformat(), outcome_count=2
        )

    def test_labels_that_carry_their_year_need_no_anchor(self):
        board = [("December 31, 2029", 0.2), ("December 31, 2027", 0.1)]
        card = _card(board, resolution_date=None, outcome_count=2)
        assert card["distribution_order"] == "chronological"
        assert [r["date"] for r in card["distribution_outcomes"]] == [
            "2029-12-31",
            "2027-12-31",
        ]


class TestABoardWhoseLegsCloseAfterItResolves:
    """ux on live `eb2418ee11` (2026-10-03 22:0xZ): a cumulative "by date"
    board can carry legs that close after its stored resolution_date. The first
    rule — the latest year not after the anchor — put those legs a year early.
    Labels and anchors are production `futures_outcomes` / `futures_markets`,
    read 2026-10-03.
    """

    PIPELINE_RESOLVES = "2026-11-01T03:59:00+00:00"  # market 60789497

    def test_the_pipeline_board_is_one_run_september_to_november(self):
        board = [
            ("October 31", 0.3),
            ("November 30", 0.2),
            ("November 15", 0.15),
            ("October 15", 0.15),
            ("September 30", 0.1),
            ("September 15", 0.1),
        ]
        card = _card(board, resolution_date=self.PIPELINE_RESOLVES, outcome_count=6)
        assert card["distribution_order"] == "chronological"
        assert {r["label"]: r["date"] for r in card["distribution_outcomes"]} == {
            "September 15": "2026-09-15",
            "September 30": "2026-09-30",
            "October 15": "2026-10-15",
            "October 31": "2026-10-31",
            "November 15": "2026-11-15",
            "November 30": "2026-11-30",
        }

    def test_the_diesel_board_puts_december_after_october(self):
        board = [("October 31", 0.5), ("December 31", 0.3), ("September 30", 0.2)]
        card = _card(board, resolution_date="2026-11-01T03:59:00+00:00", outcome_count=3)
        assert {r["label"]: r["date"] for r in card["distribution_outcomes"]} == {
            "September 30": "2026-09-30",
            "October 31": "2026-10-31",
            "December 31": "2026-12-31",
        }

    def test_a_run_wholly_after_its_anchor_stays_in_the_anchors_year(self):
        board = [("November 15", 0.6), ("November 30", 0.4)]
        card = _card(board, resolution_date="2026-11-01T03:59:00+00:00", outcome_count=2)
        assert [r["date"] for r in card["distribution_outcomes"]] == [
            "2026-11-15",
            "2026-11-30",
        ]

    def test_february_29_in_the_leap_year_it_lands_on(self):
        board = [("February 29", 0.5), ("March 1", 0.5)]
        card = _card(board, resolution_date="2028-03-15T00:00:00+00:00", outcome_count=2)
        assert [r["date"] for r in card["distribution_outcomes"]] == [
            "2028-02-29",
            "2028-03-01",
        ]

    def test_two_gaps_tied_for_widest_is_refused(self):
        """January 1 and July 2 sit 183 days apart both ways round the ring."""
        board = [("January 1", 0.5), ("July 2", 0.5)]
        card = _card(board, resolution_date="2026-11-01T00:00:00+00:00", outcome_count=2)
        assert card["distribution_order"] == "probability"

    def test_two_years_tied_for_nearest_is_refused(self):
        """Jan 2 2026 and Jan 1 2027 are each 182 days from July 3 2026."""
        board = [("January 1", 0.5), ("January 2", 0.5)]
        card = _card(board, resolution_date="2026-07-03T00:00:00+00:00", outcome_count=2)
        assert card["distribution_order"] == "probability"


class TestEveryRefusalKeepsTodaysBoard:
    """`probability` and no `date` key: the rendering that already ships."""

    @staticmethod
    def _assert_refused(card):
        assert card["distribution_order"] == "probability"
        assert all("date" not in r for r in card["distribution_outcomes"])

    def test_a_board_of_names(self):
        board = [("Google", 0.65), ("Anthropic", 0.36), ("OpenAI", 0.01), ("Meta", 0.002)]
        self._assert_refused(_card(board, name="Best AI model end of October?"))

    def test_one_row_that_is_neither_a_date_nor_the_residual(self):
        self._assert_refused(_card(HAIKU_BOARD[:7] + [("Before October 31", 0.09)]))

    def test_two_residuals(self):
        board = HAIKU_BOARD[:6] + [("No release by October 31", 0.1), ("Not this year", 0.09)]
        self._assert_refused(_card(board))

    def test_a_single_date(self):
        board = [("October 12", 0.6), ("No release by October 31", 0.4)]
        self._assert_refused(_card(board, outcome_count=2))

    def test_year_less_with_nothing_to_anchor_it(self):
        self._assert_refused(_card(HAIKU_BOARD, resolution_date=None))

    def test_dated_beside_year_less(self):
        """The `December 31, 2025` beside bare `December 31` shape (#7784)."""
        board = [("December 31", 0.3), ("December 31, 2025", 0.0), ("June 30", 0.2)]
        self._assert_refused(_card(board, outcome_count=3))

    def test_two_rows_on_one_day(self):
        board = [("October 12", 0.5), ("Oct 12", 0.3), ("October 13", 0.2)]
        self._assert_refused(_card(board, outcome_count=3))

    def test_a_day_that_does_not_exist_in_the_anchored_year(self):
        board = [("February 29", 0.5), ("March 1", 0.5)]
        self._assert_refused(
            _card(board, resolution_date="2027-03-15T00:00:00+00:00", outcome_count=2)
        )

    def test_an_unreadable_anchor(self):
        self._assert_refused(_card(HAIKU_BOARD, resolution_date="soon"))


# ─────────────────────────── through the route ────────────────────────────────


class _Outcome:
    def __init__(self, id, name, probability):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = max(probability - 0.01, 0.0)
        self.current_yes_ask = min(probability + 0.01, 1.0)


def _day_label(day: datetime) -> str:
    return f"{day:%B} {day.day}"


class _Market:
    """A date board placed off the clock, so no expiry rule can drop a rung."""

    def __init__(self, id):
        now = datetime.now(timezone.utc)
        self.id = id
        self.name = "Next Claude Haiku (4.6+) released?"
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "tech"
        self.llm_sport_category = "tech"
        self.market_tier = 2
        self.canonical_market_key = None
        self.group_id = f"polymarket:{id}"
        self.group_type = "polymarket_event"
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        self.resolution_date = now + timedelta(days=40)
        self.status = "open"
        self.created_at = now - timedelta(days=3)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.market_type = "field"
        self.mutually_exclusive = True
        # Probability order, the leader LATE: what the specimen looked like.
        offsets_and_prices = [(25, 0.30), (10, 0.25), (26, 0.20), (11, 0.15), (5, 0.10)]
        self.days = {
            _day_label(now + timedelta(days=d)): (now + timedelta(days=d)).date()
            for d, _ in offsets_and_prices
        }
        self.outcomes = [
            _Outcome(1000 + i, _day_label(now + timedelta(days=d)), p)
            for i, (d, p) in enumerate(offsets_and_prices)
        ]


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve(markets):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await _score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


class TestTheRouteServesIt:
    @pytest.mark.asyncio
    async def test_the_served_card_names_the_order_and_each_day(self):
        market = _Market(10374)
        items = await _serve([market])
        futures = [i for i in items if i["type"] == "futures"]
        # The denominator: a card the feed refused would pass everything below
        # having proved nothing.
        assert len(futures) == 1, f"the date board was not served: {items}"
        card = futures[0]["data"]["discover_card"]
        assert card["distribution_order"] == "chronological"
        served = {r["label"]: r["date"] for r in card["distribution_outcomes"]}
        assert served == {label: day.isoformat() for label, day in market.days.items()}


_FEED_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
).read_text()


@pytest.mark.parametrize("scorer", ["_score_futures", "_score_sports_mode_futures"])
def test_every_card_builder_hands_the_classifier_its_anchor(scorer):
    """The keyword's default is silent: an unadopted site refuses every year-less
    date board instead of failing loudly. The arity assertion stops a deleted
    site passing vacuously."""
    for node in ast.walk(ast.parse(_FEED_SOURCE)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == scorer:
            calls = [
                {k.arg for k in call.keywords}
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "classify_discover_card_archetype"
            ]
            break
    else:
        raise AssertionError(f"{scorer} is gone from routes/feed.py")
    assert len(calls) == 1, f"{scorer} builds {len(calls)} cards, expected 1"
    assert "resolution_date" in calls[0], f"{scorer} builds a card with no date anchor"
