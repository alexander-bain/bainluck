"""The futures NAME arm keeps BOTH halves — stemmed FTS and substring ILIKE.

WHY THIS FILE EXISTS (LAT-P096, #1866).

`/api/events/typeahead` spends 89-91% of a cold request in `futures_query`
(measured on production 2026-08-26: 3,628/3,991, 3,510/3,913, 3,665/4,113 ms via
`?debug_timing=1`). The dominant clause inside it is the futures NAME arm, and
the reason is that its FTS half has no expression index, so it computes one
`to_tsvector` per open market:

    ILIKE alone     27.8 ms   Bitmap Index Scan (ix_futures_name_trgm)
    FTS alone      742.7 ms   Index Scan, 49,551 rows removed by filter
    the OR         870.4 ms   Index Scan, 49,557 rows removed

That makes deleting the FTS half look like a free 31x win. **It is not free**, and
the whole point of this file is that the next reader does not have to re-derive
that. LAT-P096's production recall census, ten terms, open markets only:

    term        ILIKE only   FTS OR ILIKE   delta
    champions          405            598    +193
    relegation          53            116     +63
    chiefs              25             30      +5
    election         2,365          2,370      +5
    werder              28             28       0
    schalke             34             34       0
    winner           3,530          3,530       0
    trump              784            784       0
    fed                264            264       0
    mvp                 30             30       0

Six of ten terms gain nothing from the FTS half, which is precisely why removing
it passes a spot check. The four that do gain are stemming matches — `champions`
reaching "Champion", `relegation` reaching "relegated" — and they are head
queries, not curiosities.

A "fallback" shape (run FTS only when ILIKE finds nothing) is also wrong and is
pinned against here: ILIKE already returns 405 rows for `champions`, so the
fallback would never fire and all 193 rows would still be lost. The recall gap
lives INSIDE a healthy result set, not at zero.

The real fix is an FTS expression index so the planner can BitmapOr the two GINs
— DDL, which this lane may not run (ruling 131). Spec and red-first gate:
`docs/audits/latency/lat-p096-futures-name-fts-index-spec.md`,
`backend/scripts/gate_futures_name_fts_index.py`.

WHAT THIS FILE DOES NOT DO. It does not assert timings and it does not touch the
database. It asserts the SHAPE of the compiled predicate, which is the thing a
well-meaning latency edit would change.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import and_
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes.events import (
    _build_expanded_ilike,
    _build_futures_name_filter,
    _fts_filter,
)


def _sql(expression) -> str:
    """Compile a SQLAlchemy expression to literal Postgres SQL."""
    return str(
        expression.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _arm(term: str, expansion: str | None = None, fts_q: str | None = None):
    """The single-term futures NAME arm exactly as the route builds it."""
    ilike = _build_expanded_ilike(FuturesMarket.name, term, expansion)
    return _build_futures_name_filter(ilike, fts_q if fts_q is not None else term)


class TestBothArmsPresent:
    """Neither half may be dropped — each is measured to carry rows the other misses."""

    def test_fts_half_is_present(self):
        sql = _sql(_arm("champions"))
        assert "to_tsvector" in sql, (
            "The FTS half is gone. It is worth +193 open markets on `champions` "
            "and +63 on `relegation` (LAT-P096 production census) — those are "
            "stemming matches an ILIKE substring cannot reach. If you removed it "
            "for latency, the lever is the FTS expression index in "
            "docs/audits/latency/lat-p096-futures-name-fts-index-spec.md, not this."
        )
        assert "websearch_to_tsquery" in sql

    def test_ilike_half_is_present(self):
        sql = _sql(_arm("champions"))
        assert "ILIKE" in sql.upper(), (
            "The substring half is gone. FTS alone cannot match mid-token "
            "substrings, which is most of what a typeahead keystroke is."
        )

    def test_halves_are_ord_together_not_and(self):
        """OR, not AND. An AND would intersect the two and lose both their tails."""
        sql = _sql(_arm("champions")).upper()
        # The top-level combinator between the tsvector arm and the ILIKE arm.
        between = sql.split("WEBSEARCH_TO_TSQUERY")[-1]
        assert " OR " in between, (
            "The two halves must be OR'd. AND would return only rows matching "
            "BOTH, which is strictly smaller than either half alone."
        )

    def test_fts_arm_reads_the_name_column(self):
        """The tsvector must be built over `name` — not some cheaper column."""
        sql = _sql(_arm("champions"))
        match = re.search(r"to_tsvector\([^)]*coalesce\(([^,]+)", sql, re.IGNORECASE)
        assert match is not None, sql
        assert "name" in match.group(1).lower(), (
            "The FTS half must vectorise futures_markets.name. Pointing it at "
            "another column silently changes recall while looking like a tidy-up."
        )


class TestNotAFallback:
    """The FTS half runs unconditionally, not only when ILIKE is empty.

    Pinned because the fallback shape is the intuitive optimisation and it is
    measurably wrong: `champions` returns 405 ILIKE rows, so a fallback never
    fires, yet 193 rows are still missing from the answer.
    """

    def test_no_conditional_wrapping_of_the_fts_arm(self):
        sql = _sql(_arm("champions"))
        assert sql.upper().count("TO_TSVECTOR") == 1
        # A CASE/EXISTS guard around the FTS arm is how a fallback would be
        # expressed inside one predicate.
        assert "CASE" not in sql.upper(), (
            "The FTS half appears to be conditionally applied. A fallback on an "
            "empty ILIKE result never fires for head terms — see the module "
            "docstring's census."
        )

    @pytest.mark.parametrize("term", ["champions", "relegation", "chiefs", "election"])
    def test_recall_terms_keep_both_halves(self, term):
        """The four terms the census measured a real FTS gain on."""
        sql = _sql(_arm(term))
        assert "to_tsvector" in sql
        assert "ILIKE" in sql.upper()


class TestOneDefinition:
    """The route and the gate script must compile the SAME predicate.

    `backend/scripts/gate_futures_name_fts_index.py` grades the attended DDL by
    compiling the arm from the live ORM through this helper. A hand-pasted copy
    in the gate would keep passing against an index the route no longer matches
    — the exact failure LAT-P086 caught in the teams DDL (`::text` vs
    `CAST(... AS VARCHAR)`).
    """

    def test_helper_matches_the_inline_form_it_replaced(self):
        term = "champions"
        ilike = _build_expanded_ilike(FuturesMarket.name, term, None)
        from sqlalchemy import or_

        inline = or_(_fts_filter(FuturesMarket.name, term), ilike)
        assert _sql(_build_futures_name_filter(ilike, term)) == _sql(inline)

    def test_expansion_is_carried_into_the_ilike_half(self):
        """Alias expansion must survive the helper — it is recall, not decoration."""
        sql = _sql(_arm("chiefs", expansion="kansas city"))
        assert "kansas city" in sql.lower()

    def test_multi_term_ilike_filter_is_passed_through_unchanged(self):
        """The multi-term branch hands in an AND of per-term conditions."""
        combined = and_(
            _build_expanded_ilike(FuturesMarket.name, "us", None),
            _build_expanded_ilike(FuturesMarket.name, "recession", None),
        )
        sql = _sql(_build_futures_name_filter(combined, "us recession"))
        assert "%us%" in sql and "%recession%" in sql
        assert "to_tsvector" in sql


class TestStemSubstringIsNotASubstituteForFTS:
    """The code-only lever, pinned as REJECTED with the census that rejected it.

    LAT-P097 tested "DDL, not code" instead of asserting it. The candidate was to
    drop the FTS half and add a second ILIKE over the query term's Postgres stem
    — same stemmer, no DDL, no new dependency, and measurably fast (the arm went
    6,293.9 -> 259.0 ms on `champions` and 3,423.7 -> 24.8 ms on `werder` across
    three interleaved production rounds, 26,106 -> 4,315 buffers).

    It passes the ten-term LAT-P096 census with zero rows lost. Widened to the
    36-term census — the 30-day `/search` head plus stemming hazards — it loses
    recall on four terms including a head query:

        grammys      15 ->   5   (-10)   head rank 7   stem `grammi`
        cities      744 ->   4  (-740)                 stem `citi`
        qualifying 1074 -> 237  (-837)                 stem `qualifi`
        trophies     15 ->   8    (-7)                 stem `trophi`

    Porter maps a trailing `y` to `i`, so `grammys` stems to `grammi`, which is
    not a substring of "Grammy". FTS matches it because FTS stems BOTH sides. A
    substring cannot express stem equivalence, and every `-y`/`-ies` word is in
    the class.

    These tests exist because the substitute would pass the older guards above:
    it contains the token `to_tsvector` (it uses it to compute the stem) and it
    contains `ILIKE`. The shape assertions here are the ones that can tell the
    two apart.
    """

    def test_the_match_operator_vectorises_the_NAME_COLUMN(self):
        """`@@`'s left side must be a tsvector over `futures_markets.name`.

        The rejected lever also emits `to_tsvector`, but over the query STRING,
        to derive a stem — never over the column. Asserting merely that the
        token appears cannot distinguish "we search stemmed names" from "we
        stemmed the search box".
        """
        sql = _sql(_arm("champions"))
        assert re.search(
            r"to_tsvector\(\s*'[^']+'\s*,\s*coalesce\(\s*futures_markets\.name",
            sql,
            re.IGNORECASE,
        ), (
            "No tsvector is built over futures_markets.name. If this became a "
            "stem-substring arm, read the census in this class's docstring: it "
            "loses 10 of 15 open markets on `grammys`, a head query."
        )
        assert "@@" in sql

    def test_no_tsvector_is_built_over_a_string_literal(self):
        """`to_tsvector('english', 'champions')` is the rejected lever's tell."""
        sql = _sql(_arm("champions"))
        assert not re.search(
            r"to_tsvector\(\s*'[^']+'\s*,\s*'", sql, re.IGNORECASE
        ), (
            "A tsvector is being computed over a literal, which is how a stem is "
            "derived in SQL. That lever is REJECTED on measurement (LAT-P097) — "
            "it cannot express stem equivalence for `-y`/`-ies` words."
        )

    @pytest.mark.parametrize(
        "term,stem", [("grammys", "grammi"), ("cities", "citi"),
                      ("qualifying", "qualifi"), ("trophies", "trophi")]
    )
    def test_the_four_census_losses_are_not_matched_by_their_stems(self, term, stem):
        """The arm must not have quietly become `ILIKE '%<stem>%'`.

        Parametrised on the four terms the 36-term production census measured a
        recall LOSS on, so the failure message names the term that broke rather
        than a generic shape complaint.
        """
        sql = _sql(_arm(term))
        assert f"%{stem}%" not in sql, (
            f"`{term}` is being matched by its stem substring `%{stem}%`. The "
            "production census measured that as a recall loss on this exact "
            "term — see this class's docstring."
        )
        assert "to_tsvector" in sql and "websearch_to_tsquery" in sql
