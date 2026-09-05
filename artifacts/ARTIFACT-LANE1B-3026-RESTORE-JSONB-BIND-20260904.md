# lane1b/037 — the D51 undo could not run. CERT-932's named repair.

**PILLAR: MATCHING. SHIP (still owed): the seven live "Will … Finish Top 3" cards stop existing.**
This session did not deliver that ship. It removed the thing that was correctly blocking it.

Session: Fri 2026-09-04, 09:42–10:20 PT. Branch `lane1b/036-question-cards-cleanup`, rebased onto
`e1a0de7c`, now at `5829f2a3287214b3334e639736544f47618e6c1b`. PR #3052.

---

## 1. What I found on arrival

The restock said: CERT-930 GREEN — TOKEN GRANTED, run the apply. That was true when it was written
and false by the time I read it.

    CERT-932 -- CERT-930-SECOND-OPINION-RESTORE-JSONB-BIND | 16:02Z
    **BLOCK -- TOKEN WITHHELD; SUPERSEDES CERT-930**

Merge gate notice 18 says a granted token is void when a later ledger row names its cert after the
word `supersedes`, and that the response is neither to merge nor to revert. So the apply run did
not happen, and this session went to the named repair instead (D53: a BLOCK names the exact repair
and the test that catches it; the repair presentation quotes both).

**The BLOCK was right.** I did not argue it and it did not need arguing.

---

## 2. The defect, and why it is worth writing down as a class

`restore_3026_question_events.py` rebuilds deleted rows with

    INSERT INTO events SELECT (jsonb_populate_record(NULL::events, :row)).*

`:row` is a Python dict — the banked snapshot, written by `to_jsonb(e)` in SQL and read back
decoded. In a bare `text()` the bind has no type, so it compiles as `NullType`; `NullType` has no
bind processor; the dict reaches asyncpg untouched; SQLAlchemy's asyncpg jsonb codec expects the
dialect's own serializer to have produced a string and calls `.encode()` on it.

    AttributeError: 'dict' object has no attribute 'encode'

On the first insert of the first row. The undo could not put back a single event.

### The reason it survived a full green cert

Every cheaper instrument is green over this by construction. This is the part worth keeping:

| instrument | verdict | why it cannot see it |
|---|---|---|
| ESLint/ruff/black | green | it is a value error, not a syntax one |
| import / startup gate | green | the module imports fine |
| statement compiles | green | the SQL is valid; the *bind* is the problem |
| **the dry run** | **green, and prints a correct plan** | the dry run is *defined* as the path that executes no insert |
| sqlite ORM-projection proof | green | sqlite has no jsonb codec to be wrong about |
| a mock session | green | it records and asserts on the very dict that never worked |
| 171/171 focused + startup | green | none of them execute an insert |

So the failure mode has a shape: **the only code path that was never exercised was the one that
only runs in anger.** `--apply` is the run nobody gets to rehearse, and the dry run's success is
not evidence about it — it is evidence about a different branch.

> **Rule worth carrying:** when a script's safe mode is "the mode that does not write", the safe
> mode's green says nothing about the write path. That path needs its own reader, and for anything
> touching JSONB, arrays or enums that reader has to be a real server.

---

## 3. The second finding: the same defect, already applied to production

`restore_2993_bracket_events.py` carries the identical untyped bind and is **already on master**.
Measured on production this session:

    SELECT b.action, count(*), count(*) FILTER (WHERE e.id IS NULL) AS gone
    FROM bak_2993_bracket_events b LEFT JOIN events e ON e.id = b.event_id GROUP BY 1

    delete | 16 | 16
    rename |  1 |  0
    first banked: 2026-09-04 13:32:41Z

**16 events were deleted from production at 06:32 PT today**, unattended, under D51 — with an undo
that would have raised on its first insert. The repair itself ran correctly (16 delete → 16 gone,
1 rename correctly still present) and the backup is intact, so nothing is lost. But for those
hours the authorising condition of D51 was not actually satisfied.

Fixed in the same commit rather than filed. Shipping a fix for one undo while knowingly leaving
the identical broken one live is not a smaller change, it is a worse one.

`restore_2871_*` is safe — it restores table-to-table in SQL (`INSERT INTO events (cols) SELECT …
FROM bak_…`) and never binds a Python value. `restore_2947_*` restores names only, no JSONB.

---

## 4. The repair

`_populate_insert(table, on_conflict_nothing)` in both restores, typing the bind:

    text(f"INSERT INTO {table} SELECT (jsonb_populate_record(NULL::{table}, :row)).*{tail}")
        .bindparams(bindparam("row", type_=JSONB))

Proven locally against the real dialect, both arms:

    RED  (untyped)  NullType, processor None  -> asyncpg receives dict  -> .encode() AttributeError
    GRN  (JSONB)    JSONB, JSON._make_bind_processor -> asyncpg receives str '{"id": 1, …}'

---

## 5. The guards

