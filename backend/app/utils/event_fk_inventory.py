"""The inventory of everything that hangs off ``events.id`` — DERIVED, not restated.

WHY THIS FILE EXISTS
--------------------

``C-DELETE-RAIL-PRE`` finding R4: SQLAlchemy metadata declares **10** foreign keys to
``events.id`` and the shared ``_EVENT_FK_TABLES`` tuple held **eight**. The two missing
ones failed in opposite directions, which is the part worth remembering:

* ``game_moments.event_id`` is ``ON DELETE CASCADE`` — its rows vanish **silently**,
  unnamed in any response, whenever a parent event is deleted.
* ``ranking_judgments.event_id`` has **no** ``ON DELETE`` action — a parent delete
  against an event holding a judgment **fails** with an FK violation.

So a hand-maintained list does not merely go stale; it goes stale into a silent data
loss on one row and a 500 on the next. The fix is not "add the two tables". The fix is
that **the list is computed from the schema and the classification is what a human
maintains** — adding a table to ``models.py`` without saying what should happen to it
turns CI red, which is the only version of this that stays true.

TWO ENUMERATIONS, RECONCILED (queue 386, and the disagreement is the finding)
----------------------------------------------------------------------------

Fable's directive said: enumerate the FKs independently and reconcile against codex's
``C-EVENT-CHILD-CENSUS``; *"a disagreement between the two enumerations is a finding,
not a race."* Both were run 2026-08-20 against production.

**The table SET agrees exactly** — 10 tables, byte for byte, in both enumerations and
in this module's derivation from metadata.

**The DELETE RULES do not.** The census concluded, from reading ``models.py``, that a
parent delete *"would either CASCADE delete child rows (win_prob etc) or SET NULL
(futures)"*. The live catalog says otherwise:

===========================  ===============
``information_schema``        ``delete_rule``
===========================  ===============
espn_snapshots                CASCADE
game_moments                  CASCADE
win_prob_snapshots            CASCADE
futures_markets               NO ACTION
line_movement_analyses        NO ACTION
odds_aggregated               NO ACTION
odds_snapshots                NO ACTION
ranking_judgments             NO ACTION
score_snapshots               NO ACTION
scoring_plays                 NO ACTION
===========================  ===============

(query fingerprint ``31ae6a56ff829aa5``, 10 rows, 1,281 ms, 2026-08-20)

**Not one constraint is ``SET NULL``.** ``futures_markets.event_id`` being *nullable in
Python* is not ``ON DELETE SET NULL`` *in Postgres* — nullability describes what the
column may hold, the delete rule describes what the database does to it, and only the
second one is a fact about deletion. Seven of the ten tables therefore make a parent
DELETE **fail**, where the census's reading predicted a silent null-out.

This mattered because that paragraph was load-bearing for "Tranche A is delete-safe".
It is *incidentally* still safe — but for a different reason than the one written down
(A's surplus rows measured zero futures children), and a right answer reached through a
false premise is one schema change away from being a wrong one.
"""

from __future__ import annotations

from typing import Literal

#: What the delete rail is permitted to do with a child row it finds.
#:
#: There is deliberately no ``TRANSFER``. Ruling 048's whole harm requires a repoint —
#: ``SET event_id = :keep`` before the delete is exactly how 5,142 / 540 / 2,097 rows of
#: one game's data landed on another's (#1779/#1798). A vocabulary that cannot spell the
#: harmful operation cannot be extended into it by a well-meaning patch.
Disposition = Literal["SUBSTANCE", "POINTER"]

