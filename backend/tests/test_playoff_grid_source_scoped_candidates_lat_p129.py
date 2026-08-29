"""LAT-P129 — the championship grid's candidate scan stops reading the whole table.

``get_playoff_grid`` finds a league's candidate markets with three matching
paths, two of which match on ``futures_markets.external_id``:

* **A**   ``external_id`` starts with an Odds API sport key  (``soccer_epl%``)
* **B.1** ``external_id`` starts with a Kalshi series ticker (``KXMLB%``)
* **B.2** ``llm_sport_category`` matches AND the market NAME matches a league
  name pattern (Polymarket)

Written as a flat ``OR``, that predicate spans two unrelated columns, so no
single index can serve it and Postgres sequentially scans all 911,217 rows of
``futures_markets`` — 645K Polymarket and 266K Kalshi rows read to find markets
that can only ever be among the **12** ``odds_api`` rows in the table. Measured
on production 2026-08-29 for EPL: the candidate scan was a 16,503 ms parallel
Seq Scan discarding 911,180 rows to return 37, and the resolved backfill that
reuses the same expression was a further 6,246 ms to return 16.

The fix scopes each external-id path to the source that OWNS that id space —
which ``models.py`` already documents (``external_id`` is "sport_key or event
ticker", and which one it is depends entirely on ``source``). Same rows, but a
``BitmapOr`` over ``ix_fm_source_created_at`` + ``ix_futures_name_trgm``:
2,473 ms and 375 ms.

**Why these tests look the way they do.** The defect was invisible on the page:
the expression selected exactly the right markets, and the only tell was in a
query plan. So the guards assert the SHAPE of the emitted predicate, not just
its results — a correct-looking flat ``OR`` has to FAIL a test, not merely get
slower. ``_matches`` evaluates the real clause object the route hands to
SQLAlchemy, so the behavioural cases are not a re-implementation of the filter.
"""

import pytest
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BooleanClauseList,
    Grouping,
)

from app.config.league_configs import get_all_league_slugs, get_league_config
from app.routes.playoffs import (
    GRID_ID_SPACE_SOURCE,
    _build_grid_market_filters,
    _league_pattern_to_ilike,
)


# ---------------------------------------------------------------------------
# A tiny evaluator over the REAL clause object.
#
# The filter only ever uses `=`, `ILIKE`, `IN`, `AND`, `OR`, so a fixture row can
# be matched against the actual expression the route builds. That keeps the
# behavioural assertions honest: they cannot pass against a filter that the
# route does not use, and they need no database.
# ---------------------------------------------------------------------------

def _ilike_to_regex(pattern: str):
    import re as _re

    out = []
    for ch in pattern:
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(_re.escape(ch))
    return _re.compile("^" + "".join(out) + "$", _re.IGNORECASE | _re.DOTALL)


def _matches(clause, row: dict) -> bool:
    """Evaluate a grid candidate-filter clause against a fixture market row."""
    if isinstance(clause, Grouping):
        return _matches(clause.element, row)
    if isinstance(clause, BooleanClauseList):
        results = [_matches(c, row) for c in clause.clauses]
        if clause.operator is operators.and_:
            return all(results)
        if clause.operator is operators.or_:
            return any(results)
        raise AssertionError(f"unhandled boolean operator {clause.operator!r}")
    if isinstance(clause, BinaryExpression):
        column = clause.left.key
        value = row.get(column)
        bound = clause.right.value
        if clause.operator is operators.eq:
            return value == bound
        if clause.operator is operators.ilike_op:
            return value is not None and bool(_ilike_to_regex(bound).match(value))
        if clause.operator is operators.in_op:
            return value in tuple(bound)
        raise AssertionError(f"unhandled operator {clause.operator!r}")
    raise AssertionError(f"unhandled clause node {type(clause).__name__}")


def _walk(clause):
    """Yield ``(node, ancestors)`` for every node in the clause tree."""

    def rec(node, ancestors):
        yield node, ancestors
        chain = ancestors + [node]
        if isinstance(node, Grouping):
            yield from rec(node.element, chain)
        elif isinstance(node, BooleanClauseList):
            for child in node.clauses:
                yield from rec(child, chain)

    yield from rec(clause, [])


def _source_terms_in(node) -> set:
    """Every ``source = <value>`` equality anywhere under ``node``."""
    found = set()
    for child, _ in _walk(node):
        if (
            isinstance(child, BinaryExpression)
            and child.operator is operators.eq
            and child.left.key == "source"
        ):
            found.add(child.right.value)
    return found


