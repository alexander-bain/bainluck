"""#6279 — the `Recent upset` chip names the FIELD, so the scoreboard decides it.

THE PRODUCTION DEFECT, re-measured 2026-09-15T02:19Z on
`GET /api/feed?limit=100&include_futures=false&event_pct=1.0` (13 finished cards,
5 chipped `Recent upset`). Event **15307167**:

    Orebro SK  1 - 1  Nordic United FC        status=completed
    highlight.label   "Recent upset"
    headline          "Recent upset"
    reason            ""            <- silent, correctly

Nobody won that match. The chip says somebody did.

The two halves of that card were guarded by two different modules and only one
of them got a tie branch. `utils/feed_reasons.py` got its this morning (#6204,
live at v4544) and the caption duly went silent; the chip one line ABOVE it is
`flags.is_upset`, set in `compute_highlight` off `favorite_switched` — a PRICE
event — and a final price does not settle to 0/1. On this row the price had
drifted to 0.425/0.575 against an opening favourite of `home`, so the switch
fired on the drift alone and the card ended up giving one question two answers.

That is #4580's rule ("this sentence says *leading*, so the scoreboard decides
it, not the price") arriving one field to the left.

WHAT THIS FIX IS NOT, and the reason is load-bearing:

* It is **not** a rule against the chip disagreeing with the card's printed
  `Pre-match` row. On the other defective card from the same read — 15298124,
  Villarreal 1 - 2 Real Betis, printing `51% Pre-match 49%` with the 51 on the
  losers — the row is fabricated (#6277: a three-way soccer market's away slot
  is `1 - home`, so it carries the whole draw) and the chip is the only true
  statement on the card. A disagreement rule deletes the alarm and keeps the
  lie. `TestTheAlarmSurvives` pins that.
* It does **not** withdraw the chip from a final we cannot score.
  `score_is_decided` is tri-state and the third state is the point: `None` is
  "the scoreboard is unreadable", not "the match was level". `TestTheControls`
  pins that a scoreless final keeps its chip, so the gate cannot quietly widen
  into a population it has no specimen for.

THE GATE IS NOT DISPLAY-ONLY AND THESE TESTS SAY SO. `flags.is_upset` also
carries `WEIGHTS["recent_finish_upset"]`, the `"upset"` keyword that escapes the
Discover event demotion, `should_highlight`, the `signal:upset` taxonomy tag and
the served `is_upset` field on `/api/events`. A drawn match earns none of them,
and `TestTheRankingHalf` asserts each one rather than leaving them to drift.
"""

from datetime import datetime, timedelta, timezone

from app.routes.feed import _DISCOVER_EVENT_EXCEPTION_KEYWORDS
from app.utils.event_taxonomy import _extract_signals
from app.utils.highlights import (
    WEIGHTS,
    compute_highlight,
    get_highlight_label,
    score_is_decided,
    should_highlight,
)

NOW = datetime(2026, 9, 15, 2, 19, tzinfo=timezone.utc)


def _finished(
    *,
    home_score,
    away_score,
    opening_home_prob=0.598,
    current_home_prob=0.425,
    sport_key="soccer_sweden_allsvenskan",
):
    """A finished game whose favourite switched on PRICE, scored as given.

    Goes through the real `compute_highlight` — never hand-builds a
    `HighlightResult` — so these tests break if the switch classification moves
    and not merely if a string does. `completed_at` two hours back puts the row
    inside the 24h `is_recently_finished` window without the fixture having to
    know how that cascade picks its finish reference.
    """
    return compute_highlight(
        status="completed",
        commence_time=NOW - timedelta(hours=4),
        completed_at=NOW - timedelta(hours=2),
        sport_key=sport_key,
        opening_home_prob=opening_home_prob,
        opening_away_prob=1 - opening_home_prob,
        opening_favorite="home" if opening_home_prob > 0.5 else "away",
        current_home_prob=current_home_prob,
        current_away_prob=1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        now=NOW,
    )


def _the_specimen():
    """15307167 — Orebro SK 1 - 1 Nordic United FC, exactly as served."""
    return _finished(home_score=1, away_score=1)


def _a_genuine_upset():
    """15312204 — Cleveland Guardians 3 - 7 Chicago White Sox.

    The control from the same production read: away opened at 39% and won, and
    its caption ("Chicago White Sox won as a 39% underdog") agrees with its
    chip. Whatever this fix does, this card keeps every one of its signals.
    """
    return _finished(
        home_score=3,
        away_score=7,
        opening_home_prob=0.61,
        current_home_prob=0.20,
        sport_key="baseball_mlb",
    )


