"""#2871 — the historical cleanup: unmake the events a derivative market minted.

THE SHIP: a club's search page stops showing games that never happened.
Searching "FC Thun" returned 21 games for a club that has played about nine,
because `FC Thun / Lausanne-Sport - Total Corners`, `- Exact Score`,
`- First Team to Score`, `- Halftime Result` and `- Second Half Result` were
each their own event row.

PREVENTION ALREADY SHIPPED — `47e32fa9` (CERT-878), deployed v4057 on
2026-09-04 03:37Z. `is_derivative_market_name()` now refuses auto-create, so no
NEW phantom is minted. Post-deploy check at 04:23Z: 307 markets ingested / 51 of
them derivative-named / **0** new phantom events. This script is the owed DATA
REPAIR for the rows written before that landed.

    THE TAP MUST BE OFF BEFORE THIS RUNS. Cleaning while the firehose still
    writes just refills. It is off and proven off; that is what unblocked this.

------------------------------------------------------------------------------
WHY THIS IS NOT `DELETE FROM events WHERE <regex>`
------------------------------------------------------------------------------

Two measured findings kill the obvious one-liner:

1. **68% of these rows are the only record of their fixture.** Measured over the
   full population (no sampling): only 31.6% have a real counterpart — a
   non-derivative event with the same home name, the cleaned away name, within
   ±2 days. The other 68.4% are real fixtures in leagues we ingest no main line
   for (Serbian, Bulgarian, Swiss lower divisions), known to us ONLY through
   their corners market. Deleting them removes the fixture from search instead
   of fixing it, which is the opposite of the ship.

   The counterpart test uses the EXACT home name deliberately. The looser "any
   home name within ±2 days" net reads 38.8% and is **96.6% false pairs**
   (1,816 of 1,879): a team plays several times in two days, so ignoring the
   home name does not identify a fixture. Genuine name variants
   (`Colorado Rapids SC` ≡ `Colorado Rapids`) are only ~63 pairs and are
   team-identity work — lane1's, under D39, not recovered here.

2. **`events` has 11 FK children, not one.** On this population:
   `win_prob_snapshots` 284k (CASCADE), `futures_markets` 40k (NO ACTION),
   `event_provider_anchors` 4k (CASCADE), `line_movement_analyses` 698
   (NO ACTION), the other seven zero. A bare DELETE destroys ~288k rows without
   a word and is blocked by the NO ACTION pair before it gets there.

------------------------------------------------------------------------------
THE REPAIR — normalize-and-merge, two branches, ONE `events` column written
------------------------------------------------------------------------------

Group the population by ``(home_team_name, cleaned away_team_name,
date(commence_time))``. Per group:

  **Branch A — a real counterpart exists (~31%).** The survivor is the real
  event. Every bogus member is deleted; its markets move to the real event.

  **Branch B — no counterpart (~69%).** The survivor is the oldest bogus member,
  with `away_team_name` rewritten to the cleaned name — a single-column UPDATE
  that turns the phantom back into the fixture it always was. The rest of the
  group is deleted and their markets move onto it.

`home_team_name` is polluted 0 times out of 12,725: `extract_matchup` splits on
`" vs. "`, so the suffix can only ever ride on team_b. `away_team_name` is the
only `events` column this writes. `home_team_id`/`away_team_id` are NULL on all
of them, so no `teams` row is entangled.

CHILDREN, and why each disposition is what it is:

* `futures_markets` (40k) → **RE-POINTED** to the survivor. A corners market IS
  a market on that match; the bug was minting a fake *event* for it, not the
  link. `47e32fa9` refuses auto-create but explicitly still allows a derivative
  market to link to a fixture we already hold, so this is the shipped behaviour
  applied backwards. `uq_futures_source_external` is `(source, external_id)` —
  `event_id` is not in it, so re-pointing cannot collide.

* `win_prob_snapshots` (284k) → **DELETED, not re-pointed**, on BOTH branches.
  The table is keyed `(event_id, source)` and has **no `market_id`**, so these
  are *event-level* win-probability series; 284,256 of 284,260 are `polymarket`,
  i.e. derived from the derivative market's own price. Re-pointing them injects
  a corners-derived probability into a real match's curve — a cross-event data
  merge (gotcha #46) and a direct hit on *"the blend is the product"*.

  They go on Branch B too, including the survivor that keeps its row. Otherwise
  a survivor ends up correctly named while still carrying a corners curve, which
  is strictly WORSE than today, because now it looks legitimate.

* `event_provider_anchors` (4k) → **DELETED.** All of them are
  `source='polymarket'`, `id_kind='market'`. The anchor asserts "this provider
  id ↔ this fixture" and the fixture is phantom. Only `id_kind='game'` may ever
  anchor an absorption, so nothing load-bearing is lost. THE TRAP: the anchor
  uniqueness is `(source, source_id, id_kind)` — **`event_id` is not in it** —
  so a wrong re-point would be *silently accepted* forever, permanently
  asserting that a corners market's id anchors the real match. No constraint
  catches it. That is why these are deleted and never moved.

  `event_provider_anchors` is not lane1b's table (D39 lane1 / D50 authority
  lane). The deletion is confined to anchors hanging off rows this removes, it
  is backed up, and it is called out by name to both lanes.

* `line_movement_analyses` (698) → **DELETED.** All 698 are
  `analysis_type='taxonomy_enrichment'` — a regenerable LLM cache describing the
  phantom's garbage name. Re-pointing would put corners-derived taxonomy on the
  real event; deleting lets the survivor regenerate its own.

LIVE ROWS ARE DEFERRED, NOT SWEPT. Events currently `status='live'` are held
back unless `--include-live`. They are transient — every one measured was a
soccer phantom a few hours past commence, and `detect_and_close_stale_events`
closes them — and this script is idempotent, so the next run collects them once
they land in `closed`. Groups are homogeneous by liveness (measured: 0 mixed
groups out of 5,477), so holding one back never splits a fixture.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

`--apply` REFUSES to run until `--backup` has copied every in-scope row into
`bak_2871_*` and reconciled the copy exactly. The undo is one command:

    heroku run:detached -a bainluck \
      "python3 scripts/restore_2871_phantom_derivative_events.py --apply"

------------------------------------------------------------------------------
USAGE
------------------------------------------------------------------------------

    python3 scripts/repair_2871_phantom_derivative_events.py             # census + plan, no writes
    python3 scripts/repair_2871_phantom_derivative_events.py --backup    # copy rows, reconcile
    python3 scripts/repair_2871_phantom_derivative_events.py --apply --limit 50   # staged slice
    python3 scripts/repair_2871_phantom_derivative_events.py --apply     # the rest

Heroku one-off (gotcha #48 — a non-detached `heroku run` does not execute in the
sandbox; PROJECT_PATH=backend puts scripts at /app, so NEVER `cd backend` and
never a `backend/scripts/...` path):

    heroku run:detached -a bainluck "python3 scripts/repair_2871_phantom_derivative_events.py --backup"

And a one-off dyno runs the DEPLOYED SLUG, not your branch — this file must be
merged and deployed before any of the above does anything.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The population predicate is the SAME vocabulary the prevention refuses. Import
# it rather than restating it: a repair whose net differs from the fix's net
# either leaves rows behind or eats rows the fix would have allowed.
#
# `_DERIVATIVE_SUFFIX_RE` is private on purpose and stays that way. `47e32fa9`
# is emphatic that the suffix must NOT be stripped in the parse path — it is
# load bearing there (`_MATCHUP_NON_GAME_KEYWORDS` reads "winner" out of
# "- First 5 Innings Winner" to keep a period market out of a full-game blend,
# the G3 kill in test_kalshi_market_backfill_reserve). Exporting a
# `strip_derivative_suffix()` helper would put that footgun one autocomplete
# away. Stripping is correct HERE, in a one-shot repair of already-written
# rows, and nowhere else.
from app.utils.prediction_market_matching import (  # noqa: E402
    _DERIVATIVE_SUFFIX_RE,
    is_derivative_market_name,
)

# The regex is passed to Postgres as a BIND VALUE, never interpolated into the
# SQL text. That is deliberate: inside SQLAlchemy `text()`, the `(?:` of a
# non-capturing group is parsed as a bind parameter named `:Exact` and the query
# dies as a bare `query_failed` with no hint (gotcha #45). As a value it is
# never scanned for binds, so the pattern Postgres matches is byte-identical to
# the one Python matches — one vocabulary, not two that drift.
DERIV_RE = _DERIVATIVE_SUFFIX_RE.pattern

# Sanity floor. A repair that finds nothing and reports success is the worst
# possible outcome (gotcha #53: an empty result is a response shape, not an
# absence). Measured population on 2026-09-04 was 12,746; anything under this
# means the predicate broke, not that the work is done.
MIN_EXPECTED_POPULATION = 5_000

CHUNK = 500

# child table -> the disposition this repair applies. RE-POINT moves the row to
# the survivor; DELETE removes it. See the module docstring for why each is what
# it is — none of these are interchangeable.
CHILD_DELETE_TABLES = (
    "win_prob_snapshots",
    "event_provider_anchors",
    "line_movement_analyses",
)
CHILD_REPOINT_TABLES = ("futures_markets",)

BAK_PREFIX = "bak_2871_"
LEDGER = BAK_PREFIX + "market_repoint"

_POPULATION = "e.away_team_name ~* :deriv_re"

_PLAN_SQL = f"""
WITH b AS (
    SELECT e.id, e.status, e.home_team_name, e.away_team_name, e.commence_time,
           regexp_replace(e.away_team_name, :deriv_re, '', 'i') AS clean_away
    FROM events e
    WHERE {_POPULATION}
)
SELECT DISTINCT ON (b.id)
       b.id, b.status, b.home_team_name, b.away_team_name, b.clean_away,
       b.commence_time, date(b.commence_time) AS d, r.id AS real_event_id
