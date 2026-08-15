"""A bare matchup with no sport signal gets no sport (#1888).

The defect
----------
``_seasonal_sport_for_college_matchup()`` answered "what sport is
``Team A vs Team B``?" with the current month — basketball Feb–Apr, baseball
May–Jul, football Aug–Oct, None Nov–Jan. It was written for genuinely ambiguous
*college* matchups, where a month beats a shrug, but nothing downstream
restricted it to college. It became the terminal fallback for every unmapped
bare-matchup ticker on Kalshi, and its answer was written to
``llm_sport_category`` as persistent state.

#1109 fixed one victim (ITF tennis) by mapping its ticker prefix. This file
pins the general case Alex ruled on 2026-08-15: **honest-empty**.

The census that produced the ruling
-----------------------------------
Production, 2026-08-15, non-ITF unmapped bare-matchup families, 23,311 rows::

    created   basketball  baseball  football     guesser returns
    2026-02          650         3         1     basketball
    2026-03        1,935       136         2     basketball
    2026-04        2,391       157         8     basketball
    2026-05          328     1,278       146     baseball
    2026-06          142       789       285     baseball
    2026-07        3,369     6,062       878     baseball
    2026-08        1,481       916     2,354     football

The dominant tag in every month is exactly what the function returned that
month. The families underneath are soccer (Brasileirão, Liga MX, J-League,
UECL, Allsvenskan…), cricket (ODI, Test, The Hundred), ice hockey (IIHF, SHL),
squash, darts, table tennis, lacrosse and esports — none of them basketball,
baseball or football. The specimen that settles it: **KXWBCGAME, the World
Baseball Classic, is tagged ``basketball``**, because it was created in March.

Why the sweep
-------------
Gotcha #44: the defect IS the clock dependence. A single-month test passes on
the broken code for whichever month you happened to pick — and for three of
them (Nov–Jan) the broken code already returned None, so a test written in
December would have been green against the bug. Twelve months, always.
"""

from datetime import datetime, timezone

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.futures_categorization import _seasonal_sport_for_college_matchup

_ALL_MONTHS = list(range(1, 13))

#: The months where the shipped code returned a sport. These are the fails-first
#: cases — the other three (Nov–Jan) returned None already, so they prove
#: nothing on their own and are swept only to pin that they stay None.
_MONTHS_THAT_USED_TO_GUESS = {
    2: "basketball", 3: "basketball", 4: "basketball",
    5: "baseball", 6: "baseball", 7: "baseball",
    8: "football", 9: "football", 10: "football",
}

#: Real production specimens: unmapped Kalshi ticker families whose market name
#: is a bare matchup carrying no sport word. Every one of these was measured
#: holding a calendar-derived tag. None of them is a US college sport, which is
#: the population the guesser was written for.
_UNMAPPED_BARE_MATCHUPS = [
    ("KXODIMATCH-26AUG09INDAUS", "India vs Australia"),               # cricket
    ("KXSQUASHMATCH-26JUL10ELSFAR", "ElShorbagy vs Farag"),           # squash
    ("KXIIHFGAME-26MAY24FINSWE", "Finland vs Sweden"),                # ice hockey
    ("KXDARTSMATCH-26JUN24VANPRI", "van Gerwen vs Price"),            # darts
    ("KXWBCGAME-26MAR03USAJPN", "USA vs Japan"),                      # baseball!
]

#: Deliberately NOT in the list above. ``Flamengo vs Palmeiras`` is an unmapped
#: bare-matchup ticker too, but ``_is_soccer_matchup`` recognises both club
#: names and returns "soccer" BEFORE the guesser is reached — real name
#: evidence, stable in all twelve months. It sits in ``TestRealEvidenceStillWins``
#: because misfiling it here would have asserted that honest-empty should erase
#: a correct answer, which is the opposite of the ruling.
_NAME_EVIDENCE_MATCHUP = ("KXBRASILEIROGAME-26AUG09FLAPAL", "Flamengo vs Palmeiras")


class _FrozenDatetime(datetime):
    """`datetime` with `now()` pinned. Subclassed so `isinstance` still holds."""

    _frozen: datetime

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - stdlib signature
        return cls._frozen if tz is None else cls._frozen.astimezone(tz)


