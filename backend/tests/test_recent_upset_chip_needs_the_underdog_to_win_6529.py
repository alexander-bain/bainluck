"""#6529 — `Recent upset` on a game the OPENING FAVOURITE won.

THE PRODUCTION DEFECT, seen on the phone by native/189 (iPhone 17 simulator,
Sports tab, 2026-09-16 09:19Z) and re-measured off the served feed at 10:0xZ.
Event **15312650**:

    MLB  FINAL   Chicago White Sox   6   41%
                 Cleveland Guardians 7   59%        chip: "Recent upset"
                                                    reason: ""            <- silent

Cleveland opened the **58.78% favourite** and Cleveland **won**. The two numbers
the card prints are the opening pair and the 59 side is the winner, so the only
claim on the card that is not simply the score is the one that is false.

#6279 put a scoreboard gate on this exact branch, but it asks *did somebody
win?* (`someone_is_leading is not False`) — not *did the side the price switched
TO win?*. Cleveland's in-play blend fell to 0.201 while they were losing late,
the switch fired on that, and then they came back. A price crossing 0.5 and
coming back is not an upset in any field.

THE SEPARATOR WAS ALREADY ON THE ITEM. `feed_reasons` reads the scoreboard
against the board and had nothing to say, which is why `reason` is `""`.
Measured at the reader's scale (`/api/feed?mode=sports` offsets 0/60/120/180
plus Discover 0/60/120, deduped, 2026-09-16 10:0xZ): **16** finished cards
chipped `Recent upset`, **15** with a genuine underdog winner and each carrying
its "won as N% underdog" sentence, **1** false — and it is exactly the one whose
`reason` is empty.

WHAT THIS FIX IS NOT, and it is the reason #6279 could defer it:

* It is **not** a rule against the card's printed `Pre-match` row. That row is
  fabricated on a three-way soccer card (#6277: the away slot is `1 - home`, so
  it carries the whole draw), and a rule written against it would delete the
  alarm and keep the lie. `underdog_leads` reads `opening_home_prob` — the
  column pair `opening_favorite` is itself derived from — and over the 631
  finished events of the seven days to 2026-09-16 (387 soccer) the two notions
  of "favourite" disagree on **0** rows, with the stored opening pair summing to
  ≥0.98 on every one. `TestTheAlarmStillSurvives` pins Villarreal 1 - 2 Real
  Betis, the #6277 specimen, as still chipped.
* It does **not** replace #6279's clause. The two helpers go unanswerable on
  different inputs: a known draw with no opening price is
  `someone_is_leading is False` but `underdog_is_leading is None`.
  `TestBothClausesAreLoadBearing` gives each clause a row only it refuses, so
  neither can be deleted without a test going red.
* It does **not** withdraw the chip from a final we cannot score. `None` stays
  tolerated on both clauses (#4580: an unreadable scoreboard is not a denial).

THE GATE IS NOT DISPLAY-ONLY. `flags.is_upset` also carries
`WEIGHTS["recent_finish_upset"]`, the `"upset"` keyword that escapes the
Discover event demotion, `should_highlight`, the `signal:upset` taxonomy tag and
the served `is_upset` field — a game the favourite won is being RANKED UP as an
upset. `TestTheRankingHalf` asserts each reader by name.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import _DISCOVER_EVENT_EXCEPTION_KEYWORDS
from app.utils.event_taxonomy import _extract_signals
from app.utils.highlights import (
    WEIGHTS,
    compute_highlight,
    get_highlight_label,
    should_highlight,
    underdog_leads,
)

NOW = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def _finished(
    *,
    home_score,
    away_score,
    opening_home_prob=0.5878,
    current_home_prob=0.201,
    sport_key="baseball_mlb",
    opening_favorite=None,
):
    """A finished game whose favourite switched on PRICE, scored as given.

    Goes through the real `compute_highlight` — never hand-builds a
    `HighlightResult` — so these tests break if the switch classification moves
    and not merely if a string does. `completed_at` two hours back puts the row
    inside the 24h `is_recently_finished` window without the fixture having to
    know how that cascade picks its finish reference.

    `opening_favorite` defaults to the side the opening price favours, which is
    how `odds_polling` writes the column: measured on production, the two never
    disagree. It is overridable only so the no-opening-price row below can exist.
    """
    if opening_favorite is None:
        opening_favorite = "home" if opening_home_prob > 0.5 else "away"
    return compute_highlight(
        status="completed",
        commence_time=NOW - timedelta(hours=4),
        completed_at=NOW - timedelta(hours=2),
        sport_key=sport_key,
        opening_home_prob=opening_home_prob,
        opening_away_prob=None if opening_home_prob is None else 1 - opening_home_prob,
        opening_favorite=opening_favorite,
        current_home_prob=current_home_prob,
        current_away_prob=None if current_home_prob is None else 1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        now=NOW,
    )


def _the_specimen():
    """15312650 — Cleveland Guardians 7 - 6 Chicago White Sox, as served.

    Home opened 0.5878 and won 7 - 6; the blend read 0.201 at the final capture.
    """
    return _finished(home_score=7, away_score=6)


def _a_genuine_upset():
    """15304205 — Syracuse 18 - 21 California, same read.

    The control from the same page: home opened 0.6308 and LOST. Until #2753
    this was 15312659 (Diamondbacks 2 - 4 Marlins, home opened 0.5903), which
    puts the winner at 41% — inside the close band #2753 now refuses on size,
    so it can no longer stand for "a genuine upset keeps everything".
    """
    return _finished(home_score=18, away_score=21, opening_home_prob=0.6308)


class TestTheDeterminationItself:
    """`underdog_leads` already answers this; nothing new is minted. On a FINAL,
    "the underdog is ahead" IS "the underdog won"."""

    def test_the_favourite_winning_is_a_known_no(self):
        assert underdog_leads(0.5878, 7, 6) is False
        assert underdog_leads(0.3982, 1, 2) is False

    def test_the_underdog_winning_is_a_known_yes(self):
        assert underdog_leads(0.5903, 2, 4) is True
        assert underdog_leads(0.3982, 2, 1) is True

    def test_an_unreadable_scoreboard_is_neither(self):
        assert underdog_leads(0.5878, None, None) is None
        assert underdog_leads(None, 7, 6) is None


class TestTheSpecimen:
    """RED ON THE PARENT. A final the opening favourite won makes no upset
    claim, in any field."""

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

    def test_the_away_favourite_mirror_is_refused_too(self):
        """The same game with the sides swapped. A gate that only read the home
        column would pass this one."""
        result = _finished(
            home_score=6, away_score=7, opening_home_prob=0.4122, current_home_prob=0.799
        )
        assert result.flags.favorite_switched is True
        assert result.flags.is_upset is False

    def test_the_price_event_itself_is_untouched(self):
        """This fix refuses the CLAIM ABOUT THE FIELD, not the observation that
        the price moved: `favorite_switched` is a true statement about our own
        instrument and keeps its flag, its reason code and its weight."""
        result = _the_specimen()
        assert result.flags.favorite_switched is True
        assert "favorite_switched" in result.reasons


class TestBothClausesAreLoadBearing:
    """Neither clause subsumes the other, so each gets a row only it refuses.

    Delete either one and a test here goes red — which is the whole reason the
    gate is a conjunction rather than a swap.
    """

    def test_only_the_new_clause_refuses_the_favourite_winning(self):
        result = _the_specimen()
        assert result.flags.someone_is_leading is True  # #6279's clause passes
        assert result.flags.underdog_is_leading is False  # #6529's refuses
        assert result.flags.is_upset is False

    def test_only_the_old_clause_refuses_a_draw_with_no_opening_price(self):
        """#6279's population, reachable through the new clause's blind spot.

        `underdog_leads` needs an opening price to say who the underdog was, so
        on this row it answers `None` — "unanswerable", which both clauses
        tolerate. `score_is_decided` needs only the scoreboard and still says
        `False`. No such row exists on production today (0 of 631 finished
        events in the seven days to 2026-09-16 lack an opening price), which is
        why the clause is kept as a guarantee rather than dropped as dead code.
        """
        result = _finished(
            home_score=1,
            away_score=1,
            opening_home_prob=None,
            opening_favorite="home",
            sport_key="soccer_sweden_allsvenskan",
        )
        assert result.flags.favorite_switched is True
        assert result.flags.underdog_is_leading is None  # new clause passes it
        assert result.flags.someone_is_leading is False  # #6279's refuses it
        assert result.flags.is_upset is False

    def test_the_6279_specimen_is_still_refused(self):
        """15307167 — Orebro SK 1 - 1 Nordic United FC. Refused by both clauses
        now; it must not come back through the seam."""
        result = _finished(
            home_score=1,
            away_score=1,
            opening_home_prob=0.598,
            current_home_prob=0.425,
            sport_key="soccer_sweden_allsvenskan",
        )
        assert result.flags.is_upset is False
        assert get_highlight_label(result) != "Recent upset"


class TestTheAlarmStillSurvives:
    """15298124 — Villarreal 1 - 2 Real Betis. The chip is TRUE here.

    #6279 deferred this fix because a rule written against the card's PRINTED
    `Pre-match` row would refuse this card, where that row is fabricated
    (#6277) and the chip is the only honest signal left. This fix reads the
    opening probability instead, so the card keeps everything.
    """

    def test_the_villarreal_chip_is_kept(self):
        result = _finished(
            home_score=1,
            away_score=2,
            opening_home_prob=0.6535,
            current_home_prob=0.425,
            sport_key="soccer_spain_la_liga",
        )
        assert result.flags.underdog_is_leading is True
        assert result.flags.is_upset is True
        assert get_highlight_label(result) == "Recent upset"

    def test_the_gate_never_reads_the_printed_row(self):
        """Same scoreboard, same opening favourite, a current price anywhere
        the switch still fires: the verdict is identical. A gate that read the
        served pair could not give the same answer twice."""
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

    @pytest.mark.parametrize(
        "home_score,away_score,opening_home_prob,current_home_prob",
        [
            # Every genuine upset from the 2026-09-16 10:0xZ reader-scale read
            # that the specimen was measured in, by its opening pair and score.
            # #2753 moved three of them out (Cubs - Braves, Mets - Orioles,
            # Blue Jays - Tigers: winners opened at 44%, 45%, 44%) — they now
            # lose the chip on size, pinned in the #2753 test file.
            (18, 21, 0.6308, 0.30),  # 15304205 Syracuse - California
            (4, 3, 0.3982, 0.70),  # 15310521 Marlins - Dodgers
            (2, 1, 0.3982, 0.80),  # 15312658 Angels - Mariners
            (9, 3, 0.3623, 0.90),  # 15312858 Rockies - Padres
            (2, 3, 0.7085, 0.15),  # 15308140 Rakow - Zaglebie
            (0, 1, 0.8293, 0.05),  # 15307345 Hibernian - Kilmarnock
            (2, 1, 0.3383, 0.85),  # 15308141 Falkirk - Hearts
            (0, 1, 0.6978, 0.10),  # 15298811 Bristol City - Lincoln City
        ],
    )
    def test_every_true_upset_on_the_page_keeps_its_chip(
        self, home_score, away_score, opening_home_prob, current_home_prob
    ):
        """15 of the 16 chipped cards on that read were real. The fix withdraws
        the chip from exactly one card, and these are the other fourteen minus
        the two already named above."""
        result = _finished(
            home_score=home_score,
            away_score=away_score,
            opening_home_prob=opening_home_prob,
            current_home_prob=current_home_prob,
        )
        assert result.flags.is_upset is True
        assert get_highlight_label(result) == "Recent upset"

    def test_a_final_with_no_scoreboard_keeps_its_chip(self):
        """THE NON-WIDENING CONTROL, inherited from #6279 and re-asserted
        against the new clause: `None` is unreadable, not "the favourite won".
        If this ever flips, the gate has silently grown a second population."""
        result = _finished(home_score=None, away_score=None)
        assert result.flags.underdog_is_leading is None
        assert result.flags.someone_is_leading is None
        assert result.flags.is_upset is True
        assert get_highlight_label(result) == "Recent upset"

    def test_a_live_favourite_ahead_is_not_in_scope(self):
        """`is_upset` has always been a FINISHED-card flag. A live game keeps
        the live ladder's own answer, which #4580 already gated separately."""
        result = compute_highlight(
            status="live",
            commence_time=NOW - timedelta(hours=1),
            sport_key="baseball_mlb",
            opening_home_prob=0.5878,
            opening_away_prob=0.4122,
            opening_favorite="home",
            current_home_prob=0.201,
            current_away_prob=0.799,
            home_score=7,
            away_score=6,
            now=NOW,
        )
        assert result.flags.is_upset is False
        assert result.flags.favorite_switched is True

    def test_a_final_with_no_price_switch_is_unchanged(self):
        """The favourite winning was never chipped when the price stayed put.
        This fix must not invent a claim on that population either."""
        result = _finished(home_score=7, away_score=6, current_home_prob=0.72)
        assert result.flags.favorite_switched is False
        assert result.flags.is_upset is False


class TestTheRankingHalf:
    """`is_upset` is not a label. Each of its other readers is asserted here BY
    NAME, because gating only the chip would have left the favourite's win
    ranked as an upset — the same defect one field to the left."""

    def test_the_favourites_win_loses_the_upset_bonus(self):
        """RED ON THE PARENT. The only difference between these two rows is the
        scoreline, so the gap is exactly the weight and nothing else."""
        # Both at 0.6308 (#2753): at the specimen's 0.5878 the away winner
        # opened at 41%, which is now refused on size before direction.
        favourite_won = _finished(home_score=7, away_score=6, opening_home_prob=0.6308)
        underdog_won = _finished(home_score=6, away_score=7, opening_home_prob=0.6308)
        assert underdog_won.score - favourite_won.score == WEIGHTS["recent_finish_upset"]

    def test_the_favourites_win_no_longer_escapes_the_discover_demotion(self):
        """RED ON THE PARENT. `_DISCOVER_EVENT_EXCEPTION_KEYWORDS` is matched
        against the card's headline, which IS `get_highlight_label` (#4504)."""
        label = (get_highlight_label(_the_specimen()) or "").lower()
        assert not any(k in label for k in _DISCOVER_EVENT_EXCEPTION_KEYWORDS)

    def test_a_genuine_upset_still_escapes_it(self):
        label = (get_highlight_label(_a_genuine_upset()) or "").lower()
        assert any(k in label for k in _DISCOVER_EVENT_EXCEPTION_KEYWORDS)

    def test_the_favourites_win_is_not_force_highlighted(self):
        """RED ON THE PARENT. `should_highlight` returns True unconditionally
        for `is_upset`, bypassing the score threshold entirely."""
        assert should_highlight(_the_specimen(), min_score=101) is False

    def test_a_genuine_upset_is_still_force_highlighted(self):
        assert should_highlight(_a_genuine_upset(), min_score=101) is True

    def test_the_favourites_win_carries_no_upset_signal_tag(self):
        """RED ON THE PARENT. The taxonomy tag is written to the events table
        and read by tag search, so it outlives the card that spawned it."""
        tags: set[str] = set()
        _extract_signals(_the_specimen().flags, tags)
        assert "signal:upset" not in tags

    def test_a_genuine_upset_still_carries_it(self):
        tags: set[str] = set()
        _extract_signals(_a_genuine_upset().flags, tags)
        assert "signal:upset" in tags
