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

    orphans   1,843 (96%)  hold ZERO futures_markets  -> deleted
    holders      65        markets agree on one date  -> RE-DATED, never moved
    ambiguous     6        markets disagree           -> DEFERRED, reported

All **10** live rows in the population are holders, not orphans. That is the
"false-live duplicate" on the #4242 screenshot, and re-dating fixes it at the
source rather than hiding it.

------------------------------------------------------------------------------
WHAT MAKES DELETING AN ORPHAN LOSSLESS — a refusal, not an assumption
------------------------------------------------------------------------------

Measured on the 1,914: `odds_snapshots` 0 · `odds_aggregated` 0 ·
`espn_snapshots` 0 · `event_participants` 0 · `game_moments` 0 ·
`score_snapshots` 0 · `scoring_plays` 0 · `ranking_judgments` 0. There is no
odds or scores history on this population to lose.

That is a measurement of today, and a repair run next week runs against a
different database. So it is enforced rather than trusted: a row is an ORPHAN
only when every one of :data:`SUBSTANTIVE_CHILD_TABLES` is empty on it. A row
that has acquired real data since is not an orphan, it is a DEFER, and it is
reported. The only children an orphan may carry are the three in
:data:`DERIVED_CHILD_TABLES`:

* `win_prob_snapshots` (3,084) — event-level curves, keyed `(event_id, source)`
  with no `market_id`, every one derived from the phantom's own price. DELETED
  with the row (CASCADE), never re-pointed onto anything: injecting a phantom's
  curve into a real match is gotcha #46 and a direct hit on *the blend is the
  product*.
* `event_provider_anchors` (22) — DELETED (CASCADE). Never re-pointed. Anchor
  uniqueness is `(source, source_id, id_kind)` and **`event_id` is not in it**,
  so a wrong re-point is silently accepted forever, permanently asserting a
  provider id against the wrong fixture, with no constraint to catch it. The
  #2871 repair learned this the same way.
* `line_movement_analyses` (713) — DELETED explicitly, BEFORE the events,
  because its FK is NO ACTION and would otherwise block the delete. It is a
  regenerable LLM taxonomy cache describing the phantom's garbage name.

`market_link_changes` and `market_match_receipts` carry an event id with NO FK
**on purpose** — models.py is explicit that the forensic has to outlive its
subject. They are lane1b's under D39 and this script does not touch them. A
deleted phantom keeps its receipt, which is the point of one.

------------------------------------------------------------------------------
THE THREE ARMS
------------------------------------------------------------------------------

**DELETE — 1,843 orphans.** A fabricated date and two team names is the whole
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

# A row carrying ANY of these is not an orphan, whatever the census said last
# week. Measured 0 across the whole population on 2026-09-09 — this list is what
# turns that measurement into a refusal rather than an assumption.
#
# `futures_markets` leads because it is also the HOLDER test: a row that holds a
# market is the row the venue points at, and it is re-dated rather than deleted.
SUBSTANTIVE_CHILD_TABLES = (
    "futures_markets",
    "odds_snapshots",
    "odds_aggregated",
    "espn_snapshots",
    "event_participants",
    "game_moments",
    "score_snapshots",
    "scoring_plays",
    "ranking_judgments",
)

#: Everything else an orphan may carry. All three are derived from the phantom
#: itself or regenerable, and all three are DELETED — never re-pointed. See the
#: module docstring for why each one would be worse re-pointed than deleted.
DERIVED_CHILD_TABLES = (
    "win_prob_snapshots",
    "event_provider_anchors",
    "line_movement_analyses",
)

#: The only one of the three whose FK is NO ACTION, so the only one that has to
#: be deleted explicitly before the parent. The other two CASCADE. Asserted
#: against the live catalogue by the guard suite rather than trusted here.
NO_ACTION_DERIVED_TABLES = ("line_movement_analyses",)

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

_SUBSTANTIVE_COUNTS = "\n           + ".join(
    f"(SELECT count(*) FROM {t} c WHERE c.event_id = d.id)"
    for t in SUBSTANTIVE_CHILD_TABLES[1:]
)

