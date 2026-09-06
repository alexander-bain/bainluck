"""#3484 — a finished game leaves the Sports feed's first page.

Measured on production 2026-09-06 08:27Z: `GET /api/feed?limit=20&mode=sports`
served 14 dead cards out of 20. The 13 finished games scored 86-98; the only two
live games scored 35 and 40. Every one of the 13 was already `status='completed'`
with `completed_at` set 2.9h-11.8h earlier, so nothing was waiting to be marked
final — the feed was ranking settled games above unplayed ones.

Two causes, both exercised here:

1. `is_recently_finished` was a BINARY 24-hour flag, and every post-game bonus
   (`recent_finish`, `recent_finish_upset`, the EI boost, the comeback and
   lead-change bonuses) rode it at full value for the whole window. A game that
   ended sixty seconds ago and one that ended twenty-three hours ago scored the
   same, so a night's results progressively displaced everything unplayed.

2. The finish reference was `end_time if end_time else commence_time`, and
   `statpal_end_time` was NULL on 13/13 of the affected rows — so the age was in
   practice measured from KICKOFF.

The controls matter as much as the arms: the decay must re-rank a finished game,
never delete it (#1091 — a surface must never be capped into emptiness), and it
must not touch live or scheduled events.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.personalization import (
    LOW_AFFINITY_THRESHOLD,
    NAH_AFFINITY_THRESHOLD,
    PersonalizationContext,
    compute_event_multiplier,
)
from app.utils.feed_scoring import (
    COMPLETED_DECAY_HOURS,
    COMPLETED_FRESH_HOURS,
    COMPLETED_MAX_DECAY,
    apply_completed_freshness_decay,
    compute_base_score,
    compute_completed_freshness_factor,
)
from app.utils.highlights import compute_highlight


NOW = datetime(2026, 9, 6, 8, 27, 0, tzinfo=timezone.utc)


def _completed_score(hours_since_finish: float | None, *, raw_ei: float = 0.87) -> int:
    """Score a finished game of a given age through the real scoring path.

    Mirrors the production shape of the measured rows: a high-EI completed game
    with no champ-prob stakes and no tags, so the only thing separating two calls
    is the age.

    `compute_base_score` no longer decays — the decay moved behind the admission
    gate (CERT-2048, see the module docstring's "WHERE THE DECAY IS APPLIED") —
    so this composes the two exactly as `_score_events` does, and returns the
    display score a reader would rank on at multiplier 1.0.
    """
    score, _ = compute_base_score(
        highlight_score=60,
        highlight_reasons=["recent_finish", "upset"],
        home_champ_prob=0.0,
        away_champ_prob=0.0,
        sport_key="baseball_mlb",
        now=NOW,
        event_tags=[],
        event_status="completed",
        raw_ei=raw_ei,
    )
    display, _rank, _reasons = apply_completed_freshness_decay(
        display_score=score,
        rank_score=float(score),
        event_status="completed",
        hours_since_finish=hours_since_finish,
    )
    return display


class TestTheDecayIsAGradientNotAFlag:
    """The catching test: the pre-fix code scored these identically."""

    def test_a_just_finished_game_outranks_one_that_ended_hours_ago(self):
        just_finished = _completed_score(0.2)
        five_hours_old = _completed_score(5.0)
        eleven_hours_old = _completed_score(11.8)

        # Strictly ordered — this is the whole ship. Before the fix all three
        # were the same number, which is exactly how a 11.8h-old Atalanta-Roma
        # held a first-page slot at 1:27am.
        assert just_finished > five_hours_old > eleven_hours_old

    def test_the_measured_page_one_inverts_back(self):
        """The real rows: a finished game must not outrank a live game.

        Live scores are the two measured on the page (35 and 40, KBO and NPB).
        The finished games are the five oldest of the thirteen, scored through
        the same path they take in production.
        """
        live_score = 40

        for hours in (7.1, 9.0, 9.7, 11.4, 11.8):
            assert _completed_score(hours) <= live_score, (
                f"a game that ended {hours}h ago still outranks a live game"
            )

    def test_a_game_inside_the_fresh_window_keeps_its_full_score(self):
        """A game that just ended IS the product — WHAT HIT, not clutter."""
        undecayed = _completed_score(None)

        assert _completed_score(0.0) == undecayed
        assert _completed_score(COMPLETED_FRESH_HOURS) == undecayed
        # And the very next moment is already decaying.
        assert _completed_score(COMPLETED_FRESH_HOURS + 2.0) < undecayed


class TestTheFactorCurve:
    def test_full_score_before_the_fresh_window_closes(self):
        assert compute_completed_freshness_factor("completed", 0.0) == 1.0
        assert compute_completed_freshness_factor("completed", COMPLETED_FRESH_HOURS) == 1.0

    def test_maximum_decay_is_reached_and_then_held_flat(self):
        floor_factor = 1.0 - COMPLETED_MAX_DECAY
        assert compute_completed_freshness_factor(
            "completed", COMPLETED_DECAY_HOURS
        ) == pytest.approx(floor_factor)
        # Held flat well beyond — never runs away to zero or negative.
        assert compute_completed_freshness_factor(
            "completed", 240.0
        ) == pytest.approx(floor_factor)

    def test_the_ramp_is_monotonic_across_the_whole_window(self):
        hours = [h / 2 for h in range(0, 49)]
        factors = [compute_completed_freshness_factor("completed", h) for h in hours]
        assert factors == sorted(factors, reverse=True)
        assert all(0.0 < f <= 1.0 for f in factors)

    def test_an_unknown_age_keeps_the_full_score(self):
        """A missing age must never be read as 'infinitely stale'."""
        assert compute_completed_freshness_factor("completed", None) == 1.0

    def test_a_negative_age_keeps_the_full_score(self):
        """Clock skew, or a finish reference in the future, must not invert the ramp."""
        assert compute_completed_freshness_factor("completed", -3.0) == 1.0

    @pytest.mark.parametrize("status", ["live", "scheduled", "suspended", "postponed"])
    def test_only_finished_games_decay(self, status):
        assert compute_completed_freshness_factor(status, 20.0) == 1.0

    def test_closed_decays_the_same_as_completed(self):
        assert compute_completed_freshness_factor(
            "closed", 6.0
        ) == compute_completed_freshness_factor("completed", 6.0)


class TestItReranksAndNeverDeletes:
    """#1091: a surface must never be capped into emptiness.

    THIS CLASS IS THE CERT-2048 REPAIR, and the shape of what it replaced is the
    reason it is written the way it is.

    The first version defended "never deletes" with a numeric floor of 35 and
    proved it by asserting arithmetic on constants — `COMPLETED_DECAY_FLOOR > 30`,
    `int(35 * 0.7) < 30`, and a break-even derived from those same two numbers.
    Every one of those assertions passed. They were all against a gate of 30,
    which is the ANONYMOUS reader's. A reader who has down-weighted a sport is
    the only reader whose multiplier is below 1.0 — and their gate is not 30, it
    is 55. The test never executed `_score_events`, so nothing could tell it that
    it was modelling the wrong branch, and it certified the exact regression it
    was written to catch:

        98 pre-decay -> 98 * 0.7 = 68.6 >= 55   admitted
        44 decayed   -> 44 * 0.7 = 30.8 <  55   DROPPED

    So the guarantee is no longer a number to be compared against a remembered
    gate. It is structural — the decay is applied after the gate — and it is
    proved by RUNNING the gate rather than by restating it.
    """

    def test_the_decay_never_raises_a_score(self):
        for hours in (0.0, 2.0, 6.0, 24.0, 100.0):
            display, rank, _ = apply_completed_freshness_decay(90, 90.0, "completed", hours)
            assert display <= 90
            assert rank <= 90.0

    def test_the_display_and_ordering_scores_decay_by_the_same_factor(self):
        """They are returned together so they cannot drift apart.

        `_rank_score` is `max(display, base * multiplier)` and is UNCAPPED, so a
        card displaying the capped 98 can rank on a much larger number. Decaying
        only the display score would be a no-op for exactly the high-scoring
        finished games this feature exists to demote.
        """
        display, rank, _ = apply_completed_freshness_decay(98, 260.0, "completed", 24.0)
        factor = compute_completed_freshness_factor("completed", 24.0)
        assert display == int(98 * factor)
        assert rank == pytest.approx(260.0 * factor)
        # And the ordering score really did move, by a lot.
        assert rank < 150.0

    def test_a_decayed_card_says_why(self):
        _, _, reasons = apply_completed_freshness_decay(98, 98.0, "completed", 9.0)
        assert "stale_result" in reasons

    def test_an_undecayed_card_adds_no_reason(self):
        _, _, reasons = apply_completed_freshness_decay(98, 98.0, "completed", 0.5)
        assert reasons == []


# ── The required regression: the real gate, not a remembered one ──────────────
#
# Everything below drives the actual `_score_events`, with a real
# `PersonalizationContext`, so the `min_score` branch under test is production's
# own and not a number copied into a test.


def _sport(key="baseball_mlb", name="MLB"):
    s = MagicMock()
    s.key = key
    s.name = name
    return s


def _feed_event(event_id: int, *, hours_since_finish: float, raw_ei: float = 0.95):
    """A finished, high-scoring game of a given age, in production's shape.

    Modelled on the measured rows: `status='completed'`, `statpal_end_time` NULL,
    `completed_at` populated — the 13/13 shape that made the age read from
    kickoff before this ship.
    """
    e = MagicMock()
    e.id = event_id
    e.status = "completed"
    e.commence_time = NOW - timedelta(hours=hours_since_finish + 3)
    e.completed_at = NOW - timedelta(hours=hours_since_finish)
    e.statpal_end_time = None
    e.home_team_id = 100 + event_id
    e.away_team_id = 200 + event_id
    e.home_team_name = f"Home{event_id}"
    e.away_team_name = f"Away{event_id}"
    e.opening_home_probability = 0.20
    e.opening_away_probability = 0.80
    e.win_probability_sources = {"betting": {"home_probability": 0.95}}
    e.opening_home_spread = -3.5
    e.opening_over_under = 8.5
    e.opening_favorite = f"Away{event_id}"
    e.llm_importance = "regular"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.period = None
    e.raw_ei = raw_ei
    e.ei_metadata = None
    e.home_score = 7
    e.away_score = 2
    e.external_id = f"ext-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _run_score_events(events, ctx):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        return await _score_events(_mock_db(events), NOW, None, ctx)


def _low_affinity_ctx():
    """The reader the repair is about: "if it's wild" on this sport.

    Affinity 0.1 is below `LOW_AFFINITY_THRESHOLD` (0.2) and above
    `NAH_AFFINITY_THRESHOLD` (0.05), which is the band that produces
    `sport_suppress` and multiplier 0.7 — and 0.7 is the ONLY multiplier below
    1.0 that reaches the 55 gate, because "Nah" (0.0) is filtered out earlier.
    Read off the real constants rather than hardcoded, so a change to the band
    moves this fixture instead of silently making it a different reader.
    """
    affinity = (LOW_AFFINITY_THRESHOLD + NAH_AFFINITY_THRESHOLD) / 2
    assert NAH_AFFINITY_THRESHOLD < affinity < LOW_AFFINITY_THRESHOLD
    return PersonalizationContext(
        is_authenticated=True,
        sport_affinities={"baseball_mlb": affinity},
    )


class TestTheGateRunsBeforeTheDecay:
    """The required regression (CERT-2048), against the real `_score_events`."""

    @pytest.mark.asyncio
    async def test_the_low_affinity_reader_is_the_one_at_the_55_gate(self):
        """The premise. Without this the tests below could pass vacuously.

        If this reader ever stops producing `sport_suppress` at multiplier 0.7,
        they are no longer the reader whose gate is 55, and the two tests below
        would be proving something about a reader who was never at risk.
        """
        ctx = _low_affinity_ctx()
        p = compute_event_multiplier(
            ctx=ctx,
            home_team_id=101,
            away_team_id=201,
            sport_key="baseball_mlb",
            event_id=1,
        )
        assert any("sport_suppress" in r for r in p.reasons), p.reasons
        assert p.multiplier == pytest.approx(0.7)

        # And the arithmetic that made this a removal, restated against the real
        # multiplier: admitted before the decay, under the gate after it.
        assert 98 * p.multiplier >= 55
        decayed, _, _ = apply_completed_freshness_decay(98, 98.0, "completed", 24.0)
        assert decayed * p.multiplier < 55

    @pytest.mark.asyncio
    async def test_a_stale_result_stays_admitted_for_a_down_weighted_reader(self):
        """The regression itself: pre-decay-qualified, therefore still shown.

        Against the parent commit this event is absent from the payload entirely.
        """
        stale = _feed_event(1, hours_since_finish=24.0)
        items = await _run_score_events([stale], _low_affinity_ctx())

        ids = {i["data"]["id"] for i in items if i["type"] == "event"}
        assert 1 in ids, (
            "a completed card that cleared the 55 gate BEFORE the decay was "
            f"removed by it — the CERT-2048 regression. got {ids}"
        )

    @pytest.mark.asyncio
    async def test_and_it_ranks_below_a_fresh_result_for_that_same_reader(self):
        """Admitted is only half of it — the ship is that it ranks LOWER.

        Same reader, same sport, same shape; the only difference is age. If the
        repair had bought admission by weakening the decay, this fails.
        """
        fresh = _feed_event(1, hours_since_finish=0.25)
        stale = _feed_event(2, hours_since_finish=24.0)
        items = await _run_score_events([fresh, stale], _low_affinity_ctx())

        ranks = {
            i["data"]["id"]: i["_rank_score"] for i in items if i["type"] == "event"
        }
        assert {1, 2} <= set(ranks), f"both cards must survive: {ranks}"
        assert ranks[2] < ranks[1], (
            f"the 24h-old result must rank below the fresh one: {ranks}"
        )

    @pytest.mark.asyncio
    async def test_the_control_a_card_under_the_gate_before_the_decay_stays_excluded(
        self,
    ):
        """The other direction, which is what makes the repair a repair.

        Gating pre-decay must not ADMIT anything the reader's preferences
        already excluded. A weak completed game that cannot clear 55 even at
        full score is still absent — so the fix moved the decay, it did not
        quietly disable the gate.
        """
        weak = _feed_event(3, hours_since_finish=24.0, raw_ei=0.0)
        weak.win_probability_sources = {}
        weak.home_score = 1
        weak.away_score = 0
        weak.opening_home_probability = 0.5
        weak.opening_away_probability = 0.5

        ctx = _low_affinity_ctx()
        items = await _run_score_events([weak], ctx)
        ids = {i["data"]["id"] for i in items if i["type"] == "event"}
        assert 3 not in ids, (
            "gating before the decay must not admit a card the reader's own "
            f"preferences excluded: {ids}"
        )

        # ...and it is the 55 gate doing it, not the card being unscoreable:
        # the same card reaches an unsuppressed reader.
        plain = await _run_score_events([_feed_event(3, hours_since_finish=24.0,
                                                     raw_ei=0.0)],
                                        PersonalizationContext())
        assert 3 in {i["data"]["id"] for i in plain if i["type"] == "event"}


class TestTheFinishReferenceIsTheBestOneAvailable:
    """Cause 2: the age was measured from kickoff on 13/13 of the measured rows."""

    def test_completed_at_is_preferred_when_statpal_has_no_end_time(self):
        """The measured case: statpal_end_time NULL, completed_at populated.

        A three-hour baseball game that ended 12 minutes ago must read as 12
        minutes old, not three hours old.
        """
        commence = NOW - timedelta(hours=3, minutes=12)
        completed = NOW - timedelta(minutes=12)

        result = compute_highlight(
            status="completed",
            commence_time=commence,
            sport_key="baseball_mlb",
            now=NOW,
            end_time=None,
            completed_at=completed,
        )

        assert result.hours_since_finish == pytest.approx(0.2, abs=0.01)
        # Still eligible — the card does not disappear, it is just dated correctly.
        assert result.flags.is_recently_finished

    def test_statpal_end_time_still_wins_when_it_is_present(self):
        """The authoritative final whistle outranks our own bookkeeping stamp."""
        result = compute_highlight(
            status="completed",
            commence_time=NOW - timedelta(hours=9),
            sport_key="baseball_mlb",
            now=NOW,
            end_time=NOW - timedelta(hours=6),
            completed_at=NOW - timedelta(hours=1),
        )

        assert result.hours_since_finish == pytest.approx(6.0, abs=0.01)

    def test_commence_time_remains_the_last_resort(self):
        """Both references absent — unchanged from the pre-fix behaviour."""
        result = compute_highlight(
            status="completed",
            commence_time=NOW - timedelta(hours=4),
            sport_key="baseball_mlb",
            now=NOW,
            end_time=None,
            completed_at=None,
        )

        assert result.hours_since_finish == pytest.approx(4.0, abs=0.01)

    def test_a_naive_completed_at_is_read_as_utc(self):
        """A tz-naive stamp must not raise on the subtraction."""
        result = compute_highlight(
            status="completed",
            commence_time=NOW - timedelta(hours=5),
            sport_key="baseball_mlb",
            now=NOW,
            end_time=None,
            completed_at=(NOW - timedelta(hours=2)).replace(tzinfo=None),
        )

        assert result.hours_since_finish == pytest.approx(2.0, abs=0.01)

    def test_the_age_is_published_even_when_the_event_is_too_old_to_be_eligible(self):
        """The decay reads this field; it must not be None just because the
        24-hour eligibility test failed, or a stale card would read as ageless
        and keep its full score."""
        result = compute_highlight(
            status="completed",
            commence_time=NOW - timedelta(hours=40),
            sport_key="baseball_mlb",
            now=NOW,
            completed_at=NOW - timedelta(hours=38),
        )

        assert not result.flags.is_recently_finished
        assert result.hours_since_finish == pytest.approx(38.0, abs=0.01)

    @pytest.mark.parametrize("status", ["live", "scheduled"])
    def test_an_unfinished_event_publishes_no_finish_age(self, status):
        result = compute_highlight(
            status=status,
            commence_time=NOW - timedelta(hours=1),
            sport_key="baseball_mlb",
            now=NOW,
            completed_at=None,
        )

        assert result.hours_since_finish is None


class TestNothingElseMoved:
    def test_compute_base_score_cannot_decay_because_it_no_longer_knows_the_age(self):
        """The structural half of the CERT-2048 repair, pinned as a signature.

        The gate reads `compute_base_score`'s return value. As long as that
        function cannot see how old a game is, no future edit inside it can put
        the freshness cut back in front of the admission decision — the mistake
        would have to be made in `_score_events`, where the ordering is visible
        in ten lines and the tests above execute it.

        This is deliberately a signature assertion and not a value comparison:
        the old version of this test passed `hours_since_finish=11.0` and checked
        the score did not move, which was true for live events and told nobody
        anything about the completed ones.
        """
        import inspect

        params = inspect.signature(compute_base_score).parameters
        assert "hours_since_finish" not in params, (
            "the freshness age is back in front of the admission gate — "
            "see the CERT-2048 note in feed_scoring.py"
        )

    @pytest.mark.asyncio
    async def test_a_live_event_is_untouched_end_to_end(self):
        """A live game keeps every point, whatever its kickoff was.

        Through the real `_score_events`, so a decay that started firing on a
        status it has no business touching would show up here as a lost card or
        a `stale_result` on something still being played.
        """
        live = _feed_event(9, hours_since_finish=11.0)
        live.status = "live"
        live.completed_at = None
        live.period = "T7"
        # A live game earns its score from being CLOSE, not from a finished
        # blowout's post-game stack, so the control has to be a real live card
        # or it fails the anonymous gate for reasons that have nothing to do
        # with the decay.
        live.home_score = 4
        live.away_score = 3
        live.raw_ei = 70.0
        live.opening_home_probability = 0.55
        live.opening_away_probability = 0.45
        live.win_probability_sources = {"betting": {"home_probability": 0.55}}
        # And a plausible kickoff: `_score_events` drops a "live" game that
        # started 14 hours ago under a separate staleness rule that has nothing
        # to do with this feature. Measured while writing this — the same card
        # at -1h/-3h/-6h scores 67, at -14h it is filtered. Leaving the helper's
        # default here would have made this control pass for the wrong reason
        # (absent card, absent decay) if the decay ever did start touching live.
        live.commence_time = NOW - timedelta(hours=1)

        items = await _run_score_events([live], PersonalizationContext())
        events = [i for i in items if i["type"] == "event"]

        assert [i["data"]["id"] for i in events] == [9]
        assert "stale_result" not in (events[0].get("reason") or "")

    def test_omitting_the_argument_entirely_preserves_the_old_score(self):
        """Every other caller of compute_base_score passes no age at all."""
        score, reasons = compute_base_score(
            highlight_score=60,
            highlight_reasons=["recent_finish"],
            home_champ_prob=0.0,
            away_champ_prob=0.0,
            sport_key="baseball_mlb",
            now=NOW,
            event_tags=[],
            event_status="completed",
            raw_ei=0.87,
        )

        assert "stale_result" not in reasons
        assert score == 60 + 25
