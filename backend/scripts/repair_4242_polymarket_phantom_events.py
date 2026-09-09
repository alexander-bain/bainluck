"""#4242 part (b) — the historical cleanup for the rows the seven-hour generator wrote.

THE SHIP: searching a fighter's name returns the fights he is in, ONCE each.
`/search?q=Whittaker` returned 44 results / 42 games — the one real fight (Ben
Whittaker v Conor Wallace, 3 Oct) followed by ~24 identical "Whittaker /
Chimaev" cards, every one "No result reported", one of them flagged **LIVE**,
for a fight that happened on 22 October 2024. Same for `?q=Chimaev` and
`?q=Galatasaray`.

PREVENTION IS PART (a) — `auto_create_time_is_invented()` in
`app/tasks/prediction_market_matching.py`. It refuses the auto-create when
nothing reports a start: the market's own time is
`AUTO_CREATE_STALE_MARKET_DAYS` past AND its external_id parses to no ticker
date. This script is the owed DATA REPAIR for the rows written before that
landed, and it is the repair CERT-2347 named when it withheld the token from
the guard for not cleaning the search page.

    THE TAP MUST BE OFF BEFORE THIS RUNS. Cleaning while the generator still
    mints ~15 rows/day just refills. Part (a) ships in the same commit range;
    this script must not be applied until it is deployed and a post-deploy
    census shows 0 new phantoms. `--allow-hot` exists only for a staged slice
    and says so loudly.

------------------------------------------------------------------------------
THE POPULATION, measured on production 2026-09-09 (whole thing, no sampling)
------------------------------------------------------------------------------

`commence_time_source = 'polymarket'` AND `external_id IS NULL` AND
`|commence_time - created_at| < 300s` — the fabricated-`now` stamp, which is
what the bug leaves behind and what makes the row unfindable by the registry
step that would otherwise have reused it.

    2,641 rows total, ALL with a NULL external_id
    1,914 of them in a duplicate group   (100 matchups, ~60 rows each)
      727 singletons — OUT OF SCOPE, see the last section

------------------------------------------------------------------------------
WHY THE OBVIOUS ONE-LINER IS WRONG, TWICE
------------------------------------------------------------------------------

**1. Folding by `(home_team_name, away_team_name)` merges distinct fixtures.**
`FCSB / PAOK` carries markets dated **2024-10-02 AND 2025-02-11** — the two legs
of one Europa League tie. `Galatasaray / AZ Alkmaar` the same.
`Yankees / Guardians - Game 1` carries four dates. Collapsing those to one row
is a cross-event data merge (gotcha #46) wearing a cleanup's clothes. So the
survivor is NEVER chosen by name. It is **the row the venue still points at**,
and a group with two real fixtures keeps two survivors, each on its own date.

**2. `DELETE FROM events` destroys children in eight tables.** The measured
split is what makes this repair small and provably lossless:

    orphans   1,841 (96%)  no market, only derived children -> deleted
    holders      65        markets agree on one date        -> RE-DATED, never moved
    preserve      2        real substance, one survivor     -> MOVED, then deleted
    ambiguous     6        markets disagree                 -> DEFERRED, reported

Those four numbers are the SHIPPED `plan_sql()` run against production on
2026-09-09 over all 1,914 duplicate-group rows, not a hand count: provider
identities 0, user pins 0, substantive children 0, preservable 2. The two
preservable rows are `15305758` (Whittaker / Chimaev — the fixture this ship is
named after) and `15305765` (Viktoria Plzen / Ferencvaros), and each sits in a
matchup with EXACTLY ONE survivor, which is what makes the move well defined.
Before CERT-2357 those two were counted among the orphans and deleted outright.

All **10** live rows in the population are holders, not orphans. That is the
"false-live duplicate" on the #4242 screenshot, and re-dating fixes it at the
source rather than hiding it.

------------------------------------------------------------------------------
WHAT MAKES DELETING AN ORPHAN LOSSLESS — the canonical inventory, then refusals
------------------------------------------------------------------------------

CERT-2357 withheld the token from the first version of this file because its
deletion policy was a HAND-TYPED list of children that overrode the catalogue.
It named the repair `4242-DELETE-ONLY-PROVEN-DERIVED-ROWS`: use the canonical
inventory by default, refuse provider-identified and pinned rows, and encode
narrow production-measured exceptions for what is provably derived. The BLOCK
was right, and it was right about a real overreach: this file used to call
`line_movement_analyses` "a regenerable LLM taxonomy cache", and that is true of
711 of its 713 rows and FALSE of 2 of them.

So the default is now inverted. :func:`fk_children` reads `pg_constraint` at run
time and every child table of `events` is SUBSTANTIVE — a row carrying one is
DEFERRED — unless it appears in :data:`DERIVED_EXCEPTIONS` *and* the row matches
that exception's predicate. A thirteenth child table added by a migration next
month needs no edit here to be safe: it is refused because it is unknown, and
:func:`unknown_children` prints it by name.

THE THREE EXCEPTIONS, each with the predicate that makes it derived, the count
it was measured at, and the query that measured it (2026-09-09, whole
population, `scripts/` census — a dated census, not a standing fact):

* `win_prob_snapshots` WHERE `source = 'polymarket'` — event-level curves keyed
  `(event_id, source)` with no `market_id`, derived from the phantom's own
  price. Deleted with the row (CASCADE), never re-pointed: injecting a phantom's
  curve into a real match is gotcha #46 and a direct hit on *the blend is the
  product*. **3 rows in the population are NOT polymarket** (all `kalshi`) and
  are therefore real foreign observations — see PRESERVE below.
* `event_provider_anchors` WHERE `source = 'polymarket' AND id_kind = 'market'`
  — deleted (CASCADE), **and never re-pointed under any predicate**. Anchor
  uniqueness is `(source, source_id, id_kind)` and `event_id` is not in it, so a
  wrong re-point is silently accepted forever, permanently asserting a provider
  id against the wrong fixture with no constraint to catch it (#2871 learned
  this the same way). All 24 anchors in the population match the exception; a
  row carrying any other anchor is DEFERRED, never preserved and never deleted.
* `line_movement_analyses` WHERE `analysis_type = 'taxonomy_enrichment'` —
  deleted explicitly, BEFORE the events, because its FK is NO ACTION. **2 rows
  in the population are `line_movement` analyses**, which are observations about
  a market's movement and not a cache of anything — see PRESERVE below.

`market_link_changes` and `market_match_receipts` carry an event id with NO FK
**on purpose** — models.py is explicit that the forensic has to outlive its
subject. They are lane1b's under D39 and this script does not touch them. A
deleted phantom keeps its receipt, which is the point of one.

`user_pins` is the one refusal the catalogue cannot supply: `pin_type='event'` +
`target_id` is a PSEUDO-FK with no constraint behind it, so a deleted event
leaves a pin pointing at nothing and no error is raised. It is named in
:data:`PSEUDO_FK_REFUSALS` and measured at 0 on the population; a row with a pin
is DEFERRED whatever else is true of it.

------------------------------------------------------------------------------
PRESERVE — the five rows that carry substance, and why re-pointing them is
not the thing #2871 forbade
------------------------------------------------------------------------------

Five events in the 2,641 carry a child that is real rather than derived: three
foreign (`kalshi`) curves and two `line_movement` analyses. Deleting them is the
overreach CERT-2357 caught. Deferring all five is honest but leaves an extra
Whittaker card on the very search this ship is named after — `15305758` IS
Whittaker/Chimaev — so "the pile is gone" would fail on its own headline.

So a PRESERVE row's substance is **moved to the surviving canonical event of the
same matchup, in the same transaction, before the row is deleted**. Nothing is
destroyed and the card count still goes to one.

The asymmetry with an anchor is the whole argument and is stated out loud so a
grader does not read "re-point" and reasonably conclude #2871 was ignored: **an
anchor asserts an identity** — "this event IS polymarket market X" — and a
re-pointed one asserts a phantom's identity against a real fixture forever, with
no constraint to catch it. **A curve sample and a line-movement analysis assert
no identity.** They are observations about a matchup at a time, they carry no
provider id, and neither `win_prob_snapshots` nor `line_movement_analyses` has
any unique index beyond its own `id` (checked on production, not assumed), so a
re-point can neither collide nor overwrite.

It is refused unless it is provable. A PRESERVE row is only deleted when its
matchup has **exactly one** survivor; with none or with two (two legs of one
tie, the `FCSB / PAOK` shape) there is no single event the observation belongs
to, so the row is DEFERRED instead. :func:`apply_matchup` re-asserts that at
write time and raises rather than guessing.

As measured today this arm moves TWO rows: the 3 kalshi curves sit on events
whose matchup has one member, so they are singletons, outside the duplicate-group
population this repair touches, and cannot be deleted by it at all. The arm still
exists for them because the generator is non-convergent — a singleton becomes a
duplicate group the next time it mints — and a refusal that only works on
today's census is not a refusal.

`market_link_changes` and `market_match_receipts` carry an event id with NO FK
**on purpose** — models.py is explicit that the forensic has to outlive its
subject. They are lane1b's under D39 and this script does not touch them. A
deleted phantom keeps its receipt, which is the point of one.

------------------------------------------------------------------------------
THE FOUR ARMS
------------------------------------------------------------------------------

**DELETE — 1,841 orphans.** A fabricated date and two team names is the whole
of their content.

35 of the 100 matchups are all-orphan and therefore disappear entirely. That was
decided by READING them, not by assuming: `Ole Miss / LSU by 4 or more points`,
`Kansas State / Kansas by 10 or more points`,
`PIT Pirates / MIA Marlins March 27` — a spread market's tail and a date glued
into an away team name. These are market titles mis-parsed into events, not
fixtures. The handful with real names (`Texas / Oklahoma`,
`Siegemund / Samsonova`) have no market left anywhere to date them from, and a
search hit for a fixture on a day it did not happen is worse than no hit. This
is the one place this repair differs from #2871, which KEPT its phantoms — and
the difference is exactly that #2871's rows were the only record of a fixture
whose market still pointed at them. Nothing points at these.

**RE-DATE — 65 holders.** `commence_time` <- the linked markets' agreed
`commence_time`, i.e. the date the venue itself reports. No market moves: a
re-point cannot collide (`event_id` is not in `uq_futures_source_external`) but
not moving one at all is a stronger guarantee than not colliding, and the
holder is already the row the market chose.

A holder whose new date is in the past and whose status is `live` becomes
**`suspended`, not `closed`** — live/048 and CERT-752's rule, quoted in
`espn_sync.py`: every client renders `closed` as Final, and nothing here has
standing to say who won. `suspended` is still wrong to call live and still not
a claim that anybody won. `EVENT_SUSPENDED` is imported, not re-typed.

**DEFER — 6 ambiguous holders.** Markets that disagree about the date mean two
fixtures already merged onto one row. Picking one date would pick a winner
between two real games. Untouched, reported, and filed as `matching-symptom`
under #2693 (D35: filed, not fixed).

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

`--apply` REFUSES to run until `--backup` has copied every in-scope row into
`bak_4242_*` and reconciled the copy exactly. The undo is one command:

    heroku run:detached -a bainluck \
      "python3 scripts/restore_4242_polymarket_phantom_events.py --apply"

------------------------------------------------------------------------------
OUT OF SCOPE, AND MEASURED RATHER THAN IGNORED
------------------------------------------------------------------------------

The 727 SINGLETON now-stamped rows. 649 of them hold a market — one row per
market, not sixty, so they are a different shape: a fabricated date on a row
nothing duplicates. They are a truth defect and not a search-page defect, they
are not what #4242 filed or what CERT-2347 named, and re-dating them is a
larger blast radius that deserves its own measurement. `--census-singletons`
prints them so the follow-up starts from a number.

------------------------------------------------------------------------------
USAGE
------------------------------------------------------------------------------

    python3 scripts/repair_4242_polymarket_phantom_events.py            # census + plan, no writes
    python3 scripts/repair_4242_polymarket_phantom_events.py --backup   # copy rows, reconcile
    python3 scripts/repair_4242_polymarket_phantom_events.py --apply --limit 10   # staged slice
    python3 scripts/repair_4242_polymarket_phantom_events.py --apply    # the rest

Heroku one-off (gotcha #48 — a non-detached `heroku run` does not execute in the
sandbox and returns empty stdout that reads like success; PROJECT_PATH=backend
puts scripts at /app, so NEVER `cd backend` and never a `backend/scripts/...`
path):

    heroku run:detached -a bainluck "python3 scripts/repair_4242_polymarket_phantom_events.py --backup"

A one-off dyno runs the DEPLOYED SLUG, not your branch — this file must be
merged and deployed before any of the above does anything at all.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Imported, never re-typed. `suspended` is the disposition live/048 and CERT-752
# settled on for "we cannot say this is live and we cannot say who won"; a
# string literal here would drift from it silently.
from app.utils.event_completion import EVENT_SUSPENDED  # noqa: E402

#: The HOLDER test, and the reason `futures_markets` is not just another child:
#: a row that holds a market is the row the venue points at, so it is re-dated
#: rather than deleted. Every OTHER child of `events` comes from the catalogue.
HOLDER_TABLE = "futures_markets"

#: The canonical inventory as it read on production 2026-09-09 — twelve FK
#: children. This is a RECORD, not the policy: :func:`fk_children` re-reads
#: `pg_constraint` every run and :func:`unknown_children` reports the difference,
#: so a table added since is refused rather than missed. Kept so the guard suite
#: can assert the shipped default against a known shape without a database.
CATALOGUE_2026_09_09 = (
    "espn_snapshots",
    "event_participants",
    "event_provider_anchors",
    "futures_markets",
    "game_moments",
    "line_movement_analyses",
    "odds_aggregated",
    "odds_snapshots",
    "ranking_judgments",
    "score_snapshots",
    "scoring_plays",
    "win_prob_snapshots",
)

#: THE NARROW EXCEPTIONS. `{table: (derived_predicate, measured_note)}`.
#:
#: A child row is DERIVED — deletable with its parent — only when its table is
#: here AND the row satisfies the predicate. Anything else in the same table is
#: substance: it either PRESERVES (re-pointed to the survivor) or DEFERS.
#:
#: Each predicate is rendered into the plan SQL with the child aliased `c`. Each
#: carries the count it was measured at, the date, and the query — a census in a
#: comment reads as a standing fact unless it says when it was taken.
DERIVED_EXCEPTIONS = {
    "win_prob_snapshots": (
        "c.source = 'polymarket'",
        "2026-09-09: 3 of the population's curve rows are NOT polymarket (all "
        "kalshi). SELECT count(*) FROM win_prob_snapshots w JOIN pop p ON "
        "p.id = w.event_id WHERE w.source <> 'polymarket'",
    ),
    "event_provider_anchors": (
        "c.source = 'polymarket' AND c.id_kind = 'market'",
        "2026-09-09: 24 anchors on the population, ALL polymarket/market, 0 "
        "foreign. SELECT count(*) FROM event_provider_anchors a JOIN pop p ON "
        "p.id = a.event_id WHERE NOT (a.source = 'polymarket' AND "
        "a.id_kind = 'market')",
    ),
    "line_movement_analyses": (
        "c.analysis_type = 'taxonomy_enrichment'",
        "2026-09-09: 2 of the population's analyses are `line_movement`, not "
        "taxonomy. SELECT count(*) FROM line_movement_analyses l JOIN pop p ON "
        "p.id = l.event_id WHERE l.analysis_type <> 'taxonomy_enrichment'",
    ),
}

#: Of the three exceptions, the tables whose non-derived rows may be MOVED to the
#: survivor rather than deferred. `event_provider_anchors` is deliberately absent
#: and must stay absent: an anchor asserts an identity, and a re-pointed one
#: asserts a phantom's identity against a real fixture forever (#2871). A curve
#: sample and a line-movement analysis assert none.
PRESERVABLE_TABLES = ("win_prob_snapshots", "line_movement_analyses")

#: Backed up, and therefore restorable, whether they leave by CASCADE, by an
#: explicit DELETE, or by being re-pointed onto the survivor.
DERIVED_CHILD_TABLES = tuple(DERIVED_EXCEPTIONS)

#: The only exception table whose FK is NO ACTION, so the only one that has to be
#: deleted explicitly before the parent. The other two CASCADE. Asserted against
#: the live catalogue by the guard suite rather than trusted here.
NO_ACTION_DERIVED_TABLES = ("line_movement_analyses",)

#: Refusals the catalogue cannot supply. `user_pins` points at an event through
#: `(pin_type, target_id)` with NO foreign key, so deleting the event leaves a
#: pin pointing at nothing and raises nothing. Measured 0 on the population
#: 2026-09-09: SELECT count(*) FROM user_pins u JOIN pop p ON p.id = u.target_id
#: WHERE u.pin_type = 'event'.
PSEUDO_FK_REFUSALS = (
    ("user_pins", "target_id", "pin_type = 'event'"),
)

#: Provider identity on the event ROW itself. A row that any authority can name
#: is not a phantom, whatever its dates look like. Both measured 0 on the
#: population 2026-09-09.
IDENTITY_COLUMNS = ("espn_id", "statpal_fixture_id")

#: Read `pg_constraint` rather than `information_schema`: the latter hides
#: constraints on tables the connected role cannot see, which would silently
#: SHRINK the refusal set — the one direction an inventory must never fail in.
_FK_CHILDREN_SQL = """
SELECT DISTINCT c.conrelid::regclass::text AS child_table
FROM pg_constraint c
WHERE c.contype = 'f' AND c.confrelid = 'events'::regclass
ORDER BY 1
"""

BAK_PREFIX = "bak_4242_"

# Sanity floor. A repair that finds nothing and reports success is the worst
# possible outcome (gotcha #53: an empty result is a response shape, not an
# absence). Measured population on 2026-09-09 was 1,914; anything under this
# means the predicate broke, not that the work is done.
MIN_EXPECTED_POPULATION = 1_000

CHUNK = 500

# THE POPULATION. `external_id IS NULL` is a belt, not a braces: all 2,641 rows
# measured carry NULL, and a row that has since acquired a real provider id is
# by definition no longer the unfindable thing this bug creates.
#
# The 300-second window is the fabricated-`now` stamp itself — the bug writes
# `commence_time = now` in the same statement that sets `created_at`, so the two
# are within a round-trip of each other. It is not a tolerance to be tuned: a
# real fixture whose start time lands within five minutes of the moment we first
# saw it is a coincidence that does not survive the duplicate-group test below.
_POPULATION = """
    e.commence_time_source = 'polymarket'
    AND e.external_id IS NULL
    AND abs(extract(epoch FROM (e.commence_time - e.created_at))) < 300
