"""#12428: a "by...?" deadline board on Discover gets its caption back.

THE READER'S PAGE (Mon Nov 9, 11:36 AM PT). The Flow Sentinel's own feed,
``GET /api/feed?limit=50&include_events=false&include_futures=true``, carried
two cards in its top three with no caption of any kind: "Bloomberg IPO?" and
"Kimi (Moonshot AI) IPO?". ``reason`` was empty and ``headline`` null, so both
clients' ``firstMeaningful([context_summary, headline, reason, ...])`` chain
had nothing to print. The same feed's top 50 held three more of the same shape
("Netanyahu out?", "Crude Oil all time high?", "Houthis enter Aden?").

THE CAUSE IS TWO RULES READING ONE WORD.

* #6470 (Sep 16) gave these boards their caption, "25% chance by September 30,
  2027". Its licence is the venue's own "by": Polymarket names the group
  "Bloomberg IPO by...?" and the display rule deletes the word, so the level
  clause puts it back beside the date it governs. It also refused the clause
  for a proven cumulative ladder (#4640), and said so in a control that "pins
  the intersection before some later grammar creates it": at the time no date
  board could be a ladder.
* #7667 (Sep 20) was that grammar. It reads the SAME "by" off the title as the
  direction of a date ladder, so every board with two or more live date rungs
  became a proven ladder, and the refusal fired on exactly #6470's population.
  Its census counted those cards under "leader copy (#4640, correctly)".

So since Sep 20 the word that licenses the caption is also the word that
refuses it, and only one-rung boards (the binary path) kept theirs.

THE FIX. The level clause is a LEVEL, not a comparative: it states one rung's
own price and claims nothing about any other rung, which is #6470's own safety
argument. On a cumulative deadline ladder the rung it names is the board's own
answer to "will it happen within this window". So the two CAPTION slots
(``reason``, ``context_summary``) may print it on a ladder rung. The HEADLINE
keeps the refusal: it is the ranking input (``explanation_score_rank``), and
lifting it there would move these cards' order. That would be a ranking change
riding a copy fix, the thing #4805 and #4842 also declined. The comparatives
stay refused everywhere: no rung of a ladder "leads".

Fixtures are the production legs read at 11:58 AM PT through
``/api/admin/discover-quality/trace/{id}`` (57661982, 60626093, 112923); the
highlight reasons are the trace's own. The ladder flag is computed by the
route's own predicate from the raw title, never set by hand, so these tests
reach the branch the cards took.
"""

import pytest

from app.routes.feed import _leader_is_ladder_rung
from app.utils.feed_reasons import (
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)
from app.utils.graded_card import rendered_card_percents
from app.utils.market_display_name import (
    clean_market_display_name,
    elided_trailing_preposition,
)

# (raw stored name, the legs as the route holds them, the trace's reasons)
BLOOMBERG = (
    "Bloomberg IPO by...?",
    [
        ("September 30, 2027", 0.235),
        ("March 31, 2027", 0.155),
        ("June 30, 2027", 0.115),
        ("December 31, 2026", 0.025),
        ("December 31, 2027", None),
    ],
    ["category_base_tech", "compelling_x1", "tier_2", "secondary_league",
     "moderate_surprise"],
)
KIMI = (
    "Kimi (Moonshot AI) IPO by...?",
    [
        ("June 30, 2027", 0.38),
        ("December 31, 2026", 0.0335),
        ("March 31, 2027", None),
    ],
    ["category_base_tech", "compelling_x1", "tier_2", "secondary_league",
     "moderate_surprise"],
)
NETANYAHU = (
    "Netanyahu out by...?",
    [
        ("June 30, 2027", 0.69),
        ("March 31, 2027", 0.655),
        ("December 31", 0.46),
    ],
    ["category_base_geopolitics", "tier_2", "secondary_league", "rank_shakeup",
     "moderate_volume", "moderate_surprise"],
)
BOARDS = [BLOOMBERG, KIMI, NETANYAHU]
EXPECTED = {
    "Bloomberg IPO by...?": "24% chance by September 30, 2027",
    "Kimi (Moonshot AI) IPO by...?": "38% chance by June 30, 2027",
    "Netanyahu out by...?": "69% chance by June 30, 2027",
}


def _shared(raw, legs, reasons, **overrides):
    """The generator inputs, built the way `routes/feed.py` builds them: the
    cleaned title is printed, the deadline word and the ladder verdict are read
    off the raw one, and the percents are the ones the card's rows print."""
    rows = [{"name": name, "probability": p} for name, p in legs]
    printed = rendered_card_percents([p for _, p in legs[:3]])
    beneath = [p for p in printed[1:] if p is not None]
    shared = dict(
        market_name=clean_market_display_name(raw),
        highlight_reasons=list(reasons),
        leader_name=legs[0][0],
        leader_probability=legs[0][1],
        rendered_leader_percent=printed[0],
        rendered_runner_up_percent=max(beneath) if beneath else None,
        leader_is_ladder_rung=_leader_is_ladder_rung(rows, raw),
        leader_deadline_preposition=elided_trailing_preposition(raw),
    )
    shared.update(overrides)
    return shared


