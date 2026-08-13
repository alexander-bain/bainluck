"""LAT-P046 — the /typeahead TEAM POOL is a recall device, and its shape is the guard.

The behavioural proof lives in ``tests/integration/test_search_recall_contract.py``
(``test_typeahead_team_pool_reaches_past_alphabetical_duplicates``) because the
ordering is evaluated by Postgres and nothing else can evaluate it. That file
needs a real database and **skips in the sandbox**, so the properties that are
checkable without one are checked here instead of not at all.

What broke: the pool query was ``ORDER BY Team.name LIMIT 3``. Measured on
production, ``bruins`` matches 9 rows and the first three alphabetically are
three sport-variants of ONE school, so Boston Bruins was never fetched and the
name-dedup collapsed the three survivors into a single candidate. A pool of
three slots yielded one. Three of the seven residual ``entity_top_1`` failures
were this shape, and no ranking change can reach any of them.
"""

import inspect
import re

from app.routes import events as events_route
from app.utils.search_match_class import PROMINENT_SPORT_KEYS


def _team_pool_block() -> str:
    """The source of the team-pool section of `typeahead_search`, comments out.

    Sliced rather than read whole: the section is heavily commented and the
    comments QUOTE the alphabetical ordering they replaced, so a substring check
    against raw source would match the explanation instead of the code.
    """
    src = inspect.getsource(events_route.typeahead_search)
    start = src.index("# 1. Teams")
    end = src.index("# 2. Events", start)
    return "\n".join(
        line
        for line in src[start:end].splitlines()
        if not line.lstrip().startswith("#")
    )


def test_prominence_is_the_scorers_set_not_a_second_copy():
    """The pool must order by the SAME notion of prominent the scorer ranks by.

    Two copies of this set is one copy that drifts, and the failure would be
    silent: the pool would fetch by one definition of "the team a user probably
    means" while `rank_key` ranked by another, so the candidate the scorer would
    have picked is the one the pool stopped fetching.
    """
    assert events_route._POOL_PROMINENT_SPORT_KEYS == tuple(sorted(PROMINENT_SPORT_KEYS))


def test_the_fetch_is_wider_than_the_pool_the_scorer_sees():
    """Widening the FETCH is what fixes recall; widening the POOL is not the fix.

    Name-duplicates and individual-sport rows are discarded in Python, and with
    fetch == pool they were discarded AFTER consuming a slot. The scorer's input
    size is deliberately unchanged at 3 — the queue's warning that "the obvious
    fix is wrong" is about the candidate set, and this does not widen it.
    """
    assert events_route._TEAM_POOL_SIZE == 3
    assert events_route._TEAM_POOL_FETCH_LIMIT > events_route._TEAM_POOL_SIZE


def test_the_pool_is_no_longer_ordered_alphabetically_first():
    block = _team_pool_block()
    assert ".order_by(team_prominence_order" in block, (
        "the pool's ORDER BY no longer leads with prominence — "
        f"got: {block!r}"
    )
    assert not re.search(r"\.order_by\(\s*Team\.name\s*\)", block), (
        "bare alphabetical ordering is back on the team pool; that is the defect"
    )


def test_the_fetch_limit_is_the_named_constant():
    """A literal here is how the two numbers silently became one again."""
    block = _team_pool_block()
    assert ".limit(_TEAM_POOL_FETCH_LIMIT)" in block
    assert ".limit(3)" not in block


def test_the_pool_is_capped_after_the_discards_not_before():
    """The cap must sit BELOW the individual-sport `continue`.

    Above it, a tennis player row would count against the three and the fix
    would reintroduce the bug it removes — slots consumed by rows that are
    thrown away.
    """
    block = _team_pool_block()
    discard = block.index("if _is_individual_sport(row.sport_key):")
    cap = block.index("if len(team_pool) >= _TEAM_POOL_SIZE:")
    assert discard < cap, (
        "the pool cap runs before the individual-sport discard, so discarded "
        "rows consume slots again"
    )