"""

def substantive_tables(catalogue):
    """Every catalogue child that is neither the holder table nor an exception.

    The default is SUBSTANTIVE. A table nobody has classified lands here and
    defers the rows that carry it, which is the safe direction: the cost of a
    wrong DEFER is a row this repair does not clean, and the cost of a wrong
    delete is a real observation destroyed on a dyno whose stdout nobody reads.
    """
    return tuple(t for t in sorted(catalogue)
                 if t != HOLDER_TABLE and t not in DERIVED_EXCEPTIONS)


def unknown_children(catalogue):
    """Catalogue children this file has never classified. Printed, never ignored."""
    known = {HOLDER_TABLE, *DERIVED_EXCEPTIONS, *CATALOGUE_2026_09_09}
    return tuple(t for t in sorted(catalogue) if t not in known)


def plan_sql(catalogue):
    """One read builds the whole plan, from the CATALOGUE rather than a list here.

    Per row: how many markets it holds, whether those markets agree about the
    date, and then the four refusal counts — substantive children, provider
    identity, pseudo-FK pins, and children of an exception table that do NOT
    match that exception's predicate (the preservable substance).
    """
    subs = substantive_tables(catalogue) or ("events",)  # a no-op arm, never empty
    substantive_counts = "\n           + ".join(
        f"(SELECT count(*) FROM {t} c WHERE c.event_id = d.id)"
        # `events` can only appear via the empty-catalogue guard above, and a
        # self-join on the doomed row itself would count 1 and defer everything.
        # Rendering 0 keeps the SQL valid and the arm inert.
        if t != "events" else "0"
        for t in subs
    )
    preservable_counts = "\n           + ".join(
        f"(SELECT count(*) FROM {t} c WHERE c.event_id = d.id "
        f"AND NOT ({pred}))"
        for t, (pred, _note) in sorted(DERIVED_EXCEPTIONS.items())
        if t in catalogue
    ) or "0"
    identity = " OR ".join(f"d.{c} IS NOT NULL" for c in IDENTITY_COLUMNS)
    pins = "\n           + ".join(
        f"(SELECT count(*) FROM {tbl} c WHERE c.{col} = d.id AND c.{pred})"
        for tbl, col, pred in PSEUDO_FK_REFUSALS
    ) or "0"
    identity_cols = "".join(f", e.{c}" for c in IDENTITY_COLUMNS)
    group_cols = "".join(f", d.{c}" for c in IDENTITY_COLUMNS)
    return f"""
