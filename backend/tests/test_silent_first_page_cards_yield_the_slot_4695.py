"""#4695 — a page-one card that prints no sentence yields its slot.

The repair CERT-2470 named (`4695-SILENT-FIRST-PAGE-CARDS-YIELD-THE-SLOT`).

The first #4695 patch restored the resolving-soon sentence for the cards that
had one to say. That was right and it stands, but the cert's production read
was also right: it moved no card the reader was actually looking at. The three
cards it could speak for sat at 23/45/99, while the silent cards on page one
sat at 16 and 19 and stayed there. A copy fix cannot reach a card with nothing
true to say, and #4056 and #4094 both close off inventing something.

So the other door: the card yields the slot. Not dropped — swapped with the
best speaking card beyond the window, through the mechanism that already
exists for ladders, with the same loud shortfall when the pool has nothing to
swap in.

THE FIXTURES ARE VERBATIM. Every card below is a real served item from
`GET /api/feed?limit=150` on 2026-09-10 ~08:0xZ, trimmed to the fields the
control reads and not otherwise tidied. Two of them are the exact specimens
the cert bus reproduced independently at positions 16 and 19.
"""

import pytest

from app.utils.feed_market_quality import (
    enforce_first_page_quality_floor,
    is_wholly_silent_card,
)

# ── The two silent specimens, verbatim from production ───────────────────────

TAIWAN_SILENT = {
    "type": "futures",
    "score": 85,
    "headline": None,
    "reason": "",
    "context_summary": "",
    "data": {
        "name": "Will China invade Taiwan by end of 2026?",
        "hook_description": None,
        "card_sum_reason": None,
    },
}

STANLEY_CUP_SILENT = {
    "type": "futures",
    "score": 80,
    "headline": None,
    "reason": "",
    "context_summary": "",
    "data": {
        "name": "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season",
        "hook_description": None,
        "card_sum_reason": None,
    },
}

# ── The controls: cards that speak through ONE door only ─────────────────────

HOOK_ONLY = {
    "type": "futures",
    "score": 60,
    "headline": None,
    "reason": "",
    "context_summary": "",
    "data": {
        "name": "How many bills will President Trump sign in Sep 2026?",
        "hook_description": (
            "As President Trump gears up for a pivotal election year in 2026, "
            "the legislative landscape is shifting rapidly."
        ),
        "card_sum_reason": None,
    },
}

#: The door that was nearly missed. `independent_prices` is a machine key, so a
#: four-door definition read this card as silent — one more than the cert bus
#: found on production, which is how the omission surfaced.
#: `frontend/lib/cardSum.ts` renders it as a sentence the reader can read.
SUM_REASON_ONLY = {
    "type": "futures",
    "score": 85,
    "headline": None,
    "reason": "",
    "context_summary": "",
    "data": {
        "name": "Russia x Ukraine ceasefire agreement by...?",
        "hook_description": None,
        "card_sum_reason": "independent_prices",
    },
}

SPEAKING_TAIL_CARD = {
    "type": "futures",
    "score": 40,
    "headline": "Kalshi up 6.0 points today",
    "reason": "Kalshi moved up 6.0 points today",
    "context_summary": "Kalshi up 6.0 points today",
    "data": {"name": "Kalshi IPO in 2026?", "hook_description": None},
}


def _speaking(name, score=30):
    return {
        "type": "futures",
        "score": score,
        "headline": f"{name} up 2.0 points today",
        "reason": f"{name} moved up 2.0 points today",
        "context_summary": f"{name} up 2.0 points today",
        "data": {"name": name, "hook_description": None},
    }


