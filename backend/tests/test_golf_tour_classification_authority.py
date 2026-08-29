"""UX-P181 — THE OMEGA EUROPEAN MASTERS STOPS BEING BADGED "PGA TOUR".

═══ WHAT THIS IS ═══

`_classify_tour` in `app/routes/golf.py` ended in a bare `return "pga"`. Anything
it could not recognize was asserted to be a PGA Tour event — not "unknown", not
"Golf", but a confident, specific, wrong claim.

Measured against production 2026-08-29, over all 110 open `llm_sport_category
= 'golf'` markets: **69 of 110 (63%) were decided by that bare default**, and
**8 of the 69 carried a Kalshi ticker that contradicted it.**

The one that reached a pixel is the `Omega European Masters` — a DP World Tour
event, and the only open market under it is:

    id 59759220 | "Omega European Masters Winner" | KXDPWORLDTOUR-OMEM26

THREE independent authorities said DP World Tour and the function consulted none
of them:

  1. Kalshi's own series ticker literally reads `KXDPWORLDTOUR-`.
  2. The DataGolf schedule row IN THE SAME `/api/golf` PAYLOAD reads `euro`
     (35 of the 94 schedule rows are `euro`).
  3. Its own sibling one week earlier — the Husqvarna British Masters — was
     filed correctly as `dp_world`, because DataGolf happened to supply
     `market_metadata->>'tour'` for that one and not for this one.

The name patterns miss it because it is "European MASTERS", not "European TOUR",
and the external-id arm only reads `datagolf:`-prefixed ids.

═══ WHY IT IS A SHIP, NOT A LABEL NIT ═══

`tour_label` is not only the `⛳ …` chip on `components/TournamentCard.tsx`. On
`/categories/golf` the `tour` key is the SECTION GROUPING (page.tsx:246-273,
`TOUR_ORDER` at :144) and `tour_label` is the section HEADING. So the page filed
two consecutive-week DP World Tour events under two different headings, one of
them wrong. The card is also rendered on `/sport/*` and in the Discover feed via
`components/FeedCard.tsx`.

(The per-tour Follow control at page.tsx:292 is decorative — it does not filter —
so no content was hidden. Said plainly rather than overclaimed.)

═══ WHAT THE FIX CHANGES, MEASURED ═══

Replaying the REAL `_classify_tour` over the REAL 110-market population, before
vs after: **11 markets change, every one from a wrong answer to a right one, and
nothing else moves.** 8 `KXDPWORLDTOUR*` (Omega, Husqvarna ×4, Nexo ×3) and 3
`KXLPGA*` (FM Championship) that were being called PGA Tour.

At the SERVED tournament level, exactly one card changes:

    Tour Championship          PGA Tour      -> PGA Tour       datagolf-metadata
    Omega European Masters     PGA Tour      -> DP World Tour  kalshi-ticker  <== SHIP
    Husqvarna British Masters  DP World Tour -> DP World Tour  datagolf-metadata
    Golfers To Win A Pga …2027 PGA Tour      -> PGA Tour       pga-tour-name
    Golfers To Win A Pga …2030 PGA Tour      -> PGA Tour       pga-tour-name

Tour Championship and both "PGA Tour Major" cards RE-EARN their badges rather
than defaulting into them — the precondition the conveyor required before anyone
inverts the default. After UX-P168 deploys (it drops the two foreign
tournaments), ZERO served tournaments are decided by the bare default.

═══ WHAT THE FIX LETS IN — the widening measurement ═══

The dangerous move here is a bare `\\bpga\\b` name recognizer. THREE DP World
Tour events on the current DataGolf schedule are named `BMW PGA Championship`
and `BMW Australian PGA Championship`; a bare `\\bpga\\b` would badge them PGA
Tour and manufacture the exact defect this file exists to remove. The recognizer
therefore requires the full phrase "PGA Tour", and
`test_bmw_pga_championship_is_not_claimed_for_the_pga_tour` is the control.

Likewise the ticker arm deliberately does NOT list a bare `KXPGA` prefix: it
would swallow `KXPGAAWARDS-*` (the Producers Guild of America awards, misfiled
into the golf pool capture-side) and `KXPGASOLHEIM-*`. All of those already land
on `pga` via the default, so recognizing them buys no answer and only launders a
guess into a claim.

    cd backend && python3 -m pytest tests/test_golf_tour_classification_authority.py -v
"""

import inspect

import pytest

