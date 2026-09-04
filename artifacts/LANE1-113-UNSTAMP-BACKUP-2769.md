# LANE1-113 — the D42-B unstamp: backup, apply, and the one-command restore

**PILLAR: TRUTH. SHIP: one game can never again wear another game's ESPN id.**

Written **2026-09-04 06:50am PT / 13:50Z** (stamped from `date`), before any write, under
**D51 = B(b)** (a reversible data repair with a backup and a one-command restore may be applied
unattended by the owning lane) and **D42 = A with the Friday clause** (if the refused twin groups
are not clear by Friday 9/4, unstamp them and land the index anyway).

## 1. The population, measured twice this morning

`POST /api/admin/db-query` at 13:41Z and the repair rail's own dry run at 13:47Z agree:

```
contested_ids  5      rows_wearing  11
```

**Not 8 groups / 17 rows.** Three of #2769's eight cleared on their own between 9/3 and today
(`401882924` Celta/Osasuna, `401884813` Augsburg/Schalke, `761621` Red Bulls II/Crew 2). The
remaining five were re-asked of ESPN **from production egress** (the repair rail, not a sandbox
curl — notice 7) and every one is still refused:

| `espn_id` | outcome | ESPN says | rows |
|---|---|---|---|
| `401504210` | AUTHORITY_UNAVAILABLE | — (**502**, same as 9/3) | 2 |
| `401873756` | AUTHORITY_UNAVAILABLE | — (404, no usable record) | 3 |
| `401856258` | NO_ROW_AGREES | UC Irvine Anteaters v Cal State Bakersfield Roadrunners | 2 |
| `401869643` | NO_ROW_AGREES | Eastern Illinois Panthers v Little Rock Trojans | 2 |
| `748503` | NO_ROW_AGREES | Real Madrid v Real Oviedo | 2 |

`rows_planned: 0` — the rail plans nothing, by design. Row verdicts: `TEAMS_DISAGREE` 11/11.

## 2. THE BACKUP — the 11 rows exactly as they stood at 13:45Z

Read on the dyno itself (`run.8599`, a read-only one-off) as well as through db-query, so the
mapping below is production's answer and not a sandbox cache.

| `events.id` | `espn_id` | sport | fixture | commence_time (UTC) | status |
|---|---|---|---|---|---|
| `6585581` | `401873756` | baseball_ncaa | Gonzaga Bulldogs @ Oklahoma Sooners | 2026-05-29 14:00 | closed |
| `14807307` | `401873756` | baseball_ncaa | The Citadel Bulldogs @ Oklahoma Sooners | 2026-05-29 14:00 | closed |
| `14824959` | `401873756` | baseball_ncaa | The Citadel Bulldogs @ Oklahoma Sooners | 2026-05-29 23:30 | completed |
| `14794949` | `401504210` | americanfootball_cfl | Toronto Argonauts @ Winnipeg Blue Bombers | 2022-11-20 23:00 | completed |
| `14970487` | `401504210` | americanfootball_cfl | Toronto Argonauts @ Winnipeg Blue Bombers | 2022-11-20 23:00 | completed |
| `14706321` | `401856258` | baseball_ncaa | Cal State Fullerton @ UC Irvine | 2026-05-16 20:00 | closed |
| `14707563` | `401856258` | baseball_ncaa | Cal State Fullerton @ UC Riverside | 2026-05-16 20:00 | closed |
| `14797493` | `401869643` | baseball_ncaa | Eastern Illinois Panthers @ TBD | 2026-05-23 22:05 | closed |
| `14797677` | `401869643` | baseball_ncaa | Arkansas-Little Rock Trojans @ Eastern Illinois Panthers | 2026-05-23 22:05 | completed |
| `14629773` | `748503` | soccer_spain_la_liga | Oviedo @ Real Madrid | 2026-05-03 16:30 | completed |
| `14632251` | `748503` | soccer_spain_la_liga | Oviedo @ Real Madrid | 2026-05-14 19:30 | closed |

**Every one of the 11 is a past, finished fixture** — the newest kicked off 2026-05-29, the oldest
in November 2022. Nothing here is live or upcoming, so taking the id off costs no user-visible
score, clock or status update. That is the fact that makes plan B cheap rather than merely
permitted.

