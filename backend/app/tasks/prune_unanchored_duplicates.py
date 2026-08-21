"""#2020 — the bounded delete rail for the unanchored-duplicate surplus.

REBUILT 2026-08-20 (queue 386) AFTER ``C-DELETE-RAIL-PRE`` RETURNED **BLOCK**
-----------------------------------------------------------------------------

The first version of this rail shipped with five safety properties and six defects.
Alex voided all 31 attended applies. The one sentence to carry through everything
below, because it is what made those six defects invisible:

    **The step-0 band re-check mitigates NONE of them. A band bounds CARDINALITY;
    every finding was about IDENTITY.** The rail could delete exactly the right
    *number* of rows and the wrong *rows*, and report success.

WHAT CHANGED, AND WHY IT IS SMALLER RATHER THAN BIGGER
-------------------------------------------------------

The instinct after a six-finding BLOCK is to add six guards. Four of the findings
instead collapse into **one structural change**, and the collapse is the design:

    **This rail now only ever deletes a row that carries NOTHING.**

Not "a row we believe is a duplicate" — a row with no provider anchor, no futures
link, and **zero child rows in all ten tables that hang off** ``events.id``. Follow
what that single rule does to the findings:

* **R1 (two real games can share the key, and the linked one wins with no identity
  evidence).** The rail no longer needs to prove the fixture key cannot join two
  distinct games, because it no longer decides *which game a row is*. A row with no
  anchor, no link and no children holds no observation about any game; deleting it
  cannot lose a distinct game's data, whichever game it "was". The live counter-
  specimen proves the rule bites: #2018's surplus row carried **101**
  ``win_prob_snapshots``, so under this rail it is **withheld, not deleted** — and
  ``TestTheHostileSpecimens`` re-runs codex's exact construction to show it.
* **R3 (unique history destroyed, exposure unpriced).** Nothing with history is
  deletable, so the destroyed-history figure is **zero by construction** rather than
  by measurement. The rail deletes no child rows at all; the child DELETE loop is
  *gone*, not guarded.
* **R4 (incomplete FK inventory).** ``ranking_judgments`` can no longer cause an FK
  violation and ``game_moments`` can no longer vanish by cascade, because a row with
  either is not deletable. The inventory is derived from schema metadata anyway
  (``app.utils.event_fk_inventory``) and an unclassified child **stops the rail**.
* **R5 (the never-absorbs test could be satisfied by a real transfer).** The rail
  issues no child statements whatsoever, so there is no repoint to hide. The test was
  strengthened separately — it now reads *executed statements*, not source text.

The two that needed real mechanism rather than deletion:

* **R2 (the dry run authorized a COUNT, not the rows Alex inspected).** Dry-run now
  returns a ``plan_hash``: a content address over the complete ordered id set. Apply
  **requires** it and **re-derives it inside the locked transaction** before any
  write. Same count, different set now refuses. This is #1949's lesson verbatim — *a
  work list that can be recomputed at apply time is a work list that can differ from
  the reviewed one.*
* **R6 (the verifier locked the surplus but not the keeper, in no deterministic
  order).** One lock statement, over candidates **and** keepers, ``ORDER BY id``.

WHAT #2057 RECUT, AND WHY IT IS THE SAME FINDING FROM THE OTHER SIDE
---------------------------------------------------------------------

#2057: **17/17 duplicate games carry markets on ONE copy only.** So a fixture can
present ``linked_copies == 1`` and the linked copy can still be the **wrong keeper** —
the unlinked copy may hold every odds snapshot, every win-probability reading, the
whole scoring record, while the "keeper" holds one market and nothing else. The old
keeper rule looked at futures links and *only* futures links, so it read that fixture
as clean and deleted the substance.

The recut is not a second rule bolted on. It is the same rule as above applied to the
keeper question: **a copy's claim to be surplus is measured across all ten child
tables, not across futures links alone.** A surplus row holding anything the keeper
does not is withheld and reported. Nothing is transferred to make it deletable —
transfer *is* ruling 048's harm.

THE PARTITION
-------------

A "fixture" is ``(home_team_name, away_team_name, commence_time)`` — exact time.
Fixtures split by how many copies hold a futures-market link: ``linked_copies == 1``
is Tranche A, the only prunable shape; ``0`` (B) and ``>= 2`` (C) have no keeper this
rail can determine and yield an empty batch **by construction**, not by the caller
remembering not to ask.

WHAT THIS COSTS, MEASURED
--------------------------

Of Tranche A's 60,889 surplus rows, ``C-EVENT-CHILD-CENSUS`` (10/10 tables,
2026-08-20) measured **1,214** carrying a ``win_prob_snapshots`` row and **16** a
``line_movement_analyses`` row; the other eight tables are zero. So the withhold rule
costs roughly **1,230 rows of the 60,889** — about 2% — and those 1,230 are precisely
the rows whose deletion would have been unrecoverable. The remaining ~59,659 are
empty by measurement and delete with nothing lost.

Note what the earlier modelled figure did here. R3 projected ``60,889 × 101 =
6,149,789`` child rows destroyed, extrapolating #2018's MLB row across an esports
partition. The measured total is **1,230**. The model was wrong by ~5,000×, in the
alarming direction — which is a reason to measure, not a reason to discount the
finding: it was right that the loss was **unpriced**, and being unpriced is what made
a 5,000× error possible in either direction.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import text

from app.utils.event_fk_inventory import (
    CASCADING_CHILD_TABLES,
    EVENT_PSEUDO_FK_SUBSTANCE,
    parent_substance_columns,
    parent_substance_predicate,
    pseudo_fk_substance_predicate,
    substance_tables,
    unclassified_event_children,
)

logger = logging.getLogger(__name__)

UNANCHORED_TAG = "provenance:unanchored"

#: Hard ceiling on a single call, above the default and below anything that could
#: be mistaken for "just run it once". ~61K rows is ~31 calls at the default.
MAX_DELETE_CEILING = 5000
DEFAULT_MAX_DELETE = 2000

#: The provider-id columns on ``events``. A row with ANY of them set is *anchored*,
#: and an anchored row is never this rail's to delete.
#:
#: ``provenance:unanchored`` is a **creation-history tag, not a standing claim that the
#: ids are null** — ``event_registry`` stamps it at creation and ``_attach_claim`` can
#: add a provider id later **without removing it**. The dated 0/0/0 census was an
#: observation; these columns make it an enforced invariant, re-derived from the row
#: itself under lock. That distinction is the whole of R1's first half.
ANCHOR_COLUMNS = ("external_id", "espn_id", "statpal_fixture_id")

PLAN_HASH_VERSION = "q386.1"


class PruneRefused(Exception):
    """The rail declined to delete. Never raised after a destructive statement."""


def _anchor_predicate(alias: str) -> str:
    return " AND ".join(f"{alias}.{col} IS NULL" for col in ANCHOR_COLUMNS)


def _substance_predicate(alias: str) -> str:
    """SQL true when the row holds NO observation — in a child table, in a polymorphic
    pseudo-FK, **or in its own columns**.

    Built from the derived inventory rather than a literal list, so a new child table
    in ``models.py`` widens this predicate automatically. ``NOT EXISTS`` per table
    rather than a count: we never need the number, only whether it is zero, and the
    planner can stop at the first row.

    **Rail v3 (C-DELETE-RAIL-PRE-R2 finding 1) adds the second and third clauses, and
    the second one is the BLOCK.** This predicate previously read only the ten child
    tables, so "childless" was silently equated with "carries nothing" — and codex
    executed the real ``prune()`` deleting a childless row that was the only record of a
    distinct completed 5–3 game. The event row is itself an observation; see
    ``parent_substance_columns()`` (derived from the live schema).
    """
    child = " AND ".join(
        f"NOT EXISTS (SELECT 1 FROM {t} c_{i} WHERE c_{i}.event_id = {alias}.id)"
        for i, t in enumerate(substance_tables())
    )
    return " AND ".join((
        child,
        parent_substance_predicate(alias),
        pseudo_fk_substance_predicate(alias),
    ))


def _partition_cte() -> str:
    """The partition, with identity and substance carried as first-class columns.

    The old version selected only names, exact time and futures-link presence. Both
    additions here are R1: an id-less, childless row is the only thing that can be
    deleted without making a correspondence claim.
    """
    return f"""
    WITH tagged AS (
        SELECT e.id,
               e.home_team_name,
               e.away_team_name,
               e.commence_time,
               EXISTS (
                   SELECT 1 FROM futures_markets fm WHERE fm.event_id = e.id
               ) AS linked,
               ({_anchor_predicate('e')})    AS anchor_free,
               ({_substance_predicate('e')}) AS empty_of_substance
          FROM events e
         WHERE e.sport_id = :sport_id
           AND e.event_tags @> CAST(:tag AS jsonb)
    ),
    fixtures AS (
        SELECT home_team_name, away_team_name, commence_time,
               COUNT(*) AS copies,
               COUNT(*) FILTER (WHERE linked) AS linked_copies,
               COUNT(*) FILTER (WHERE NOT anchor_free) AS anchored_copies,
               COUNT(*) FILTER (
                   WHERE NOT linked AND NOT empty_of_substance
               ) AS substantive_surplus
          FROM tagged
         GROUP BY 1, 2, 3
    ),
    partition_fixtures AS (
        SELECT * FROM fixtures WHERE linked_copies = :linked_copies
    )
    """


def _census_sql():
    return text(
        _partition_cte()
        + """
    SELECT COUNT(*)                                AS fixtures,
           COALESCE(SUM(copies), 0)                AS total_rows,
           COALESCE(SUM(linked_copies), 0)         AS keepers,
           COALESCE(SUM(copies - linked_copies), 0) AS surplus,
           COALESCE(SUM(anchored_copies), 0)       AS anchored_copies,
           COALESCE(SUM(substantive_surplus), 0)   AS withheld_substantive,
           -- R2 finding 4: the surplus must ACCOUNT. `anchored_copies` counts anchored
           -- ROWS, but one anchored copy withholds EVERY surplus row in its fixture, so
           -- reporting it as the withheld population left readers unable to reconcile
           -- why the live count shrank (one anchored keeper + ten empty siblings
           -- reported `withheld_anchored: 1` against 10 undeletable rows).
           -- This is the count of surplus rows withheld BECAUSE their fixture is
           -- anchored — a different number, in the same unit as `surplus`.
           COALESCE(SUM(
               CASE WHEN anchored_copies > 0
                    THEN copies - linked_copies - substantive_surplus
                    ELSE 0 END
           ), 0)                                   AS withheld_due_to_anchor,
           COALESCE(SUM(
               CASE WHEN anchored_copies = 0
                    THEN copies - linked_copies - substantive_surplus
                    ELSE 0 END
           ), 0)                                   AS deletable
      FROM partition_fixtures
    """
    )


def _batch_sql():
    """The candidate batch: unlinked, anchor-free, childless, in an anchored fixture-free
    fixture. Ordering is total for one state (``commence_time``, then ``id``) — that is
    necessary for a reproducible batch and, per R2, nowhere near sufficient to bind two
    transactions. The ``plan_hash`` does that.
    """
    return text(
        _partition_cte()
        + """
    SELECT t.id
      FROM tagged t
      JOIN partition_fixtures p
        ON p.home_team_name = t.home_team_name
       AND p.away_team_name = t.away_team_name
       AND p.commence_time  = t.commence_time
     WHERE t.linked = false
       AND t.anchor_free = true
       AND t.empty_of_substance = true
       AND p.anchored_copies = 0
     ORDER BY t.commence_time ASC, t.id ASC
     LIMIT :cap
    """
    )


def _lock_sql():
    """R6 — ONE statement, candidates AND keepers, ``ORDER BY id``.

    The old verifier put ``FOR UPDATE`` on the outer ``events e`` only and read the
    keeper through a correlated ``EXISTS`` with no lock at all, so a concurrent
    delete/merge could remove the keeper after the check while this transaction still
    owned the surplus — **both copies gone**, which is unrecoverable fixture loss. And
    with no ``ORDER BY`` on 2,000 candidate locks, two overlapping callers acquire in
    planner order and deadlock (gotcha #13).

    Both are fixed by locking the union in one statement in ascending id order.
    ``FOR UPDATE`` on the keeper is stronger than the ``FOR KEY SHARE`` strictly needed
    to stop it being deleted; the extra strength is deliberate. Split strengths mean
    split statements, split statements mean two lock acquisitions that can interleave,
    and this is an attended operation of ~2,000 rows where deadlock-freedom is worth
    more than write concurrency against 2,565 esports keepers.
    """
    return text(
        """
        SELECT e.id
          FROM events e
         WHERE e.id = ANY(:ids)
         ORDER BY e.id ASC
           FOR UPDATE
        """
    )


def _reverify_sql():
    """Re-derive EVERY selection property from the locked row itself.

    Not a re-read of the batch query: the batch query proves the candidate set was
    chosen correctly, this proves the rows *in hand* are still safe to destroy, and
    those become different claims the moment anything else can write to ``events``.
    Same redundancy and same reason as ``event_absorption_guard.assert_absorbable_now``.
    """
    return text(
        f"""
    SELECT e.id,
           (e.sport_id = :sport_id)              AS right_sport,
           (e.event_tags @> CAST(:tag AS jsonb)) AS tagged,
           NOT EXISTS (
               SELECT 1 FROM futures_markets fm WHERE fm.event_id = e.id
           )                                     AS unlinked,
           ({_anchor_predicate('e')})            AS anchor_free,
           ({_substance_predicate('e')})         AS empty_of_substance,
           EXISTS (
               SELECT 1
                 FROM events k
                 JOIN futures_markets fm ON fm.event_id = k.id
                WHERE k.id <> e.id
                  AND k.sport_id       = e.sport_id
                  AND k.home_team_name = e.home_team_name
                  AND k.away_team_name = e.away_team_name
                  AND k.commence_time  = e.commence_time
           )                                     AS keeper_exists
      FROM events e
     WHERE e.id = ANY(:ids)
    """
    )


_REVERIFY_PROPERTIES = (
    "right_sport",
    "tagged",
    "unlinked",
    "anchor_free",
    "empty_of_substance",
    "keeper_exists",
)


def compute_plan_hash(
    *, sport_id: int, linked_copies: int, ids: list[int]
) -> str:
    """A content address over the COMPLETE ordered id set.

    R2's fix. The dry run publishes this; apply requires it and re-derives it inside
    the locked transaction. A count-preserving swap — codex's executed specimen went
    ``dry_batch=[101,102]`` then ``apply_batch=[99,102]``, same in-band count — changes
    the hash and refuses.

    The ids are hashed **in batch order, not sorted**: order is part of what was
    reviewed, and a reordering means the LIMIT would have cut somewhere else.

    ``sport_id`` and ``linked_copies`` are inside the digest so a plan cannot be
    replayed against a different partition that happens to yield the same ids.
    """
    payload = json.dumps(
        {
            "v": PLAN_HASH_VERSION,
            "sport_id": sport_id,
            "linked_copies": linked_copies,
            "ids": ids,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class CensusDoesNotAccount(PruneRefused):
    """The census's own populations do not sum to the surplus it reported.

    **C-DELETE-RAIL-PRE-R3 finding 3 (P2): this inherited from ``Exception``, so it
    escaped the route as an uncaught 500 with neither an explicit rollback nor a
    commit.** The arithmetic guard existed and was correct; its promised operational
    behaviour did not, and the difference is invisible from inside the rail.

    Subclassing ``PruneRefused`` is the whole fix: the route already translates that
    into a named **409**, and a refusal is a 409 rather than a 500 because the rail
    worked correctly and declined. A guard whose only observable effect is a stack
    trace teaches the operator that the rail is broken, when what it is actually
    saying is that the population moved.
    """


async def census(session, *, sport_id: int, linked_copies: int) -> dict[str, int]:
    """Count the partition. Pure read — safe to call on any path.

    **R2 finding 3: the operating census must state its EXACT withheld and deletable
    populations at run time, and they must ACCOUNT.** Every surplus row is in exactly
    one of three buckets — withheld because it holds substance, withheld because its
    fixture carries an anchor, or deletable — so the three must sum to ``surplus``. If
    they do not, the census is describing a population the rail is not operating on, and
    an attended operator reconciling "why did the live count shrink" has no way to tell
    which number lied. That is a refusal, not a warning: the previous version could
    report ``withheld_anchored: 1`` against ten undeletable rows and nothing noticed,
    because nothing was ever required to add up.
    """
    row = (
        await session.execute(
            _census_sql(),
            {
                "sport_id": sport_id,
                "tag": f'["{UNANCHORED_TAG}"]',
                "linked_copies": linked_copies,
            },
        )
    ).mappings().one()
    counts = {
        "fixtures": int(row["fixtures"] or 0),
        "total_rows": int(row["total_rows"] or 0),
        "keepers": int(row["keepers"] or 0),
        "surplus": int(row["surplus"] or 0),
        # Rows, not fixtures. Kept alongside the row-unit figure below precisely because
        # confusing the two units is what finding 4 was.
        "anchored_copies": int(row["anchored_copies"] or 0),
        "withheld_substantive": int(row["withheld_substantive"] or 0),
        "withheld_due_to_anchor": int(row["withheld_due_to_anchor"] or 0),
        "deletable": int(row["deletable"] or 0),
    }
    accounted = (
        counts["withheld_substantive"]
        + counts["withheld_due_to_anchor"]
        + counts["deletable"]
    )
    counts["surplus_accounted"] = accounted
    if accounted != counts["surplus"]:
        raise CensusDoesNotAccount(
            f"surplus={counts['surplus']} but withheld_substantive="
            f"{counts['withheld_substantive']} + withheld_due_to_anchor="
            f"{counts['withheld_due_to_anchor']} + deletable={counts['deletable']} "
            f"= {accounted}. The census does not describe the population the rail "
            f"operates on; refusing rather than reporting an unreconcilable count."
        )
    return counts


async def _lock_and_reverify(
    session, *, ids: list[int], sport_id: int
) -> None:
    """Lock candidates and keepers in one deterministic order, then re-derive."""
    keeper_ids = [
        int(r[0])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT k.id
                      FROM events e
                      JOIN events k
                        ON k.id <> e.id
                       AND k.sport_id       = e.sport_id
                       AND k.home_team_name = e.home_team_name
                       AND k.away_team_name = e.away_team_name
                       AND k.commence_time  = e.commence_time
                     WHERE e.id = ANY(:ids)
                    """
                ),
                {"ids": ids},
            )
        ).all()
    ]

    # ONE lock statement, ascending id, over the union. See ``_lock_sql``.
    all_ids = sorted(set(ids) | set(keeper_ids))
    locked = {
        int(r[0])
        for r in (await session.execute(_lock_sql(), {"ids": all_ids})).all()
    }

    vanished = [i for i in ids if i not in locked]
    if vanished:
        raise PruneRefused(
            f"{len(vanished)} candidate row(s) vanished between selection and lock: "
            f"{vanished[:10]}"
        )
    lost_keepers = [i for i in keeper_ids if i not in locked]
    if lost_keepers:
        raise PruneRefused(
            f"{len(lost_keepers)} KEEPER row(s) vanished between selection and lock: "
            f"{lost_keepers[:10]} — both copies of a fixture would be gone. Refused."
        )

    rows = (
        await session.execute(
            _reverify_sql(),
            {"ids": ids, "sport_id": sport_id, "tag": f'["{UNANCHORED_TAG}"]'},
        )
    ).mappings().all()

    seen = {r["id"] for r in rows}
    missing = [i for i in ids if i not in seen]
    if missing:
        raise PruneRefused(
            f"{len(missing)} candidate row(s) unreadable after lock: {missing[:10]}"
        )

    for r in rows:
        for prop in _REVERIFY_PROPERTIES:
            if not r[prop]:
                raise PruneRefused(
                    f"event {r['id']} failed re-verification on '{prop}' — batch "
                    "refused, nothing deleted"
                )


