"""#4365 part 2 — move the two NHL prop rows a since-fixed cascade order left as basketball.

## what these rows are, and why the classifier fix cannot reach them

``PIT Penguins at PHI Flyers: Points`` and its ``: Assists`` sibling are stored
``llm_sport_category = 'basketball'``. They are Kalshi NHL game props, created
2026-04-22 under tickers ``KXNHLPTS-26APR22PITPHI`` and ``KXNHLAST-26APR22PITPHI``.

On this HEAD the shipped classifier already answers ``hockey`` for both: step 1
of the cascade resolves the ticker to ``icehockey_nhl`` and the ticker is
consulted FIRST. **The ordering is the whole story, and it is younger than the
rows.**

Dated from the history rather than reasoned about:

* the rows were ingested **2026-04-22 16:45:24 UTC**;
* ``97862989`` *"Fix Kalshi sport misclassification: ticker before name rules"*
  is dated **2026-04-22 17:34:44 −0700** = 2026-04-23 00:34 UTC — roughly eight
  hours after the rows already existed, and that is its commit time, not its
  deploy;
* before that commit, step 2 (name rules) ran BEFORE the ticker.

So the ticker was never missing: ``kxnhlpts`` and ``kxnhlast`` entered the map on
2026-03-30 in ``2e2b2dba``. It simply did not get to speak first. The name rules
did, and ``_STAT_TO_SPORT`` — a table headed *"Stats that uniquely identify a
sport"* — maps ``points`` and ``assists`` to basketball. Both are core NHL stats,
so the table's premise is false for exactly those two keys.

``97862989``'s own message describes the identical symptom for another market:
``KXNHLEAST-26`` stored ``basketball`` and therefore invisible in the NHL grid.

The ordering has since been fixed. The rows have not, because
``app/tasks/kalshi.py`` writes the tag through::

    coalesce(nullif(FuturesMarket.llm_sport_category, "other"), sport_category)

which is #1888's honest-empty rule: **an existing real tag is never
overwritten.** A row stamped ``basketball`` in April keeps ``basketball``
through every poll since, and will forever.

## the harm, seen rather than reasoned about

``https://bainluck.com/futures/12508872`` at 390px: the eyebrow reads **NHL**
and so does "Part of: NHL", because those come from the event. The page then
ends in a **MORE BASKETBALL** rail offering four college-basketball
championships. That rail is ``frontend/app/futures/[id]/page.tsx:958-965``,
whose heading *and* whose contents key straight off ``llm_sport_category``::

    tags={[`sport:${market.llm_sport_category}`]}

So the wrong column is not an internal detail here — it is the only input to a
section of the page.

## why it is id-bound AND evidence-gated, not one or the other

Identical in shape to ``repair_kalshi_senate_category`` (#4229/#4365 part 1),
and deliberately so — that rail is certed and live, and this is the same class
of defect with a different target category. Both gates must pass:

1. **the id is in** :data:`NHL_PROP_ROW_IDS` — a frozen, enumerated bound, and
2. **the SHIPPED classifier independently says** ``hockey`` **for that row's own
   stored name and ticker**, and
3. the row is really ``source='kalshi'`` and is not already ``hockey``.

Gate 2 is what makes the id list safe rather than merely short. Put a genuine
basketball prop's id in the bound by mistake and the repair REFUSES it, because
``_categorize_kalshi_market`` returns ``basketball`` for that name. The test
proves that with a control row rather than asserting it in prose.

## a sibling module, not a widening

``repair_kalshi_senate_category.TARGET_CATEGORY`` is ``politics`` and is pinned
by a source-scan guard that forbids every sport token in that module's
literals — the guard exists because a repair growing sport vocabulary of its own
is how these rails drift from the poller. Widening that constant to take a
parameter would delete the guard's subject. So this is a separate module with
its own frozen bound.

The duplication is real and is the cheaper of the two mistakes today. If a third
of these appears, consolidate them **then**, with all three id lists in hand.

## no second classifier

This module contains no sport keywords beyond :data:`TARGET_CATEGORY` itself, no
regex over market names, and no cascade of its own. It asks
``app.tasks.kalshi._categorize_kalshi_market``, the exact function the Kalshi
ingest path calls, so the repair cannot disagree with the poller.

🔴 The guard here CANNOT be the senate module's "no sport literals" scan,
because this rail's target *is* a sport. It is instead: the target token appears
exactly once, and no other sport token appears at all. See
``test_the_only_sport_word_in_this_module_is_the_target``.

## D51 — backup and restore

Every planned change carries its ``before`` value in the returned payload, on
the dry run as well as the apply, and ``apply=True`` logs the restore statement.
The undo is one statement and it is exact, because the ids are enumerated::

    UPDATE futures_markets SET llm_sport_category = 'basketball'
     WHERE id IN (<the ids reported as changed>);
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select, update

from app.models import FuturesMarket

logger = logging.getLogger(__name__)


#: The enumerated bound. Measured on production 2026-09-09 by lane1b/109.
#:
#: The census: every row whose name matches the game-prop shape
#: ``^.+ (at|vs\.?|@) .+: *(points|assists)`` and is stored ``basketball``
#: (1,609 rows), replayed through the SHIPPED classifier. It disagreed on
#: exactly two. The other 1,607 are correctly basketball and gate 2 refuses
#: every one of them.
#:
#: 🔴 THIS LIST IS A BOUND, NOT A CLAIM THAT THESE ROWS ARE WRONG. The claim
#: that a row is wrong is made by the shipped classifier, per row, at run time.
NHL_PROP_ROW_IDS: tuple[int, ...] = (
    12508872,  # PIT Penguins at PHI Flyers: Points   (KXNHLPTS-26APR22PITPHI)
    12508876,  # PIT Penguins at PHI Flyers: Assists  (KXNHLAST-26APR22PITPHI)
)

#: The only category this repair is allowed to write. Named once, here, so the
#: source-scan guard can assert this module has no other sport vocabulary.
TARGET_CATEGORY = "hockey"


def _shipped_classification(name: str, external_id: Optional[str]) -> str:
    """Ask the SHIPPED Kalshi ingest classifier, never a copy of it.

    Imported inside the function for the same reason ``app/tasks/kalshi.py``
    imports its own helpers late: this module is reached from a route, and the
    task module pulls in the Kalshi client at import time.

    ``kalshi_category`` is passed as ``None`` deliberately. It is the *fallback*
    arm of the cascade, reached only when the ticker, the name rules and league
    detection have all declined; supplying a value here could carry a row on
    venue metadata the name evidence does not support, which is exactly the kind
    of "second opinion" this repair must not invent.

    ``external_id`` is passed and matters: for this cohort the ticker IS the
    evidence — it is what the classifier now reads FIRST and, in April, read
    only after the name rules had already answered.
    """
    from app.tasks.kalshi import _categorize_kalshi_market

    return _categorize_kalshi_market(name or "", None, event_ticker=external_id)


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    🔴 ONE STATEMENT PER DISTINCT BEFORE-VALUE, not one statement for all rows.
    The senate sibling's first version interpolated the before-value *map* where
    the value belongs, producing a line that looks like a restore and is not
    one — worse than no restore line at all, since D51 is granted on the promise
    that a runnable one-command undo exists.

    Today every row in the bound is `basketball`, so this emits one statement;
    if the bound ever spans two prior categories it emits two, and neither is
    wrong.
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
    """Plan (and optionally apply) the #4365 part 2 category correction.

    Returns a payload complete enough to BE the D51 backup: every row
    considered, its stored category, what the shipped classifier says, and a
    verdict with a named reason for each refusal.
    """
    rows = (
        await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.source,
                FuturesMarket.external_id,
                FuturesMarket.llm_sport_category,
            ).where(FuturesMarket.id.in_(NHL_PROP_ROW_IDS))
        )
    ).all()

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
            # This rail gates on a Kalshi ticker; a row from another venue has
            # no such evidence and must not be judged by this classifier.
            refused.append({**record, "reason": "not_kalshi"})
        elif verdict != TARGET_CATEGORY:
            # THE GATE THAT MAKES THE ID LIST SAFE.
            refused.append({**record, "reason": "classifier_disagrees"})
        elif row.llm_sport_category == TARGET_CATEGORY:
            refused.append({**record, "reason": "already_correct"})
        else:
            planned.append(record)

    missing = sorted(set(NHL_PROP_ROW_IDS) - {r.id for r in rows})

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
            "#4365 part 2 repair applied: %s rows -> %s. D51 RESTORE:\n%s",
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
