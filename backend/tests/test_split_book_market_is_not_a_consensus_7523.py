"""A split book market publishes nothing, not the midpoint of the split (#7523).

SPECIMEN, production 2026-09-20 14:46Z. Event 15305946, Brest @ Auxerre, LIVE at
85' with Auxerre leading 2-1, served as the TOP CARD of Discover (`score 98`):

    win_probability_sources  betting 0.5005, betting_book_count 6
                             kalshi  0.84   (verified live speaker)
    hero_probability         0.5005  source "blend"
    rendered                 "Auxerre 50%"

Auxerre's second goal landed ~14:40Z and the books repriced one at a time, so at
the 14:41:30 poll three had moved and three had not:

    [0.164, 0.176, 0.200, 0.801, 0.801, 0.934]

`statistics.median` of an even-sized list interpolates its two middle readings:
(0.200 + 0.801) / 2 = 0.5005. Six books, none of them quoting 50%, and the
published "sportsbook consensus" was the empty middle of the split — which then
fired `signal:very_close` and ranked the card into slot 1.

The tests below are behavioural: they drive the real `_ingest_event_odds` and
read the Core update it executes. The harness is the one #5426 built, for the
same reason it was built there — the write is the subject, so a test that calls
a helper and asserts on its return value would not have caught this.
"""

import pytest

from app.tasks.odds_polling import BETTING_BOOK_FLOOR, _ingest_event_odds
from app.utils.book_consensus import (
    CONSENSUS_SPLIT_GAP,
    median_invents_its_answer,
)
from tests.test_discovery_advances_betting_consensus_5426 import (
    FUTURE,
    _FakeEvent,
    _RecordingSession,
)
from tests.test_discovery_advances_betting_consensus_5426 import (
    patched_snapshots as _patched_snapshots,
)

# Re-exported under its own name so pytest can resolve the fixture by argument.
# Bound rather than star-imported: a direct `import patched_snapshots` is read
# as a redefinition by every test that takes it as a parameter (F811).
patched_snapshots = _patched_snapshots

#: The six de-vigged readings the specimen's books were quoting at 14:41:30.
AUXERRE_SPLIT = [0.801, 0.164, 0.934, 0.176, 0.801, 0.200]


class TestTheRuleItself:
    def test_the_specimen_is_named_as_a_split(self):
        assert median_invents_its_answer(AUXERRE_SPLIT) == (0.200, 0.801)

    def test_books_that_agree_are_not_a_split_even_at_an_even_count(self):
        """The ordinary case, which must stay byte-identical to today.

        Production's measured middle-two gap is p90 0.0153, so this is what the
        rule sees on essentially every event it runs on.
        """
        assert median_invents_its_answer([0.571, 0.578, 0.581, 0.590]) is None

    def test_an_odd_count_is_never_an_invention(self):
        """The median IS one of the readings, so nothing is manufactured.

        A 2/1 split still returns a quoted price. That price can be the stale
        cluster's, which is a real but DIFFERENT defect — this rule must not
        quietly claim it, or a later specimen of it will read as already fixed.
        """
        assert median_invents_its_answer([0.17, 0.18, 0.84]) is None

    def test_the_threshold_is_a_boundary_not_a_direction(self):
        """Exactly at the gap is still a summary; a hair over it is not.

        Pinning both sides is what stops the constant being silently widened to
        the point where the rule stops firing on its own specimen.
        """
        assert median_invents_its_answer([0.0, 0.40, 0.40 + CONSENSUS_SPLIT_GAP, 1.0]) is None
        assert (
            median_invents_its_answer(
                [0.0, 0.40, 0.40 + CONSENSUS_SPLIT_GAP + 1e-6, 1.0]
            )
            is not None
        )

    def test_a_pair_is_the_smallest_set_that_can_split(self):
        assert median_invents_its_answer([0.20, 0.80]) == (0.20, 0.80)
        assert median_invents_its_answer([0.80]) is None
        assert median_invents_its_answer([]) is None

    def test_the_threshold_clears_ordinary_book_noise(self):
        """p90 of the measured middle-two gap is 0.0153 (see the issue).

        A threshold anywhere near that would drop the betting leg on healthy
        markets, which is the regression this number exists to avoid.
        """
        assert CONSENSUS_SPLIT_GAP >= 0.05


