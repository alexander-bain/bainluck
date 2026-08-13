"""Emit the REAL `/api/events/search` futures arm as runnable SQL, for any query.

WHY THIS FILE EXISTS
--------------------
#1794 asks for a before/after on the `fed` arm's block count. It has been owed
for three cycles, and the reason is the same every cycle: the NUMBER was
recorded and the QUERY was not. "3,158 -> 999 shared blocks" is not
re-runnable by anyone except the person who typed the query, and that person
did not write it down. LAT-P045 measured 10,020 blocks for what it believed
was the same arm and could not tell a regression from a scope mismatch --
because there was nothing to compare the SQL against.

A performance criterion phrased as a number without the query that produces it
is not a criterion. It is an anecdote with a decimal point.

So this compiles the arm FROM THE LIVE ORM rather than from memory. It imports
the same helpers `search_events()` uses, assembles the same UNION of recall
arms with the same pushed-down open/unresolved filters, and prints it with
literal binds. If the route's recall arms change, this output changes with
them; a hand-copied SQL blob in an issue comment would not.

It deliberately selects only `futures_markets.id` and omits the
`selectinload()` eager loads: those are separate round trips and are not part
of the arm whose plan is under measurement.

USAGE
-----
    python3 scripts/explain_search_arm.py fed
    python3 scripts/explain_search_arm.py "march madness" --arm name

Then hand the SQL to the query-plan rail (see CLAUDE.md), which is the only
path that reaches production -- TCP 5432 egress is blocked from an agent
session, so `pg:psql` is not available (gotcha #125):

    POST /api/admin/db-query
    {"sql": "<output>", "explain": true, "analyze": true, "timeout_ms": 25000}

`--arm name` isolates the name arm alone. That decomposition is what showed the
outcome arm to be 71% of `fed`'s total blocks, independently reproducing the
69% already recorded in the comment at `events.py:2963`.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import case, or_, select, union
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes import events as E


def _outcome_id_match(term: str, exp: str | None):
    """Mirror of the nested helper at `events.py:2886`.

    Inlined, not imported, because it is defined inside `search_events()` and
    is therefore unreachable from module scope. Keep the two in step.
    """
    return FuturesMarket.id.in_(
        select(FuturesOutcome.market_id).where(
            E._build_expanded_ilike(FuturesOutcome.name, term, exp)
        )
    )


def build_futures_arm(query: str, arm: str = "all"):
    """Rebuild the futures candidate query for `query` exactly as the route does."""
    terms = E._strip_search_scaffolding(query.strip().split())
    expanded = E._apply_search_synonyms(E.expand_search_terms(terms))

    if len(terms) > 1:
        futures_name_ilike = E.and_(
            *[E._futures_name_match_term(t, x) for t, x in expanded]
        )
        futures_outcome_match = E.and_(
            *[_outcome_id_match(t, x) for t, x in expanded]
        )
    else:
        term, exp = expanded[0]
        futures_name_ilike = E._futures_name_match_term(term, exp)
        # LAT-P010/#1494 GAP 1: a single sub-3-char term drops itself from the
        # outcome arm and keeps only its expansion.
        if not E._has_extractable_trigram(term):
            futures_outcome_match = _outcome_id_match(exp, None) if exp else None
        else:
            futures_outcome_match = _outcome_id_match(term, exp)

    league_ticker_match = E._build_league_ticker_match(expanded)

    if arm == "name":
        arms = [futures_name_ilike]
    else:
        arms = [
            a
            for a in (futures_name_ilike, futures_outcome_match, league_ticker_match)
            if a is not None
        ]
        arms.extend(E._alias_futures_arms(terms))

    # AND distributes over UNION, so the open/unresolved filter is pushed into
    # each arm as well as kept on the outer query -- see the long comment at
    # `events.py:3031`. Unfiltered arms cost `nba champion` 6,387ms vs 701ms.
    open_now = (
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= datetime.now(timezone.utc),
        ),
    )
    arm_selects = [select(FuturesMarket.id).where(a, *open_now) for a in arms]
    if len(arm_selects) > 1:
        candidates = union(*arm_selects).subquery()
        candidate_filter = FuturesMarket.id.in_(select(candidates.c.id))
    else:
        candidate_filter = FuturesMarket.id.in_(arm_selects[0])

    rank = E._search_rank_tsquery(
        E._weighted_search_vector(
            FuturesMarket.name, E._SEARCH_FUTURES_MARKET_WEIGHT
        ),
        E._expanded_tsquery(expanded),
    )
    whens = [(futures_name_ilike, 0)]
    if arm != "name" and league_ticker_match is not None:
        whens.append((league_ticker_match, 1))

    stmt = (
        select(FuturesMarket.id)
        .where(candidate_filter, *open_now)
        .order_by(
            case(*whens, else_=2).asc(),
            rank.desc(),
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume.desc().nulls_last(),
            FuturesMarket.updated_at.desc(),
        )
        .limit(E._SEARCH_FUTURES_WINDOW)
    )
    return stmt, terms, expanded, len(arms)


def compile_sql(stmt) -> str:
    """Literal-bind and unescape.

    SQLAlchemy doubles `%` when compiling with literal binds for a paramstyle
    that treats it as a placeholder. Left as `%%`, every ILIKE in the output
    matches a literal percent sign and the query silently returns nothing --
    which would look like a fast plan rather than a broken one.
    """
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).replace("%%", "%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="the search query, e.g. fed")
    ap.add_argument(
        "--arm",
        choices=("all", "name"),
        default="all",
        help="'all' = the production UNION; 'name' = the name arm alone",
    )
    args = ap.parse_args()

    stmt, terms, expanded, n_arms = build_futures_arm(args.query, args.arm)
    print(f"-- query={args.query!r} arm={args.arm}")
    print(f"-- terms={terms}")
    print(f"-- expanded={expanded}")
    print(f"-- recall arms={n_arms}")
    print(compile_sql(stmt))


if __name__ == "__main__":
    main()
