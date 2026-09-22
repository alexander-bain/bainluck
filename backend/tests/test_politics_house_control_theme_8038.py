"""#8038 — the HOUSE CONTROL market must reach the congressional theme.

`/politics` published a Senate control card with no House card beside it, while
Kalshi `CONTROLH-2026` — *"Which party will win the U.S. House?"*, `volume_24h`
**982,211**, twenty-three times its Senate twin — sat in the payload classified
`"other"`.

The two faults are one fault seen twice:

* `_find_chamber_control` searches only `congressional_markets`, so a market
  outside that theme is invisible to it however well `_HOUSE_CONTROL_RE` reads;
* `_classify_theme` had no ticker arm for the `CONTROL[HS]-` family, so both
  chamber-control markets depended on `_THEME_BY_NAME`. `"…U.S. Senate?"`
  matches its `\\bsenate\\b` arm and arrived; `"…U.S. House?"` matches nothing
  and did not. The Senate card was working by luck, not by rule.

🔴 THE REFUSALS ARE THE DESIGN. The obvious repair — loosen the congressional
name arm from ``house\\s*(?:of\\s*rep|seat)`` to a bare ``\\bhouse\\b`` — is
what this file exists to forbid, and the reason was measured rather than
assumed. It is *not* "White House" (the presidential arm claims that two lines
earlier) and *not* "housing" (no word boundary). It is foreign and state
chambers: see
:meth:`TestTheNameRuleIsNotLoosened.test_the_literal_words_house_of_representatives_are_NOT_congressional`.

That alternative repair was run against this file as a mutation — ticker arm
deleted, name arm widened — and it fails four tests here including the one
above, so the claim is checked, not asserted.

The fix is therefore id-anchored — the ticker, where the English ambiguity that
caused the bug does not exist. :func:`test_house_control_is_found_too` in
``test_politics_chamber_control_8006.py`` already proves the extractor builds
the card once the market is in the pool, so what is proven here is the half
that was missing: that it gets into the pool at all.
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
    _find_chamber_control,
)


def _mk(external_id, name, outcomes=(("Democratic Party", 0.9075), ("Republican Party", 0.0925))):
    return SimpleNamespace(
        id=1,
        external_id=external_id,
        name=name,
        source="kalshi",
        mutually_exclusive=True,
        outcomes=[SimpleNamespace(name=n, current_probability=p) for n, p in outcomes],
    )


# --- the real rows, as production held them 2026-09-22 ---------------------

def _house_control():
    return _mk("CONTROLH-2026", "Which party will win the U.S. House?")


def _senate_control():
    return _mk("CONTROLS-2026", "Which party will win the U.S. Senate?",
               [("Democratic Party", 0.605), ("Republican Party", 0.395)])


class TestTheChamberControlFamilyIsCongressional:
    def test_the_house_control_market_is_congressional(self):
        """The whole ship: `CONTROLH-2026` was `"other"` and is now in the pool
        `_find_chamber_control` searches."""
        assert _classify_theme(_house_control()) == "congressional"

    def test_the_senate_control_market_is_congressional(self):
        assert _classify_theme(_senate_control()) == "congressional"

    def test_the_house_market_reaches_the_card_once_classified(self):
        """Classification and extraction joined up, which is what a reader sees:
        a HOUSE CONTROL card reading ~91% D."""
        market = _house_control()
        assert _classify_theme(market) == "congressional"

        control = _find_chamber_control([market])

        assert control["house"] is not None
        assert control["house"]["dem"] == pytest.approx(90.75, abs=0.5)
        assert control["house"]["gop"] == pytest.approx(9.25, abs=0.5)

    def test_the_ticker_arm_is_what_admits_the_house_market_not_its_name(self):
        """🔴 The load-bearing assertion.

        Both positives above would also pass on a widened name regex, so neither
        can tell the two repairs apart. This one can: the ticker is the family's
        and the NAME is deliberately one the congressional name arm refuses. If
        someone deletes the ticker arm and widens `_THEME_BY_NAME` instead, this
        is the test that goes red.
        """
        assert _classify_theme(_mk("CONTROLH-2026", "Chamber outcome, 2026")) == "congressional"

    def test_the_senate_twin_is_anchored_by_ticker_too(self):
        """`CONTROLS-2026` already reached the theme on the `\\bsenate\\b` name
        arm, so every other senate assertion here would survive deleting its
        ticker entry. This one would not: the name is one no arm of
        `_THEME_BY_NAME` matches, so only the ticker can carry it.

        Worth having because the Senate card's correctness currently depends on
        Kalshi keeping the word "Senate" in the title — the same single point of
        failure that cost us the House card.
        """
        assert _classify_theme(_mk("CONTROLS-2026", "Chamber outcome, 2026")) == "congressional"

    def test_a_name_the_ticker_arm_never_sees_is_unchanged(self):
        """The arm is additive: a market outside the family still classifies by
        name exactly as before, so this fix cannot be the cause of a later
        theme regression."""
        assert _classify_theme(_mk("KXGOV-26-TX", "Who will win the Texas Governor race?")) == "gubernatorial"


class TestTheNameRuleIsNotLoosened:
    """The ambiguity the ticker arm exists to avoid, asserted directly.

    Every row here contains the word "house" and none of them is a congressional
    race. A bare `\\bhouse\\b` arm in `_THEME_BY_NAME` turns all three red.
    """

    @pytest.mark.parametrize("name,expected", [
        ("Will Trump win the White House in 2028?", "presidential"),
        ("Who will be the next occupant of the White House?", "presidential"),
    ])
    def test_the_white_house_is_still_presidential(self, name, expected):
        assert _classify_theme(_mk("POLY-WH-1", name)) == expected

    def test_housing_is_not_a_congressional_race(self):
        assert _classify_theme(_mk("POLY-HS-1", "Will housing starts top 1.5M in 2026?")) != "congressional"

    def test_the_house_seat_phrasing_still_matches(self):
        """The narrow arm is kept, not merely left alone — these are the two
        phrasings it actually accepts and they must keep working."""
        assert _classify_theme(_mk("POLY-H-2", "Will the GOP gain a House seat?")) == "congressional"
        assert _classify_theme(_mk("POLY-H-3", "Which party wins the House of Rep?")) == "congressional"

    def test_the_unambiguous_congressional_words_still_match(self):
        """The arms this fix must not disturb, since the ticker entry is
        additive and sits ahead of all of them."""
        assert _classify_theme(_mk("POLY-S-1", "Will Democrats win the Senate?")) == "congressional"
        assert _classify_theme(_mk("POLY-C-1", "Who controls Congress after the midterms?")) == "congressional"

    def test_the_literal_words_house_of_representatives_are_NOT_congressional(self):
        """🔴 COUNTERINTUITIVE, MEASURED, AND DELIBERATELY PINNED HERE.

        `house\\s*(?:of\\s*rep|seat)` sits inside `\\b(?:…)\\b`, so `of Rep`
        followed by "resentatives" fails the trailing word boundary and the full
        phrase matches nothing. That reads like an obvious bug — it is why this
        test is written out rather than left as a silent gap — but the repair
        would be a regression, so the behaviour is pinned instead.

        Every open market naming that phrase on 2026-09-22 was measured, and not
        one is a US congressional race:

            Dutch House of Representatives dissolved in 2026?          polymarket
            2026 Nepal House of Representatives election               kalshi
            Texas House of Representatives winner                      kalshi
            Nigerian House of Representatives Election Winner          polymarket
            Malaysian House of Representatives dissolved by …          polymarket (x2)
            Will Republicans lose a seat in the House of Rep… in any
              state Trump won in 2024?                                 polymarket

        They are foreign chambers and one state legislature. `_THEME_BY_NAME`
        catches Dutch and Nigerian on its international arm, but it has **no
        Nepal and no Malaysia entry** — so widening this arm to `rep\\w*` would
        file a Nepali general election under US Congressional. The narrowness is
        load-bearing in the opposite direction from the one it first appears to
        fail in.

        If a genuine US market ever uses the full phrase, the fix is the same
        one this whole file argues for — anchor it by ticker, not by name.

        The same trailing boundary also drops the PLURAL "House seats" while
        accepting "a House seat". That one is pinned below as observed
        behaviour only: unlike the phrase above I did not census live rows for
        it, so it is recorded, not endorsed.
        """
        assert _classify_theme(_mk("POLY-H-1", "Which party wins the House of Representatives?")) != "congressional"
        assert _classify_theme(_mk("KXNEPALHOUSE-26MAR05", "Who will win the 2026 Nepal House of Representatives election?")) != "congressional"
        assert _classify_theme(_mk("POLY-H-4", "Will the GOP gain 5 House seats?")) != "congressional"


class TestThePrefixIsHyphenAnchored:
    """`CONTROLS` is an English word. Unhyphenated, it would claim any future
    `CONTROLSOMETHING-*` series for the congressional theme — a silent
    mis-classification nobody would think to look for."""

    @pytest.mark.parametrize("external_id", [
        "CONTROLSOMETHING-26",
        "CONTROLSTATE-26-TX",
    ])
    def test_a_lookalike_ticker_is_not_claimed(self, external_id):
        assert _classify_theme(_mk(external_id, "An unrelated question")) != "congressional"

    def test_the_registered_prefixes_carry_their_hyphen(self):
        """Read off the table itself, so deleting the hyphen in the source fails
        here rather than only in the lookalike test above."""
        assert {p for p, _ in _THEME_BY_TICKER_CLASSIFY_ONLY} == {"controlh-", "controls-"}

    def test_the_family_is_kept_out_of_the_query_table(self):
        """🔴 THE COST RATCHET, ASSERTED IN THE DIRECTION IT CAN ACTUALLY FAIL.

        `_THEME_BY_TICKER` has a SECOND consumer — the market-selection query
        spreads it as `external_id.like(f"{prefix.upper()}%")`, and those arms
        cannot use an index. `test_every_ticker_prefix_still_reaches_the_query`
        pins that table precisely because the scan is expensive.

        This family does not belong there: both rows carry
        `llm_sport_category = 'politics'` (measured on production 2026-09-22),
        so the category arm already fetches them and a LIKE arm would buy zero
        rows. The obvious way to write this fix — append to `_THEME_BY_TICKER`
        and bump the expected set — costs the cold build for nothing, so it is
        refused here rather than left to review.
        """
        assert not [p for p, _ in _THEME_BY_TICKER if p.startswith("control")]
