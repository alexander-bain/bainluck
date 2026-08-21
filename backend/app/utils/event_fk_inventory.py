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
}

#: Polymorphic references with no database FK. Not derivable — enumerated, and the
#: reason is written next to it so the next reader does not "clean up" the duplication.
#:
#: **RECLASSIFIED POINTER -> SUBSTANCE (rail v3, C-DELETE-RAIL-PRE-R2 finding 2).**
#: These were treated as "a reference that carries no observation of its own, safe to
#: null", and the rail emitted ``UPDATE user_pins SET target_id = NULL``. That write is
#: **impossible under the declared schema** — both `models.py` and
#: `add_auth_personalization.py` declare ``user_pins.target_id`` as ``nullable=False``,
#: so a real database raises ``IntegrityError`` and the event DELETE is never reached.
#: All 48 rail tests were green because the committed fake session accepts every UPDATE.
#:
#: Two things were wrong and only one of them was the NULL:
#:
#: 1. the write could not succeed, and a dry run could not reveal that, because the
#:    rehearsal never executed the pointer path against a constraint-bearing session;
#: 2. **a pin IS substance.** It is a user saying "I care about this game." A candidate
#:    holding one does not "carry nothing", which is the exact claim the rail's whole
#:    deletion predicate rests on.
#:
#: So the rail no longer nulls anything. A pinned row is WITHHELD at the predicate, and
#: the impossible statement is deleted rather than repaired — a refusal that happens at
#: selection is reviewable in a dry run; one that happens at the final write is not.
EVENT_PSEUDO_FK_SUBSTANCE: dict[str, tuple[str, str]] = {
    # table: (id column, the predicate that scopes it to events)
    "user_pins": ("target_id", "pin_type = 'event'"),
}

#: Tables whose FK is ``ON DELETE CASCADE``. Deleting the parent removes these WITHOUT
#: any statement naming them. The rail names them in its response anyway — an effect
#: nothing in the output mentions is an effect nobody reviews (R4's silent half).
CASCADING_CHILD_TABLES: frozenset[str] = frozenset(
    {"espn_snapshots", "game_moments", "win_prob_snapshots"}
)


#: Columns ON THE EVENT ROW ITSELF whose presence means the row is an observation.
#:
#: **C-DELETE-RAIL-PRE-R2 finding 1 — "childless" is not "carries nothing".** The rebuild
#: turned "no child rows" into "holds no observation" and those are not the same claim,
#: because *the parent row is itself the system's record of game-existence, result and
#: line*. Codex executed the real ``prune()`` against a linked keeper and an anchorless,
#: childless row representing a DISTINCT completed 5–3 game with opening 0.57 / closing
#: 0.64, sharing only the stale name/time fixture key — and got ``deleted=1``.
#:
#: That is ruling 048 restated from the destructive side: the name/time fixture key
#: cannot prove two rows are one game, so emptiness of the ten child tables cannot be
#: read as duplicate identity. #2018 is the certified specimen — an exact-time collision
#: between two genuinely different games.
#:
#: Every column here is a fact somebody recorded about a game. If any is present, the
#: row is withheld; the rail's remaining population is rows that assert nothing at all.
PARENT_SUBSTANCE_COLUMNS: tuple[str, ...] = (
    "home_score",                 # the result
    "away_score",
    "completed_at",               # the settlement fact
    "opening_home_probability",   # the opening line
    "opening_away_probability",
    "closing_home_probability",   # the closing line
    "closing_away_probability",
    "espn_win_prob_home",         # a source's own observation
    "raw_ei",                     # a computed observation over the whole game
)

#: JSONB columns that must be tested for empty as well as NULL — ``{}`` is what an
#: initialized-but-never-written blob looks like, and reading it as substance would
#: withhold most of the population for holding nothing.
PARENT_SUBSTANCE_JSONB: tuple[str, ...] = (
    "box_score_data",
    "win_probability_sources",
)

#: ``events.status`` is NOT NULL with a ``scheduled`` default, so it cannot be tested for
#: presence. Anything OTHER than these is a claim about the game having happened.
EMPTY_STATUSES: tuple[str, ...] = ("scheduled",)


def parent_substance_predicate(alias: str) -> str:
    """SQL true when the row's OWN columns record nothing about a game.

    Deliberately built here, next to the column list, rather than in the rail: the list
    and the predicate going out of sync is the same failure as the hand-maintained FK
    tuple that R4 replaced.
    """
    parts = [f"{alias}.{col} IS NULL" for col in PARENT_SUBSTANCE_COLUMNS]
    parts += [
        f"({alias}.{col} IS NULL OR {alias}.{col}::text IN ('{{}}', '[]'))"
        for col in PARENT_SUBSTANCE_JSONB
    ]
    statuses = ", ".join(f"'{s}'" for s in EMPTY_STATUSES)
    parts.append(f"({alias}.status IS NULL OR {alias}.status IN ({statuses}))")
    return " AND ".join(parts)


def pseudo_fk_substance_predicate(alias: str) -> str:
    """SQL true when no polymorphic pseudo-FK row points at this event.

    Today this is exactly ``user_pins``. See ``EVENT_PSEUDO_FK_SUBSTANCE`` for why a pin
    is substance and not a nullable pointer.
    """
    return " AND ".join(
        f"NOT EXISTS (SELECT 1 FROM {t} p_{i} "
        f"WHERE p_{i}.{col} = {alias}.id AND p_{i}.{scope})"
        for i, (t, (col, scope)) in enumerate(EVENT_PSEUDO_FK_SUBSTANCE.items())
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
