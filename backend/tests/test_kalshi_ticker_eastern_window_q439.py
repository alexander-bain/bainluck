"""Q439 (#2214) — a Kalshi game ticker's clock is US EASTERN, on every rail.

## The defect, in one sentence

``prediction_market_matching`` holds **two** answers to the question *"is this
ticker's game the same game as this event?"* — one that converts the ticker's
Eastern wall clock to UTC and one that does not — and the LINK is decided by the
correct one while the UNLINK is decided by the wrong one.

## Measured on production, 2026-08-29

``GET /api/admin/prediction-markets/match-trace?external_id=KXMLBGAME-26AUG291610KCCLE``::

    extraction.ticker_date : 2026-08-29T16:10:00+00:00     <- 16:10 ET, labelled UTC
    time_window            : 13:10Z .. 19:10Z              <- +/-3h around the wrong centre
    candidates             : []
    (the real event, Guardians vs Royals, commences 2026-08-29T20:10:00Z)

Kalshi's own market rules for that ticker say *"the Kansas City vs Cleveland
professional baseball game originally scheduled for **Aug 29, 2026 at 4:10 PM
EDT**"*. 4:10 PM EDT is 20:10 UTC. The ticker's ``1610`` is Eastern; every rail
that reads it as UTC is 4h (EDT) or 5h (EST) wrong — always outside the +/-3h
same-game window, in every month of the year.

Consequences measured the same day:

* every one of the **44** open ``KXMLBGAME`` rows had ``event_id IS NULL``,
  while the ticker-date cohorts that had already resolved were 90-100% linked —
  the live matcher never lands the link, the settled backfill does it later;
* **45 of 48** MLB games commencing in the next 36h carried no ``kalshi`` key in
  ``win_probability_sources``, so the game card showed no Kalshi price;
* the same class holds for the date-only arm: **44/44** open ``KXMLSGAME`` rows
  unlinked, because a midnight-anchored date-only ticker sits ~24h from an
  evening kickoff's UTC commence and the old +/-18h rule called that a different
  game.

## Why the fix is a deletion and not a second correction

The Eastern correction already exists in this module.
``_ticker_date_conflicts_with_event`` was given it by #1811, whose block comment
states the measurement outright: *"ticker HHMM read as UTC -> modal delta is -4h
(i.e. OUTSIDE the +/-3h window); the helper's rule would refuse 98.0% of
currently-linked MLB markets"*. #1811 fixed the arm it was looking at and left
the two unlink arms on the uncorrected helper. So the repository wrote down the
exact failure rate of the code it was leaving in place.

Ruling 048's clause — *two matchers that disagree is what this exists to end* —
applies to a matcher and its inverse just as much as to two matchers. There is
one question here, so there is one function.
"""

import ast
import inspect
import re
import textwrap
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import prediction_market_matching as pmm
from app.tasks.prediction_market_matching import (
    _find_matching_event,
    _kalshi_prefix,
    _match_prediction_markets,
    _ticker_date_conflicts_with_event,
    WRONG_GAME_PREFIXES,
)
from app.utils.prediction_market_matching import extract_game_date_from_ticker

UTC = timezone.utc


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


# Real production rows, 2026-08-29. (ticker, event commence UTC, why it is the
# same game). Every one of these is a link the live matcher refused.
SAME_GAME_ROWS = [
    # MLB, EDT (UTC-4). Kalshi's own rules text names the ET start.
    ("KXMLBGAME-26AUG291610KCCLE", _dt(2026, 8, 29, 20, 10), "16:10 EDT = 20:10Z"),
    ("KXMLBGAME-26AUG291310LADDET", _dt(2026, 8, 29, 17, 10), "13:10 EDT = 17:10Z"),
    ("KXMLBGAME-26AUG292205BALATH", _dt(2026, 8, 30, 2, 5), "22:05 EDT = 02:05Z next day"),
    # A doubleheader's two halves, each on its own event.
    ("KXMLBGAME-26AUG291305BOSNYYG1", _dt(2026, 8, 29, 17, 5), "game 1, 13:05 EDT"),
    ("KXMLBGAME-26AUG291915BOSNYYG2", _dt(2026, 8, 29, 23, 15), "game 2, 19:15 EDT"),
    # EST (UTC-5) — the offset is 5h in winter, still outside +/-3h.
    ("KXNBAGAME-26JAN151930BOSNYK", _dt(2026, 1, 16, 0, 30), "19:30 EST = 00:30Z next day"),
    # Date-only ticker, evening kickoff: ~24h apart in UTC, same Eastern day.
    ("KXMLSGAME-26AUG29ATLCLT", _dt(2026, 8, 30, 0, 30), "20:30 EDT Aug 29 = 00:30Z Aug 30"),
]


