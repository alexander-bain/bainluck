"""ITF tennis must not be tagged by the calendar (#1109).

The defect
----------
``_categorize_kalshi_market`` resolves a ticker prefix first, and that step is
described in its own docstring as authoritative — "ticker never lies". ATP and
WTA prefixes were mapped from the start. **ITF never was.**

An ITF market name is a bare matchup — ``"Velcz vs Kimhi"`` — with no sport word
in it. With step 1 returning nothing, the cascade fell through to the name rules
and reached ``_seasonal_sport_for_college_matchup()``, which guesses a sport
**from the current month**: basketball Feb–Apr, baseball May–Jul, football
Aug–Oct, nothing Nov–Jan. It was written for genuinely ambiguous college
matchups, where a month is better than a shrug. Applied to a tennis market it is
simply wrong twelve times a year, in four different directions.

Measured in production 2026-08-15, 25,073 ITF markets:

    correct tennis     808   ( 3.2%)
    as baseball     13,335
    as football      7,128
    as basketball    3,431
    ---------------------------------
    mis-tagged      24,265   (96.8%)

By creation month the fingerprint is exact — 2026-04 basketball 3,403, 2026-05
baseball 2,855, 2026-07 baseball 9,827, 2026-08 football 2,071. That is the
calendar, not the sport.

Two consequences worth naming, because they change what a fix has to do:

* **The tag MIGRATES.** ``tasks/kalshi.py`` re-stamps ``llm_sport_category`` on
  every upsert, so an ITF row created in July as baseball becomes football when
  re-polled in August. A backfill that runs before the writer is fixed is
  self-undoing for every still-open row.
* **The calibration curves eat it.** Football's curve was the reported symptom,
  but baseball's slice is nearly twice as large and no issue tracked it.

What this file pins
-------------------
The writer, across the whole clock. A single-month test would pass on the broken
code for eight months of the year, which is the shape of gotcha #44 — the defect
IS the clock dependence, so the guard has to sweep the clock rather than pick a
convenient hour to stand on.
"""

from datetime import datetime, timezone

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.sport_keys import (
    KALSHI_TICKER_TO_SPORT_KEY,
    LLM_CATEGORY_TO_SPORT_KEYS,
    get_sport_key_from_ticker,
)

#: Real production specimens: the four ITF ticker families and the bare-matchup
#: names that carry no sport word for the rules engine to find.
_ITF_SPECIMENS = [
    ("KXITFMATCH-26JUL19VELKIM", "Velcz vs Kimhi", "tennis_itf"),
    ("KXITFWMATCH-26AUG02SMIJON", "Smitkova vs Jones", "tennis_itf_w"),
    ("KXITFDOUBLES-26JUL19VELKIM", "Velcz/Kimhi vs Adams/Brown", "tennis_itf"),
    ("KXITFWDOUBLES-26AUG02SMIJON", "Smitkova/Jones vs Diaz/Ruiz", "tennis_itf_w"),
]

#: The four seasons the guesser has. Every month is swept anyway; these are the
#: boundaries where the old behaviour changed answer.
_ALL_MONTHS = list(range(1, 13))


class _FrozenDatetime(datetime):
    """`datetime` with `now()` pinned. Subclassed so `isinstance` still holds."""

    _frozen: datetime

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - stdlib signature
        return cls._frozen if tz is None else cls._frozen.astimezone(tz)


@pytest.fixture
def freeze_month(monkeypatch):
    """Pin the classifier's clock to a given month, UTC.

    Offset-free by construction: the month is the input under test, not a
    derived age, so there is nothing here for gotcha #44's "offset first, then
    truncate" rule to protect — but the clock is still frozen OUT of the test
    rather than read from it.
    """

    def _freeze(month: int):
        frozen = type(
            "_Frozen",
            (_FrozenDatetime,),
            {"_frozen": datetime(2026, month, 15, 12, 0, tzinfo=timezone.utc)},
        )
        monkeypatch.setattr(
            "app.utils.futures_categorization.datetime", frozen
        )

    return _freeze


