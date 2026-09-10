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
    _CARD_TEXT_DOORS_DATA,
    _CARD_TEXT_DOORS_TOP,
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

#: THE DOOR THAT OPENS ON ANOTHER SURFACE (CERT-2473's BLOCK; the second
#: presentation had this backwards and the BLOCK was right).
#:
#: `card_sum_reason` IS rendered as a sentence by `frontend/lib/cardSum.ts` —
#: but only through `FeedCard.tsx`, which serves `/sports`, `/my-stuff` and
#: `/categories/[slug]`. Discover renders through `DiscoverCard.tsx` ->
#: `discover/FuturesCard.tsx`, whose caption chain (`feedContextSnippet`) reads
#: context_summary / headline / reason / hook_description and NOTHING else.
#:
#: So on the page this floor governs, this card prints a percentage, a question,
#: and not one word. It is SILENT, and it must yield its slot. This is the
#: production specimen the cert bus found still on page one.
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
            (SPEAKING_TAIL_CARD, "headline/reason/context"),
        ],
    )
    def test_a_card_speaking_through_any_single_door_is_not_silent(self, card, door):
        """One sentence anywhere is enough. Demoting a card the reader CAN
        read would be a worse defect than the one this control removes."""
        assert not is_wholly_silent_card(card), f"{door} was not counted as speech"

    def test_a_field_only_another_surface_renders_is_not_speech_here(self):
        """CERT-2473. `card_sum_reason` is a door on `/sports`, not on Discover.

        The whole failure mode of the second presentation: a field was counted
        as speech because SOME component renders it, and the card stayed on the
        page reading a percentage and a question with no words at all. Speech is
        what THIS surface renders.
        """
        assert is_wholly_silent_card(SUM_REASON_ONLY), (
            "card_sum_reason is not in the Discover caption chain "
            "(feedContextSnippet); a card whose only text is `independent_prices` "
            "prints nothing on Discover and must yield its slot"
        )

    def test_the_door_list_is_the_discover_caption_chain(self):
        """The doors ARE `feedContextSnippet`'s futures branch, not a guess.

        Pinned as a set so that adding a door nobody rendered — or dropping one
        the renderer reads — fails here, next to the sentence naming the file.
        """
        assert set(_CARD_TEXT_DOORS_TOP) | set(_CARD_TEXT_DOORS_DATA) == {
            "context_summary",
            "headline",
            "reason",
            "hook_description",
        }

    def test_whitespace_is_not_speech(self):
        card = {
            "type": "futures",
            "headline": "   ",
            "reason": "",
            "context_summary": None,
            "data": {"name": "x", "hook_description": "\n"},
        }
        assert is_wholly_silent_card(card)

    def test_an_item_with_no_type_at_all_is_not_judged(self):
        """Fail safe in the same direction as everything else here: unknown
        card type means "do not demote", never "demote"."""
        assert not is_wholly_silent_card(
            {"headline": None, "reason": "", "context_summary": "", "data": {}}
        )

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

    def test_the_hook_only_control_keeps_its_slot(self):
        """A card speaking through ONE real Discover door is not SILENT.

        This is the direction that fails if the door list shrinks too far — the
        opposite error from CERT-2473's, and just as bad: demoting a card the
        reader can actually read.

        Clause (d) is switched off here (`why_now_window=0`) on purpose. #4080
        added a third, independent reason to yield a slot — a card can speak and
        still name nothing that HAPPENED — and a hook is editorial framing
        ("Can the Dodgers repeat?"), which is a "what". Letting that class run
        inside this test would make it pass or fail for a reason that is not its
        subject; the hook-only card's treatment under clause (d) is pinned in
        `test_clause_d_why_now_floor_4080.py` instead. What this test still
        guards, and all it guards, is that the SILENCE predicate reads all four
        Discover doors.
        """
        items = [HOOK_ONLY] + [_speaking(f"c-{n}") for n in range(12)]

        out, meta = enforce_first_page_quality_floor(
            items, first_page_size=10, why_now_window=0
        )

        assert meta["silent_in_window"] == 0
        assert meta["demoted"] == 0
        assert out[0] is HOOK_ONLY

    def test_the_sum_reason_card_yields_its_slot(self):
        """CERT-2473's specimen, through the floor rather than the predicate.

        `Russia x Ukraine ceasefire agreement by...?` carries only the machine
        key `independent_prices`, which Discover never prints. It must leave the
        window for a card that speaks — this is the cross-layer proof the BLOCK
        asked for, at the level the reader experiences.
        """
        items = [SUM_REASON_ONLY] + [_speaking(f"c-{n}") for n in range(12)]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["silent_in_window"] == 1
        assert meta["demoted"] == 1
        assert meta["unreplaced"] == 0
        assert SUM_REASON_ONLY not in out[:10], (
            "the silent Russia/Ukraine specimen kept its page-one slot"
        )
        assert SUM_REASON_ONLY in out, "it must be demoted, never dropped"
        assert len(out) == len(items), "page length is preserved"

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


