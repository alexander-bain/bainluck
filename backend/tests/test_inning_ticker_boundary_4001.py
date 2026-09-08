"""#4001 — `INNING` is a ticker SEGMENT, not a substring to go looking for.

#3992 gave `_classify_from_ticker` a fallback so a per-inning market is
period-scoped even when its name carries no marker:

    if "inning" in ticker_lower:
        if "total" in ticker_lower:  return "inning_total"
        ...

`"inning"` was tested as a bare substring, and **`KXPGAWINNINGSCORE` contains
it** — `kxpgaw·inning·score`. So golf's Winning Score classified `inning_winner`:
a baseball period, on a golf market. `inning_winner` is in `_PM_PERIOD_SCOPES`,
so such a market is dropped from the projection pool outright and no longer takes
the `moneyline` path in `_build_game_markets`.

**Reach on the day it was found was zero, and that is why #3992 was right to
ship**: 4 `KXPGAWINNINGSCORE` markets existed and NONE was linked to an event,
while both classifier call sites read event-linked markets only. The cert bus
graded it a nonblocking follow-up on CERT-2271 for exactly that reason. It
becomes reachable the moment one of those four is linked, and it would then be a
*silent* wrong answer on a golf page rather than a loud one.

The fix is the construction the half and quarter tickers already use: explicit
prefixes in `_TICKER_PERIOD_MAP`, matched with `startswith`. A prefix table
cannot collide this way — `kxpgawinningscore` does not START with
`kxmlbinning…`.

The NAME path never had this bug and is asserted here anyway, because it is the
thing that makes the two halves independent: `_SINGLE_INNING_RE` is
`\\binning\\b`, and the "w" in "winning" is a word character, so the opening
boundary fails.

Ticker roots are production's, measured 2026-09-08: `KXMLBINNINGTOTAL` and
`KXMLBINNINGWIN` (1,170 markets each, 117 linked) are the only inning roots that
exist, plus the 4 unlinked `KXPGAWINNINGSCORE`.
"""

import pytest

from app.routes.events import (
    _PM_PERIOD_SCOPES,
    _SINGLE_INNING_RE,
    _TICKER_PERIOD_MAP,
    _classify_from_ticker,
    _classify_game_market,
)

#: The collision, verbatim from production.
GOLF_WINNING_SCORE = "KXPGAWINNINGSCORE-26-X"


class TestGolfIsNotAnInning:
    def test_the_winning_score_ticker_is_not_a_period(self):
        """🔴 #4001's acceptance, in one line."""
        assert _classify_game_market("Winning Score", GOLF_WINNING_SCORE) == "moneyline"

    def test_the_ticker_alone_never_answers_inning(self):
        got = _classify_from_ticker(GOLF_WINNING_SCORE)
        assert got not in _PM_PERIOD_SCOPES, (
            f"{GOLF_WINNING_SCORE} classified {got!r} — a golf market wearing a "
            "baseball period is dropped from the projection pool"
        )
        assert not got.startswith("inning_")

    @pytest.mark.parametrize(
        "ticker",
        [
            # The shape of the bug, not just the one instance: any ticker whose
            # league segment ENDS in "w" puts an "inning" inside "winning".
            "KXPGAWINNINGSCORE-26-X",
            "KXLPGAWINNINGSCORE-26-X",
            "KXPGAWINNINGMARGIN-26-X",
        ],
    )
    def test_no_w_plus_inning_ticker_is_ever_an_inning(self, ticker):
        assert not _classify_from_ticker(ticker).startswith("inning_")


class TestTheRealInningTickersStillWork:
    """#3992's behaviour, re-asserted from this side of the change. If the
    prefix table missed a root, these are what go red."""

    @pytest.mark.parametrize("inning", range(1, 10))
    def test_every_inning_total_ticker(self, inning):
        ticker = f"KXMLBINNINGTOTAL-26SEP081840NYMMIA-{inning}"
        assert _classify_from_ticker(ticker) == "inning_total"
        assert _classify_game_market("New York M vs Miami", ticker) == "inning_total"

    @pytest.mark.parametrize("inning", range(1, 10))
    def test_every_inning_winner_ticker(self, inning):
        """🔴 Kalshi truncates this root: `…INNINGWIN`, not `…INNINGWINNER`.
        A prefix table written from the half/quarter pattern alone would spell
        it `kxmlbinningwinner` and silently match nothing."""
        ticker = f"KXMLBINNINGWIN-26SEP081840NYMMIA-{inning}"
        assert _classify_from_ticker(ticker) == "inning_winner"
        assert _classify_game_market("New York M vs Miami", ticker) == "inning_winner"

    def test_the_inning_labels_are_still_periods(self):
        for label in ("inning_total", "inning_spread", "inning_winner"):
            assert label in _PM_PERIOD_SCOPES

    def test_the_prefix_table_carries_the_inning_roots(self):
        """Named on the table rather than only through the classifier, so that
        deleting an entry is what fails rather than some downstream default."""
        assert _TICKER_PERIOD_MAP["kxmlbinningtotal"] == "inning_total"
        assert _TICKER_PERIOD_MAP["kxmlbinningwin"] == "inning_winner"
        assert _TICKER_PERIOD_MAP["kxmlbinningspread"] == "inning_spread"


class TestTheNamePathWasNeverTheProblem:
    """Asserted with the TICKER absent, so the two paths cannot cover for each
    other — the failure mode #3992's own cert review named."""

    def test_the_word_boundary_holds_against_winning(self):
        assert _SINGLE_INNING_RE.search("winning score") is None
        assert _SINGLE_INNING_RE.search("2nd inning total") is not None

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Winning Score", "moneyline"),
            ("Winning Margin", "spread"),
            ("New York M vs Miami: 2nd Inning Total", "inning_total"),
            # #3951's plural still outranks nothing and stays half-game.
            ("New York M vs Miami: First 5 Innings Total", "half_total"),
        ],
    )
    def test_the_name_decides_with_no_ticker_at_all(self, name, expected):
        assert _classify_game_market(name, None) == expected


class TestTheOtherPeriodTickersDoNotMove:
    @pytest.mark.parametrize(
        "ticker,expected",
        [
            ("KXNBA2HSPREAD-26X", "half_spread"),
            ("KXNFL1HTOTAL-26X", "half_total"),
            ("KXNBA3QWINNER-26X", "quarter_winner"),
            ("KXMLB1HTOTAL-26X", "half_total"),
            # The base types the catch-alls still answer.
            ("KXMLBTOTAL-26SEP08NYMMIA", "game_total"),
            ("KXMLBSPREAD-26SEP08NYMMIA", "spread"),
        ],
    )
    def test_unchanged(self, ticker, expected):
        assert _classify_from_ticker(ticker) == expected
