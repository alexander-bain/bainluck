"""#5548 — a SETTLED Polymarket container must not block its own retirement.

THE GAP IS BETWEEN TWO DIFFERENT QUESTIONS. `_retire_unbacked_blend_source`
asks "can anything here speak?" (`count_admissible_speakers`); the writer asks
"did anything here speak?" (`compute_source_home_probability`). #5031 closed the
case where both answer no. This file is the case where they DISAGREE — and the
disagreement is permanent, so the stored price freezes on the page forever.

Polymarket collapses a settled container to its winning outcome alone:

    market 60258512  "San Diego Padres vs. San Francisco Giants"
       outcomes: [('San Diego Padres', 1.0)]

That row is a bare matchup by title with no derivative vocabulary, so it stays
ADMISSIBLE (count == 1, no retirement). But all three resolution paths in
`find_moneyline_outcome` — the team-match loop, the full-matchup fallback and
the generic Yes/No last resort — skip any outcome that is not strictly between
0 and 1, so a one-sided settled book resolves by NO route and the reading is
None (no overwrite). Event 15309667 published **0.069** for the Giants hours
after Polymarket had settled the game to the Padres.

WHAT MAKES THIS SAFE TO RETIRE IS PERMANENCE, and that is the line every test
below is drawn around. A settled price does not come back off 0.00/1.00, so the
silence is structural. A winner market that is merely UNPRICED right now is
transient, and retiring on it would drop and re-add the leg as prices come and
go — twitching the hero by a whole source weight every fifteen minutes, which
is precisely what `count_admissible_speakers`' docstring exists to prevent. So
the settled test abstains in every direction it can: an empty book abstains, an
unpriced outcome abstains, and a group with no admissible speaker at all
abstains (that is #5031's case and keeps its own funnel counter).

Measured on production 2026-09-12 08:2xZ, with the real recognizer rather than
by eye: of the nine events #5548 named, SEVEN wear this shape; across all 430
scheduled/live events holding a Polymarket leg the new arm retires 11, every one
a US Open match already played whose markets are all `resolved`.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_speakers_are_all_settled,
    count_admissible_speakers,
)


NOW = datetime(2026, 9, 12, 8, 20, tzinfo=timezone.utc)

# The production specimen, by name, so a reader can find it at the venue.
HOME = "San Francisco Giants"
AWAY = "San Diego Padres"
EVENT_ID = 15309667


# =============================================================================
# Fakes — only the attributes the gate and the writer actually read
# =============================================================================


class _Market:
    def __init__(self, mid, name, *, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id


class _Outcome:
    current_yes_bid = current_yes_ask = None

    def __init__(self, rank, name, probability, market_id=None):
        self.rank = rank
        self.name = name
        self.current_probability = probability
        self.market_id = market_id


class _EventRow:
    def __init__(self, event_id, wps=None, opening=None):
        self.id = event_id
        self.win_probability_sources = wps
        self.opening_home_probability = opening


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Serves the SELECTs the retirement issues and records its UPDATEs."""

    def __init__(self, event_row, outcomes=()):
        self._event_row = event_row
        self._outcomes = list(outcomes)
        self.updates = []
        self.added = []
        self.commits = 0

    async def get(self, model, pk):
        assert model is Event
        return self._event_row if pk == self._event_row.id else None

    async def execute(self, stmt):
        text = str(stmt)
        if text.lstrip().upper().startswith("UPDATE"):
            self.updates.append(stmt)
            return _Result([])
        if "futures_outcomes" in text:
            return _Result(self._outcomes)
        if "win_prob_snapshots" in text:
            return _Result([], scalar=None)
        if "odds_snapshots" in text:
            return _Result([], scalar=None)
        if "events" in text:
            return _Result([], scalar=self._event_row.win_probability_sources)
        raise AssertionError(f"unexpected statement: {text[:160]}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — error path only
        pass

    def written_sources(self):
        for stmt in self.updates:
            values = dict(stmt._values)
            col = Event.__table__.c.win_probability_sources
            if col in values:
                return values[col].value
        return None


def _entry(mid, name, outcomes=(), *, source="polymarket", external_id=None):
    return MarketOutcomes(
        market=_Market(mid, name, source=source, external_id=external_id),
        outcomes=[_Outcome(rank, oname, prob) for rank, oname, prob in outcomes],
    )


def _ref(market_id, name, *, source="polymarket", external_id=None, event_id=EVENT_ID):
    from app.tasks.prediction_market_matching import _LinkedMarketRef

    return _LinkedMarketRef(
        market_id=market_id,
        source=source,
        external_id=external_id,
        name=name,
        event_id=event_id,
        event_commence_time=NOW - timedelta(hours=6),
        home_team_name=HOME,
        away_team_name=AWAY,
    )


# The real row, at its real id, in the shape production served it.
def _settled_container():
    return _entry(60258512, f"{AWAY} vs. {HOME}", [(1, AWAY, 1.0)])


# =============================================================================
# 1. The predicate — settled is PERMANENT, unpriced is TRANSIENT
# =============================================================================


class TestASettledBookIsStructuralSilence:
    def test_the_production_one_sided_container_reads_as_settled(self):
        """60258512: one outcome, the winner, at 1.0 — admissible and mute."""
        group = [_settled_container()]
        assert count_admissible_speakers(group) == 1, (
            "the settled container keeps its bare-matchup title, so the "
            "speaker count cannot see the problem — that is the whole defect"
        )
        assert admissible_speakers_are_all_settled(group) is True

    def test_a_multi_outcome_book_all_at_one_is_settled(self):
        """59751062 (Braves/Phillies): 8 outcomes, every one at 1.0."""
        group = [
            _entry(
                59751062,
                "Atlanta Braves vs. Philadelphia Phillies",
                [(rank, f"leg {rank}", 1.0) for rank in range(1, 9)],
            )
        ]
        assert admissible_speakers_are_all_settled(group) is True

    def test_a_book_settled_to_zero_is_settled_too(self):
        """60258522 (Angels/Nationals) settled to 0.0, not 1.0.

        Kills the mutant that tests only the 1.0 boundary. Both ends of the
        book are terminal prices and `find_moneyline_outcome` skips both.
        """
        group = [_entry(60258522, f"{AWAY} vs. {HOME}", [(1, AWAY, 0.0)])]
        assert admissible_speakers_are_all_settled(group) is True

    def test_live_props_on_the_event_do_not_rescue_a_settled_winner(self):
        """15309635's real shape: a settled container beside 40 live props.

        The props are not admissible, so they can never speak for the winner —
        their prices are irrelevant to whether the SOURCE has an opinion. Kills
        the mutant that asks the question of every market in the group instead
        of only the admissible ones.
        """
        group = [
            _settled_container(),
            _entry(
                60735759,
                "CJ Abrams: Hits + Runs + RBIs O/U 4.5",
                [(1, "Over", 0.095), (2, "Under", 0.905)],
            ),
        ]
        assert admissible_speakers_are_all_settled(group) is True


class TestTheTransientCaseIsLeftAlone:
    def test_a_two_sided_live_winner_market_is_not_settled(self):
        group = [_entry(59852299, f"{AWAY} vs. {HOME}", [(1, AWAY, 0.705), (2, HOME, 0.295)])]
        assert admissible_speakers_are_all_settled(group) is False

    def test_an_unpriced_winner_market_is_not_settled(self):
        """THE test this whole guard is drawn around.

        An untraded winner market whose outcomes carry no price is the
        TRANSIENT silence #5031 deliberately protects. Kills the mutant that
        drops the `raw is None` check — without it an unpriced book reads as
        settled and the hero loses a source every time a market goes quiet.
        """
        group = [_entry(59852299, f"{AWAY} vs. {HOME}", [(1, AWAY, None), (2, HOME, None)])]
        assert admissible_speakers_are_all_settled(group) is False

    def test_a_half_priced_book_is_not_settled(self):
        """One side terminal, the other not yet fetched — abstain.

        A book mid-write is not a book that has settled.
        """
        group = [_entry(59852299, f"{AWAY} vs. {HOME}", [(1, AWAY, 1.0), (2, HOME, None)])]
        assert admissible_speakers_are_all_settled(group) is False

    def test_an_empty_book_is_not_settled(self):
        """Outcomes not fetched yet. Kills the mutant that drops the empty check
        and lets `all([])` return True for a book we have never read."""
        group = [_entry(59852299, f"{AWAY} vs. {HOME}", [])]
        assert admissible_speakers_are_all_settled(group) is False

    def test_one_live_admissible_market_saves_the_group(self):
        """A settled book AND a live winner market, both admissible.

        Kills the `any`-instead-of-`all` mutant: one settled speaker must not
        condemn a group that still has a speaker able to price a side. The
        second market is a clean two-sided winner deliberately — a container
        carrying a `Spread -16.5` outcome is refused a step earlier by
        `outcomes_refute_game_winner` (#5273), so building this case out of one
        would test that gate instead of this one and pass for the wrong reason.
        """
        group = [
            _entry(55275300, "Will Kansas State beat Kansas?", [(1, "Yes", 1.0), (2, "No", 0.0)]),
            _entry(
                59947630,
                "Washington State vs. Kansas State",
                [(1, "Washington State", 0.115), (2, "Kansas State", 0.885)],
            ),
        ]
        assert count_admissible_speakers(group) == 2
        assert admissible_speakers_are_all_settled(group) is False


class TestTheZeroSpeakerCaseStaysWithFiveOhThreeOne:
    def test_a_group_of_only_derivatives_is_not_reported_as_settled(self):
        """No admissible speaker at all — that is #5031's case, not this one.

        Kills the mutant that returns True for an empty admissible list, which
        would re-label every #5031 retirement as a settled-book retirement and
        silently merge two populations in the funnel.
        """
        group = [
            _entry(
                59852281,
                f"{AWAY} vs. {HOME} - Exact Score",
                [(1, f"{AWAY} 2 - 2 {HOME}", 1.0)],
            )
        ]
        assert count_admissible_speakers(group) == 0
        assert admissible_speakers_are_all_settled(group) is False

    def test_an_empty_group_abstains_without_raising(self):
        assert admissible_speakers_are_all_settled([]) is False
        assert admissible_speakers_are_all_settled(None) is False


# =============================================================================
# 2. The writer — the frozen leg is actually removed
# =============================================================================


@pytest.mark.asyncio
class TestTheSettledContainerRetiresItsLeg:
    async def test_the_frozen_giants_leg_is_removed(self):
        """RED ON MASTER: master leaves 0.069 on a game Polymarket has settled.

        Event 15309667's real state on 2026-09-12: a Polymarket leg of 0.069
        for the Giants, hours after the container collapsed to
        `[('San Diego Padres', 1.0)]`. Nothing on master ever overwrites it.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(
            EVENT_ID,
            {
                "polymarket": {"value": 0.069, "updated_at": "2026-09-12T05:16:54+00:00"},
                "kalshi": {"value": 0.02, "updated_at": "2026-09-12T05:20:00+00:00"},
            },
        )
        session = _FakeSession(event_row, outcomes=[_Outcome(1, AWAY, 1.0, market_id=60258512)])
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, [_ref(60258512, f"{AWAY} vs. {HOME}")], stats,
        )

        assert spoke is None, "a settled one-sided book cannot price a side"
        written = session.written_sources()
        assert written is not None, "the frozen leg must be retired, not left alone"
        assert "polymarket" not in written
        assert written["kalshi"]["value"] == 0.02, (
            "a retirement removes ONE source key and never touches a sibling"
        )
        assert stats["funnel"]["blend_source_retired_settled_book"] == 1
        assert "blend_source_retired_no_winner_market" not in stats["funnel"], (
            "the two structural silences must stay separable in the funnel"
        )
        assert session.commits == 1

    async def test_an_unpriced_winner_market_still_keeps_its_leg(self):
        """The #5031 protection, re-asserted against THIS change.

        Kills the mutant that retires whenever the reading is None. No outcomes
        are served, so the winner market is unpriced — transient, not settled.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(EVENT_ID, {"polymarket": {"value": 0.42, "updated_at": "x"}})
        session = _FakeSession(event_row)
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, [_ref(59852299, f"{AWAY} vs. {HOME}")], stats,
        )

        assert spoke is None
        assert session.updates == [], (
            "an unpriced winner market is transient — the stored leg stays"
        )
        assert stats.get("funnel", {}) == {} or (
            "blend_source_retired_settled_book" not in stats["funnel"]
        )

    async def test_the_zero_speaker_retirement_keeps_its_original_counter(self):
        """#5031's population must not be re-labelled by this ship.

        A group of pure derivatives still retires, and still under
        `blend_source_retired_no_winner_market` — otherwise the funnel would
        report a new cause where an old one fired.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(EVENT_ID, {"polymarket": {"value": 0.07, "updated_at": "x"}})
        session = _FakeSession(event_row)
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, [_ref(59852281, f"{AWAY} vs. {HOME} - Exact Score")], stats,
        )

        assert spoke is None
        assert session.written_sources() is not None
        assert stats["funnel"]["blend_source_retired_no_winner_market"] == 1
        assert "blend_source_retired_settled_book" not in stats["funnel"]