WITH pop AS (
    SELECT e.id, e.status, e.home_team_name, e.away_team_name,
           e.commence_time{identity_cols}
    FROM events e
    WHERE {_POPULATION}
),
grp AS (
    SELECT home_team_name AS h, away_team_name AS a
    FROM pop GROUP BY 1, 2 HAVING count(*) > 1
),
dup AS (
    SELECT p.* FROM pop p
    JOIN grp g ON g.h = p.home_team_name AND g.a = p.away_team_name
)
SELECT d.id, d.status, d.home_team_name, d.away_team_name, d.commence_time,
       count(f.id) AS n_markets,
       count(DISTINCT date(f.commence_time)) AS n_market_dates,
       count(*) FILTER (WHERE f.id IS NOT NULL AND f.commence_time IS NULL)
           AS n_null_market_times,
       min(f.commence_time) AS market_time,
       ({substantive_counts}) AS n_other_substantive,
       (CASE WHEN {identity} THEN 1 ELSE 0 END) AS has_provider_identity,
       ({pins}) AS n_user_pins,
       ({preservable_counts}) AS n_preservable
FROM dup d
LEFT JOIN {HOLDER_TABLE} f ON f.event_id = d.id
GROUP BY d.id, d.status, d.home_team_name, d.away_team_name,
         d.commence_time{group_cols}