class TestTheTwoLayersCannotDrift:
    """CERT-2473's root cause, guarded: the backend decided what "speech" is
    from a field SOME component renders, while the page this floor governs
    renders four other fields. Both halves were green; nothing tested the join
    — the same shape as #4695 itself (ten read sites, no emitter) and #4708 (an
    emitter with no read site). Third time this week, so it gets a guard.
    """

    def _discover_caption_fields(self) -> set[str]:
        """The fields `feedContextSnippet`'s FUTURES branch actually reads."""
        import re
        from pathlib import Path

        utils = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "components"
            / "discover"
            / "utils.ts"
        )
        assert utils.exists(), f"the Discover caption chain moved: {utils}"
        source = utils.read_text()
        match = re.search(r"return firstMeaningful\(\[(.*?)\]\)", source, re.S)
        assert match, (
            "could not find `firstMeaningful([...])` in feedContextSnippet — if the "
            "caption chain was restructured, re-derive the door list from the new "
            "shape rather than deleting this test"
        )
        return {
            field.split(".")[-1]
            for field in re.findall(r"\b(?:item|data)\.(\w+)", match.group(1))
        }

    def test_the_backend_doors_are_exactly_the_discover_caption_chain(self):
        backend = set(_CARD_TEXT_DOORS_TOP) | set(_CARD_TEXT_DOORS_DATA)
        frontend = self._discover_caption_fields()
        assert backend == frontend, (
            "the silence predicate and the Discover caption chain disagree.\n"
            f"  backend doors : {sorted(backend)}\n"
            f"  Discover reads: {sorted(frontend)}\n"
            "A field the backend counts as speech but Discover never prints "
            "leaves a wordless card on page one (CERT-2473). A field Discover "
            "prints but the backend ignores demotes a card the reader can read."
        )

    def test_card_sum_reason_is_not_in_the_discover_chain(self):
        """The specific claim the BLOCK rested on, asserted at the source."""
        assert "card_sum_reason" not in self._discover_caption_fields()


class TestOnlyFuturesCardsAreJudged:
    """Scope by card type, both directions (gotcha #43).

    The door list is `feedContextSnippet`'s FUTURES branch. Off that branch it
    means nothing: a game card's story is the score, a concept card's is the
    matchup, a bundle's is its member rows. None needs a caption to speak.

    This is not hypothetical. Unscoped, the predicate demoted the finished NFL
    opener that #4681 and notice 27 exist to put ON page one —
    `test_finished_marquee_on_discover_4681` passed on master and failed here,
    on the rebase that first brought the two together.
    """

    #: The #4681 specimen's shape: a settled game whose story is the score, with
    #: no caption of any kind.
    FINISHED_GAME = {
        "type": "event",
        "score": 67,
        "headline": None,
        "data": {
            "id": 14780138,
            "sport": "americanfootball_nfl",
            "status": "completed",
            "home_team": "Seattle Seahawks",
            "away_team": "New England Patriots",
            "home_score": 13,
            "away_score": 10,
        },
    }

    def test_a_captionless_finished_game_is_not_silent(self):
        assert not is_wholly_silent_card(self.FINISHED_GAME), (
            "a settled game card renders two teams and a score; demoting it for "
            "want of a caption contradicts #4681 and notice 27"
        )

    def test_a_captionless_finished_game_keeps_its_page_one_slot(self):
        items = [self.FINISHED_GAME] + [_speaking(f"c-{n}") for n in range(12)]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["silent_in_window"] == 0
        assert meta["demoted"] == 0
        assert out[0] is self.FINISHED_GAME

    @pytest.mark.parametrize("card_type", ["event", "concept", "tournament", "bundle"])
    def test_no_non_futures_card_is_ever_called_silent(self, card_type):
        card = dict(SUM_REASON_ONLY, type=card_type)
        assert not is_wholly_silent_card(card)

    def test_but_a_futures_card_with_the_same_emptiness_still_yields(self):
        """The control that keeps the scope from becoming a blanket exemption."""
        assert is_wholly_silent_card(dict(SUM_REASON_ONLY, type="futures"))