from app.routes.golf import (
    _KALSHI_TOUR_TICKER_PREFIXES,
    _PGA_TOUR_NAME_RE,
    _WOMENS_RE,
    TOUR_DISPLAY_NAMES,
    _classify_tour,
)


def classify(name, *, ext=None, meta=None, key="", is_major=False):
    """Drive the real function the way `golf.py:1740` drives it."""
    return _classify_tour(
        name,
        key,
        is_major,
        bool(_WOMENS_RE.search(name)),
        market_external_ids=list(ext or []),
        market_metadata_tours=list(meta or []),
    )


# The verbatim production rows, `futures_markets` 2026-08-29. Keeping the real
# external_ids matters: a hand-simplified `KXDPWORLDTOUR-X` would still pass
# while the real `KXDPWORLDTOURR2LEAD-...` (a prefix, not an exact match) failed.
OMEGA_WINNER = ("Omega European Masters Winner", "KXDPWORLDTOUR-OMEM26", None)
HUSQVARNA_DG = (
    "Husqvarna British Masters hosted by Sir Nick Faldo - Winner",
    "datagolf:euro:2026133:win",
    "euro",
)
HUSQVARNA_KALSHI_R2 = (
    "Husqvarna British Masters hosted by Sir Nick Faldo End of Round 2 Leader",
    "KXDPWORLDTOURR2LEAD-HUBMHBSNF26",
    None,
)
TOUR_CHAMPIONSHIP_DG = ("TOUR Championship - Winner", "datagolf:pga:60:win", "pga")
GOLFERS_MAJOR_2027 = ("Golfers to win a PGA Tour Major in 2027 ", "KXGOLFMAJOR-27", None)
NEXO_R1 = ("Nexo Championship End of Round 1 Leader", "KXDPWORLDTOURR1LEAD-NEC26", None)
FM_CHAMPIONSHIP = ("FM Championship Winner", "KXLPGATOUR-FMC26", None)
PGA_AWARDS = ("PGA Award for Best Television - Drama?", "KXPGAAWARDS-26-DRA", None)


class TestTheShip:
    """The Omega European Masters is a DP World Tour event and now says so."""

    def test_omega_european_masters_is_dp_world(self):
        name, eid, meta = OMEGA_WINNER
        assert classify(name, ext=[eid], meta=[meta] if meta else None) == "dp_world"

    def test_and_the_badge_string_the_card_renders_is_dp_world_tour(self):
        """Pins the exact literal the committed frontend fixture carries."""
        assert TOUR_DISPLAY_NAMES["dp_world"] == "DP World Tour"

    def test_the_defect_was_real_and_it_was_the_bare_default_that_caused_it(self):
        """Strip the ticker and the row falls back to the wrong answer.

        This is the discriminator: it proves the ticker is what moved the
        result, not some unrelated arm that would have fired anyway.
        """
        name, eid, _ = OMEGA_WINNER
        assert classify(name, ext=[eid]) == "dp_world"
        assert classify(name, ext=[]) == "pga", (
            "the name alone still cannot tell — if this ever returns dp_world, "
            "a name pattern started matching and this guard stopped discriminating"
        )


class TestTheControls:
    """Everything that was already right stays right."""

    def test_husqvarna_still_dp_world_via_datagolf_metadata(self):
        name, eid, meta = HUSQVARNA_DG
        assert classify(name, ext=[eid], meta=[meta]) == "dp_world"

    def test_husqvarna_kalshi_round_leader_agrees_with_its_datagolf_sibling(self):
        """The two providers' rows for one tournament must not disagree."""
        n1, e1, m1 = HUSQVARNA_DG
        n2, e2, _ = HUSQVARNA_KALSHI_R2
        assert classify(n1, ext=[e1], meta=[m1]) == classify(n2, ext=[e2]) == "dp_world"

    def test_tour_championship_re_earns_pga_from_datagolf_metadata(self):
        name, eid, meta = TOUR_CHAMPIONSHIP_DG
        assert classify(name, ext=[eid], meta=[meta]) == "pga"

    def test_golfers_to_win_a_pga_tour_major_re_earns_pga_from_the_recognizer(self):
        """RE-EARNS, not defaults — the conveyor's precondition for inverting.

        Asserted at the recognizer as well as the return value, because the
        default returns the same string and a return-value-only assertion
        cannot tell the two apart.
        """
        name, eid, _ = GOLFERS_MAJOR_2027
        assert classify(name, ext=[eid]) == "pga"
        assert _PGA_TOUR_NAME_RE.search(name), "the recognizer, not the default"
        # ...and the recognizer is actually WIRED IN. It and the default return
        # the same string today, so no input can tell them apart and a
        # return-value assertion cannot see the arm being deleted. Pinned at the
        # call site instead — narrowly, by name.
        assert "_PGA_TOUR_NAME_RE" in inspect.getsource(_classify_tour), (
            "the positive PGA recognizer is no longer consulted by _classify_tour; "
            "with the default still 'pga' nothing else in this file can notice"
        )

    def test_the_existing_name_patterns_still_win(self):
        assert classify("DP World Tour: Dubai Classic") == "dp_world"
        assert classify("LIV Golf Adelaide") == "liv"
        assert classify("Asian Tour: Hainan Open") == "asian"

    def test_the_womens_gate_still_precedes_everything(self):
        assert classify("LPGA: FM Championship Winner", ext=["KXDPWORLDTOUR-X26"]) == "lpga"

    def test_a_major_still_beats_every_new_arm(self):
        assert classify("Masters Winner?", key="masters", is_major=True,
                        ext=["KXDPWORLDTOUR-X26"]) == "major"