FROM b
LEFT JOIN events r
       ON r.home_team_name = b.home_team_name
      AND r.away_team_name = b.clean_away
      AND r.id <> b.id
      AND r.away_team_name !~* :deriv_re
      AND r.commence_time BETWEEN b.commence_time - INTERVAL '2 days'
                              AND b.commence_time + INTERVAL '2 days'
ORDER BY b.id, r.id
"""

_CENSUS_SQL = f"""
SELECT e.status, COUNT(*) AS n
FROM events e WHERE {_POPULATION}
GROUP BY e.status ORDER BY n DESC
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
        "SELECT COUNT(*) FROM {src} s "
        "WHERE s.{key} = ANY(CAST(:ids AS int[])) "
        "AND NOT EXISTS (SELECT 1 FROM {bak} b WHERE b.id = s.id)"
    ),
    "ledger_ddl": (
        "CREATE TABLE IF NOT EXISTS {ledger} ("
        " market_id BIGINT PRIMARY KEY,"
        " old_event_id BIGINT NOT NULL,"
        " new_event_id BIGINT NOT NULL,"
        " moved_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
    ),
    # Write-ahead: the ledger row lands in the SAME transaction as the move, so
    # an interrupted run still knows where every market came from.
    "ledger_insert": (
        "INSERT INTO {ledger} (market_id, old_event_id, new_event_id) "
        "SELECT f.id, f.event_id, :survivor FROM futures_markets f "
        "WHERE f.event_id = ANY(CAST(:doomed AS int[])) "
        "ON CONFLICT (market_id) DO NOTHING"
    ),
    "repoint": (
        "UPDATE futures_markets SET event_id = :survivor, updated_at = NOW() "
        "WHERE event_id = ANY(CAST(:doomed AS int[]))"
    ),
    "child_delete": "DELETE FROM {tbl} WHERE event_id = ANY(CAST(:members AS int[]))",
    # `events` has NO `updated_at` column (only `created_at`) — an
    # `updated_at = NOW()` here fails every rename. `futures_markets` does have
    # one, which is why "repoint" sets it and this does not. Guarded by
    # test_update_events_only_writes_columns_that_exist.
    "rename": (
        "UPDATE events SET away_team_name = :clean "
        "WHERE id = :survivor AND away_team_name <> :clean"
    ),
    "event_delete": "DELETE FROM events WHERE id = ANY(CAST(:doomed AS int[]))",
}


