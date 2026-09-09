"""#4229 — move the Kalshi Senate rows the shipped classifier can no longer mislabel.

## why this module has to exist at all

The classifier half of #4229 (`_AMBIGUOUS_EVIDENCE` gains ``senators``, plus a
strong-evidence rule keyed on senate/senator co-occurring with a legislative
act) makes every one of these rows come back ``politics``. It still does not
move a single stored row, and the difference is the whole ship.

``app/tasks/kalshi.py`` writes the tag through::

    coalesce(nullif(FuturesMarket.llm_sport_category, "other"), sport_category)

which is #1888's honest-empty rule: **an existing real tag is never
overwritten.** So a row already stamped ``hockey`` keeps ``hockey`` through
every future poll, forever, no matter what the classifier now says.

🔴 **CORRECTION (lane1b/106, 2026-09-09).** This paragraph used to continue:
"Polymarket is the opposite — ``app/tasks/polymarket.py`` assigns
unconditionally, so its four rows in this class retag on the next poll and are
deliberately NOT in scope here." The first clause is true; **the second does not
follow, and CERT-2376 quoted it as covering the whole twelve-row cohort.** A
writer only rewrites a row it is handed, and Polymarket discovery never hands it
these: the scan is 10.6 hours wide and both remaining events are months outside
it (``updated_at`` 2026-05-17 and 2026-06-18, on a poll that stamps
``func.now()`` every upsert). Two of the four DID self-heal, because they were
inside the horizon — which is why the claim survived a builder and a grader. **A
claim about the WRITE is not a claim about the ROW.** The Polymarket half is
``app/tasks/repair_polymarket_senate_category.py``, which gates on the venue's
own tags; it is out of scope *here* because the evidence channel differs, not
because those rows correct themselves.

CERT-2372 blocked the classifier-only SHA for exactly this reason: the Fed
Chair card still reads HOCKEY after deploy. This is the named repair,
``4229-BACKFILL-THE-FOUR-LIVE-SENATE-ROWS``.

## why it is id-bound AND evidence-gated, not one or the other

An id list alone is a blind write: if an id is wrong, stale, or recycled, the
repair relabels a real hockey market and nothing objects. A predicate alone
(``name ILIKE '%senat%' AND llm_sport_category='hockey'``) is unbounded: it
would sweep the 133 resolved Belleville/Ottawa rows that legitimately match
that name pattern.

So both gates must pass for a row to move:

1. **the id is in** :data:`SENATE_ROW_IDS` — a frozen, enumerated bound, and
2. **the SHIPPED classifier independently says** ``politics`` **for that row's
   own stored name**, and
3. the row is really ``source='kalshi'`` and is not already ``politics``.

Gate 2 is what makes this safe rather than merely bounded. Put an
Ottawa/Belleville id in the list by mistake and the repair REFUSES it, because
``_categorize_kalshi_market`` returns ``hockey`` for that name. The test proves
this with a control row rather than asserting it in prose.

## no second classifier

The single most likely way this rail rots is by growing sport rules of its own
and drifting from the shipped one — the failure Q495 guards against in the
Polymarket sibling. This module therefore contains **no sport keywords**, no
regex over market names, and no category literal other than the two it must
name to express "did this become politics, and was it a sport before". It asks
``app.tasks.kalshi._categorize_kalshi_market``, which is the exact function the
Kalshi ingest path calls, so the repair cannot disagree with the poller.
``test_repair_carries_no_sport_rules_of_its_own`` fails if that changes.

## D51 — backup and restore

Every planned change carries its ``before`` value in the returned payload, and
``apply=True`` logs the restore statement. The undo is one statement, and it is
exact because the ids are enumerated::

    UPDATE futures_markets SET llm_sport_category = 'hockey'
     WHERE id IN (<the ids reported as changed>);

There is no separate backup table: the before-state of eight rows is one
column of one enumerated set, so a table would be more moving parts, not more
safety. The payload IS the backup and it is written to the task log.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select, update

from app.models import FuturesMarket

logger = logging.getLogger(__name__)


#: The enumerated bound. Measured on production 2026-09-09 by lane1b/104 (the
#: OPEN rows) and lane1b/108 (the resolved tail, #4365 part 1): every Kalshi row
#: whose name matches ``senat*``, that is stored under a sport category, and
#: that the shipped classifier calls ``politics``.
#:
#: The census that produced it also returned six OPEN rows that are genuinely
#: hockey (``59693566`` NHL: OTT Senators Total Points, and five Polymarket
#: ``Senators vs. …`` matchups). They are absent here by measurement, and gate 2
#: would refuse them anyway.
#:
#: 🔴 THIS LIST IS A BOUND, NOT A CLAIM THAT THESE ROWS ARE WRONG. The claim
#: that a row is wrong is made by the shipped classifier, per row, at run time.
SENATE_ROW_IDS: tuple[int, ...] = (
    109237,    # Which Senators will vote for Kevin Warsh as Fed chair?
    109373,    # How many Senators will vote for Kevin Warsh for Fed Chair?
    109593,    # How many Republican senators will lose reelection in 2026?
    109595,    # How many Democratic Senators will lose reelection in 2026?
    20269743,  # Which Senators will vote for Kari Lake?
    25924671,  # How many Senators will vote for the Clarity Act?
    25924714,  # Which Senators will vote for the Clarity Act?
    59693468,  # Which Senators will vote for Heidi Overton?
    # ---- #4365 part 1, the resolved tail (lane1b/108, 2026-09-09) ----------
    # #4229 shipped the OPEN rows only, and disclosed this remainder rather than
    # widening its frozen bound after the cert. The population is NOT the 133
    # rows the name class matches: replaying `_shipped_classification` over
    # every non-open Kalshi `senat*` row stored under a sport category returns
    # `hockey` for 130 of them (Belleville/Ottawa/AHL) and `politics` for these
    # three. Gate 2 is what draws that line, so the three ids below are the
    # measurement's OUTPUT, not its input — put a Belleville id here and the
    # repair still refuses it.
    31835562,  # How many Senators will vote to confirm Todd Blanche as AG?
    33282801,  # Which Senators will vote for Todd Blanche?
    52755933,  # How many Senators vote to confirm Jay Clayton as DNI?
)

#: The only category this repair is allowed to write. Named once, here, so the
#: source-scan guard can assert the module has no other category vocabulary.
TARGET_CATEGORY = "politics"


def _shipped_classification(name: str, external_id: Optional[str]) -> str:
    """Ask the SHIPPED Kalshi ingest classifier, never a copy of it.

    Imported inside the function for the same reason ``app/tasks/kalshi.py``
    imports its own helpers late: this module is imported by a route, and the
    task module pulls in the Kalshi client at import time.

    ``kalshi_category`` is passed as ``None`` deliberately. It is the *fallback*
    arm of the cascade, reached only when name rules and league detection have
    both declined; supplying a value here could carry a row on venue metadata
    that the name evidence does not support, which is exactly the kind of
    "second opinion" this repair must not invent.
    """
    from app.tasks.kalshi import _categorize_kalshi_market

    return _categorize_kalshi_market(name or "", None, event_ticker=external_id)


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    🔴 ONE STATEMENT PER DISTINCT BEFORE-VALUE, not one statement for all rows.
    The first version of this logged::

        UPDATE futures_markets SET llm_sport_category = {109237: 'hockey'}
         WHERE id IN (109237);

    — the before-value *map* interpolated where the value belongs, which is not
    valid SQL and would fail on paste. That is worse than no restore line: D51
    is granted to a repair that "ships a one-command restore", so a line that
    looks like one and is not is the exact thing the grant assumes away.

    Grouping by before-value is what makes a single statement honest. Today
    every row is `hockey`, so this emits one statement; if the bound ever spans
    two prior categories it emits two, and neither is wrong.
    """
    by_before: dict[Optional[str], list[int]] = {}
    for row in planned:
        by_before.setdefault(row["before"], []).append(row["id"])

    lines = []
    for before, ids in sorted(by_before.items(), key=lambda kv: str(kv[0])):
        ids_csv = ", ".join(str(i) for i in sorted(ids))
        value = "NULL" if before is None else f"'{before}'"
        lines.append(
            f"UPDATE futures_markets SET llm_sport_category = {value} "
            f"WHERE id IN ({ids_csv});"
        )
    return "\n".join(lines)


