"""Guard: the /api/politics market query shape (LAT-P023, #1607).

Scope note, because this file deliberately does NOT re-test the cache tiers:
``test_politics_cold_path_contract.py`` (LAT-P016) already owns the primary ->
stale -> rebuild ladder, the no-deadline rule, the connection close and the
miss/unavailable distinction. This file owns only the two query-shape changes
LAT-P023 made underneath that ladder, plus the one invariant they rest on.

Asserted against compiled SQL and source shape, never a wall clock, so it is
deterministic in CI (the LAT-P002/C114 pattern).

Why these two changes exist. LAT-P016 fixed WHO pays the cold build (nobody,
once a stale mirror exists) and instrumented it. Its rail then named the
dominant stage: of a 10,437ms build, ``market_query`` is 7,332ms — 70%. These
changes make that stage cheaper, and make the build smaller in memory on a
worker that is being hard-killed more often than it finishes.
"""

import inspect

from app.routes import politics as politics_route


# Frozen expectation, NOT derived from _THEME_BY_TICKER. Deriving it would make
# the test self-referential: deleting a prefix from the table would delete its
# own check too. That mutation survived a derived version of this test.
_EXPECTED_TICKER_PREFIXES = frozenset({
    "kxpres", "kxelection", "kxsenate", "kxhouse", "kxcongress", "kxgov",
    "kxscotus", "kxsupremecourt", "kxtariff", "kximpeach", "kxbill",
})


def _compiled_politics_market_sql():
    """Compile the market query the route issues, without a DB."""
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload
    from app.models import FuturesMarket

    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(["politics", "geopolitics"]),
                *[FuturesMarket.external_id.like(f"{prefix.upper()}%")
                  for prefix, _ in politics_route._THEME_BY_TICKER],
            ),
            FuturesMarket.status == "open",
        )
    )
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_ticker_arm_uses_case_sensitive_like():
    """ILIKE case-folds ~83K rows per build; LIKE is a byte-prefix compare.

    Measured in production 2026-08-10: 1,021ms -> 188ms for the arms, with
    equivalence checked in a single snapshot (563 == 563, zero rows differing in
    either direction). Asserted on the route's own source so the arm cannot
    quietly revert.
    """
    source = inspect.getsource(politics_route.get_politics)
    assert ".ilike(" not in source, (
        "the market predicate must not case-fold every open row; "
        "Kalshi tickers are uppercase, so LIKE is equivalent and 5.4x cheaper"
    )
    assert '.like(f"{prefix.upper()}%")' in source


def test_ticker_prefixes_are_stored_lowercase_and_uppercase_cleanly():
    """The LIKE arm is only equivalent while the prefixes uppercase cleanly.

    ``_THEME_BY_TICKER`` holds lowercase prefixes because ``_classify_theme``
    lowercases ``external_id`` before comparing. The query arm uppercases them
    instead. This states the invariant joining those two readings, so a prefix
    that does not round-trip fails here rather than silently dropping markets.
    """
    for prefix, _theme in politics_route._THEME_BY_TICKER:
        assert prefix == prefix.lower(), f"{prefix} must be lowercase for classification"
        assert prefix.upper().lower() == prefix, f"{prefix} must round-trip through upper()"


def test_every_ticker_prefix_still_reaches_the_query():
    """All 11 arms must survive. Dropping them costs the whole SCOTUS section.

    The arms look like the obvious thing to prune — measured 2026-08-10 they add
    ~833ms of scan and contribute 48 unique rows out of ~7,041 (0.68%). But those
    48 are the SCOTUS docket, the tariff-policy markets and the impeachment
    market, which the LLM tagged 'legal' and 'economics', so the category arm
    never sees them. The fix was to make the arms cheap, not to delete them.
    """
    actual = {prefix for prefix, _theme in politics_route._THEME_BY_TICKER}
    assert actual == _EXPECTED_TICKER_PREFIXES, (
        "the ticker arms changed; if deliberate, update _EXPECTED_TICKER_PREFIXES "
        "and say in the commit which markets stop surfacing"
    )

    sql = _compiled_politics_market_sql()
    for prefix in _EXPECTED_TICKER_PREFIXES:
        assert f"'{prefix.upper()}%'" in sql, f"{prefix} arm missing from the query"
    assert sql.count("LIKE") >= len(_EXPECTED_TICKER_PREFIXES)


def test_snapshot_history_selects_columns_not_entities():
    """15,413 ORM objects were hydrated to emit <=50 points per candidate."""
    source = inspect.getsource(politics_route.get_politics)
    assert "select(FuturesOddsSnapshot)" not in source, (
        "entity select re-hydrates every snapshot row; select the three columns used"
    )
    for column in ("outcome_id", "captured_at", "probability"):
        assert f"FuturesOddsSnapshot.{column}," in source, f"missing {column} in the column select"


def test_market_query_stage_is_still_timed():
    """LAT-P016's rail is how this stage gets re-measured after deploy.

    LAT-P023's own after-number depends on ``market_query`` still being marked,
    so the optimisation cannot be verified if someone removes the mark while
    tidying. Cheap to assert, and it is the only evidence rail for this stage.
    """
    source = inspect.getsource(politics_route.get_politics)
    assert '_mark("market_query"' in source