@pytest.fixture
def freeze_month(monkeypatch):
    """Pin the classifier's clock to a given month, UTC.

    Offset-free by construction (gotcha #44): the month is the input under
    test, not an age derived from the wall clock, so there is no anchor here to
    drift. The clock is still frozen OUT of the test rather than read from it —
    a sweep that reads ``now()`` would test one month and claim twelve.
    """

    def _freeze(month: int):
        frozen = type(
            "_Frozen",
            (_FrozenDatetime,),
            {"_frozen": datetime(2026, month, 15, 12, 0, tzinfo=timezone.utc)},
        )
        monkeypatch.setattr("app.utils.futures_categorization.datetime", frozen)

    return _freeze


class TestTheGuesserIsGone:
    """The function keeps its signature and callers; it just has no answer."""

    @pytest.mark.parametrize("month", _ALL_MONTHS)
    def test_it_returns_none_in_every_month(self, freeze_month, month):
        """Fails-first in nine of twelve months on the shipped code.

        Recorded because it bounds what this sweep proves: run only in
        November, this assertion was green against the bug.
        """
        freeze_month(month)
        assert _seasonal_sport_for_college_matchup() is None, (
            f"month {month} still produces a sport "
            f"(shipped code: {_MONTHS_THAT_USED_TO_GUESS.get(month)!r}). "
            "A bare matchup with no sport signal has no sport — it lands in "
            "'other' until real evidence arrives (#1888)."
        )

    def test_the_answer_is_identical_across_the_whole_clock(self, freeze_month):
        """The property, stated directly rather than inferred from 12 rows.

        The bug was never "wrong in August" — it was "answers from the
        calendar". A classifier whose output varies with the month it is
        called in cannot be written to persistent state, whatever it returns.
        """
        answers = set()
        for month in _ALL_MONTHS:
            freeze_month(month)
            answers.add(_seasonal_sport_for_college_matchup())
        assert answers == {None}, f"clock-dependent: {answers}"


class TestTheUnmappedMarketsLandInOther:
    """End-to-end through the real cascade, not just the leaf function."""

    @pytest.mark.parametrize("month", _ALL_MONTHS)
    @pytest.mark.parametrize("ticker,name", _UNMAPPED_BARE_MATCHUPS)
    def test_an_unmapped_bare_matchup_is_other_in_every_month(
        self, freeze_month, month, ticker, name
    ):
        """"other" is the honest answer, and it is a STABLE one.

        The value matters less than the invariance: whatever these rows are
        tagged, they must be tagged the same thing in March and in September,
        because nothing about the market changed between them.
        """
        freeze_month(month)
        assert _categorize_kalshi_market(name, None, ticker) == "other", (
            f"{ticker!r} in month {month} was given a sport by the calendar. "
            "This family has no ticker mapping and no sport word in its name; "
            "the only signal available is the clock, and the clock is not "
            "evidence."
        )

    @pytest.mark.parametrize("ticker,name", _UNMAPPED_BARE_MATCHUPS)
    def test_the_tag_cannot_migrate_across_months(
        self, freeze_month, ticker, name
    ):
        """The re-stamp defect, stated as the property it violated.

        ``tasks/kalshi.py`` re-stamps ``llm_sport_category`` on every upsert, so
        a classifier that varies by month rewrites history: a July row created
        "baseball" became "football" on its next August poll, with no code
        change and no new information. Pinning single months would not catch
        that; pinning that all months AGREE does.
        """
        seen = set()
        for month in _ALL_MONTHS:
            freeze_month(month)
            seen.add(_categorize_kalshi_market(name, None, ticker))
        assert len(seen) == 1, (
            f"{ticker!r} is classified {len(seen)} different ways across the "
            f"year ({sorted(seen)}) — the tag migrates on re-poll."
        )