class TestTheDeterminationItself:
    """`score_is_decided` already answers this question; nothing new is minted."""

    def test_a_level_final_is_a_known_no(self):
        assert score_is_decided(1, 1) is False
        assert score_is_decided(0, 0) is False

    def test_a_decided_final_is_a_known_yes(self):
        assert score_is_decided(3, 7) is True

    def test_an_unreadable_scoreboard_is_neither(self):
        assert score_is_decided(None, None) is None
        assert score_is_decided(2, None) is None


class TestTheSpecimen:
    """RED ON THE PARENT. A 1 - 1 final makes no upset claim, in any field."""

    def test_the_chip_is_gone(self):
        assert get_highlight_label(_the_specimen()) != "Recent upset"

    def test_the_flag_is_false(self):
        assert _the_specimen().flags.is_upset is False

    def test_the_reason_code_is_absent(self):
        assert "upset" not in _the_specimen().reasons

    def test_the_headline_does_not_say_upset(self):
        """`primary_reason` is served in its own right, so the claim cannot
        simply move one field to the left (T10-1 / #5439's lesson)."""
        assert (_the_specimen().primary_reason or "") != "Recent upset"

    def test_a_goalless_draw_is_refused_too(self):
        """0 - 0 is a KNOWN answer, not a missing one (#4580)."""
        result = _finished(home_score=0, away_score=0)
        assert result.flags.is_upset is False
        assert get_highlight_label(result) != "Recent upset"

    def test_the_price_event_itself_is_untouched(self):
        """This fix refuses the CLAIM ABOUT THE FIELD, not the observation that
        the price moved: `favorite_switched` is a true statement about our own
        instrument and keeps its flag, its reason code and its weight."""
        result = _the_specimen()
        assert result.flags.favorite_switched is True
        assert "favorite_switched" in result.reasons


class TestTheAlarmSurvives:
    """15298124 — Villarreal 1 - 2 Real Betis. The chip is TRUE here.

    The card prints `51% Pre-match 49%` with the 51 on Real Betis, who were a
    24.5% shot on Kalshi's three-way; the row is fabricated by #6277. The chip
    is the one honest signal left on that card and this fix must not touch it.
    """

    def test_the_villarreal_chip_is_kept(self):
        # 0.6535 is the row's stored opening (#6529's measurement); this used
        # the Orebro specimen's 0.598, which puts Betis at 40.2% — inside the
        # close band #2753 now refuses, and not what Villarreal opened at.
        result = _finished(
            home_score=1,
            away_score=2,
            opening_home_prob=0.6535,
            current_home_prob=0.425,
            sport_key="soccer_spain_la_liga",
        )
        assert result.flags.is_upset is True
        assert get_highlight_label(result) == "Recent upset"

    def test_the_gate_never_reads_the_printed_row(self):
        """Same scoreboard, same opening favourite, a current price on EITHER
        side of 0.5 where the switch still fires: the verdict is identical.
        A gate that read the served pair could not give the same answer twice.
        """
        left = _finished(
            home_score=1, away_score=2, opening_home_prob=0.6535, current_home_prob=0.425
        )
        right = _finished(
            home_score=1, away_score=2, opening_home_prob=0.6535, current_home_prob=0.10
        )
        assert left.flags.is_upset is right.flags.is_upset is True