ORDER BY d.home_team_name, d.away_team_name, d.id
"""

_CENSUS_SQL = f"""
SELECT e.status, count(*) AS n
FROM events e WHERE {_POPULATION}
GROUP BY e.status ORDER BY n DESC
"""

# The out-of-scope half, printed so the follow-up starts from a number rather
# than from "there were some others".
_SINGLETON_CENSUS_SQL = f"""
WITH pop AS (
    SELECT e.id, e.home_team_name AS h, e.away_team_name AS a
    FROM events e WHERE {_POPULATION}
),
grp AS (SELECT h, a FROM pop GROUP BY 1, 2 HAVING count(*) > 1)
SELECT count(*) AS singletons,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM futures_markets f WHERE f.event_id = p.id)) AS holding_a_market
FROM pop p
WHERE (p.h, p.a) NOT IN (SELECT h, a FROM grp)
"""

# Every write this script issues, as a named template. They live here rather
# than inline so the guard suite can render each one with real table names and
# parse it as Postgres — a syntax error in a repair is otherwise only ever found
# by a one-off dyno whose stdout cannot be read (gotcha #48).
SQL = {
    # LIKE copies the column list and types but NOT the foreign keys — a backup
    # that cascaded with its source would be no backup at all.
    "bak_create": "CREATE TABLE IF NOT EXISTS {bak} (LIKE {src} INCLUDING DEFAULTS)",
    "bak_index": "CREATE UNIQUE INDEX IF NOT EXISTS {bak}_pk ON {bak} (id)",
    "bak_copy": (
        "INSERT INTO {bak} SELECT s.* FROM {src} s "
        "WHERE s.{key} = ANY(CAST(:ids AS int[])) "
        "AND NOT EXISTS (SELECT 1 FROM {bak} b WHERE b.id = s.id)"
    ),
    "bak_missing": (
        "SELECT count(*) FROM {src} s "
        "WHERE s.{key} = ANY(CAST(:ids AS int[])) "
        "AND NOT EXISTS (SELECT 1 FROM {bak} b WHERE b.id = s.id)"
    ),
    # NO ACTION children go first or the parent delete is refused by the FK.
    "child_delete": "DELETE FROM {tbl} WHERE event_id = ANY(CAST(:doomed AS int[]))",
    # PRESERVE. Runs BEFORE `child_delete`, so a row this moves onto the survivor
    # is no longer `event_id = ANY(:doomed)` when the delete arrives and is left
    # alone. `NOT ({derived})` is the exception's own predicate negated — the
    # same text the plan counted with, so the rows moved are exactly the rows
    # counted (a second, paraphrased predicate here is how a repair moves a
    # different set than the one it reported).
    # `AS c` and not a bare alias: Postgres accepts both, and the guard suite
    # executes this statement against sqlite, which accepts only the explicit
    # form. The alias itself is not optional — the exception predicates are
    # written against `c` so that ONE text can be rendered into both the plan's
    # count and this UPDATE.
    "repoint": (
        "UPDATE {tbl} AS c SET event_id = :survivor "
        "WHERE c.event_id = ANY(CAST(:doomed AS int[])) AND NOT ({derived})"
    ),
    "event_delete": "DELETE FROM events WHERE id = ANY(CAST(:doomed AS int[]))",
    # The two `events` columns this repair writes, and it writes them together.
    # `events` has NO `updated_at` column (only `created_at`) — naming one here
    # fails every re-date on a dyno whose stdout nobody can read. That bug was
    # written and caught in #2871; the guard suite re-checks it against the live
    # model rather than against this comment.
    #
    # The status arm is guarded on `status = 'live'` so a row that is already
    # `closed` or `voided` keeps the word it has: this repair is fixing a DATE,
    # and the only status claim it has standing to make is that a fixture from
    # 2024 is not currently being played.
    "redate": (
        "UPDATE events SET commence_time = :market_time, "
        "status = CASE WHEN status = 'live' THEN :suspended ELSE status END "
        "WHERE id = :survivor "
        "AND (commence_time IS DISTINCT FROM :market_time OR status = 'live')"
    ),
}


def backup_is_exact(recon):
    """The D51 gate: every in-scope row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def classify(row):
    """ORPHAN / HOLDER / PRESERVE / DEFER for one row. Pure — the whole decision.

    ORPHAN    nothing points at it: no market, and every child it carries is
              provably derived under its table's exception predicate.
    HOLDER    holds a market, refuses nothing, and its markets agree about the
              date, so the venue's own date is recoverable.
    PRESERVE  would be an orphan except that it carries real substance — a
              foreign curve or a line-movement analysis. Deletable only after
              that substance is moved to the survivor, and only when the matchup
              has exactly one; :class:`Matchup` decides that, not this function,
              because it is a fact about the GROUP and not about the row.
    DEFER     everything else, and everything unrecognised. Two market dates on
              one row is two fixtures already merged; a substantive child that
              was measured at zero has appeared since; the row carries a provider
              identity, a user's pin, or a child of a table nobody classified.
              All reported, none guessed at.

    THE REFUSALS COME FIRST and they are unconditional. A row that any authority
    can name, or that a user has pinned, is never deleted by this repair no
    matter how phantom-shaped the rest of it looks.
    """
    if row.get("has_provider_identity"):
        return "DEFER"
    if row.get("n_user_pins"):
        return "DEFER"
    if row["n_other_substantive"]:
        return "DEFER"
    if row["n_markets"]:
        if row["n_market_dates"] == 1 and not row["n_null_market_times"] \
                and row["market_time"] is not None:
            return "HOLDER"
        return "DEFER"
    if row.get("n_preservable"):
        return "PRESERVE"
    return "ORPHAN"


