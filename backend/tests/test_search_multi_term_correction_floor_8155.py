"""#8155 — the multi-term "did you mean" floor, pinned where Postgres is absent.

The behavioural guards for this ship live in
``tests/integration/test_search_recall_contract.py`` and need a real Postgres with
``pg_trgm``; that suite runs in the dedicated ``search-recall`` CI job, not on
every invocation. The floor itself is a bare float that anything could nudge, and
its safe window is **0.017 wide** — so it gets a guard that runs everywhere.

The window is not a preference. Measured read-only on production 2026-09-23 with
``word_similarity`` over ``teams``, on the 12 distinct ``origin='user'``
zero-result multi-term queries in ``search_query_logs`` plus five synthetic
members of the reported class:

    WANT corrected                                    REFUSE
    los angeles lakerz -> Los Angeles Lakers  0.8889  france d'or -> France          0.5833
    green bay packrs   -> Green Bay Packers   0.8235  queens club -> Queens (NC)     0.5833
    boston red socks   -> Boston Red Sox      0.7647  soccer d'or -> Soccer Intell.  0.5833
    red socks          -> Boston Red Sox      0.6000  as roma vs. fc barcelona       0.5417
                                                      bitcoin price 2026 -> N. Price 0.3158

So any floor in ``(0.5833, 0.6000]`` is correct and anything outside it ships a
defect: too low asserts "did you mean France" to somebody searching for the Ballon
d'Or, too high puts ``red socks`` — the query a TestFlight tester actually
reported — back on a blank page.
"""

from app.routes.events import (
    _SEARCH_MULTI_TERM_CORRECTION_FLOOR,
    _strip_search_scaffolding,
)

#: The best-scoring query that MUST still be refused, and the worst-scoring one
#: that MUST still be corrected. Both measured; see the module docstring.
WORST_REFUSED_WORD_SIMILARITY = 0.5833333
BEST_WANTED_WORD_SIMILARITY = 0.6  # `red socks` -> Boston Red Sox


def test_the_floor_refuses_every_measured_false_correction():
    """Too low and `france d'or` is answered "did you mean France"."""
    assert _SEARCH_MULTI_TERM_CORRECTION_FLOOR > WORST_REFUSED_WORD_SIMILARITY, (
        f"floor {_SEARCH_MULTI_TERM_CORRECTION_FLOOR} does not exclude the "
        f"measured false-correction band at {WORST_REFUSED_WORD_SIMILARITY} "
        "(france d'or -> France, queens club -> Queens (NC), soccer d'or -> "
        "Soccer Intellectuals). Lowering it asserts a wrong club to the reader, "
        "which the `fed` guard in the recall contract rules is worse than an "
        "empty bucket."
    )


def test_the_floor_still_rescues_the_query_this_ship_exists_for():
    """Too high and `Red socks` goes back to the blank page a tester reported."""
    assert _SEARCH_MULTI_TERM_CORRECTION_FLOOR < BEST_WANTED_WORD_SIMILARITY, (
        f"floor {_SEARCH_MULTI_TERM_CORRECTION_FLOOR} excludes `red socks` -> "
        f"Boston Red Sox, which scores exactly {BEST_WANTED_WORD_SIMILARITY}. "
        "That is the single query #8155 was filed for. Note the comparison is "
        "strict on purpose: word_similarity returns float4 and a literal is "
        "float8, so a floor OF 0.6 is a knife-edge on this exact value."
    )


def test_the_reported_query_really_does_take_the_multi_term_path():
    """The premise, pinned — otherwise both tests above guard nothing.

    If `red socks` were reduced to one term by scaffold stripping it would take
    the single-term arm, the floor would never be consulted, and this whole ship
    would be inert. `socks` is not scaffolding and must not become so.
    """
    assert len(_strip_search_scaffolding(["red", "socks"])) == 2, (
        "`red socks` no longer survives scaffold stripping as two terms, so the "
        "multi-term correction arm it was written for is now unreachable and the "
        "floor guards nothing (#8155)"
    )


def test_the_floor_is_not_accidentally_disabled():
    """A floor of 0 or None would let every near-miss through while still being
    "a number in the file". The band tests above would catch 0, but not None."""
    assert isinstance(_SEARCH_MULTI_TERM_CORRECTION_FLOOR, float), (
        "the multi-term correction floor must be a plain float compared in SQL; "
        f"got {type(_SEARCH_MULTI_TERM_CORRECTION_FLOOR).__name__}"
    )