def backup_is_exact(recon):
    """The D51 gate: every in-scope row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo.
    """
    return bool(recon) and all(n == 0 for n in recon.values())


class Group:
    """One fixture: the rows that must collapse into a single event."""

    __slots__ = ("home", "clean_away", "date", "members", "real_event_id")

    def __init__(self, home, clean_away, date, real_event_id):
        self.home = home
        self.clean_away = clean_away
        self.date = date
        self.real_event_id = real_event_id
        self.members = []  # list of dicts, ordered by id

    @property
    def branch(self):
        return "A" if self.real_event_id is not None else "B"

    @property
    def has_live(self):
        return any(m["status"] == "live" for m in self.members)

    @property
    def survivor_id(self):
        """Branch A survives onto the real event; Branch B onto its oldest row."""
        if self.real_event_id is not None:
            return self.real_event_id
        return self.members[0]["id"]

    @property
    def doomed_ids(self):
        """Every member that goes away. Branch B keeps its survivor."""
        keep = None if self.real_event_id is not None else self.members[0]["id"]
        return [m["id"] for m in self.members if m["id"] != keep]

    @property
    def member_ids(self):
        return [m["id"] for m in self.members]

    def __repr__(self):
        return (f"<{self.branch} {self.home} vs {self.clean_away} {self.date} "
                f"{len(self.members)} members -> {self.survivor_id}>")