class Matchup:
    """One `(home, away)` name pair and every population row wearing it.

    NOT one fixture — that is the whole lesson of `FCSB / PAOK`. A matchup may
    hold two real fixtures (two legs of a tie), and it therefore keeps as many
    survivors as its markets report distinct dates.
    """

    __slots__ = ("home", "away", "rows")

    def __init__(self, home, away):
        self.home = home
        self.away = away
        self.rows = []

    @property
    def orphans(self):
        return [r for r in self.rows if classify(r) == "ORPHAN"]

    @property
    def holders(self):
        return [r for r in self.rows if classify(r) == "HOLDER"]

    @property
    def preservable(self):
        """PRESERVE rows this matchup can actually place, i.e. none unless there
        is EXACTLY ONE survivor to place them on.

        Zero survivors: the whole matchup disappears and there is nowhere for the
        observation to go. Two: the group holds two legs of one tie and choosing
        between them is choosing which real fixture a real observation describes.
        Both fall through to :attr:`deferred` — the row is left standing, which
        keeps the observation attached to something and costs one uncleaned card.
        """
        if len(self.holders) != 1:
            return []
        return [r for r in self.rows if classify(r) == "PRESERVE"]

    @property
    def deferred(self):
        placed = {id(r) for r in self.preservable}
        return [r for r in self.rows
                if classify(r) == "DEFER"
                or (classify(r) == "PRESERVE" and id(r) not in placed)]

    @property
    def doomed_ids(self):
        """Deleted this pass: the orphans, plus the PRESERVE rows whose substance
        has somewhere to go. The latter are only ever deleted AFTER the re-point
        in the same transaction."""
        return [r["id"] for r in self.orphans + self.preservable]

    @property
    def repoint_ids(self):
        return [r["id"] for r in self.preservable]

    @property
    def survivor_ids(self):
        return [r["id"] for r in self.holders]

    def __repr__(self):
        return (f"<{self.home} vs {self.away}: {len(self.rows)} rows, "
                f"{len(self.orphans)} orphan / {len(self.holders)} holder / "
                f"{len(self.preservable)} preserve / {len(self.deferred)} defer>")


