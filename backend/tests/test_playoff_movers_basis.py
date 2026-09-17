"""#6675 — the playoff grid's 24h delta must subtract the same QUANTITY.

#1844 made both sides of ``merged - old_p`` agree about vig. They still did not
agree about what the column sums to: ``_compute_movers`` de-vigged EVERY source,
including the ones that store a probability rather than a price, so each such
column was re-scaled by its own sum.

On a winner market that is nearly invisible (sum ~1.0). On "Pro Basketball
Playoff Qualifiers" — 30 independent binaries, sum 16.54 — it divided every
reconstructed price by ~16.5, and the NBA grid told a reader that all 30 teams'
playoff odds had risen by ~94% of their own value in a day.

These are regression guards for the CLASS, not for the NBA specimen: the same
arithmetic was wrong on every kalshi award market, and NHL/NFL were unexposed
only because they had no snapshots in the window.
"""

import ast
import pathlib

import pytest

from app.routes.playoffs import (
    _ALREADY_PROBABILITY_SOURCES,
    _DEVIGGED_AT_INGEST_SOURCES,
)
from app.utils.odds_math import devig_consensus


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------

#: A 30-team make-playoffs column as kalshi actually publishes it: independent
#: binaries, 16 qualifiers, so it sums to ~16.5 and MUST NOT be re-scaled.
#: Values are the production shape (0.985 down to 0.035) rather than a toy.
_QUALIFIER_COLUMN = {
    1: 0.985, 2: 0.96, 3: 0.87, 4: 0.82, 5: 0.76, 6: 0.74, 7: 0.71, 8: 0.68,
    9: 0.66, 10: 0.63, 11: 0.58, 12: 0.55, 13: 0.52, 14: 0.49, 15: 0.46,
    16: 0.44, 17: 0.41, 18: 0.38, 19: 0.35, 20: 0.32, 21: 0.29, 22: 0.26,
    23: 0.23, 24: 0.20, 25: 0.17, 26: 0.14, 27: 0.11, 28: 0.08, 29: 0.05,
    30: 0.035,
}


def test_qualifier_column_from_a_probability_source_is_not_rescaled():
    """The headline defect: a 16-qualifier column must survive intact."""
    out = devig_consensus(
        {"kalshi": _QUALIFIER_COLUMN},
        already_normalized=_ALREADY_PROBABILITY_SOURCES,
    )

    assert out[1] == pytest.approx(0.985), (
        "OKC's reconstructed price must stay 0.985; re-scaling by the column "
        "sum is what printed '▲93' under a 99% cell"
    )
    assert sum(out.values()) == pytest.approx(sum(_QUALIFIER_COLUMN.values()))


def test_the_defect_is_the_delta_not_the_level():
    """What a reader actually sees: merged - old_p on an unmoved market.

    Nothing moved, so every trend must be ~0. Under the old behaviour each
    old_p was merged/16.54 and the printed trend was ~94% of the cell.
    """
    old = devig_consensus(
        {"kalshi": _QUALIFIER_COLUMN},
        already_normalized=_ALREADY_PROBABILITY_SOURCES,
    )

    worst = max(abs(_QUALIFIER_COLUMN[k] - old[k]) for k in _QUALIFIER_COLUMN)
    assert worst < 0.001, f"an unmoved market must print no movement, saw {worst:.4f}"

    # And the specific number the issue reported, asserted as an upper bound so
    # this fails loudly if the re-scaling ever returns.
    okc_trend = _QUALIFIER_COLUMN[1] - old[1]
    assert okc_trend < 0.01, f"OKC printed +{okc_trend:.4f} (the bug printed +0.9253)"


def test_a_price_source_is_still_devigged():
    """The #1844 fix must not be undone: sportsbook columns still normalize.

    A three-way book column summing to 1.20 is a 20% overround, and removing it
    is the whole point of the historical reconstruction.
    """
    out = devig_consensus(
        {"fanduel": {1: 0.60, 2: 0.36, 3: 0.24}},
        already_normalized=_ALREADY_PROBABILITY_SOURCES,
    )

    assert sum(out.values()) == pytest.approx(1.0)
    assert out[1] == pytest.approx(0.50)