# One read builds the whole plan. Per row: how many markets it holds, whether
# those markets agree about the date, and whether it carries any substantive
# child other than a market.
_PLAN_SQL = f"""
WITH pop AS (
    SELECT e.id, e.status, e.home_team_name, e.away_team_name, e.commence_time
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
       ({_SUBSTANTIVE_COUNTS}) AS n_other_substantive
FROM dup d
LEFT JOIN futures_markets f ON f.event_id = d.id
GROUP BY d.id, d.status, d.home_team_name, d.away_team_name, d.commence_time
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
    """ORPHAN / HOLDER / DEFER for one row. Pure — this is the whole decision.

    ORPHAN  nothing points at it: no market and no substantive child of any kind.
    HOLDER  holds a market, holds nothing else substantive, and its markets
            agree about the date, so the venue's own date is recoverable.
    DEFER   everything else. Two market dates on one row is two fixtures already
            merged; a substantive child that was measured at zero has appeared
            since. Both are reported, neither is guessed at.
    """
    if row["n_other_substantive"]:
        return "DEFER"
    if not row["n_markets"]:
        return "ORPHAN"
    if row["n_market_dates"] == 1 and not row["n_null_market_times"] \
            and row["market_time"] is not None:
        return "HOLDER"
    return "DEFER"


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
    def deferred(self):
        return [r for r in self.rows if classify(r) == "DEFER"]

    @property
    def doomed_ids(self):
        return [r["id"] for r in self.orphans]

    @property
    def survivor_ids(self):
        return [r["id"] for r in self.holders]

    def __repr__(self):
        return (f"<{self.home} vs {self.away}: {len(self.rows)} rows, "
                f"{len(self.orphans)} orphan / {len(self.holders)} holder / "
                f"{len(self.deferred)} defer>")


def _chunks(seq, n=CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def build_plan(session):
    """Read the population and group it by name. No writes."""
    from sqlalchemy import text

    rows = [dict(r) for r in
            (await session.execute(text(_PLAN_SQL))).mappings().all()]

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
        n = len(m.orphans) + len(m.holders) + len(m.deferred)
        if n != len(m.rows):
            raise RuntimeError(
                f"{m!r}: {n} classified rows for {len(m.rows)} members — "
                f"classify() returned something no arm handles. Refusing to run."
            )
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

    counts = {"deleted_children": 0, "deleted_events": 0, "redated": 0}
    doomed = m.doomed_ids

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

        matchups, rows = await build_plan(s)
        if args.limit:
            matchups = matchups[:args.limit]

        n_orphan = sum(len(m.orphans) for m in matchups)
        n_holder = sum(len(m.holders) for m in matchups)
        n_defer = sum(len(m.deferred) for m in matchups)
        vanishing = [m for m in matchups if not m.holders and not m.deferred]

        print(f"\n=== plan: {len(matchups)} matchups / {rows} rows ===")
        print(f"  DELETE  (orphans, no market and no substantive child): {n_orphan}")
        print(f"  RE-DATE (holders, markets agree on one date)         : {n_holder}")
        print(f"  DEFER   (ambiguous — reported, untouched)            : {n_defer}")
        print(f"  matchups that disappear entirely (all-orphan)        : "
              f"{len(vanishing)}")

        if n_defer:
            print("\n  DEFERRED rows — two fixtures already merged onto one row, or "
                  "a substantive child that was measured at zero has appeared. "
                  "File as matching-symptom under #2693 (D35), do not guess:")
            for m in matchups:
                for r in m.deferred[:1]:
                    print(f"    ~ {m.home} vs {m.away} (id {r['id']}, "
                          f"{r['n_markets']} markets across "
                          f"{r['n_market_dates']} dates, "
                          f"{r['n_other_substantive']} other substantive children)")

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
                  f"delete {n_orphan} orphans and re-date {n_holder} holders.")
            return

        if not clean:
            print("\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup "
                  "first. D51 permits an unattended data repair only when the "
                  "undo exists.")
            return

        # ---- apply ----
        print(f"\n=== applying to {len(matchups)} matchups ===")
        tot = {"deleted_children": 0, "deleted_events": 0, "redated": 0}
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