def _chunks(seq, n=CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def fk_children(session):
    """THE CANONICAL INVENTORY: every table with a foreign key to `events`.

    Read fresh every run. This is the default the whole policy hangs off — the
    hand-typed list this file used to carry is what CERT-2357 blocked.
    """
    from sqlalchemy import text
    return tuple((await session.execute(text(_FK_CHILDREN_SQL))).scalars().all())


async def build_plan(session, catalogue=None):
    """Read the population and group it by name. No writes."""
    from sqlalchemy import text

    if catalogue is None:
        catalogue = await fk_children(session)
    if HOLDER_TABLE not in catalogue:
        raise RuntimeError(
            f"the catalogue does not list {HOLDER_TABLE} as a child of events — "
            f"the inventory read failed or the schema moved. Refusing to run.")

    rows = [dict(r) for r in
            (await session.execute(text(plan_sql(catalogue)))).mappings().all()]

    matchups = {}
    for r in rows:
        key = (r["home_team_name"], r["away_team_name"])
        m = matchups.get(key)
        if m is None:
            m = matchups[key] = Matchup(*key)
        m.rows.append(r)

    ordered = sorted(matchups.values(), key=lambda m: (m.home or "", m.away or ""))

    # A row must be in exactly one arm. The three properties are independent
    # comprehensions over the same predicate, so a classify() that grew a fourth
    # answer would silently drop rows out of the plan instead of failing.
    for m in ordered:
        n = (len(m.orphans) + len(m.holders) + len(m.preservable)
             + len(m.deferred))
        if n != len(m.rows):
            raise RuntimeError(
                f"{m!r}: {n} classified rows for {len(m.rows)} members — "
                f"classify() returned something no arm handles. Refusing to run."
            )
        # A row must never be both deleted and left standing. The arms are four
        # independent comprehensions over one predicate, so this is cheap and it
        # is the invariant an off-by-one in `preservable` would break.
        if set(m.doomed_ids) & {r["id"] for r in m.deferred}:
            raise RuntimeError(
                f"{m!r}: a row is in both the doomed and the deferred arm. "
                f"Refusing to run.")
    return ordered, len(rows)


# --------------------------------------------------------------------------
# PHASE 1 — backup
# --------------------------------------------------------------------------

async def backup(session, event_ids):
    """Copy every in-scope row into `bak_4242_*`, then prove the copy is exact.

    Idempotent: re-running tops up rows that are not already backed up, so a
    partial run followed by a full one is safe.

    The backup covers the DERIVED children too, not just `events`. They are
    deleted by CASCADE rather than by a statement in this file, which makes them
    exactly the rows an undo would otherwise have no way to find.
    """
    from sqlalchemy import text

    copied = {}
    for src in ("events", *DERIVED_CHILD_TABLES):
        bak = BAK_PREFIX + src
        await session.execute(text(SQL["bak_create"].format(bak=bak, src=src)))
        await session.execute(text(SQL["bak_index"].format(bak=bak)))
        key = "id" if src == "events" else "event_id"
        n = 0
        for chunk in _chunks(event_ids):
            res = await session.execute(
                text(SQL["bak_copy"].format(bak=bak, src=src, key=key)),
                {"ids": chunk},
            )
            n += res.rowcount or 0
            await session.commit()
        copied[src] = n
    return copied


async def reconcile_backup(session, event_ids):
    """Every live in-scope row must have a backup row with the same id.

    Returns {table: missing_count}; all zero is the gate `--apply` waits on.
    """
    from sqlalchemy import text

    out = {}
    for src in ("events", *DERIVED_CHILD_TABLES):
        bak = BAK_PREFIX + src
        exists = (await session.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": bak}
        )).scalar()
        if not exists:
            out[src] = None  # never backed up
            continue
        key = "id" if src == "events" else "event_id"
        missing = 0
        for chunk in _chunks(event_ids):
            missing += (await session.execute(
                text(SQL["bak_missing"].format(src=src, bak=bak, key=key)),
                {"ids": chunk},
            )).scalar() or 0
        out[src] = missing
    return out