**`tests/integration/test_restore_3026_jsonb_roundtrip_pg.py`** — the gate CERT-932 named. Seeds a
question-shaped event with three JSONB columns, an LMA, a `win_prob_snapshot`, an
`event_provider_anchor` and a linked fiction market; drives the **shipped** `build_plan` →
`ensure_backup` → `apply_plan`; restores with the **shipped** `restore_events` / `restore_links`;
asserts every row and every JSONB payload comes back **by content**, plus the market relink. Three
tests: the round trip, idempotency (a second `--apply` is a no-op — the state in which a person
runs an undo is the state in which they run it twice), and the red arm.

Two design decisions worth keeping:

1. **The red arm is *derived*, not retyped.** It takes the shipped statement and strips only the
   bind type (`text(typed(table, flag).text)`), so it differs from the real path in exactly one
   dimension. A hand-copied SQL string drifts, and a red arm testing slightly different SQL proves
   slightly the wrong thing.
2. **The seed uses the `no_fixture_named` path deliberately**, not `duplicate`. The `duplicate`
   path turns on a counterpart search whose result depends on what else is in the table; a gate
   about JSONB binds must not be able to go red for a reason about matching.

Anchor asserted first (`len(plan) == 1`, action/why/id/market_ids) — if the seeded row is not the
row the repair wants to delete, every later assertion is about something else.

**`tests/test_restore_jsonb_bind_contract.py`** — the cheap half, runs everywhere. Asks
SQLAlchemy's asyncpg dialect what value each restore statement would hand the driver; fails if it
is a dict; also fails if the string is not this row's JSON (`str(dict)` is a string too). It
**discovers** restore scripts by scanning for `jsonb_populate_record`, so a third one joins
automatically, and asserts both known files are in the scan so a rename cannot halve coverage. Its
own red arm asserts the untyped form still passes a raw dict, i.e. that the check can still fail.

Wired: registered in `test_pg_gate_seed_completeness.py`'s `COVERED`, and a `search-recall` step
with the all-skipped detector its neighbours carry. `search-recall` is in `deploy`'s `needs`, so
this is a real deploy gate, not a file that exists.

### The seed-completeness gate earned its keep, immediately

My first version failed it: *"7 `INSERT INTO` statements but only 6 parsed."* The seventh was the
red arm's hand-written untyped INSERT, which has no `(cols) VALUES` form. The tempting fix — hide
the literal from the regex — is exactly what that gate exists to prevent. The right fix was to stop
hand-writing the SQL at all and derive it from the shipped statement, which is also what made the
red arm strictly better (§5.1). **A guard that inconveniences you is sometimes telling you the
design is wrong, not the guard.**

---

## 6. What I could not prove locally, stated plainly

The round-trip gate has **never executed on this machine.** `initdb` dies on
`shmget: Operation not permitted`, confirmed twice this session — once sandboxed, once with the
sandbox disabled, so it is a machine restriction and not the harness. Its first execution is in
CI's `search-recall` job.

What *is* locally proven: the bind-processor contract (§4, both arms), 170/170 focused + startup on
the rebased tree, ruff clean, the CI wiring and seed-completeness gates green over the new file,
and the new gate collecting and skipping with a legible reason.

Do not let anyone read "the round trip passes" off this session's local run. It does not exist
locally.

---

## 7. Housekeeping done

`runner-inbox/integrator/174-merge-cce5dc94….md` was **pending** for the now-void sha — written by
this lane at 08:59 when CERT-930 was still standing. Marked
`.superseded-20260904-0958-cert932-block-token-withheld-sha-force-pushed`, with both reasons in the
file: the token was withdrawn at 16:02Z, and the sha no longer exists on the remote (force-pushed
to `5829f2a3`). Never consumed; nothing reached production; nothing to revert.

**Correction to my own restock:** §4 said to run the #2927 post-deploy check "when #3045 lands". I
initially read it as landed — `test_link_tennis_write_outcomes.py` is on master. That file predates
#2927. Detecting by the actual subject (`select_discovered_series` / `_DISCOVERY_TAGS` in
`kalshi_api.py`) shows it is **absent**: #3045 has not merged, directive `integrator/173` is still
pending. Production agrees — `KXATPDOUBLES` 255 rows / **0 open**, `KXWTADOUBLES` 215 / **0 open**,
newest 8/30; `KXHONEYDEUCE` still has no row of any kind. §4 and §5 (golf) stay blocked.

> This is gotcha #154's cousin: **a file's presence on master is not its feature's presence.**
> Content-detect the subject of the change, not a file that shipped alongside it.

---

## 8. What is still owed

1. CI green on `5829f2a3` — in flight; `search-recall` is the one that matters, it is the gate's
   first ever run.
2. Re-present to the bus as a repair subject quoting `repairs: CERT-932`, per notice 8(b).
3. **Then the ship**: `--backup --apply`, expecting `225 deleted, 49 held`, `104 markets unlinked`,
   `21 lma deleted`, `residue_after.still_deletable = 0`; then the pre-registered proof (event
   15301524 → 404, `Greg Mueller` → 0, `Finish Top 3` → 0, `Announcers` → held only); then close
   #3026.
4. #2927 post-deploy check and the golf per-tag-fairness build, both still behind #3045.

Unchanged and not to be re-asked: #2927 CONTAINERS (D61, Alex's word owed), #3053 (the 34 held
rows), the #2947/#2693 rows that are lane1's, #2936 (ux).