def test_mixed_sources_devig_only_the_price_half():
    """A market quoted by both kinds: each column keeps its own basis.

    fanduel's 1.20-sum column normalizes to 0.50; kalshi's 0.50 is already the
    probability. The consensus is the mean of two agreeing sources, not an
    artefact of normalizing one of them twice.
    """
    out = devig_consensus(
        {
            "fanduel": {1: 0.60, 2: 0.36, 3: 0.24},
            "kalshi": {1: 0.50, 2: 0.30, 3: 0.20},
        },
        already_normalized=_ALREADY_PROBABILITY_SOURCES,
    )

    assert out[1] == pytest.approx(0.50)


def test_default_is_unchanged_so_the_live_path_cannot_move():
    """``already_normalized`` defaults to empty.

    ``_aggregate_futures_outcomes`` (the live ingest path) shares this helper
    and passes Odds API columns only. It must keep de-vigging everything.
    """
    column = {"fanduel": {1: 0.60, 2: 0.36, 3: 0.24}}

    assert devig_consensus(column) == devig_consensus(
        column, already_normalized=frozenset()
    )
    assert sum(devig_consensus(column).values()) == pytest.approx(1.0)


def test_an_unclassified_source_is_still_devigged():
    """The default arm is the sportsbook arm, stated as a decision.

    A source absent from the frozenset is treated as a price source. That is
    deliberate — the Odds API book list churns without a code change — and it is
    why the source-scan below exists to catch a new PROBABILITY source.
    """
    out = devig_consensus(
        {"some_new_book": {1: 0.60, 2: 0.36, 3: 0.24}},
        already_normalized=_ALREADY_PROBABILITY_SOURCES,
    )
    assert sum(out.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# The classification cannot silently go stale
# ---------------------------------------------------------------------------

def test_the_two_source_sets_are_disjoint():
    assert not (_ALREADY_PROBABILITY_SOURCES & _DEVIGGED_AT_INGEST_SOURCES)


def _snapshot_writer_sources() -> set[str]:
    """Every string literal assigned to ``bookmaker=`` in the ingest tasks.

    A new source reaches ``futures_odds_snapshots`` by exactly this route, so
    scanning for the literal is how an unclassified one is caught at CI time
    rather than by a reader seeing a wrong arrow (memory: an allowlist whose
    default is a real value stores plausible wrong data).
    """
    tasks = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks"
    found: set[str] = set()

    for path in sorted(tasks.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            # ORM/Core form: FuturesOddsSnapshot(bookmaker="kalshi", ...)
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "bookmaker" and isinstance(kw.value, ast.Constant):
                        if isinstance(kw.value.value, str):
                            found.add(kw.value.value)
            # Bulk form: {"bookmaker": "kalshi", ...} passed to executemany.
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "bookmaker"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        found.add(value.value)
    return found


def test_every_snapshot_writer_source_is_classified():
    """A new ingest source must be put in one bucket or the other."""
    written = _snapshot_writer_sources()

    assert written, "the AST scan found no bookmaker= literals — the scan broke"

    unclassified = written - _ALREADY_PROBABILITY_SOURCES - _DEVIGGED_AT_INGEST_SOURCES
    assert not unclassified, (
        f"unclassified snapshot source(s): {sorted(unclassified)}. Decide whether "
        "each stores a PROBABILITY (add to _ALREADY_PROBABILITY_SOURCES) or a "
        "vig-inclusive PRICE (add to _DEVIGGED_AT_INGEST_SOURCES). Getting this "
        "wrong re-scales that source's 24h deltas by its own column sum (#6675)."
    )


def test_the_scan_sees_the_three_probability_writers():
    """Anchor the scan: if it stops finding these, it has silently gone blind.

    Stated reach, so nobody reads this guard as broader than it is: the scan
    finds sources written as a STRING LITERAL, which is exactly the three
    probability sources. The seven Odds API sportsbooks arrive through a
    dynamic ``market.bookmaker`` field and are invisible to it — that is
    tolerable, because an unrecognized source falls to the sportsbook arm
    (``test_an_unclassified_source_is_still_devigged``), which is already
    correct for them. The failure this guard exists to prevent is a new
    PROBABILITY source being de-vigged, and such a source is added the same way
    these three were.
    """
    written = _snapshot_writer_sources()
    for source in ("kalshi", "polymarket", "datagolf_model"):
        assert source in written, f"scan lost {source}; it no longer guards anything"