class TestOneQuestionOneAnswer:
    """There must not be a second, disagreeing decider in this module."""

    def test_no_uncorrected_helper_survives_alongside_the_corrected_one(self):
        far = getattr(pmm, "_ticker_date_far_from_event", None)
        if far is None:
            return  # deleted — the contradiction cannot exist
        disagreements = []
        for ticker, commence, why in SAME_GAME_ROWS:
            td = extract_game_date_from_ticker(ticker)
            prefix = _kalshi_prefix(ticker)
            if far(td, commence) != _ticker_date_conflicts_with_event(td, commence, prefix):
                disagreements.append(f"{ticker} ({why})")
        assert not disagreements, (
            "two functions in one module answer 'same game?' differently for "
            "these production rows, and the LINK path uses one while the UNLINK "
            "path uses the other:\n  " + "\n  ".join(disagreements)
        )

    @staticmethod
    def _calls_in(func):
        """Every function CALL made inside ``func``, by name, from the AST.

        Deliberately not a substring scan: a comment that merely names the old
        helper must not read as a call site, and a call site must not be able to
        hide behind one.
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name:
                    out.append((name, node))
        return out

    def test_the_unlink_arms_are_wired_to_the_corrected_decider(self):
        # Q438's lesson, applied: a rule with a correct implementation and no
        # consumer is a document. Assert the CALL SITE, not just the function.
        names = [n for n, _ in self._calls_in(_match_prediction_markets)]
        assert "_ticker_date_far_from_event" not in names, (
            "the Phase-2 wrong-game unlink and the Phase-2 date-mismatch unlink "
            "still decide with the helper that reads the ticker's Eastern clock "
            "as UTC — the arm that unlinks must use the same rule as the arm "
            "that links"
        )
        assert names.count("_ticker_date_conflicts_with_event") >= 2, (
            "both Phase-2 unlink arms must decide with the corrected rule; "
            f"found {names.count('_ticker_date_conflicts_with_event')} call site(s)"
        )

    def test_the_unlink_arms_pass_the_ticker_prefix(self):
        # The corrected decider is prefix-aware (esports carries a measured
        # +/-12h window). Passing "" would silently collapse esports to +/-3h.
        calls = [
            node for name, node in self._calls_in(_match_prediction_markets)
            if name == "_ticker_date_conflicts_with_event"
        ]
        assert calls, "no call site found"
        for node in calls:
            positional = len(node.args)
            keyword = {kw.arg for kw in node.keywords}
            assert positional >= 3 or "prefix" in keyword, (
                "the prefix argument is missing, so esports silently loses its "
                "measured +/-12h window and falls back to +/-3h"
            )
            third = node.args[2] if positional >= 3 else None
            if isinstance(third, ast.Constant):
                assert third.value not in ("", None), "empty prefix passed"


class TestTheTickerClockIsEastern:
    def test_every_production_row_reads_as_the_same_game(self):
        wrong = []
        for ticker, commence, why in SAME_GAME_ROWS:
            td = extract_game_date_from_ticker(ticker)
            if _ticker_date_conflicts_with_event(td, commence, _kalshi_prefix(ticker)):
                wrong.append(f"{ticker} vs {commence.isoformat()} ({why})")
        assert not wrong, "refused a link the provider's own rules text confirms:\n  " + "\n  ".join(wrong)

    def test_doubleheader_halves_still_separate(self):
        # The +/-3h window exists to keep the two halves apart. Correcting the
        # timezone must not cost that: game 1's ticker must still refuse game
        # 2's event.
        g1 = extract_game_date_from_ticker("KXMLBGAME-26AUG291305BOSNYYG1")
        g2_event = _dt(2026, 8, 29, 23, 15)
        assert _ticker_date_conflicts_with_event(g1, g2_event, "kxmlbgame") is True

    def test_a_genuinely_different_day_is_still_refused(self):
        td = extract_game_date_from_ticker("KXMLBGAME-26AUG291610KCCLE")
        assert _ticker_date_conflicts_with_event(td, _dt(2026, 9, 2, 20, 10), "kxmlbgame") is True

    def test_every_wrong_game_prefix_is_decided_by_the_corrected_rule(self):
        # WRONG_GAME_PREFIXES is the unlink arm's allowlist. Its members are the
        # population this defect silently emptied.
        assert {"kxmlbgame", "kxmlsgame", "kxnflgame", "kxnbagame", "kxnhlgame"} <= WRONG_GAME_PREFIXES


class TestTheCandidateSearchWindowIsCentredOnTheRealStart:
    """The trace's ``candidates: []`` half — the +/-3h window itself."""

    @staticmethod
    def _window_of(statement):
        """The two timestamp literals the compiled SELECT windows on."""
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        stamp = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?"
        m = re.search(
            rf"commence_time BETWEEN '({stamp})' AND '({stamp})'", sql
        )
        assert m, f"no commence_time BETWEEN window in:\n{sql}"

        def _utc(s):
            d = datetime.fromisoformat(s)
            return d.astimezone(UTC) if d.tzinfo else d.replace(tzinfo=UTC)

        return _utc(m.group(1)), _utc(m.group(2))

    @pytest.mark.asyncio
    async def test_pass1_window_contains_the_real_event(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        captured = []

        class _Spy:
            async def execute(self, statement):
                captured.append(statement)
                result = MagicMock()
                result.scalars.return_value.unique.return_value.all.return_value = []
                return result

        ticker = "KXMLBGAME-26AUG291610KCCLE"
        market = SimpleNamespace(
            id=1, source="kalshi", external_id=ticker,
            name="Kansas City vs Cleveland",
            commence_time=_dt(2026, 9, 1, 20, 10),  # Kalshi's close_time, 3d late
            llm_sport_category="baseball",
        )
        matchup = SimpleNamespace(
            team_a="Royals", team_b="Guardians", format_type="ticker_parsed",
        )
        await _find_matching_event(
            _Spy(), matchup, market, _dt(2026, 8, 29, 15, 0),
            game_date_override=extract_game_date_from_ticker(ticker),
        )

        start, end = self._window_of(captured[0])
        real_commence = _dt(2026, 8, 29, 20, 10)
        assert start <= real_commence <= end, (
            f"the +/-3h candidate window is {start.isoformat()}..{end.isoformat()}, "
            f"which excludes the game it is looking for ({real_commence.isoformat()}). "
            "The window is centred on the ticker's Eastern clock read as UTC."
        )
        # Still tight: correcting the centre must not widen the window.
        assert (end - start) <= timedelta(hours=6, minutes=1)