class TestTheTickerMapping:
    """Step 1 must resolve, because that is what short-circuits the guesser."""

    @pytest.mark.parametrize("ticker,_name,expected_key", _ITF_SPECIMENS)
    def test_every_itf_family_resolves_to_a_tennis_sport_key(
        self, ticker, _name, expected_key
    ):
        assert get_sport_key_from_ticker(ticker) == expected_key

    def test_itf_is_its_own_tour_not_folded_into_atp_or_wta(self):
        """Folding ITF into ATP/WTA would trade a visible bug for a quiet one.

        An ITF women's qualifier surfacing as a WTA match is still a false
        claim about the world; it is merely one nobody would file.
        """
        itf_keys = {
            v for k, v in KALSHI_TICKER_TO_SPORT_KEY.items() if k.startswith("kxitf")
        }
        assert itf_keys == {"tennis_itf", "tennis_itf_w"}

    def test_the_new_keys_are_reachable_from_the_tennis_category(self):
        """Otherwise a tennis-category lookup silently omits the ITF rows."""
        for key in ("tennis_itf", "tennis_itf_w"):
            assert key in LLM_CATEGORY_TO_SPORT_KEYS["tennis"]

    def test_the_prefix_resolves_to_the_tennis_llm_category(self):
        """Step 1 keys on `sport_key.split('_')[0]`, so the prefix is the
        contract — a key like `itf_tennis` would resolve to nothing."""
        from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

        for key in ("tennis_itf", "tennis_itf_w"):
            assert SPORT_PREFIX_TO_LLM_CATEGORY[key.split("_")[0]] == "tennis"


class TestTheBleedIsStopped:
    """The specimen, swept across the clock that caused it."""

    @pytest.mark.parametrize("month", _ALL_MONTHS)
    @pytest.mark.parametrize("ticker,name,_key", _ITF_SPECIMENS)
    def test_an_itf_market_is_tennis_in_every_month_of_the_year(
        self, freeze_month, month, ticker, name, _key
    ):
        """The fails-first case, twelve times over.

        On the shipped code this returns basketball in Feb–Apr, baseball in
        May–Jul, football in Aug–Oct and 'other' in Nov–Jan. Four wrong answers
        and not one of them tennis.
        """
        freeze_month(month)
        assert _categorize_kalshi_market(name, None, ticker) == "tennis", (
            f"ITF market {ticker!r} tagged wrongly in month {month}. The ticker "
            "is authoritative at step 1 precisely so the month never gets a "
            "vote on a sport we already know."
        )

    @pytest.mark.parametrize("month", _ALL_MONTHS)
    def test_the_answer_does_not_depend_on_the_month_at_all(
        self, freeze_month, month
    ):
        """Stated as invariance rather than as twelve equalities.

        The defect was never 'football is wrong' — it was that the answer moved.
        A fix that pinned August to tennis and left the rest to the guesser
        would satisfy the test above only if it were written per-month, so the
        property gets asserted directly.
        """
        freeze_month(month)
        answers = {
            _categorize_kalshi_market(name, None, ticker)
            for ticker, name, _ in _ITF_SPECIMENS
        }
        assert answers == {"tennis"}


class TestTheGuesserIsStillThereForWhatItWasWrittenFor:
    """Scope control: this fix routes ITF around the guesser, it does not
    delete it. A genuinely ambiguous college matchup still gets a month-based
    answer, which is the behaviour it was written for and is not in scope here.

    Recorded rather than silently assumed, because the wider defect — a
    clock-dependent classifier writing PERSISTENT state, for ANY unmapped
    bare-matchup ticker — is real and outlives this issue.
    """

    def test_the_seasonal_inference_no_longer_answers_at_all(
        self, freeze_month
    ):
        """SUPERSEDED 2026-08-15 by Alex's honest-empty ruling (#1888).

        This test used to assert the opposite — that a college matchup still
        got a month-based answer — on the scope note above: #1109 routed ITF
        *around* the guesser rather than deleting it, and the guesser's
        original behaviour was deliberately left in place as out of scope.

        The wider defect that note names ("a clock-dependent classifier writing
        PERSISTENT state, for ANY unmapped bare-matchup ticker") was then
        measured: 23,311 non-ITF rows across soccer, cricket, ice hockey,
        squash, darts, table tennis, lacrosse and esports, each carrying
        whichever sport the calendar was on when they were created. Alex ruled
        honest-empty — the function returns None always, and unmapped bare
        matchups land in "other" until real evidence arrives.

        Kept as a pointer rather than deleted: this is the exact assertion a
        future reader would otherwise re-add, believing they were restoring a
        feature. The full guard is ``test_seasonal_sport_guess_honest_empty``.
        """
        from app.utils.futures_categorization import (
            _seasonal_sport_for_college_matchup,
        )

        for month in (3, 9, 12):
            freeze_month(month)
            assert _seasonal_sport_for_college_matchup() is None