class TestTheControls:
    """Green on BOTH trees. The gate refuses one population and no other."""

    def test_a_genuine_upset_keeps_everything(self):
        result = _a_genuine_upset()
        assert result.flags.is_upset is True
        assert "upset" in result.reasons
        assert get_highlight_label(result) == "Recent upset"
        assert result.primary_reason == "Recent upset"

    def test_a_final_with_no_scoreboard_keeps_its_chip(self):
        """THE NON-WIDENING CONTROL. `None` is unreadable, not level; 41 of 64
        live rows carried no score at all when #4580 measured it. If this ever
        flips, the gate has silently grown a second population."""
        result = _finished(home_score=None, away_score=None)
        assert result.flags.someone_is_leading is None
        assert result.flags.is_upset is True
        assert get_highlight_label(result) == "Recent upset"

    def test_a_final_the_favourite_won_is_now_refused_too_6529(self):
        """GAP 2, DEFERRED HERE AND CLOSED BY #6529. The assertion is inverted.

        This test used to pin a final the opening favourite WON as still
        chipped — #6279 deferred that population on the grounds that a rule
        written against the card's printed `Pre-match` row would land on the
        wrong one, because a three-way soccer row hands the whole draw to the
        away side (#6277).

        #6529 found the specimen on the phone (15312650, Cleveland Guardians
        7 - 6 Chicago White Sox, opening 58.78% Cleveland) and closed it
        WITHOUT that rule: `underdog_leads` reads `opening_home_prob`, the
        column pair `opening_favorite` is itself derived from, never the
        printed row. Measured over 631 finished events in the seven days to
        2026-09-16 the two notions of "favourite" disagree on 0 rows.

        Kept in this file rather than moved: the deferral was recorded here, so
        its lifting belongs here too, and `TestTheAlarmSurvives` two classes up
        is the control that the #6277 population is still not the one being
        refused.
        """
        result = _finished(
            home_score=7,
            away_score=3,
            opening_home_prob=0.61,
            current_home_prob=0.42,
            sport_key="baseball_mlb",
        )
        assert result.flags.favorite_switched is True
        assert result.flags.someone_is_leading is True
        assert result.flags.underdog_is_leading is False
        assert result.flags.is_upset is False
        assert get_highlight_label(result) != "Recent upset"

    def test_a_level_final_with_no_price_switch_is_unchanged(self):
        """15307040, Rio Ave 3 - 3 CF Estrela on the same read: a draw that was
        never chipped, because the price never crossed. It must still not be."""
        result = _finished(home_score=3, away_score=3, current_home_prob=0.62)
        assert result.flags.favorite_switched is False
        assert result.flags.is_upset is False

    def test_a_live_level_game_is_not_in_scope(self):
        """`is_upset` has always been a FINISHED-card flag. A live 1 - 1 keeps
        the live ladder's own answer, which #4580 already gated separately."""
        result = compute_highlight(
            status="live",
            commence_time=NOW - timedelta(hours=1),
            sport_key="soccer_sweden_allsvenskan",
            opening_home_prob=0.598,
            opening_away_prob=0.402,
            opening_favorite="home",
            current_home_prob=0.425,
            current_away_prob=0.575,
            home_score=1,
            away_score=1,
            now=NOW,
        )
        assert result.flags.is_upset is False
        assert result.flags.favorite_switched is True
        assert get_highlight_label(result) == "Odds moved"

    def test_a_stale_final_outside_the_window_is_unchanged(self):
        """The 24h eligibility window is not this fix's business."""
        result = compute_highlight(
            status="completed",
            commence_time=NOW - timedelta(days=5),
            completed_at=NOW - timedelta(days=5),
            sport_key="baseball_mlb",
            opening_home_prob=0.61,
            opening_away_prob=0.39,
            opening_favorite="home",
            current_home_prob=0.20,
            current_away_prob=0.80,
            home_score=3,
            away_score=7,
            now=NOW,
        )
        assert result.flags.is_recently_finished is False
        assert result.flags.is_upset is False


class TestTheRankingHalf:
    """`is_upset` is not a label. Each of its five other readers is asserted
    here BY NAME, because gating only the chip would have left them saying
    "upset" about a 1 - 1 — the same defect one field to the left."""

    def test_the_drawn_final_loses_the_upset_bonus(self):
        """RED ON THE PARENT. The only difference between these two rows is the
        scoreline, so the gap is exactly the weight and nothing else."""
        # Both at Villarreal's 0.6535: at the default 0.598 the away winner
        # sits at 40.2%, which #2753 refuses on size before the draw matters.
        drawn = _finished(home_score=1, away_score=1, opening_home_prob=0.6535)
        decided = _finished(home_score=1, away_score=2, opening_home_prob=0.6535)
        assert decided.score - drawn.score == WEIGHTS["recent_finish_upset"]

    def test_the_drawn_final_no_longer_escapes_the_discover_demotion(self):
        """RED ON THE PARENT. `_DISCOVER_EVENT_EXCEPTION_KEYWORDS` is matched
        against the card's headline, which IS `get_highlight_label` (#4504)."""
        label = (get_highlight_label(_the_specimen()) or "").lower()
        assert not any(k in label for k in _DISCOVER_EVENT_EXCEPTION_KEYWORDS)

    def test_a_genuine_upset_still_escapes_it(self):
        label = (get_highlight_label(_a_genuine_upset()) or "").lower()
        assert any(k in label for k in _DISCOVER_EVENT_EXCEPTION_KEYWORDS)

    def test_the_drawn_final_is_not_force_highlighted(self):
        """RED ON THE PARENT. `should_highlight` returns True unconditionally
        for `is_upset`, bypassing the score threshold entirely."""
        drawn = _the_specimen()
        assert should_highlight(drawn, min_score=101) is False

    def test_a_genuine_upset_is_still_force_highlighted(self):
        assert should_highlight(_a_genuine_upset(), min_score=101) is True

    def test_the_drawn_final_carries_no_upset_signal_tag(self):
        """RED ON THE PARENT. The taxonomy tag is written to the events table
        and read by tag search, so it outlives the card that spawned it."""
        tags: set[str] = set()
        _extract_signals(_the_specimen().flags, tags)
        assert "signal:upset" not in tags

    def test_a_genuine_upset_still_carries_it(self):
        tags: set[str] = set()
        _extract_signals(_a_genuine_upset().flags, tags)
        assert "signal:upset" in tags