**Which row ESPN's name is closest to, recorded for #1204, not acted on.** `748503`: both rows say
`Oviedo`, ESPN says `Real Oviedo` — a vocabulary gap, and the 5/03 row (`14629773`) is the one
whose date matches a Real Madrid fixture. `401869643`: `14797677` carries
`Arkansas-Little Rock Trojans` against ESPN's `Little Rock Trojans` — the same club under two
names. When #1204 merges those identities, the correct row can be re-stamped **one at a time**,
which is precisely what the unique index will then enforce.

## 3. THE APPLY — what was run

One `heroku run:detached` one-off, plain (not base64 — that trips the obfuscation guardrail), no
`cd` and no path prefix (both silently no-op, `PROJECT_PATH=backend`). Per-row session, per-row
commit, **default lock wait** — `events` is write-hot and a short `lock_timeout` rolls back on
every row.

The statement is the repair rail's own clear, byte for byte
(`app/tasks/repair_authority_id_collisions.py`, `_CLEAR_SQL`):

```sql
UPDATE events SET espn_id = NULL WHERE id = :i AND espn_id = :v
```

**The compare is IN the write.** `AND espn_id = :v` is what makes this safe to run unattended: a
row whose id moved between this measurement and the write matches nothing, reports
`rowcount=0`, and is left exactly as it is.

```python
import asyncio
from sqlalchemy import text
from app.tasks.base import get_task_session
PAIRS = [(6585581,'401873756'),(14629773,'748503'),(14632251,'748503'),(14706321,'401856258'),(14707563,'401856258'),(14794949,'401504210'),(14797493,'401869643'),(14797677,'401869643'),(14807307,'401873756'),(14824959,'401873756'),(14970487,'401504210')]
SQL = text("UPDATE events SET espn_id = NULL WHERE id = :i AND espn_id = :v")
async def m():
    total = 0
    for i, v in PAIRS:
        async with get_task_session() as s:
            r = await s.execute(SQL, {"i": i, "v": v})
            await s.commit()
            total += r.rowcount
            print("LANE1-113-UNSTAMP " + str(i) + " " + v + " rowcount=" + str(r.rowcount))
    print("LANE1-113-UNSTAMP total=" + str(total))
asyncio.run(m())
```

## 4. THE ONE-COMMAND RESTORE

Put the file below on disk and run the two lines. It is the repair rail's own undo statement
(`UPDATE events SET espn_id = :v WHERE id = :i AND espn_id IS NULL`) over the same 11 pairs — the
`AND espn_id IS NULL` guard means a row that `espn_sync` has since re-anchored to a **correct** id
is skipped rather than overwritten (the rail calls that `ESPN_ID_REOCCUPIED`; a restore that skips
some rows is working, not failing).

```bash
cat > /tmp/lane1-114-restore.py <<'PY'
import asyncio
from sqlalchemy import text
from app.tasks.base import get_task_session
PAIRS = [(6585581,'401873756'),(14629773,'748503'),(14632251,'748503'),(14706321,'401856258'),(14707563,'401856258'),(14794949,'401504210'),(14797493,'401869643'),(14797677,'401869643'),(14807307,'401873756'),(14824959,'401873756'),(14970487,'401504210')]
SQL = text("UPDATE events SET espn_id = :v WHERE id = :i AND espn_id IS NULL")
async def m():
    total = 0
    for i, v in PAIRS:
        async with get_task_session() as s:
            r = await s.execute(SQL, {"i": i, "v": v})
            await s.commit()
            total += r.rowcount
            print("LANE1-113-RESTORE " + str(i) + " " + v + " rowcount=" + str(r.rowcount))
    print("LANE1-113-RESTORE total=" + str(total))
asyncio.run(m())
PY
heroku run:detached -a bainluck "python3 -c $(printf '%q' "$(cat /tmp/lane1-114-restore.py)")"
```

**One honest caveat about the restore, and it is a consequence of the ship, not a defect.** Putting
these ids back re-creates the five collisions. *Before* `uq_events_espn_id` is installed that
simply works. *After* it is installed the database will refuse the second row of each group — which
is the whole point of the index. Restoring after the index has landed therefore means dropping the
index first (`alembic downgrade`, i.e. a revert deploy), and reverting a deployed migration is
Alex's call only.

## 5. Verification

Both before and after, through `POST /api/admin/db-query`:

```sql
SELECT count(*) AS contested_ids FROM (
  SELECT espn_id FROM events WHERE espn_id IS NOT NULL
  GROUP BY espn_id HAVING count(*) > 1) t
```

Before: **5**. After: recorded in `REPORT-LANE1-113.md`.