async def repair(session, apply: bool = False) -> dict[str, Any]:
    """Plan (and optionally apply) the #4229 Kalshi category correction.

    Returns a payload that is complete enough to be the D51 backup: every row
    considered, its stored category, what the shipped classifier says, and the
    verdict with a named reason for each refusal.
    """
    rows = (
        (
            await session.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.name,
                    FuturesMarket.source,
                    FuturesMarket.external_id,
                    FuturesMarket.llm_sport_category,
                ).where(FuturesMarket.id.in_(SENATE_ROW_IDS))
            )
        )
        .all()
    )

    planned: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []

    for row in rows:
        verdict = _shipped_classification(row.name, row.external_id)
        record = {
            "id": row.id,
            "name": row.name,
            "before": row.llm_sport_category,
            "classifier": verdict,
        }
        if row.source != "kalshi":
            # Polymarket rows self-heal on their own poll; this rail must not
            # race the writer that owns them.
            refused.append({**record, "reason": "not_kalshi"})
        elif verdict != TARGET_CATEGORY:
            # THE GATE THAT MAKES THE ID LIST SAFE.
            refused.append({**record, "reason": "classifier_disagrees"})
        elif row.llm_sport_category == TARGET_CATEGORY:
            refused.append({**record, "reason": "already_correct"})
        else:
            planned.append(record)

    missing = sorted(set(SENATE_ROW_IDS) - {r.id for r in rows})

    changed = 0
    if apply and planned:
        result = await session.execute(
            update(FuturesMarket)
            .where(FuturesMarket.id.in_([p["id"] for p in planned]))
            .values(llm_sport_category=TARGET_CATEGORY)
        )
        await session.commit()
        changed = result.rowcount or 0
        logger.warning(
            "#4229 repair applied: %s rows -> %s. D51 RESTORE:\n%s",
            changed,
            TARGET_CATEGORY,
            restore_sql(planned),
        )

    return {
        "examined": len(rows),
        "planned": planned,
        "refused": refused,
        "missing_ids": missing,
        "changed": changed,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # should be able to read the restore before deciding to apply, not only
        # in a log line they have to go and find afterwards.
        "restore_sql": restore_sql(planned),
        "terminal": "changed" if apply else "dry_run",
    }