def _external_id_predicates(clause):
    """Yield ``(node, ancestors)`` for every ``external_id ILIKE ...`` term."""
    for node, ancestors in _walk(clause):
        if (
            isinstance(node, BinaryExpression)
            and node.operator is operators.ilike_op
            and node.left.key == "external_id"
        ):
            yield node, ancestors


ALL_SLUGS = sorted(get_all_league_slugs())
BOTH_FILTERS = ("with_status", "bare")


def _filters(slug):
    with_status, bare = _build_grid_market_filters(get_league_config(slug))
    return {"with_status": with_status, "bare": bare}


def _market(**kw):
    row = {
        "source": "polymarket",
        "external_id": "0xdeadbeef",
        "name": "Some Market",
        "llm_sport_category": None,
        "status": "open",
    }
    row.update(kw)
    return row


# ---------------------------------------------------------------------------
# The load-bearing guard: revert the fix and this fails, it does not get slower.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", ALL_SLUGS)
@pytest.mark.parametrize("which", BOTH_FILTERS)
def test_every_external_id_predicate_is_scoped_by_source(slug, which):
    """No bare ``external_id ILIKE`` may reach the planner, for any league.

    This is the whole defect. A flat ``OR`` of ``external_id`` prefixes against
    ``llm_sport_category``/``name`` cannot use an index, and the table is
    911,217 rows. Every such predicate must sit under an ``AND`` that also pins
    ``source``, so the planner gets a driver it can index.
    """
    clause = _filters(slug)[which]
    predicates = list(_external_id_predicates(clause))
    for node, ancestors in predicates:
        conjunctions = [
            a
            for a in ancestors
            if isinstance(a, BooleanClauseList) and a.operator is operators.and_
        ]
        assert conjunctions, (
            f"{slug}/{which}: `external_id ILIKE {node.right.value!r}` is not "
            f"inside any AND — it will be OR-ed across columns and seq-scan the "
            f"whole of futures_markets"
        )
        assert any(_source_terms_in(a) for a in conjunctions), (
            f"{slug}/{which}: `external_id ILIKE {node.right.value!r}` is not "
            f"conjoined with a `source =` term"
        )


@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_sport_keys_scope_to_odds_api_and_tickers_scope_to_kalshi(slug):
    """The SECOND door: scoping to the WRONG source is fast and silently empty.

    Pinning "is scoped at all" is not enough — sending both id spaces to
    ``kalshi`` would satisfy the guard above, keep the plan fast, and quietly
    drop every Odds API market from the grid. The pairing itself is the
    contract.
    """
    config = get_league_config(slug)
    clause = _filters(slug)["bare"]
    by_prefix = {}
    for node, ancestors in _external_id_predicates(clause):
        sources = set()
        for a in ancestors:
            if isinstance(a, BooleanClauseList) and a.operator is operators.and_:
                sources |= _source_terms_in(a)
        by_prefix[node.right.value] = sources

    for sport_key in config.sport_keys:
        assert by_prefix.get(f"{sport_key}%") == {"odds_api"}, (
            f"{slug}: sport key {sport_key!r} must be scoped to odds_api"
        )
    for prefix in config.external_id_prefixes or []:
        assert by_prefix.get(f"{prefix}%") == {"kalshi"}, (
            f"{slug}: ticker prefix {prefix!r} must be scoped to kalshi"
        )
    assert len(by_prefix) == len(config.sport_keys) + len(
        config.external_id_prefixes or []
    ), f"{slug}: unexpected extra external_id predicates {sorted(by_prefix)}"


def test_id_space_source_map_is_the_documented_pairing():
    """``GRID_ID_SPACE_SOURCE`` names real ``LeagueConfig`` fields and real sources."""
    assert GRID_ID_SPACE_SOURCE == {
        "sport_keys": "odds_api",
        "external_id_prefixes": "kalshi",
    }
    config = get_league_config("mlb")
    for attr in GRID_ID_SPACE_SOURCE:
        assert hasattr(config, attr), f"LeagueConfig has no field {attr!r}"


# ---------------------------------------------------------------------------
# Behavioural: same markets in, same markets out — evaluated on the real clause.
# ---------------------------------------------------------------------------

def test_odds_api_sport_key_market_still_matches():
    clause = _filters("epl")["with_status"]
    assert _matches(
        clause,
        _market(source="odds_api", external_id="soccer_epl_winner", status="open"),
    )


def test_kalshi_ticker_market_still_matches():
    clause = _filters("mlb")["with_status"]
    assert _matches(
        clause,
        _market(source="kalshi", external_id="KXMLBCHAMP-26", status="resolved"),
    )


