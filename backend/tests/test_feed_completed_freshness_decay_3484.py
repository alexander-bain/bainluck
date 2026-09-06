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

import pytest

from app.utils.feed_scoring import (
    COMPLETED_DECAY_FLOOR,
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
        hours_since_finish=hours_since_finish,
    )
    return score


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

    "Never deletes" is exact for the anonymous reader — the one the measurement
    was taken as, and the one whose gate is the binding constraint. The single
    exception, a down-weighted sport, is pinned explicitly below rather than
    papered over.
    """

    def test_the_decay_never_pushes_a_score_below_the_floor(self):
        # 300 is well above any real score, 24h is the oldest an event can be
        # and still be a feed candidate.
        for score in (36, 50, 98, 130, 300):
            decayed, _ = apply_completed_freshness_decay(score, "completed", 24.0)
            assert decayed >= COMPLETED_DECAY_FLOOR

    def test_the_floor_clears_the_anonymous_min_score_gate(self):
        """routes/feed.py drops an event scoring under min_score (30 anonymous).

        If the floor ever slipped to or below that gate, the decay would start
        silently deleting recent results instead of re-ranking them.

        SCOPE, stated precisely so this is not read as more than it is: the gate
        is applied to `min(98, int(base_score * personalization_multiplier))`.
        This guarantee is therefore exact for the anonymous reader and for any
        personalized reader whose multiplier is >= 1.0 (whose gate is 10, lower
        still). A reader who has DOWN-weighted a sport carries a multiplier below
        1.0 against the same gate of 30, so for them a fully-decayed result can
        fall under it — see the test below, which pins that as understood
        behaviour rather than leaving it to be discovered.
        """
        assert COMPLETED_DECAY_FLOOR > 30

    def test_a_down_weighted_sport_can_drop_an_old_result_and_that_is_understood(self):
        """The one case where the decay does remove a card, made explicit.

        A reader who down-weighted this sport (multiplier < 1.0, gate still 30)
        loses a fully-decayed result. That is a deliberate consequence: the card
        is a six-hour-old game in a sport they asked to see less of. It is pinned
        here so a future change to the floor, the gate or the multiplier cannot
        move this line without a test going red.
        """
        anonymous_gate = 30
        down_weighted_multiplier = 0.7

        # The worst case is a card sitting ON the floor — that is the lowest a
        # decayed score can go, so if the floor survives, everything above it does.
        assert COMPLETED_DECAY_FLOOR >= anonymous_gate

        # ...for the anonymous reader. Multiply by a down-weight and it goes under.
        assert int(COMPLETED_DECAY_FLOOR * down_weighted_multiplier) < anonymous_gate

        # And the boundary is not folklore: it is the multiplier at which the
        # floor stops clearing the gate.
        breakeven = anonymous_gate / COMPLETED_DECAY_FLOOR
        assert down_weighted_multiplier < breakeven < 1.0
        # A real, high-scoring result is comfortably clear of it even down-weighted.
        decayed_from_98, _ = apply_completed_freshness_decay(98, "completed", 24.0)
        assert int(decayed_from_98 * down_weighted_multiplier) >= anonymous_gate

    def test_a_score_already_at_or_under_the_floor_is_left_alone(self):
        for score in (0, 12, COMPLETED_DECAY_FLOOR):
            decayed, reasons = apply_completed_freshness_decay(score, "completed", 24.0)
            assert decayed == score
            assert reasons == []

    def test_the_decay_never_raises_a_score(self):
        for hours in (0.0, 2.0, 6.0, 24.0, 100.0):
            decayed, _ = apply_completed_freshness_decay(90, "completed", hours)
            assert decayed <= 90

    def test_a_decayed_card_says_why(self):
        _, reasons = apply_completed_freshness_decay(98, "completed", 9.0)
        assert "stale_result" in reasons

    def test_an_undecayed_card_adds_no_reason(self):
        _, reasons = apply_completed_freshness_decay(98, "completed", 0.5)
        assert reasons == []


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
    def test_a_live_event_score_is_unchanged_by_the_new_argument(self):
        kwargs = dict(
            highlight_score=60,
            highlight_reasons=["live"],
            home_champ_prob=0.0,
            away_champ_prob=0.0,
            sport_key="baseball_mlb",
            now=NOW,
            event_tags=[],
            event_status="live",
            raw_ei=0.5,
            game_progress=0.6,
            source_count=3,
        )
        without, _ = compute_base_score(**kwargs)
        with_age, _ = compute_base_score(**kwargs, hours_since_finish=11.0)

        assert without == with_age

    def test_a_scheduled_event_score_is_unchanged_by_the_new_argument(self):
        kwargs = dict(
            highlight_score=45,
            highlight_reasons=["starting_soon"],
            home_champ_prob=0.0,
            away_champ_prob=0.0,
            sport_key="baseball_mlb",
            now=NOW,
            event_tags=[],
            event_status="scheduled",
            raw_ei=None,
        )
        without, _ = compute_base_score(**kwargs)
        with_age, _ = compute_base_score(**kwargs, hours_since_finish=11.0)

        assert without == with_age

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
