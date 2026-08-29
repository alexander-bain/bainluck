"""LAT-P132 (#2302) — the men's college basketball grid stops 503ing.

``/api/playoffs/ncaa-basketball`` was returning HTTP 503 at the route's 25 s
wall. LAT-P131 recorded it as "the one league that cannot be built at all" and
left it out of the hourly warm list, reading its timing split as
``app=17.87 s, db=7.26 s`` — a Python problem, not a query problem.

**That split also carried ``unfinished=1``**, and ``app/utils/request_timing.py``
defines that flag as "a statement started and never recorded a finish". An
unfinished statement contributes nothing to ``db``, and ``app`` is computed by
subtraction, so its whole duration is reported as application time. The 17.87 s
of "app" was a query. Re-measured on production 2026-08-29, the same route
served ``wall=21558 ms; db=20980; app=578; q=26; maxq=16159`` — one query, 16.2 s
of a 21.6 s request.

That query is the candidate scan. LAT-P129 stopped it sequentially scanning all
911,217 rows by scoping each external-id path to the source that owns its id
space; what it left behind is that ``source = 'kalshi'`` was then the ONLY term
an index could serve, so the planner bitmapped *the whole of Kalshi* and
rechecked 265,961 rows in the heap to return 90. ``external_id ILIKE 'KXMLB%'``
is not index-usable in any form: ``ILIKE`` never uses a btree, and this database
collates ``en_US.UTF-8`` so even ``LIKE`` would need ``text_pattern_ops`` — DDL,
a migration slot, gotcha #31, parked as **P129-3, NEEDS ALEX**.

The fix adds a ``[low, high)`` range beside the ``ILIKE`` — a plain comparison,
which the *already existing* ``uq_futures_source_external`` btree serves. No DDL,
no migration slot, so P129-3's gate does not apply to this form. Measured with
``EXPLAIN (ANALYZE, BUFFERS)`` on the exact predicate the builder emits:

======================  ==========  =========  ==================  ============
league                  OLD ms      NEW ms     rows                heap blocks
======================  ==========  =========  ==================  ============
ncaa-basketball         24,465      984        12 = 12             73,644 -> 161
nba                     22,804      586        9,042 = 9,042       74,137 -> 5,033
ncaa-football           926         1,171      13 = 13             314 -> 314
======================  ==========  =========  ==================  ============

**Why these tests look the way they do.** LAT-P129 wrote this same range and
**rejected it**: *"a range is only a prefix in ``C`` collation … same rows today
is a coincidence, not an equality."* That objection is right about
``external_id >= 'KXMLB'``, and this ship answers it in the construction rather
than in a census:

* the ``ILIKE`` is **conjoined, never replaced**, so the range can only ever
  remove rows, never add wrong ones;
* ``low`` is ``prefix[:-1]`` — one character SHORT — so every string starting
  with the prefix carries a non-ignorable character beyond it and is greater at
  the PRIMARY collation level, where no case or punctuation tie-break can reach.
  ``>= prefix`` has no such proof: glibc sorts lowercase before uppercase.

Both of those are invisible in results — every league returns the identical row
set with or without them — so the guards here assert the SHAPE and the BOUNDS.
Tightening ``low`` back to ``prefix`` must FAIL a test, not merely become subtly
wrong; dropping the ``ILIKE`` for speed must FAIL a test, not merely become
fast.
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
    _external_id_prefix_condition,
    external_id_prefix_range,
)


ALL_SLUGS = sorted(get_all_league_slugs())
BOTH_FILTERS = ("with_status", "bare")


def _configured_prefixes():
    """Every ``(source, prefix)`` pair any league config asks the grid to match."""
    pairs = set()
    for slug in ALL_SLUGS:
        config = get_league_config(slug)
        for attr, source in GRID_ID_SPACE_SOURCE.items():
            for prefix in getattr(config, attr, None) or []:
                pairs.add((source, prefix))
    return sorted(pairs)


CONFIGURED_PREFIXES = _configured_prefixes()


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


def _external_id_terms(node, op):
    """Every ``external_id <op> <value>`` term anywhere under ``node``."""
    found = []
    for child, _ in _walk(node):
        if (
            isinstance(child, BinaryExpression)
            and child.operator is op
            and child.left.key == "external_id"
        ):
            found.append(child.right.value)
    return found


def _filters(slug):
    with_status, bare = _build_grid_market_filters(get_league_config(slug))
    return {"with_status": with_status, "bare": bare}


# ---------------------------------------------------------------------------
# 1. The landmine: every prefix this fleet configures must get a range.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source,prefix", CONFIGURED_PREFIXES)
def test_every_configured_prefix_gets_a_range(source, prefix):
    """A new prefix with no safe range FAILS here rather than costing 16 s.

    ``external_id_prefix_range`` refuses to guess, and refusing degrades to a
    bare ``ILIKE`` — correct, and back to a 266K-row heap recheck. That is a
    decision, so it is made in a review, not defaulted at 03:00.
    """
    assert external_id_prefix_range(prefix) is not None, (
        f"{source} prefix {prefix!r} yields no range, so its candidate scan "
        "falls back to the unindexable bare ILIKE"
    )


def test_the_configured_prefix_set_is_not_empty():
    """The parametrize above is vacuous if the configs stop declaring prefixes."""
    assert len(CONFIGURED_PREFIXES) >= 20, CONFIGURED_PREFIXES


# ---------------------------------------------------------------------------
# 2. The shape, in both filters, for every league.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", ALL_SLUGS)
@pytest.mark.parametrize("which", BOTH_FILTERS)
def test_every_external_id_ilike_is_accompanied_by_both_bounds(slug, which):
    """Revert to a bare ``ILIKE`` and this FAILS — it does not merely get slower.

    Counted rather than merely detected: one league that quietly loses its
    bounds while its siblings keep theirs is the regression this catches.
    """
    clause = _filters(slug)[which]
    ilikes = _external_id_terms(clause, operators.ilike_op)
    lows = _external_id_terms(clause, operators.ge)
    highs = _external_id_terms(clause, operators.lt)

    if not ilikes:
        pytest.skip(f"{slug} configures no external_id prefixes")

    assert len(lows) == len(ilikes), (
        f"{slug}/{which}: {len(ilikes)} external_id ILIKE terms but "
        f"{len(lows)} lower bounds"
    )
    assert len(highs) == len(ilikes), (
        f"{slug}/{which}: {len(ilikes)} external_id ILIKE terms but "
        f"{len(highs)} upper bounds"
    )


@pytest.mark.parametrize("slug", ALL_SLUGS)
@pytest.mark.parametrize("which", BOTH_FILTERS)
def test_the_range_never_replaces_the_ilike(slug, which):
    """The second door, and it is the form LAT-P129 rejected.

    A range ALONE is faster still and looks identical on today's rows. It is
    also the thing P129 refused, because a range is only a prefix in ``C``
    collation. The ``ILIKE`` staying conjoined is what makes an over-wide bound
    harmless, so its disappearance must be a test failure.
    """
    clause = _filters(slug)[which]
    lows = _external_id_terms(clause, operators.ge)
    ilikes = _external_id_terms(clause, operators.ilike_op)

    if not lows:
        pytest.skip(f"{slug} configures no external_id prefixes")

    assert ilikes, (
        f"{slug}/{which}: external_id has range bounds but no ILIKE left — the "
        "range became the authority, which is exactly P129-3's rejected form"
    )


@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_bounds_land_inside_the_same_and_group_as_their_ilike(slug):
    """A bound in the wrong ``AND`` group would filter a DIFFERENT path's rows.

    ``or_(and_(source, low, high, ilike), ...)`` is the shape. Hoisting a bound
    out to the top level would apply the NCAA range to the MLB arm.
    """
    clause = _filters(slug)["with_status"]
    for node, ancestors in _walk(clause):
        if not (
            isinstance(node, BinaryExpression)
            and node.operator is operators.ge
            and node.left.key == "external_id"
        ):
            continue
        parent = ancestors[-1]
        assert isinstance(parent, BooleanClauseList), parent
        assert parent.operator is operators.and_, (
            f"{slug}: lower bound {node.right.value!r} sits under an OR"
        )
        siblings = [
            c for c in parent.clauses
            if isinstance(c, BinaryExpression) and c.left.key == "external_id"
        ]
        ops = {c.operator for c in siblings}
        assert operators.ilike_op in ops and operators.lt in ops, (
            f"{slug}: lower bound {node.right.value!r} is not grouped with its "
            f"own ILIKE and upper bound; found {sorted(str(o) for o in ops)}"
        )


# ---------------------------------------------------------------------------
# 3. The bounds themselves — the proof, executed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("KXMLB", ("KXML", "KXMLC")),
        ("KXMARMADROUND", ("KXMARMADROUN", "KXMARMADROUNE")),
        ("basketball_ncaab", ("basketball_ncaa", "basketball_ncaac")),
        ("soccer_epl", ("soccer_ep", "soccer_epm")),
        ("golf_pga", ("golf_pg", "golf_pgb")),
        ("AB0", ("AB", "AB1")),
    ],
)
def test_range_bounds_are_exactly_this(prefix, expected):
    assert external_id_prefix_range(prefix) == expected


@pytest.mark.parametrize("source,prefix", CONFIGURED_PREFIXES)
def test_the_low_bound_is_one_character_short_of_the_prefix(source, prefix):
    """🔴 The whole proof lives in this one character. Do not tighten it.

    ``low = prefix`` is P129's form and it is unsafe in ``en_US.UTF-8``: glibc
    sorts lowercase before uppercase at the tertiary level, so a ``'kxmlb…'``
    row sorts BELOW ``'KXMLB'`` and would be silently dropped. ``prefix[:-1]``
    cannot have that problem — every prefix match carries one more non-ignorable
    character than the bound, so it is greater at the PRIMARY level, and no
    case, accent or punctuation weight is ever consulted.
    """
    low, _ = external_id_prefix_range(prefix)
    assert low == prefix[:-1]
    assert low != prefix, "the low bound was tightened back to P129's rejected form"
    assert len(low) == len(prefix) - 1


@pytest.mark.parametrize("source,prefix", CONFIGURED_PREFIXES)
def test_the_high_bound_ends_in_an_alphanumeric_of_the_same_class(source, prefix):
    """``'z' + 1`` is ``'{'`` — punctuation, which ``en_US.UTF-8`` IGNORES.

    A bound ending in an ignorable character does not mean what it looks like it
    means, so the successor is only ever taken inside a class: ``a..y``,
    ``A..Y``, ``0..8``.
    """
    _, high = external_id_prefix_range(prefix)
    last_prefix, last_high = prefix[-1], high[-1]
    assert last_high.isalnum() and last_high.isascii()
    assert ord(last_high) == ord(last_prefix) + 1
    assert last_prefix.isdigit() == last_high.isdigit()
    assert last_prefix.isupper() == last_high.isupper()


@pytest.mark.parametrize("source,prefix", CONFIGURED_PREFIXES)
def test_realistic_ids_fall_inside_the_range(source, prefix):
    """Executed against the id shapes these two sources actually mint.

    Ordinary string comparison here is ``C`` collation, which is STRICTER than
    production's ``en_US.UTF-8`` for same-case ids — passing here and passing
    there are not the same claim, and the collation-sensitive half is proved in
    the docstring and measured on production. What this pins is that the bounds
    are not simply off by a character.
    """
    low, high = external_id_prefix_range(prefix)
    suffixes = ["", "-26AUG29", "GAME-26AUG29DETMIN", "_championship_winner", "9", "Z"]
    for suffix in suffixes:
        candidate = prefix + suffix
        assert low <= candidate < high, (
            f"{candidate!r} starts with {prefix!r} but falls outside "
            f"[{low!r}, {high!r})"
        )


@pytest.mark.parametrize("last", list("abcdefghijklmnopqrstuvwxy0123456"))
def test_the_successor_sweep_never_leaves_the_alphanumerics(last):
    """Every permitted last character, executed — not three hand-picked ones."""
    low, high = external_id_prefix_range("KX" + last)
    assert low == "KX"
    assert high[-1].isalnum() and high[-1].isascii()


# ---------------------------------------------------------------------------
# 4. Refusals — and a refusal is still correct, only slow.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "prefix",
    [
        "",            # nothing to bound
        "K",           # one character: low would be '' and bound nothing
        "KXMLz",       # 'z' + 1 == '{', punctuation
        "KXMLZ",       # 'Z' + 1 == '[', punctuation
        "KXML9",       # '9' + 1 == ':', punctuation
        "KXML_",       # last character is not alphanumeric
        "KX ML",       # a space is not in the safe alphabet
        "KX%LB",       # a wildcard is not in the safe alphabet
        "KXMLÉ",  # non-ASCII: accents are a secondary weight
        "KXMLB%",      # a caller that already appended the wildcard
    ],
)
def test_unsafe_prefixes_are_refused(prefix):
    assert external_id_prefix_range(prefix) is None


@pytest.mark.parametrize("prefix", ["KXMLz", "K", "KX ML"])
def test_a_refused_prefix_still_gets_a_working_ilike(prefix):
    """Slow is a correct answer. Missing a grid column is not.

    The fallback keeps the exact predicate that shipped before this change, so
    a refusal costs latency and nothing else.
    """
    clause = _external_id_prefix_condition(prefix)
    assert isinstance(clause, BinaryExpression)
    assert clause.operator is operators.ilike_op
    assert clause.left.key == "external_id"
    assert clause.right.value == f"{prefix}%"


def test_a_safe_prefix_emits_exactly_three_terms():
    """Two bounds and the ILIKE — no more, and crucially no fewer."""
    clause = _external_id_prefix_condition("KXMLB")
    assert isinstance(clause, BooleanClauseList)
    assert clause.operator is operators.and_
    ops = [c.operator for c in clause.clauses]
    assert ops.count(operators.ge) == 1
    assert ops.count(operators.lt) == 1
    assert ops.count(operators.ilike_op) == 1
    assert len(ops) == 3
