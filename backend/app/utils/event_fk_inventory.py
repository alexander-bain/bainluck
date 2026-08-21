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
#: **C-DELETE-RAIL-PRE-R3 finding 2: this dict was the allowlist defect again, one
#: table over.** It held exactly ``user_pins`` while ``user_seen_markets`` and
#: ``discover_interactions`` both carry event ids that the live feed consumes for
#: seen/dismissed behaviour — and R3 executed the real prune flow against rows
#: referenced by each and got ``deleted=1`` for both, while the rail's own response
#: claimed "NO observation of any kind".
#:
#: A polymorphic reference genuinely cannot be derived from FK metadata — that is what
#: makes it polymorphic. But the CANDIDATES can be: a table carrying an
#: ``(<x>_id, <x>_type)`` column pair is nominated by the schema, and what a human
#: maintains is the CLASSIFICATION. An unclassified candidate turns CI red
#: (``test_every_schema_nominated_pseudo_fk_is_classified``), so the list cannot go
#: quietly stale the way it just did.
EVENT_PSEUDO_FK_SUBSTANCE: dict[str, tuple[str, str]] = {
    # table: (id column, the predicate that scopes it to events)
    #
    # A pin is a user saying "I care about this game" (rail v3, R2 finding 2).
    "user_pins": ("target_id", "pin_type = 'event'"),
    # A seen row is the record that we showed this event to somebody. Deleting the
    # event destroys the dedup history and the user starts seeing it again.
    "user_seen_markets": ("item_id", "item_type = 'event'"),
    # A dismiss/like is an explicit user judgement about this event, and the feed's
    # personalization reads it directly (`feed.py` seen/dismissed paths).
    "discover_interactions": ("item_id", "item_type = 'event'"),
    # A recorded review decision about this event is human labour. It is the one
    # class here that is not reconstructible from behaviour at all.
    "discover_review_decisions": ("item_id", "item_type = 'event'"),
}

#: Schema-nominated polymorphic tables that are explicitly NOT substance, with the
#: reason. Being on this list is a positive claim by a human, not an omission — which
#: is the whole difference between this design and the one R3 blocked.
EVENT_PSEUDO_FK_DERIVED: dict[str, str] = {
    # A search projection, rebuilt from its source rows by the typeahead builder.
    # Destroying it loses nothing that cannot be regenerated, and treating it as
    # substance would withhold rows for holding a cache entry.
    "typeahead_index": "derived search projection — regenerable, holds no observation",
}

#: Column-name pairs that mark a polymorphic reference. Used only to NOMINATE tables
#: for classification; it never decides anything on its own.
PSEUDO_FK_COLUMN_PAIRS: tuple[tuple[str, str], ...] = (
    ("item_id", "item_type"),
    ("target_id", "target_type"),
    ("target_id", "pin_type"),
    ("entity_id", "entity_type"),
    ("subject_id", "subject_type"),
)


def schema_nominated_pseudo_fk_tables() -> tuple[str, ...]:
    """Tables the SCHEMA says might hold a polymorphic event reference.

    The independent oracle for :data:`EVENT_PSEUDO_FK_SUBSTANCE`. It does not read
    that dict, so the two cannot share a blind spot — which is precisely how the
    previous guard passed while three tables went unprotected.
    """
    from app.models.models import Base

    found: list[str] = []
    for table in Base.metadata.sorted_tables:
        names = {c.name for c in table.columns}
        if any(idc in names and typc in names for idc, typc in PSEUDO_FK_COLUMN_PAIRS):
            found.append(table.name)
    return tuple(sorted(found))

#: Tables whose FK is ``ON DELETE CASCADE``. Deleting the parent removes these WITHOUT
#: any statement naming them. The rail names them in its response anyway — an effect
#: nothing in the output mentions is an effect nobody reviews (R4's silent half).
CASCADING_CHILD_TABLES: frozenset[str] = frozenset(
    {"espn_snapshots", "game_moments", "win_prob_snapshots"}
)