class TestTheWriteTheReaderSees:
    @pytest.mark.asyncio
    async def test_the_specimen_publishes_no_consensus(self, patched_snapshots):
        """The whole ship: 0.5005 is never written, and the key is REMOVED.

        Removal, not a skipped write — `betting` is already in the JSONB from
        the poll before the goal, and leaving it would serve the pre-goal price
        as if it were current. That is ruling 051's own argument.
        """
        event_data = patched_snapshots(AUXERRE_SPLIT)
        event = _FakeEvent(
            {
                "betting": {"value": 0.1760, "updated_at": "2026-09-20T14:40:01Z"},
                "kalshi": {"value": 0.84, "updated_at": "2026-09-20T14:41:57Z"},
            },
            status="live",
        )
        session = _RecordingSession(status="live")

        await _ingest_event_odds(session, event, event_data, FUTURE, {})

        assert len(session.sources_writes) == 1
        written = session.sources_writes[0]
        assert "betting" not in written, (
            "the midpoint of a split market must not be published — "
            f"got {written.get('betting')!r}"
        )
        # The drop stays visible, and the other sources are untouched: the blend
        # re-weights over Kalshi's 0.84 and the card prints 84%, not 50%.
        assert written["betting_book_count"] == 6
        assert written["kalshi"]["value"] == 0.84

    def test_and_the_reader_then_sees_kalshis_verified_84(self):
        """The ship's claim, asserted instead of described.

        Dropping a source is only the right repair if what is left is better
        than what went. Both bags below are the ones production actually served
        at 14:46Z — the defect bag verbatim, and the same bag with `betting`
        removed the way the writer above removes it — so this is a replay of the
        row, not a call with invented inputs (notice 37).
        """
        from app.utils.aggregation import compute_aggregate_probability

        class _Row:
            status = "live"
            home_score, away_score = 2, 1
            completed_at = None
            espn_win_prob_home = None
            opening_home_probability, opening_away_probability = 0.3178, 0.4078
            win_probability_sources: dict = {}

        served = _Row()
        served.win_probability_sources = {
            "kalshi": {"value": 0.84, "updated_at": "2026-09-20T14:41:57+00:00"},
            "betting": {"value": 0.5005, "updated_at": "2026-09-20T14:41:30+00:00"},
            "betting_book_count": 6,
        }
        assert compute_aggregate_probability(served) == pytest.approx(0.5005), (
            "the defect, reproduced: the served blend WAS the invented midpoint"
        )

        repaired = _Row()
        repaired.win_probability_sources = {
            "kalshi": {"value": 0.84, "updated_at": "2026-09-20T14:41:57+00:00"},
            "betting_book_count": 6,
        }
        assert compute_aggregate_probability(repaired) == pytest.approx(0.84)

    @pytest.mark.asyncio
    async def test_agreeing_books_still_publish_their_median(
        self, patched_snapshots
    ):
        """The no-change half. An even count is not by itself a refusal."""
        event_data = patched_snapshots([0.571, 0.578, 0.581, 0.590])
        event = _FakeEvent({}, status="live")
        session = _RecordingSession(status="live")

        await _ingest_event_odds(session, event, event_data, FUTURE, {})

        written = session.sources_writes[0]
        assert written["betting"]["value"] == pytest.approx(0.5795)
        assert written["betting_book_count"] == 4

    @pytest.mark.asyncio
    async def test_an_odd_split_still_publishes_a_quoted_price(
        self, patched_snapshots
    ):
        """Scope, asserted rather than described.

        Three books mid-move publish 0.18 — a price a book actually quoted.
        This fix does not reach that case, and the test says so out loud so the
        next reader does not mistake the silence for coverage.
        """
        event_data = patched_snapshots([0.17, 0.18, 0.84])
        event = _FakeEvent({}, status="live")
        session = _RecordingSession(status="live")

        await _ingest_event_odds(session, event, event_data, FUTURE, {})

        assert session.sources_writes[0]["betting"]["value"] == pytest.approx(0.18)

    @pytest.mark.asyncio
    async def test_a_partial_caller_under_the_floor_still_leaves_it_alone(
        self, patched_snapshots
    ):
        """#5426 outranks this rule, and the order of the branches says so.

        A narrow fetch that reads two disagreeing books has not measured the
        market; deleting a full poll's good consensus on that evidence is the
        exact regression #5426 exists to prevent.
        """
        event_data = patched_snapshots([0.20, 0.80])
        event = _FakeEvent(
            {"betting": {"value": 0.62, "updated_at": "2026-09-20T14:00:00Z"}},
            status="live",
        )
        session = _RecordingSession(status="live")

        await _ingest_event_odds(
            session, event, event_data, FUTURE, {},
            update_opening=False, drop_below_floor=False,
        )

        assert session.sources_writes == [], (
            "a partial-coverage caller under the book floor writes nothing at "
            "all (#5426) — not even the split drop"
        )

    @pytest.mark.asyncio
    async def test_a_split_below_the_floor_is_still_dropped(
        self, patched_snapshots
    ):
        """Both refusals end in the same absence, so neither can mask the other."""
        assert BETTING_BOOK_FLOOR == 3
        event_data = patched_snapshots([0.20, 0.80])
        event = _FakeEvent(
            {"betting": {"value": 0.62, "updated_at": "2026-09-20T14:00:00Z"}},
            status="live",
        )
        session = _RecordingSession(status="live")

        await _ingest_event_odds(session, event, event_data, FUTURE, {})

        assert "betting" not in session.sources_writes[0]