#: Every FK to ``events.id``, with what its presence MEANS for a deletion.
#:
#: ``SUBSTANCE`` — the row is an observation somebody made about a game. Its presence on
#: a candidate row means that row is **not** an empty duplicate, whatever its name and
#: time say, and the rail withholds the row rather than destroying the observation.
#: Every one of the ten is SUBSTANCE, and that is not a failure of discrimination: there
#: is no child table of ``events`` whose rows are worthless. What makes the rail able to
#: do useful work anyway is that the *overwhelming majority* of the surplus holds none of
#: them — measured, not assumed: of Tranche A's 60,889 surplus rows, 1,214 carry a
#: ``win_prob_snapshots`` row and 16 a ``line_movement_analyses`` row, and the other
#: eight tables are zero (``C-EVENT-CHILD-CENSUS``, 10/10 tables, 2026-08-20).
#:
#: ``POINTER`` — a reference TO the event that carries no observation of its own. Safe to
#: null. ``user_pins`` is polymorphic and has no FK at all, so it is listed here rather
#: than derived; a pseudo-FK that no catalog query returns is precisely the kind of thing
#: that goes missing from a derived inventory.
EVENT_CHILD_DISPOSITIONS: dict[str, Disposition] = {
    "espn_snapshots": "SUBSTANCE",
    "futures_markets": "SUBSTANCE",
    "game_moments": "SUBSTANCE",
    "line_movement_analyses": "SUBSTANCE",
    "odds_aggregated": "SUBSTANCE",
    "odds_snapshots": "SUBSTANCE",
    "ranking_judgments": "SUBSTANCE",
    "score_snapshots": "SUBSTANCE",
    "scoring_plays": "SUBSTANCE",
    "win_prob_snapshots": "SUBSTANCE",
    # Added 2026-08-26 (#2213, queue 413) when `event_provider_anchors` gained an
    # ORM model and this derivation could finally see it. The rail refused to run
    # until it was classified, which is this file working exactly as designed —
    # the table has existed in Postgres since 2026-08-24 and was invisible here
    # for two days purely because no model declared the FK.
    #
    # SUBSTANCE, and the reasoning is worth stating because the first instinct is
    # POINTER. An anchor row is not an observation about the game — nobody watched
    # anything to produce it — so on the letter of the definition it looks like a
    # bare reference. But the classification's actual question is *"does this row's
    # presence mean the parent is not an anonymous duplicate?"*, and for an anchor
    # the answer is the strongest yes in the table: a provider id NAMES this row.
    # The delete rail exists to remove rows that nothing names.
    #
    # The FK is ON DELETE CASCADE, so a delete would silently take the anchor with
    # it and release the id back to the pool — which is tidy, and is exactly why
    # this must not be POINTER. Ruling 048's drain has one piece of evidence and
    # it is this row; a rail that can destroy its own evidence while reporting a
    # clean deletion is the shape of failure that produced #1779/#1798.
    "event_provider_anchors": "SUBSTANCE",
    # Added 2026-09-05 (#2927, container graph Phase 1) the moment
    # `event_participants` gained an ORM model. The rail refused to run until it
    # was classified and 37 tests went red saying so — this file working exactly
    # as designed, for the second time, and the reason the classification below
    # is argued rather than asserted.
    #
    # SUBSTANCE, and — as with `event_provider_anchors` — the first instinct is
    # POINTER. A participant row looks like a restatement of
    # `home_team_name`/`away_team_name`, which are still written and still
    # correct; on that reading it carries no observation of its own.
    #
    # It is SUBSTANCE for one specific and sufficient reason: **for a doubles
    # fixture the participant rows are the only place the second player on each
    # side exists.** `events` has exactly two name columns and a doubles side
    # holds two people, which is the whole reason this table was added (spec §3).
    # Deleting the parent CASCADES them away, so a rail that classified this
    # POINTER could destroy the only record of who played — while reporting a
    # clean deletion. That is the shape of #1779/#1798 and the same argument the
    # anchor entry above makes: the rail must not be able to erase its own
    # evidence.
    #
    # THE CONSEQUENCE, STATED RATHER THAN DISCOVERED LATER. Once the M3 backfill
    # runs, every two-sided event carries participant rows, and a SUBSTANCE
    # child that every row has makes the delete rail withhold everything. That
    # is a real narrowing of the rail's reach and it is not bought back by
    # mis-classifying the table — the honest fix, when it matters, is for the
    # rail to distinguish a participant row DERIVED from the parent's own name
    # columns from one that carries a name found nowhere else. Today it costs
    # nothing: this migration ships the table EMPTY, M3 is a separate attended
    # step not authorised by "go 2927", and `substance_tables()` is evaluated
    # against rows that do not exist yet.
    "event_participants": "SUBSTANCE",
}

#: Polymorphic references with no database FK. Not derivable — enumerated, and the
#: reason is written next to it so the next reader does not "clean up" the duplication.
EVENT_POINTER_TABLES: dict[str, tuple[str, str]] = {
    # table: (id column, the predicate that scopes it to events)
    "user_pins": ("target_id", "pin_type = 'event'"),
}

#: Tables whose FK is ``ON DELETE CASCADE``. Deleting the parent removes these WITHOUT
#: any statement naming them. The rail names them in its response anyway — an effect
#: nothing in the output mentions is an effect nobody reviews (R4's silent half).
CASCADING_CHILD_TABLES: frozenset[str] = frozenset(
    {
        "espn_snapshots",
        "game_moments",
        "win_prob_snapshots",
        # `ON DELETE CASCADE` in the `anchors_and_captures` migration (#1946).
        # Listed so the rail NAMES it — R4's silent half is the whole reason this
        # set exists, and an anchor is the one child whose silent removal would
        # also remove the proof that the deletion was correct.
        "event_provider_anchors",
        # `ON DELETE CASCADE` in `containers_phase1` (#2927). Named here for
        # R4's silent half: a doubles side's second player exists in this table
        # and nowhere else, so a deletion that removed it without saying so is
        # precisely the unreviewed effect this set exists to prevent.
        "event_participants",
    }
)


def derive_event_child_tables() -> tuple[str, ...]:
    """Every table with an FK to ``events.id``, read off SQLAlchemy metadata.

    This is the executable half of R4. It is a *derivation*, so it cannot drift from
    the models the way a tuple of string literals did.
    """
    from app.models.models import Base  # noqa: PLC0415

    found: set[str] = set()
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            target = fk.target_fullname  # e.g. "events.id"
            if target.split(".")[0] == "events":
                found.add(table.name)
    return tuple(sorted(found))


def unclassified_event_children() -> tuple[str, ...]:
    """Tables that hang off ``events`` and that nobody has said what to do with.

    Non-empty ⇒ the schema grew a child and the disposition table did not. The rail
    refuses to run at all in that state, and CI goes red, because the alternative is
    that the new table becomes whichever of "silently cascaded" or "FK violation" its
    ``ondelete`` happens to say — chosen by default rather than by anyone.
    """
    return tuple(
        t for t in derive_event_child_tables() if t not in EVENT_CHILD_DISPOSITIONS
    )


def substance_tables() -> tuple[str, ...]:
    """The tables whose presence on a row makes that row not-empty."""
    return tuple(
        t for t in derive_event_child_tables()
        if EVENT_CHILD_DISPOSITIONS.get(t) == "SUBSTANCE"
    )