class TestWhatCountsAsSilent:
    def test_both_production_specimens_are_silent(self):
        assert is_wholly_silent_card(TAIWAN_SILENT)
        assert is_wholly_silent_card(STANLEY_CUP_SILENT)

    @pytest.mark.parametrize(
        "card,door",
        [
            (HOOK_ONLY, "hook_description"),
            (SUM_REASON_ONLY, "card_sum_reason"),
            (SPEAKING_TAIL_CARD, "headline/reason/context"),
        ],
    )
    def test_a_card_speaking_through_any_single_door_is_not_silent(self, card, door):
        """One sentence anywhere is enough. Demoting a card the reader CAN
        read would be a worse defect than the one this control removes."""
        assert not is_wholly_silent_card(card), f"{door} was not counted as speech"

    def test_whitespace_is_not_speech(self):
        card = {
            "headline": "   ",
            "reason": "",
            "context_summary": None,
            "data": {"name": "x", "hook_description": "\n"},
        }
        assert is_wholly_silent_card(card)

    def test_a_card_carrying_no_text_keys_at_all_is_not_judged(self):
        """Absence of capture is not silence.

        The #1958 corpus fixture is reduced to the audit oracle's fields and
        carries no text doors. Judging it on values alone would call all 49 of
        its cards silent and hand the floor a page with nothing clean to swap
        in — the #1091 failure mode, from a fixture.
        """
        assert not is_wholly_silent_card(
            {"type": "futures", "score": 80, "data": {"name": "Only the oracle fields"}}
        )
        assert not is_wholly_silent_card({"type": "futures", "score": 80})


class TestTheSilentCardYieldsItsSlot:
    def test_both_specimens_leave_page_one_for_speaking_cards(self):
        """The reader's page one, reproduced: two silent cards in the window
        and speaking cards behind them."""
        window = [_speaking(f"clean-{n}", score=90 - n) for n in range(8)]
        window.insert(3, TAIWAN_SILENT)
        window.insert(6, STANLEY_CUP_SILENT)
        tail = [SPEAKING_TAIL_CARD, _speaking("tail-2")]

        out, meta = enforce_first_page_quality_floor(window + tail, first_page_size=10)

        assert meta["silent_in_window"] == 2
        assert meta["demoted"] == 2
        assert meta["unreplaced"] == 0

        names = [(i.get("data") or {}).get("name") for i in out[:10]]
        assert "Will China invade Taiwan by end of 2026?" not in names
        assert (
            "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season"
            not in names
        )
        assert "Kalshi IPO in 2026?" in names

    def test_the_silent_card_is_demoted_not_dropped(self):
        """Ruling (d): named Alex exclusions are the only hard-drops. A card
        with nothing to say is not on that list — it keeps its place further
        down the feed."""
        items = [TAIWAN_SILENT] + [_speaking(f"c-{n}") for n in range(11)]

        out, _ = enforce_first_page_quality_floor(items, first_page_size=10)

        assert len(out) == len(items)
        assert any(i is TAIWAN_SILENT for i in out)

    def test_no_score_is_touched(self):
        """Score invariance — the floor reorders and nothing else."""
        items = [TAIWAN_SILENT] + [_speaking(f"c-{n}") for n in range(11)]
        before = {id(i): i["score"] for i in items}

        out, _ = enforce_first_page_quality_floor(items, first_page_size=10)

        assert {id(i): i["score"] for i in out} == before

    def test_the_controls_keep_their_slots(self):
        """The hook-only and sum-reason-only cards speak, so page one keeps
        them. This is the direction that fails if the door list shrinks."""
        items = [HOOK_ONLY, SUM_REASON_ONLY] + [_speaking(f"c-{n}") for n in range(12)]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["silent_in_window"] == 0
        assert meta["demoted"] == 0
        assert out[0] is HOOK_ONLY
        assert out[1] is SUM_REASON_ONLY

    def test_a_page_with_nothing_to_swap_in_keeps_the_silent_card_loudly(self):
        """Gotcha #53 / #1091: a short page is worse than a silent one. The
        offender stays and the meta says so, rather than the page shrinking."""
        items = [TAIWAN_SILENT, STANLEY_CUP_SILENT] + [
            _speaking(f"c-{n}") for n in range(8)
        ]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert len(out) == 10
        assert meta["silent_in_window"] == 2
        assert meta["unreplaced"] == 2
        assert meta["clean_replacements_available"] == 0
        assert any(i is TAIWAN_SILENT for i in out[:10])

    def test_ladders_and_silence_are_both_screened_and_counted_apart(self):
        """One mechanism, two classes, reported separately so neither hides
        the other in the log line."""
        ladder = _speaking("Will META close above $540")
        ladder["_quality_ladder_or_bucket"] = True

        items = [ladder, TAIWAN_SILENT] + [_speaking(f"c-{n}") for n in range(12)]

        _, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["offenders_in_window"] == 2
        assert meta["silent_in_window"] == 1
        assert meta["demoted"] == 2