#: Columns that are NOT substance. **Everything else on the row IS.**
#:
#: **C-DELETE-RAIL-PRE-R3 finding 1, and it is a finding about STRATEGY, not contents.**
#: R2 said "childless is not carries nothing" and v3 answered it by ENUMERATING what
#: counts as something — a nine-column allowlist. R3 then executed the real ``prune()``
#: against a distinct-game candidate whose sole recorded observation was
#: ``opening_home_spread = -1.5``, a column the allowlist did not name, and got
#: ``deleted=1``. The allowlist covered 12 of the table's 55 columns; 43 were unguarded.
#:
#: **A fourth round that lengthens the list is the same move a fourth time.** R3 named
#: why it cannot converge: the guard test iterated *the same production constant* the
#: implementation did, so it was **self-oracular** — an omitted column disappeared from
#: implementation and oracle together, and the suite went green on exactly the rows it
#: failed to protect. Three enumeration rounds was the evidence.
#:
#: So the polarity is inverted, on Alex's ruling (2026-08-21): **deny by default.** A row
#: is deletable only when every column NOT named here is empty. A column added to
#: ``models.py`` tomorrow is PROTECTED the day it is born, and making it deletable
#: requires a human to write its name down in this set — which is the same contract the
#: FK half of this module has had since R4, now applied to the parent row.
#:
#: The three groups below are the only things a row can carry that are not a claim about
#: a game. Note what is deliberately ABSENT: ``espn_id`` and ``statpal_fixture_id`` are
#: substance (an anchor is a claim), as are venue, broadcast, game state, all spreads and
#: totals, the EI fields, the LLM classifications, tags and every tournament fact.
PARENT_IGNORABLE_COLUMNS: frozenset[str] = frozenset(
    {
        # --- bookkeeping: true of every row, says nothing about a game
        "id",
        "created_at",
        # --- the fixture key ITSELF. These are what makes two rows candidates for
        # being the same game; they cannot also be the evidence that one of them is
        # real, or nothing is ever comparable.
        "sport_id",
        "home_team_id",
        "away_team_id",
        "home_team_name",
        "away_team_name",
        "commence_time",
        # --- derived from the fixture key or from team identity, not recorded about
        # THIS game. Normalisation is a function of the name; alt-names belong to the
        # club and are the same on every row that names it.
        "home_team_normalized",
        "away_team_normalized",
        "home_team_alt_names",
        "away_team_alt_names",
        # --- provenance OF THE ROW rather than an observation IN it. `external_id` is
        # the creating source's key for this row: it identifies the row, and every row
        # in the population has one, including the empty ones.
        "external_id",
        "commence_time_source",
    }
)

#: Per-column definition of "empty" for columns where ``IS NULL`` is not the whole
#: story. Anything not listed and not auto-classified below is empty iff it is NULL.
#:
#: ``status`` is here rather than in the ignorable set's spirit: it IS substance —
#: anything other than ``scheduled`` is a claim that the game happened — but it is
#: NOT NULL, so its emptiness needs a value test rather than a null test.
PARENT_EMPTY_VALUE_SQL: dict[str, str] = {
    "status": "({alias}.status IS NULL OR {alias}.status IN ('scheduled'))",
}

#: Retained for readers of older reports. ``EMPTY_STATUSES`` is now expressed inside
#: ``PARENT_EMPTY_VALUE_SQL``; the tuple is kept so nothing that quotes it breaks.
EMPTY_STATUSES: tuple[str, ...] = ("scheduled",)


def _event_columns() -> tuple:
    """The LIVE column set, read from the mapped table at call time.

    Imported lazily and never cached at module scope: a cached snapshot taken at
    import time is a second copy of the schema, and a second copy is the thing that
    goes stale. The whole point of R3's fix is that there is exactly one source of
    truth for what columns exist, and it is the table.
    """
    from app.models.models import Event

    return tuple(Event.__table__.columns)


def parent_substance_columns() -> tuple[str, ...]:
    """Every column that counts as an observation — DERIVED, never restated.

    ``schema minus denylist``. A new column appears here automatically.
    """
    return tuple(
        c.name for c in _event_columns() if c.name not in PARENT_IGNORABLE_COLUMNS
    )


def _empty_sql_for(alias: str, column) -> str:
    """SQL true when this column records nothing.

    Type-directed so that a newly-added JSONB or boolean column gets a correct
    emptiness test without anyone remembering to add one — the failure mode being
    guarded against is a protected-but-untestable column silently withholding the
    entire population.
    """
    name = column.name
    if name in PARENT_EMPTY_VALUE_SQL:
        return PARENT_EMPTY_VALUE_SQL[name].format(alias=alias)

    type_name = str(column.type).upper()
    if "JSON" in type_name:
        # ``{}`` / ``[]`` is what an initialised-but-never-written blob looks like;
        # reading it as substance would withhold most of the population for nothing.
        return (
            f"({alias}.{name} IS NULL OR "
            f"{alias}.{name}::text IN ('{{}}', '[]'))"
        )
    if "BOOLEAN" in type_name:
        return f"({alias}.{name} IS NULL OR {alias}.{name} = false)"
    return f"{alias}.{name} IS NULL"


#: Back-compat: the derived substance list, materialised at import for callers and
#: reports that expect a tuple. ``parent_substance_columns()`` is the live read; this
#: is a convenience over it, and both come from the same derivation, so they cannot
#: disagree the way a hand-written list disagreed with the schema.
def __getattr__(name: str):  # noqa: D401 - module-level lazy attribute
    if name == "PARENT_SUBSTANCE_COLUMNS":
        return parent_substance_columns()
    if name == "PARENT_SUBSTANCE_JSONB":
        return tuple(
            c.name
            for c in _event_columns()
            if "JSON" in str(c.type).upper() and c.name not in PARENT_IGNORABLE_COLUMNS
        )
    raise AttributeError(name)


def parent_substance_predicate(alias: str) -> str:
    """SQL true when the row's OWN columns record nothing about a game.

    Built from the live schema at call time (R3's ruling), so the predicate and the
    table cannot drift. Deterministically ordered by column position, so the emitted
    SQL is stable and diffable across runs.
    """
    parts = [
        _empty_sql_for(alias, c)
        for c in _event_columns()
        if c.name not in PARENT_IGNORABLE_COLUMNS
    ]
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