def _slots(raw, legs, reasons, **overrides):
    shared = _shared(raw, legs, reasons, **overrides)
    headline = generate_futures_headline(**shared)
    return {
        "headline": headline,
        "reason": generate_futures_reason(**shared),
        # As the route passes it: the generated headline, or the signal label
        # behind it. These boards have no label (`primary_reason` is None).
        "context_summary": generate_futures_context_summary(
            headline=headline or None, **shared
        ),
    }


def _served(slots):
    """What the clients' `firstMeaningful` chain prints."""
    for key in ("context_summary", "headline", "reason"):
        if (slots[key] or "").strip():
            return slots[key].strip()
    return ""


class TestTheBoardsAreWhatTheRouteSays:
    """The intersection is real, not staged: the route's own predicate calls
    each board a ladder, and the title carries the venue's "by"."""

    @pytest.mark.parametrize("board", BOARDS, ids=lambda b: b[0])
    def test_a_proven_ladder_with_the_venues_by(self, board):
        shared = _shared(*board)
        assert shared["leader_is_ladder_rung"] is True
        assert shared["leader_deadline_preposition"] == "by"


class TestTheCaptionIsBack:
    @pytest.mark.parametrize("board", BOARDS, ids=lambda b: b[0])
    def test_the_card_prints_the_deadline_level(self, board):
        assert _served(_slots(*board)) == EXPECTED[board[0]]

    @pytest.mark.parametrize("board", BOARDS, ids=lambda b: b[0])
    def test_the_context_summary_carries_it(self, board):
        # The first link of both clients' chain, so the slot a reader sees.
        assert _slots(*board)["context_summary"] == EXPECTED[board[0]]

    @pytest.mark.parametrize("board", BOARDS, ids=lambda b: b[0])
    def test_the_reason_carries_it_too(self, board):
        # The slot the Flow Sentinel's explanation measure reads.
        assert _slots(*board)["reason"] == EXPECTED[board[0]]

    def test_the_percent_is_the_one_the_row_prints(self):
        # 0.235 prints 24 on the card's top row; the caption agrees with it.
        slots = _slots(*BLOOMBERG)
        assert slots["reason"].startswith("24% ")


class TestTheHeadlineAndTheRankingAreUnchanged:
    @pytest.mark.parametrize("board", BOARDS, ids=lambda b: b[0])
    def test_the_headline_stays_empty(self, board):
        # `explanation_score_rank` reads the headline. Empty in, empty out, so
        # these cards' order cannot move with this fix.
        assert _slots(*board)["headline"] == ""


class TestTheRefusalsThatStillHold:
    def test_no_rung_of_a_ladder_is_a_new_favorite(self):
        raw, legs, reasons = BLOOMBERG
        slots = _slots(raw, legs, reasons + ["leader_change"])
        assert "favorite" not in slots["reason"].lower()
        assert "lead" not in slots["reason"].lower()
        assert slots["reason"] == EXPECTED[raw]

    def test_without_the_venues_by_it_stays_silent(self):
        # The word comes from the venue, never from the label (#6470).
        raw, legs, reasons = BLOOMBERG
        for word in (None, "on", "at"):
            slots = _slots(raw, legs, reasons, leader_deadline_preposition=word)
            assert _served(slots) == "", word

    def test_a_numeric_ladder_has_no_date_to_be_a_bound_on(self):
        raw = "Amazon 2026 capex above ___?"
        legs = [("Above 120", 0.45), ("Above 140", 0.21), ("Above 160", 0.08)]
        slots = _slots(raw, legs, ["moderate_surprise"])
        assert slots["reason"] == ""

    def test_a_market_past_its_resolution_stays_silent(self):
        raw, legs, _ = BLOOMBERG
        assert _served(_slots(raw, legs, ["stale_past_resolution"])) == ""

    def test_a_card_with_a_live_signal_keeps_its_own_sentence(self):
        # The level clause is the fallback rung. A signal the card can state
        # still speaks first.
        raw, legs, reasons = KIMI
        slots = _slots(raw, legs, reasons + ["resolving_soon_7d"])
        assert slots["reason"] == "Kimi (Moonshot AI) IPO resolving within a week"

    @pytest.mark.parametrize("code, window", [
        ("resolving_soon_1d", "Resolves within a day"),
        ("resolving_soon_2d", "Resolves within two days"),
        ("resolving_soon_7d", "Resolves within a week"),
        ("resolving_soon_30d", "Resolves within a month"),
    ])
    def test_a_borrowed_window_never_shares_a_caption_with_the_level(
        self, code, window
    ):
        # The resolving codes are keyed on the market's ONE stored date, which
        # on a date ladder is the EARLIEST rung's (#9782). "38% chance by June
        # 30, 2027; resolves within a week" would put two deadlines in one
        # caption, so where a window speaks the caption is what it was.
        raw, legs, reasons = KIMI
        slots = _slots(raw, legs, reasons + [code])
        assert slots["context_summary"] == window
        assert "June 30, 2027" not in _served(slots)