def test_polymarket_category_and_name_market_still_matches():
    clause = _filters("epl")["with_status"]
    assert _matches(
        clause,
        _market(
            source="polymarket",
            external_id="0xabc",
            name="Which club wins the EPL title?",
            llm_sport_category="soccer",
            status="open",
        ),
    )


def test_foreign_source_carrying_another_id_space_is_not_matched_by_that_path():
    """The narrowing's semantics, stated rather than left to be discovered.

    A Polymarket row whose ``external_id`` happens to start with an Odds API
    sport key is NOT an Odds API market, and path A no longer claims it. This
    is the one behaviour the fix changes, and it changes nothing today: across
    all 911,217 rows, ZERO non-odds_api rows match any of the 18 configured
    sport keys and ZERO non-kalshi rows match any of the 7 configured ticker
    prefixes (measured 2026-08-29). Such a row remains reachable through path
    B.2, which is the path that is actually meant to find Polymarket markets.
    """
    clause = _filters("epl")["with_status"]
    decoy = _market(
        source="polymarket",
        external_id="soccer_epl_impostor",
        name="Unrelated market",
        llm_sport_category=None,
        status="open",
    )
    assert not _matches(clause, decoy)

    # ...and the same row IS still found once it looks like what it is.
    assert _matches(
        clause,
        {**decoy, "llm_sport_category": "soccer", "name": "EPL Winner 2026"},
    )


def test_wrong_league_sport_key_does_not_match():
    clause = _filters("epl")["with_status"]
    assert not _matches(
        clause,
        _market(source="odds_api", external_id="baseball_mlb_winner", status="open"),
    )


# ---------------------------------------------------------------------------
# The parts that must NOT have moved.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_status_split_is_preserved(slug):
    """Ticker paths may be ``resolved``; the category path may not.

    Division winners settle, so Kalshi/Odds API markets are searched in
    ``open|closed|resolved``. Polymarket's category path stays ``open|closed``
    so the grid never loads that category's whole resolved inventory. Collapsing
    the two is a latency regression wearing a simplification's clothes.
    """
    config = get_league_config(slug)
    clause = _filters(slug)["with_status"]
    resolved_row = _market(
        source="odds_api",
        external_id=f"{config.sport_keys[0]}_winner",
        status="resolved",
    )
    assert _matches(clause, resolved_row)

    category_resolved = _market(
        source="polymarket",
        llm_sport_category=config.sport_category,
        name=_representative_name(config),
        status="resolved",
    )
    assert not _matches(clause, category_resolved)


def _representative_name(config) -> str:
    """A market name that satisfies this league's first live name pattern."""
    for pattern in config.league_name_patterns or []:
        body = _league_pattern_to_ilike(pattern)
        if body:
            return f"The {body} market"
    return "anything"


@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_bare_filter_carries_no_status_term(slug):
    """The resolved backfill adds ``status == 'resolved'`` itself.

    If the bare filter grew a status term, the backfill would AND two status
    predicates and silently return nothing.
    """
    clause = _filters(slug)["bare"]
    for node, _ in _walk(clause):
        if isinstance(node, BinaryExpression):
            assert node.left.key != "status", (
                f"{slug}: bare market_filter must not constrain status"
            )


@pytest.mark.parametrize(
    "pattern,expected",
    [
        (r"\bEPL\b", "EPL"),
        (r"\bBundesliga\b", "Bundesliga"),
        (r"\bMLB\b", "MLB"),
        # `\b` and `\s` are stripped before the `\s+`->`%` rule can fire, so
        # multi-word patterns collapse to a literal `+`. That is PRE-EXISTING
        # behaviour and is pinned, not fixed, here: these patterns match nothing
        # today, and changing that would widen every grid's candidate set — a
        # product change, not this queue's latency one. Parked as P129-2.
        (r"\bPremier\s+League\b", "Premier+League"),
        (r"\bWorld\s+Series\b", "World+Series"),
    ],
)
def test_league_pattern_to_ilike_is_unchanged(pattern, expected):
    assert _league_pattern_to_ilike(pattern) == expected


@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_every_league_builds_both_filters(slug):
    with_status, bare = _build_grid_market_filters(get_league_config(slug))
    assert with_status is not None
    assert bare is not None


def test_category_path_requires_the_name_pattern_too():
    """Path B.2 must keep pushing the name filter to SQL.

    Dropping it turns the category term into ``llm_sport_category = 'soccer'``
    alone — 231,096 rows for soccer — which is how the grid loaded a whole
    category's inventory before the name filter was pushed down.
    """
    clause = _filters("epl")["with_status"]
    assert not _matches(
        clause,
        _market(
            source="polymarket",
            llm_sport_category="soccer",
            name="Ligue 1 Winner",
            status="open",
        ),
    )