def _chunks(seq, n=CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def build_plan(session, include_live=False):
    """Read the population and fold it into fixtures. No writes."""
    from sqlalchemy import text

    rows = (await session.execute(
        text(_PLAN_SQL), {"deriv_re": DERIV_RE}
    )).mappings().all()

    # The predicate is the load-bearing part of this whole script. If Python and
    # Postgres disagree about what a derivative name is, the repair operates on
    # a different set than the one it was sized against.
    disagree = [r["away_team_name"] for r in rows
                if not is_derivative_market_name(r["away_team_name"])]
    if disagree:
        raise RuntimeError(
            f"predicate disagreement: Postgres matched {len(disagree)} name(s) "
            f"that Python's is_derivative_market_name() rejects, e.g. "
            f"{disagree[:3]!r}. Refusing to run — one vocabulary or none."
        )

    groups = {}
    for r in rows:
        key = (r["home_team_name"], r["clean_away"], r["d"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = Group(r["home_team_name"], r["clean_away"],
                                    r["d"], r["real_event_id"])
        # bool_or over the group: if ANY member found the real fixture, the
        # whole group is Branch A. They are the same fixture, so a group must
        # never split across branches.
        if r["real_event_id"] is not None and g.real_event_id is None:
            g.real_event_id = r["real_event_id"]
        g.members.append(dict(r))

    ordered = []
    for g in groups.values():
        g.members.sort(key=lambda m: m["id"])
        ordered.append(g)
    ordered.sort(key=lambda g: (g.home or "", g.clean_away or "", str(g.date)))

    live = [g for g in ordered if g.has_live]
    actionable = ordered if include_live else [g for g in ordered if not g.has_live]
    return actionable, live, len(rows)


# --------------------------------------------------------------------------
# PHASE 1 — backup
# --------------------------------------------------------------------------

async def _child_ddl(session, src):
    from sqlalchemy import text

    bak = BAK_PREFIX + src
    await session.execute(text(SQL["bak_create"].format(bak=bak, src=src)))
    await session.execute(text(SQL["bak_index"].format(bak=bak)))
    return bak


async def backup(session, event_ids, apply):
    """Copy every in-scope row into `bak_2871_*`, then prove the copy is exact.

    Idempotent: re-running tops up rows that are not already backed up, so a
    partial run followed by a full one is safe.
    """
    from sqlalchemy import text

    tables = ["events", *CHILD_DELETE_TABLES, *CHILD_REPOINT_TABLES]
    copied = {}

    if not apply:
        return {t: None for t in tables}

    for src in tables:
        bak = await _child_ddl(session, src)
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

    # The re-point ledger is not a `LIKE` copy — it records the transition, not
    # the row, because a market that moved is not a market that was deleted.
    await session.execute(text(SQL["ledger_ddl"].format(ledger=LEDGER)))
    await session.commit()
    return copied


async def reconcile_backup(session, event_ids):
    """Every live in-scope row must have a backup row with the same id.

    Returns {table: missing_count}; all zero is the gate `--apply` waits on.
    """
    from sqlalchemy import text

    out = {}
    for src in ["events", *CHILD_DELETE_TABLES, *CHILD_REPOINT_TABLES]:
        bak = BAK_PREFIX + src
        exists = (await session.execute(text(
            "SELECT to_regclass(:t) IS NOT NULL"
        ), {"t": bak})).scalar()
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
# PHASE 2 — apply, one transaction per fixture
# --------------------------------------------------------------------------

async def apply_group(session, g):
    """Collapse one fixture. One transaction; a failure isolates to this group.

    `events` is write-hot (constant poller locks), so the unit of work is one
    fixture — ~2.3 event rows — with the DEFAULT lock wait. A batch UPDATE over
    thousands of ids, or an aggressive `lock_timeout`, rolls back on contention
    (measured, #1220/#1229 repairs).
    """
    from sqlalchemy import text

    survivor = g.survivor_id
    doomed = g.doomed_ids
    members = g.member_ids
    counts = {"repointed": 0, "deleted_children": 0, "renamed": 0, "deleted_events": 0}

    # 1. Markets move off the doomed rows onto the survivor, ledgered first.
    if doomed:
        await session.execute(
            text(SQL["ledger_insert"].format(ledger=LEDGER)),
            {"survivor": survivor, "doomed": doomed},
        )
        res = await session.execute(
            text(SQL["repoint"]), {"survivor": survivor, "doomed": doomed}
        )
        counts["repointed"] = res.rowcount or 0

    # 2. Phantom children die on EVERY member, survivor included. See docstring:
    #    a correctly-named survivor still carrying a corners-derived curve is
    #    worse than the phantom, because it now looks legitimate.
    for tbl in CHILD_DELETE_TABLES:
        res = await session.execute(
            text(SQL["child_delete"].format(tbl=tbl)), {"members": members}
        )
        counts["deleted_children"] += res.rowcount or 0

    # 3. Branch B: the one column this repair writes to `events`.
    #    NOTE: `events` has NO `updated_at` column (only `created_at`) — an
    #    `updated_at = NOW()` here fails every rename. `futures_markets` does
    #    have one, which is why step 1 sets it and this does not.
    if g.real_event_id is None:
        res = await session.execute(
            text(SQL["rename"]), {"clean": g.clean_away, "survivor": survivor}
        )
        counts["renamed"] = res.rowcount or 0

    # 4. The rows that never were.
    if doomed:
        res = await session.execute(text(SQL["event_delete"]), {"doomed": doomed})
        counts["deleted_events"] = res.rowcount or 0

    await session.commit()
    return counts


async def run(args):
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        census = (await s.execute(text(_CENSUS_SQL), {"deriv_re": DERIV_RE})).all()
        total = sum(r.n for r in census)
        print("=== #2871 phantom derivative events — population ===")
        for r in census:
            print(f"  {r.status:>12}: {r.n:>7}")
        print(f"  {'TOTAL':>12}: {total:>7}")

        if total == 0:
            print("\nNothing to repair — population is 0 (idempotent no-op).")
            return
        if total < MIN_EXPECTED_POPULATION and not args.allow_small:
            print(f"\n⚠️  population {total} is below the {MIN_EXPECTED_POPULATION} floor. "
                  f"Either the predicate broke or a prior run already did the work — "
                  f"the two look identical from here. Pass --allow-small once you know which.")
            if args.apply or args.backup:
                return

        actionable, live, rows = await build_plan(s, include_live=args.include_live)
        if args.limit:
            actionable = actionable[:args.limit]

        branch_a = [g for g in actionable if g.branch == "A"]
        branch_b = [g for g in actionable if g.branch == "B"]
        n_delete = sum(len(g.doomed_ids) for g in actionable)
        n_rename = len(branch_b)

        print(f"\n=== plan: {len(actionable)} fixtures "
              f"({len(branch_a)} Branch A / {len(branch_b)} Branch B) ===")
        print(f"  events deleted : {n_delete}")
        print(f"  events renamed : {n_rename}  (Branch B survivors)")
        if live:
            print(f"  DEFERRED (live): {len(live)} fixtures / "
                  f"{sum(len(g.members) for g in live)} events — held back; they "
                  f"close within hours and the next run collects them"
                  + ("" if not args.include_live else " [--include-live: INCLUDED]"))

        print("\n  first 10 fixtures:")
        for g in actionable[:10]:
            print(f"    [{g.branch}] {g.home} vs {g.clean_away} {g.date} "
                  f"| {len(g.members)} rows -> survivor {g.survivor_id}")

        event_ids = [i for g in actionable for i in g.member_ids]

        # ---- backup ----
        if args.backup:
            print(f"\n=== backup: copying {len(event_ids)} events + children into "
                  f"{BAK_PREFIX}* ===")
            copied = await backup(s, event_ids, apply=True)
            for t, n in copied.items():
                print(f"  {t:>24}: +{n} rows")

        recon = await reconcile_backup(s, event_ids)
        print("\n=== backup reconciliation (in-scope rows with no backup row) ===")
        for t, n in recon.items():
            state = "NEVER BACKED UP" if n is None else ("OK" if n == 0 else f"MISSING {n}")
            print(f"  {t:>24}: {state}")
        clean = backup_is_exact(recon)

        if not args.apply:
            print(f"\nDRY-RUN — no writes. Pass --backup to copy, then --apply to "
                  f"collapse {len(actionable)} fixtures "
                  f"({n_delete} deletes, {n_rename} renames).")
            return

        if not clean:
            print("\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup first. "
                  "D51 permits an unattended data repair only when the undo exists.")
            return

        # ---- apply ----
        print(f"\n=== applying to {len(actionable)} fixtures ===")
        tot = {"repointed": 0, "deleted_children": 0, "renamed": 0, "deleted_events": 0}
        failures = []
        for i, g in enumerate(actionable, 1):
            # One bad fixture must never wipe the pass (gotcha #42).
            for attempt in (1, 2):
                try:
                    c = await apply_group(s, g)
                    for k, v in c.items():
                        tot[k] += v
                    break
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    if attempt == 2:
                        failures.append((repr(g), str(exc)[:200]))
                    else:
                        await asyncio.sleep(0.5)
            if i % 250 == 0:
                print(f"  {i}/{len(actionable)} fixtures | {tot}")

        print(f"\nCOMMITTED: {tot}")
        if failures:
            print(f"\n⚠️  {len(failures)} fixtures failed (left untouched, re-runnable):")
            for r, e in failures[:10]:
                print(f"    {r}: {e}")

        # ---- verify ----
        after = (await s.execute(text(_CENSUS_SQL), {"deriv_re": DERIV_RE})).all()
        after_total = sum(r.n for r in after)
        print(f"\nPOST-REPAIR POPULATION: {after_total} "
              f"(was {total}; expected residue = deferred live + anything skipped by --limit)")
        for r in after:
            print(f"  {r.status:>12}: {r.n:>7}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true",
                   help="copy every in-scope row into bak_2871_* and reconcile")
    p.add_argument("--apply", action="store_true",
                   help="collapse the fixtures (refuses unless the backup reconciles)")
    p.add_argument("--include-live", action="store_true",
                   help="also touch fixtures with a currently-live row (default: defer)")
    p.add_argument("--limit", type=int, default=0,
                   help="process at most N fixtures — for a staged first slice")
    p.add_argument("--allow-small", action="store_true",
                   help="proceed even though the population is below the sanity floor")
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