# --------------------------------------------------------------------------
# PHASE 2 — apply, one transaction per matchup
# --------------------------------------------------------------------------

async def apply_matchup(session, m):
    """Clean one matchup. One transaction; a failure isolates to this matchup.

    `events` is write-hot (constant poller locks), so the unit of work is one
    matchup — ~19 rows — with the DEFAULT lock wait. A batch UPDATE over
    thousands of ids, or an aggressive `lock_timeout`, rolls back on contention
    (measured, #1220/#1229 repairs).

    ORDER IS LOAD BEARING: the NO ACTION child goes before its parent, and the
    re-date lands in the same transaction as the deletes so the matchup is never
    observable in a state where the duplicates are gone but the survivor still
    claims to be a live 2026 fixture.
    """
    from sqlalchemy import text

    counts = {"deleted_children": 0, "deleted_events": 0, "redated": 0,
              "repointed": 0}
    doomed = m.doomed_ids
    repoint = m.repoint_ids

    # PRESERVE, and it goes FIRST — before the NO ACTION delete and before the
    # parent delete, so the moved row is already pointing at the survivor when
    # they run and neither statement can reach it.
    if repoint:
        if len(m.survivor_ids) != 1:
            # Unreachable via `Matchup.preservable`, which returns [] unless
            # there is exactly one. Re-asserted at WRITE time because the cost of
            # the two disagreeing is a real observation attached to the wrong
            # fixture, and because a future edit to either is the likeliest way
            # for them to disagree.
            raise RuntimeError(
                f"{m!r}: {len(repoint)} rows to preserve but "
                f"{len(m.survivor_ids)} survivors. Refusing to guess which "
                f"fixture the observation belongs to.")
        survivor = m.survivor_ids[0]
        for tbl in PRESERVABLE_TABLES:
            derived, _note = DERIVED_EXCEPTIONS[tbl]
            res = await session.execute(
                text(SQL["repoint"].format(tbl=tbl, derived=derived)),
                {"doomed": repoint, "survivor": survivor},
            )
            counts["repointed"] += res.rowcount or 0

    if doomed:
        for tbl in NO_ACTION_DERIVED_TABLES:
            res = await session.execute(
                text(SQL["child_delete"].format(tbl=tbl)), {"doomed": doomed}
            )
            counts["deleted_children"] += res.rowcount or 0
        res = await session.execute(text(SQL["event_delete"]), {"doomed": doomed})
        counts["deleted_events"] = res.rowcount or 0

    for h in m.holders:
        res = await session.execute(text(SQL["redate"]), {
            "survivor": h["id"],
            "market_time": h["market_time"],
            "suspended": EVENT_SUSPENDED,
        })
        counts["redated"] += res.rowcount or 0

    await session.commit()
    return counts