class TestRealEvidenceStillWins:
    """Honest-empty must not become honest-deaf."""

    def test_a_mapped_ticker_is_unaffected(self):
        """Step 1 is authoritative and must stay that way.

        ITF is the case in point: #1109 fixed it by GROWING THE TICKER MAP, and
        that fix has to keep working after the guesser is emptied — otherwise
        this change would quietly re-break the issue it builds on.
        """
        assert (
            _categorize_kalshi_market("Velcz vs Kimhi", None, "KXITFMATCH-26JUL19VELKIM")
            == "tennis"
        )

    def test_a_name_that_names_its_sport_is_unaffected(self):
        """Step 2 (the rules engine) runs before the guesser and is untouched."""
        assert (
            _categorize_kalshi_market(
                "Yankees vs Red Sox: Total Runs O/U 8.5", None, "KXUNKNOWNFAM-26AUG09"
            )
            == "baseball"
        )

    @pytest.mark.parametrize("month", _ALL_MONTHS)
    def test_recognised_club_names_still_resolve_without_a_ticker_mapping(
        self, freeze_month, month
    ):
        """The narrow case honest-empty must NOT swallow.

        ``_is_soccer_matchup`` reads the team names and is consulted before the
        guesser, so an unmapped Brasileirão fixture resolves on evidence rather
        than on the calendar — and resolves to the same thing in every month.
        This is the shape every future rescue of the "other" pile should take:
        add a signal, not a default.
        """
        ticker, name = _NAME_EVIDENCE_MATCHUP
        freeze_month(month)
        assert _categorize_kalshi_market(name, None, ticker) == "soccer"


class TestTheUpsertDoesNotRestampASportTag:
    """#1888(c) — kill the migration independently of the guesser.

    Scope, stated honestly: the sharded ``backend-tests`` job has no Postgres
    service, so this cannot round-trip a real upsert and assert the stored tag
    after a second poll. What it pins is the SHAPE of the SET clause, which is
    where the defect lived — an unconditional assignment. A behavioural version
    of this belongs with the real-Postgres contract tests if the SET clause
    ever grows a third writer.
    """

    def _set_clause_source(self) -> str:
        """The SET clause as CODE — comments stripped before matching.

        House standard, and it earned its place here on the first run: the
        commit that fixed the re-stamp also documented it, and the docs quote
        the broken line verbatim ("this line used to read
        ``update_set[...] = sport_category``"). A raw ``inspect.getsource``
        search found that sentence first and reported the fix missing. A guard
        that reads prose cannot tell a fix from a description of the bug it
        fixed — and it fails in the dangerous direction too, since a comment
        mentioning ``coalesce`` would satisfy it over code that does not.

        Unlike the ``_executable_text`` helper in
        ``test_admin_query_rail_retired.py``, STRING tokens are KEPT: the
        ``"other"`` sentinel is the invariant under test, not incidental text.
        """
        import inspect
        import io
        import tokenize

        from app.tasks import kalshi

        kept = [
            tok.string
            for tok in tokenize.generate_tokens(
                io.StringIO(inspect.getsource(kalshi)).readline
            )
            if tok.type != tokenize.COMMENT
        ]
        # Whitespace removed entirely: tokenizing re-spaces the source
        # (`FuturesMarket . llm_sport_category`), so matching on how the code is
        # FORMATTED would make this guard fail on a reflow that changes nothing.
        code = "".join("".join(kept).split())

        marker = 'update_set["llm_sport_category"]='
        assert marker in code, (
            "the llm_sport_category SET clause has moved or been renamed — "
            "this guard is now vacuous and must be re-pointed, not deleted"
        )
        start = code.index(marker)
        return code[start : start + 200]

    def test_the_existing_value_is_read_before_it_is_written(self):
        """The invariant: a tag is written once, by evidence, or not at all."""
        clause = self._set_clause_source()
        assert "coalesce" in clause and "FuturesMarket.llm_sport_category" in clause, (
            "the upsert assigns llm_sport_category without consulting the "
            "existing value. That is the re-stamp: every poll overwrites the "
            "stored tag with a freshly computed one, so any repair backfill is "
            "self-undoing for still-open rows (#1888)."
        )

    def test_other_is_the_one_value_that_can_be_upgraded(self):
        """Honest-empty is a landing state, not a verdict.

        Without the ``nullif``, a row parked in "other" could never be fixed by
        the ticker map growing a prefix — which is exactly how ITF was
        repaired. The door has to stay open in that one direction.
        """
        clause = self._set_clause_source()
        assert 'nullif' in clause and '"other"' in clause, (
            "'other' is not treated as empty, so real evidence arriving later "
            "cannot upgrade a parked row."
        )