async def prune(
    session,
    *,
    sport_id: int,
    linked_copies: int = 1,
    apply: bool = False,
    max_delete: int = DEFAULT_MAX_DELETE,
    expected_min: int | None = None,
    expected_max: int | None = None,
    plan_hash: str | None = None,
) -> dict[str, Any]:
    """Census the partition, and on ``apply`` delete at most ``max_delete`` EMPTY rows.

    Returns the census on every path. ``apply=True`` requires **both**:

    * a band (``expected_min``/``expected_max``) — bounds cardinality; and
    * ``plan_hash`` from the dry run — bounds **identity**.

    The band alone was the first version's authorization and it is exactly what R2
    showed to be insufficient: Alex can inspect one batch and delete another forty
    seconds later while both report the approved count.
    """
    if max_delete < 1 or max_delete > MAX_DELETE_CEILING:
        raise PruneRefused(
            f"max_delete must be 1..{MAX_DELETE_CEILING}; got {max_delete}"
        )

    # R4 — a child table nobody has classified stops the rail, on every path
    # including the read-only one. A census that silently ignores a new child table
    # is how the operator learns about it from a 500 on call 1 of 31.
    orphans = unclassified_event_children()
    if orphans:
        raise PruneRefused(
            f"unclassified child table(s) of events: {list(orphans)} — add them to "
            "EVENT_CHILD_DISPOSITIONS in app/utils/event_fk_inventory.py and say what "
            "should happen to them. The rail will not guess."
        )

    counts = await census(session, sport_id=sport_id, linked_copies=linked_copies)

    result: dict[str, Any] = {
        "rail": "prune_unanchored_duplicates",
        "issue": "#2020",
        "rebuilt": "queue 386 — C-DELETE-RAIL-PRE R1-R6 + #2057 recut",
        "sport_id": sport_id,
        "linked_copies": linked_copies,
        "keeper_rule": (
            "the futures-linked copy, AND only when every other copy of the fixture "
            "is anchor-free and holds NO observation of any kind — zero child rows in "
            f"all {len(substance_tables())} substance tables (#2057 recut), zero rows "
            f"in {len(EVENT_PSEUDO_FK_SUBSTANCE)} polymorphic pseudo-FK table(s), and "
            f"all {len(parent_substance_columns())} parent-local substance columns empty "
            "with a 'scheduled' status (rail v3 / R2 finding 1)"
            if linked_copies == 1
            else "UNDETERMINED — this rail only prunes partitions with exactly one "
                 "linked copy, so nothing is deletable here"
        ),
        "apply": apply,
        "max_delete": max_delete,
        "census": counts,
        "expected_band": [expected_min, expected_max],
        # R4's silent half: an effect no response names is an effect nobody reviews.
        # Nothing here is ever deleted by this rail — a row with any of these is
        # withheld — but the cascade is named so the reader knows what WOULD go.
        "substance_tables": list(substance_tables()),
        "cascading_tables": sorted(CASCADING_CHILD_TABLES),
        # Renamed from `pointer_tables`, because they are no longer pointers the rail
        # nulls — they are substance the rail withholds on (R2 finding 2).
        "pseudo_fk_substance_tables": sorted(EVENT_PSEUDO_FK_SUBSTANCE),
        "parent_substance_columns": list(parent_substance_columns()),
    }

    if linked_copies != 1:
        return {
            **result,
            "batch": [],
            "deleted": 0,
            "terminal": "refused",
            "reason": (
                f"linked_copies={linked_copies}: the keeper is not determined by the "
                "futures link, so this rail has no keeper rule for it"
            ),
        }

    if apply:
        if expected_min is None or expected_max is None:
            return {
                **result, "batch": [], "deleted": 0, "terminal": "refused",
                "reason": "apply requires expected_min and expected_max — the band "
                          "is what makes stop-on-mismatch mechanical",
            }
        if plan_hash is None:
            return {
                **result, "batch": [], "deleted": 0, "terminal": "refused",
                "reason": (
                    "apply requires plan_hash from the dry run. The band bounds how "
                    "MANY rows are deleted; only the plan hash bounds WHICH. Run the "
                    "dry run, review its batch, and pass back the plan_hash it "
                    "returned."
                ),
            }
        if not (expected_min <= counts["deletable"] <= expected_max):
            return {
                **result, "batch": [], "deleted": 0, "terminal": "refused",
                "reason": (
                    f"CENSUS MISMATCH: deletable={counts['deletable']} is outside the "
                    f"authorized band [{expected_min}, {expected_max}] — nothing "
                    "deleted. Re-authorize against the live number or investigate "
                    "the drift before retrying."
                ),
            }

    batch = [
        int(r[0])
        for r in (
            await session.execute(
                _batch_sql(),
                {
                    "sport_id": sport_id,
                    "tag": f'["{UNANCHORED_TAG}"]',
                    "linked_copies": linked_copies,
                    "cap": int(max_delete),
                },
            )
        ).all()
    ]

    if not batch:
        return {
            **result, "batch": [], "deleted": 0, "terminal": "no_work",
            "reason": (
                "no deletable surplus rows in this partition — "
                f"{counts['surplus']} surplus row(s) exist, of which "
                f"{counts['withheld_substantive']} hold an observation (child row, "
                f"pin, or a non-empty column on the row itself) and "
                f"{counts['withheld_due_to_anchor']} sit in a fixture with an anchored "
                "copy. Those two plus deletable sum to surplus, checked. "
                "gotcha #53: this is not the same as an exhausted partition."
            ),
        }

    observed_hash = compute_plan_hash(
        sport_id=sport_id, linked_copies=linked_copies, ids=batch
    )

    # The dry run runs the apply path's guard queries TOO, and that is the point of
    # it. A dry run that exercises a different set of statements than the apply is not
    # a rehearsal — it is a second, easier query wearing the apply's name, and the
    # first thing the operator would learn about a broken re-verification is a 500 on
    # the first destructive call. The locks it takes are released by the caller's
    # rollback on this path.
    verified = True
    verify_refusal: str | None = None
    try:
        await _lock_and_reverify(session, ids=batch, sport_id=sport_id)
    except PruneRefused as exc:
        verified = False
        verify_refusal = str(exc)
        if apply:
            raise

    if not apply:
        return {
            **result,
            "batch": batch,
            "batch_size": len(batch),
            "deleted": 0,
            "verified": verified,
            "verify_refusal": verify_refusal,
            "plan_hash": observed_hash,
            "terminal": "dry_run" if verified else "refused",
            "reason": (
                verify_refusal if not verified else
                f"DRY RUN — would delete {len(batch)} of {counts['deletable']} "
                f"deletable rows; {counts['deletable'] - len(batch)} would remain "
                f"after this batch. Pass plan_hash={observed_hash} to apply THIS set."
            ),
        }

    # R2 — the plan is re-derived INSIDE the locked transaction and compared to the
    # address the operator reviewed. Same count, different set stops here.
    if observed_hash != plan_hash:
        return {
            **result,
            "batch": [], "deleted": 0, "terminal": "refused",
            "plan_hash": observed_hash,
            "submitted_plan_hash": plan_hash,
            "reason": (
                "PLAN MISMATCH: the batch this transaction derived is not the batch "
                f"the dry run published (submitted {plan_hash}, live {observed_hash}). "
                "The row set changed between review and apply — the count may still "
                "match, which is exactly why the count is not the authorization. "
                "Re-run the dry run and review the new batch."
            ),
        }

    # ── destructive from here, and not before ────────────────────────────────
    #
    # There is no child-table DELETE loop. There was one, and removing it is R3's
    # fix: every row in ``batch`` has already been proved to hold zero child rows in
    # all ten substance tables, both at selection and again under lock. A loop that
    # deletes from ten tables where the row count is provably zero is not a safety
    # measure — it is ten statements that would silently start doing something if the
    # proof above ever weakened.

    # There is no pointer-nulling loop either, and its removal is R2's finding 2.
    # It ran `UPDATE user_pins SET target_id = NULL`, a statement that CANNOT SUCCEED —
    # `user_pins.target_id` is `nullable=False` in both the model and the migration, so
    # a real database raises IntegrityError here and the DELETE below is never reached.
    # Only the committed fake session, which accepts every UPDATE, made that green.
    # A pin is now SUBSTANCE: a pinned row is withheld at the predicate and can never be
    # in `batch`, so there is nothing left to null. See EVENT_PSEUDO_FK_SUBSTANCE.

    deleted = (
        await session.execute(
            text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": batch}
        )
    ).rowcount

    if deleted != len(batch):
        # Bound to an explicit id list and holding row locks on every one of them, so
        # this cannot happen without something else having deleted the rows inside our
        # own lock. Say so rather than round it off.
        raise PruneRefused(
            f"deleted {deleted} but the batch held {len(batch)} — rolling back"
        )

    remaining = counts["deletable"] - deleted
    return {
        **result,
        "batch": batch[:50],
        "batch_size": len(batch),
        "deleted": deleted,
        "plan_hash": observed_hash,
        "remaining_deletable": remaining,
        "exhausted": remaining <= 0,
        "terminal": "complete",
        "reason": f"deleted {deleted}; {remaining} deletable rows remain",
    }