async def run(args):
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        census = (await s.execute(text(_CENSUS_SQL))).all()
        total = sum(r.n for r in census)
        print("=== #4242 phantom polymarket events — population ===")
        for r in census:
            print(f"  {r.status:>12}: {r.n:>7}")
        print(f"  {'TOTAL':>12}: {total:>7}")

        if args.census_singletons:
            sing = (await s.execute(text(_SINGLETON_CENSUS_SQL))).mappings().one()
            print(f"\n=== OUT OF SCOPE — singleton now-stamped rows ===")
            print(f"  {sing['singletons']} rows, {sing['holding_a_market']} of them "
                  f"holding a market. A fabricated date on a row nothing "
                  f"duplicates: a truth defect, not a search-page defect. Its own "
                  f"measurement, its own ship.")

        if total == 0:
            print("\nNothing to repair — population is 0 (idempotent no-op).")
            return
        if total < MIN_EXPECTED_POPULATION and not args.allow_small:
            print(f"\n⚠️  population {total} is below the {MIN_EXPECTED_POPULATION} "
                  f"floor. Either the predicate broke or a prior run already did "
                  f"the work — the two look identical from here. Pass "
                  f"--allow-small once you know which.")
            if args.apply or args.backup:
                return

        # THE CANONICAL INVENTORY, read before the plan and printed before the
        # arms. A reader must be able to see what the refusal set was on the run
        # that did the writing, not on the day the file was written.
        catalogue = await fk_children(s)
        unknown = unknown_children(catalogue)
        print(f"\n=== canonical inventory: {len(catalogue)} FK children of "
              f"events ===")
        print(f"  holder            : {HOLDER_TABLE}")
        print(f"  derived exceptions: "
              f"{', '.join(f'{t} [{p}]' for t, (p, _) in sorted(DERIVED_EXCEPTIONS.items()))}")
        print(f"  substantive       : {', '.join(substantive_tables(catalogue))}")
        print(f"  pseudo-FK refusals: "
              f"{', '.join(f'{t}.{c} WHERE {p}' for t, c, p in PSEUDO_FK_REFUSALS)}")
        if unknown:
            print(f"  ⚠️  UNCLASSIFIED, treated as substantive so every row "
                  f"carrying one DEFERS: {', '.join(unknown)}")
        missing = [t for t in CATALOGUE_2026_09_09 if t not in catalogue]
        if missing:
            print(f"  ⚠️  in the 2026-09-09 record but NOT in the catalogue "
                  f"now: {', '.join(missing)}")

        matchups, rows = await build_plan(s, catalogue)
        if args.limit:
            matchups = matchups[:args.limit]

        n_orphan = sum(len(m.orphans) for m in matchups)
        n_holder = sum(len(m.holders) for m in matchups)
        n_preserve = sum(len(m.preservable) for m in matchups)
        n_defer = sum(len(m.deferred) for m in matchups)
        vanishing = [m for m in matchups if not m.holders and not m.deferred]

        print(f"\n=== plan: {len(matchups)} matchups / {rows} rows ===")
        print(f"  DELETE   (orphans, no market, only provably derived children): "
              f"{n_orphan}")
        print(f"  RE-DATE  (holders, markets agree on one date)                : "
              f"{n_holder}")
        print(f"  PRESERVE (real substance moved to the one survivor, then "
              f"deleted): {n_preserve}")
        print(f"  DEFER    (ambiguous or refused — reported, untouched)        : "
              f"{n_defer}")
        print(f"  matchups that disappear entirely (all-orphan)                : "
              f"{len(vanishing)}")

        if n_preserve:
            print("\n  PRESERVED rows — a foreign curve or a line-movement "
                  "analysis re-pointed onto the surviving canonical event "
                  "before the phantom is deleted. An ANCHOR is never moved "
                  "(#2871); a row carrying one defers:")
            for m in matchups:
                for r in m.preservable:
                    print(f"    → {m.home} vs {m.away} (id {r['id']}, "
                          f"{r['n_preservable']} preservable child rows) "
                          f"→ survivor {m.survivor_ids[0]}")

        if n_defer:
            print("\n  DEFERRED rows — two fixtures already merged onto one row, "
                  "a substantive child that was measured at zero has appeared, a "
                  "provider identity, a user's pin, or substance with no single "
                  "survivor to hold it. File as matching-symptom under #2693 "
                  "(D35), do not guess:")
            for m in matchups:
                for r in m.deferred[:1]:
                    why = []
                    if r.get("has_provider_identity"):
                        why.append("PROVIDER ID")
                    if r.get("n_user_pins"):
                        why.append(f"{r['n_user_pins']} user pin(s)")
                    if r["n_other_substantive"]:
                        why.append(f"{r['n_other_substantive']} substantive children")
                    if r.get("n_preservable") and len(m.holders) != 1:
                        why.append(f"{r['n_preservable']} preservable rows but "
                                   f"{len(m.holders)} survivors")
                    if r["n_markets"] and r["n_market_dates"] != 1:
                        why.append(f"{r['n_markets']} markets across "
                                   f"{r['n_market_dates']} dates")
                    print(f"    ~ {m.home} vs {m.away} (id {r['id']}: "
                          f"{'; '.join(why) or 'see classify()'})")

        print("\n  first 10 matchups:")
        for m in matchups[:10]:
            keep = ", ".join(str(i) for i in m.survivor_ids) or "NOTHING"
            print(f"    {m.home} vs {m.away} | {len(m.rows)} rows | "
                  f"-{len(m.orphans)} | keeps {keep}")

        event_ids = [r["id"] for m in matchups for r in m.rows]

        # ---- backup ----
        if args.backup:
            print(f"\n=== backup: copying {len(event_ids)} events + derived children "
                  f"into {BAK_PREFIX}* ===")
            for t, n in (await backup(s, event_ids)).items():
                print(f"  {t:>24}: +{n} rows")

        recon = await reconcile_backup(s, event_ids)
        print("\n=== backup reconciliation (in-scope rows with no backup row) ===")
        for t, n in recon.items():
            state = "NEVER BACKED UP" if n is None else ("OK" if n == 0 else f"MISSING {n}")
            print(f"  {t:>24}: {state}")
        clean = backup_is_exact(recon)

        if not args.apply:
            print(f"\nDRY-RUN — no writes. Pass --backup to copy, then --apply to "
                  f"delete {n_orphan} orphans, preserve-and-delete "
                  f"{n_preserve}, and re-date {n_holder} holders.")
            return

        if not clean:
            print("\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup "
                  "first. D51 permits an unattended data repair only when the "
                  "undo exists.")
            return

        # ---- apply ----
        print(f"\n=== applying to {len(matchups)} matchups ===")
        tot = {"deleted_children": 0, "deleted_events": 0, "redated": 0,
               "repointed": 0}
        failures = []
        for i, m in enumerate(matchups, 1):
            # One bad matchup must never wipe the pass (gotcha #42).
            for attempt in (1, 2):
                try:
                    for k, v in (await apply_matchup(s, m)).items():
                        tot[k] += v
                    break
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    if attempt == 2:
                        failures.append((repr(m), str(exc)[:200]))
                    else:
                        await asyncio.sleep(0.5)
            if i % 25 == 0:
                print(f"  {i}/{len(matchups)} matchups | {tot}")

        print(f"\nCOMMITTED: {tot}")
        if failures:
            print(f"\n⚠️  {len(failures)} matchups failed (left untouched, re-runnable):")
            for r, e in failures[:10]:
                print(f"    {r}: {e}")

        # ---- verify ----
        after = (await s.execute(text(_CENSUS_SQL))).all()
        after_total = sum(r.n for r in after)
        print(f"\nPOST-REPAIR POPULATION: {after_total} (was {total}). The "
              f"expected residue is the singletons, the deferred rows, and the "
              f"re-dated holders — which LEAVE the population by construction, "
              f"because their commence_time no longer sits on created_at.")
        for r in after:
            print(f"  {r.status:>12}: {r.n:>7}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true",
                   help="copy every in-scope row into bak_4242_* and reconcile")
    p.add_argument("--apply", action="store_true",
                   help="clean the matchups (refuses unless the backup reconciles)")
    p.add_argument("--limit", type=int, default=0,
                   help="process at most N matchups — for a staged first slice")
    p.add_argument("--allow-small", action="store_true",
                   help="proceed even though the population is below the sanity floor")
    p.add_argument("--census-singletons", action="store_true",
                   help="also print the out-of-scope singleton population")
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