class TestWhatTheFixLetsIn:
    """A fix that WIDENS must be measured for what it admits."""

    def test_bmw_pga_championship_is_not_claimed_for_the_pga_tour(self):
        """THE control that matters.

        `BMW PGA Championship` (2026-09-17) and `BMW Australian PGA
        Championship` are DP World Tour events on the current DataGolf
        schedule. A bare `\\bpga\\b` recognizer would badge them PGA Tour.
        """
        for name in ("BMW PGA Championship", "BMW Australian PGA Championship"):
            assert not _PGA_TOUR_NAME_RE.search(name), (
                f"{name!r} is a DP WORLD TOUR event — the recognizer must not "
                "claim it. Requiring the full phrase 'PGA Tour' is the whole point."
            )

    def test_and_when_such_an_event_carries_the_dp_world_ticker_it_is_dp_world(self):
        assert classify("BMW PGA Championship Winner",
                        ext=["KXDPWORLDTOUR-BMWPGA26"]) == "dp_world"

    def test_the_ticker_arm_does_not_recognize_a_bare_kxpga_prefix(self):
        """`KXPGAAWARDS-*` is the Producers Guild of America, not golf."""
        assert not any(p == "KXPGA" for p, _ in _KALSHI_TOUR_TICKER_PREFIXES)
        name, eid, _ = PGA_AWARDS
        assert not any(
            eid.upper().startswith(p) for p, _ in _KALSHI_TOUR_TICKER_PREFIXES
        ), "the awards ticker must reach no tour arm"

    def test_the_prefix_is_a_prefix_not_an_exact_match(self):
        """Round-leader and make-cut series append to the tour token."""
        for eid in (
            "KXDPWORLDTOURR1LEAD-NEC26",
            "KXDPWORLDTOURR2LEAD-HUBMHBSNF26",
            "KXDPWORLDTOURMAKECUT-HUBMHBSNF26",
        ):
            assert classify("Some Round Leader", ext=[eid]) == "dp_world", eid

    def test_the_ticker_match_is_case_insensitive(self):
        """Kalshi serves uppercase, but nothing in the schema guarantees it."""
        assert classify("Some Winner", ext=["kxdpworldtour-omem26"]) == "dp_world"

    def test_nexo_and_fm_championship_are_the_other_rows_that_move(self):
        n, e, _ = NEXO_R1
        assert classify(n, ext=[e]) == "dp_world"
        n, e, _ = FM_CHAMPIONSHIP
        assert classify(n, ext=[e]) == "lpga"

    def test_id_anchored_evidence_outranks_the_name_recognizer(self):
        """Gotcha #32 / ruling 048: an id beats a name, never the other way."""
        assert classify("PGA Tour: Something Winner",
                        ext=["KXDPWORLDTOUR-X26"]) == "dp_world"

    @pytest.mark.parametrize("tour", [t for _, t in _KALSHI_TOUR_TICKER_PREFIXES])
    def test_every_ticker_prefix_maps_to_a_tour_that_can_be_displayed(self, tour):
        """A tour key with no display name renders as the raw key on the card."""
        assert tour in TOUR_DISPLAY_NAMES


class TestTheDefaultIsStillTheDefault:
    """This queue did NOT invert it. Pinned so the next queue's diff is honest."""

    def test_an_unrecognized_event_still_returns_pga(self):
        assert classify("Some Tournament Winner?") == "pga"
