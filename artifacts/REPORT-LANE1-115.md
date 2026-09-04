# lane1/115 — the sport belongs to the population, and the missing Monday-night game is built

**PILLAR: MATCHING.** **SHIP: a Monday Night Football game stops being missing from the site.**

Session: Fri 2026-09-04, ~11:2xam–1:0xpm PT, stamped from `date`. Ran in the same window as
lane1/114 (`artifacts/REPORT-LANE1-114.md`) after that session's ship landed.
Directive consumed: `runner-inbox/lane1/115-two-nfl-rows-are-holding-the-statpal-flip-clock-3070.md`,
handed over by the **authority lane** under D50. Issue **#3070**. PR **#3090**, **CERT-947**.

---

## 0. One line

Row A of #3070 is built and staged — but the in-grain rail could not create an NFL game at all
until `sport_id` stopped being a module constant that both of its shells hardcoded to MLB, so the
change is that, plus the one-game reviewed population it unblocks. **Not applied**: the rail reads
its reviewed file off the dyno, so the apply is a separate attended step after this deploys.

## 1. Both rows re-measured before touching either

113's trap — *a filed population number goes stale* (#2769 said 8 groups / 17 rows, production said
5 / 11) — so the directive's two rows were re-read from production first. Both exactly as filed:

```
(A) 401873107  14780589  Houston Texans @ Pittsburgh Steelers      2026-12-07 01:20Z
    401873108  — ABSENT —
    401873109  14780591  Minnesota Vikings @ New England Patriots  2026-12-11 01:15Z

(B) 14781722  Denver Broncos @ Arizona Cardinals  2026-10-25 20:05Z  espn 401873019  statpal 280624  822 snaps
    14751059  Denver Broncos @ Arizona Cardinals  2026-12-27 18:00Z  espn —          statpal —       1 snap
```

Then **ESPN was asked directly rather than assumed** (113's other trap):
`site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=401873108` → HTTP 200, Dallas
Cowboys @ Seattle Seahawks, `2026-12-08T01:15Z`, season 2026 type 2, **week 13**. Notice 7 says
reachability is measured from production, not the sandbox — here the sandbox reached ESPN fine,
which is worth recording because 9/1's "ESPN 403" was sandbox egress only.

## 2. Why row A and not row B

The directive says either repair alone clears the bar, and leaves the choice to the lane.

**Row B has no rail.** `14751059` is the `NO_ANCHOR_CHANNEL` shape (gotcha #32 / ruling 048): an
`odds_api` listing from 2026-05-14 that drew one snapshot, was never claimed by any provider and
never drained. Removing it means deleting a row, and **ruling 079 means no branch of the repair
rails deletes a row** — `repair_event_espn_id`'s own docstring says so in as many words. Building
a DELETE rail to drop one stale listing is a larger and far more dangerous change than creating
the game that is genuinely missing.

**Row A has one, and it is the right one.** `event-create-from-truth` is the attended CREATE
consumer: two-call, plan-addressed, `apply=false` persists a plan and returns its hash,
`apply=true&plan_hash=` consumes THAT plan and re-derives nothing. Hand-inserting the row would
have bypassed all of it.

So: row A. Row B stays filed on #3070, with the reasoning on the issue rather than in a report
nobody will re-read.

## 3. The defect the ship walked into — and it was the real work

The rail binds an apply to a **committed reviewed population**. There were three, and all three
were MLB. So both of its shells — `app/tasks/create_events_from_truth.py` (the live rail) and
`scripts/derive_event_create_plan.py` (the local dry run) — hardcoded `MLB_SPORT_ID` at **four
sites between them**: scoping the club-anchor lookup, and stamping the created row's `sport_id`.

That is correct while every population is MLB. The moment one is not, it is the quietest kind of
defect there is: the plan builds, the gate passes, the apply succeeds, and one NFL game is created
under a baseball sport row with **nothing downstream complaining**.

And the module's own header says why this class matters here specifically: it exists so the two
producers *cannot* derive different rows from one approval, because the plan is a content address.
A sport each shell chooses for itself is exactly that divergence, one field lower down.

**The fix:** `sport_id` moves onto the population. `TRUTH_SET_REGISTRY` becomes a `NamedTuple`
carrying `(path, subset, sport_id, sport_key)`, and both shells resolve through one
`sport_for(population)`. A `NamedTuple` rather than a dataclass deliberately — the registry is read
positionally (`entry[0]`) by a test that predates the sport fields, and breaking that to gain
attribute access would be paying for style with coverage.

Also added: `registry_entry_for()` as the single lookup, so `truth_set_path_for`, `sport_for` and
`select_population` all refuse an unknown token by the same route instead of three copies of the
same `if entry is None`.

## 4. The anchor question, which is the one that could have killed it

Memory said 32/32 NFL franchises have two `teams` rows (#2866). If both rows sat in the NFL sport,
`anchors_from_rows` would refuse `CLUB_ANCHOR_NOT_UNIQUE` and this whole path would be closed. So
it was checked **before** any code was written.

```
552    sport 1       americanfootball_nfl            Dallas Cowboys     slug dallas-cowboys
17750  sport 190411  americanfootball_nfl_preseason  Dallas Cowboys     slug —
12     sport 1       americanfootball_nfl            Seattle Seahawks   slug seattle-seahawks
17742  sport 190411  americanfootball_nfl_preseason  Seattle Seahawks   slug —
```

**Within `sport_id = 1` each club is exactly one row.** The double is the *preseason* registry
under a different sport id — structurally the same split the module's docstring already documents
for MLB (`33178` vs `53232`, "a resolver that took `name` alone would have had a 50% chance of
binding 328 regular-season games to preseason club rows"). NFL is that story again with different
numbers.

Which is the argument for the change rather than an aside: **the anchor is 1:1 *because* the
resolution is sport-scoped.** A sport that is a default parameter a shell can forget to pass is a
coin flip on which copy of the club a brand-new row binds to.

## 5. Population 4

`app/data/event_create_truth_set_nfl_week13_mnf.json` — its own file, not an appended row. Ruling
079's shape and the exact precedent of the Aug-19 four: the sets above declare MLB scopes, and
appending would silently change an object Alex already reviewed, so the `plan_hash` he approved
would cover a game he never saw. **A new population is a new reviewed object, a new address and a
new approval.**

One extra field over the older sets: `truth_id_hash_formula`. Nothing in the rail verifies
`truth_id_hash` — it is carried into plan context as provenance and never recomputed — so it can
rot into a number that means nothing, and the three existing files' stamps are not reproducible
from their contents (six formulations tried, none matched). This set declares its formulation and
a test recomputes it. **The older files are deliberately left alone**: recomputing a stamp on a
reviewed object is changing the object.

## 6. Proved against production, not only in tests

`python3 scripts/derive_event_create_plan.py --population 4` (read-only; it writes a local
artifact and has no apply mode at all, by design):

```
population       4          plan_hash  ff6b0e518447e3f3a4e383383184b0ff
rows             1          gate passes True  (no_longer_missing=[], still_missing 1)
context   {"population":"4","sport_id":1,"sport_key":"americanfootball_nfl",
           "truth_set_hash":"0c2dfd74b47aaa19f7b7cd36f74dc1c0","row_one":"401873108"}
row       {"truth_id":"401873108","provider":"espn","sport_id":1,
           "away_team_id":552,"home_team_id":12,
           "commence_time":"2026-12-08T01:15:00+00:00"}
```

`sport_id: 1`, resolved from real `teams` rows on production. That is the change working end to
end, not a unit test agreeing with itself.

## 7. The forged credential, removed on the way past

The dry-run shell stamped every plan with
`"ruling": "Alex 2026-08-17 — attended CREATE from venue truth, approved"`.

The **rail** dropped that exact string under queue 371 ruling (b)(3), with a twelve-line comment
calling it a FORGED CREDENTIAL — *"worse than no credential, because a missing one prompts the
question and a forged one answers it"*. The dry-run shell kept it. So the two producers disagreed
about what they were claiming, and adding population 4 is what made that live: the string would
have been stamped verbatim onto an NFL game, asserting a human approval dated three weeks before
that game was ever reviewed.

Removed, with the rail's own reasoning quoted in place. `context` is outside `plan_hash` (the
address is the sorted row digests), so this re-addresses nothing.

## 8. Tests — 13 new, and the important one is the regression

`backend/tests/test_event_create_population_4_nfl_3070.py`.

The load-bearing test is **not** the feature. It is
`test_the_mlb_populations_still_name_mlb`: `sport_id` is inside the create digest (queue 368), so
moving populations 1-3 would re-address every row of an approval Alex has already given — he would
present a `plan_hash` the rail no longer mints, and be refused with nothing saying why. That is the
change's real blast radius and it is pinned.

Also pinned: unknown populations refused **by name** (`UNKNOWN_POPULATION`) rather than defaulted —
since a silent default is the failure being replaced, it must not default; every registered
population declares a sport, so one added later cannot inherit MLB by omission; the registry is
still readable positionally; the planned row carries `sport_id == 1` and `!= MLB_SPORT_ID`; an
unanchored club is still refused rather than looked up another way; and the reviewed set matches
what ESPN attested field by field.

Focused band (D40 — CI is the suite of record): `test_event_create_plan_q363`,
`test_repair_apply_plan_r2_block`, `test_create_events_from_truth_consumer`, the new file,
`test_startup`, `test_tasks_wiring` → **123 passed, 1 skipped, exit 0**. Ruff clean. Residue scan
clean.

## 9. What is NOT done

- **Not applied.** The rail reads its reviewed file off the dyno, so the two-call apply can only
  run after this deploys. The exact calls, and the one-row rollback
  (`DELETE FROM events WHERE espn_id = '401873108'`), are in the PR body and on #3070.
- **The gate has not moved.** NFL identity is still `both=320, statpal_only=1, ours_only=1`,
  `pct 99.38` against the 99.5 bar. The prediction, from the directive's own table: applying row A
  takes `pct` to **99.69** and the gate to **MEETS**, with `ours_covered_pct` unchanged at 99.69.
  That is falsifiable and should be checked, not assumed, by whoever applies it.
- **Row B untouched**, for the reason in §2.
- **No LOOK shot.** D48 asks for before/after of the surfaces the work touches; this ship changes
  nothing rendered until the apply runs. The shot belongs to the session that applies it — an NFL
  page showing Cowboys @ Seahawks on Dec 8.

## 10. New traps

- **A repair rail can be the right rail and still not reach your case.**
  `event-create-from-truth` was exactly the mechanism for a missing game, and it was bound to
  three MLB populations by a constant in two shells. Read what the rail is *bound to*, not only
  what it does.
- **`sport_id` being a default parameter is the tell.** `build_rows(..., sport_id=MLB_SPORT_ID)`
  had a default precisely so callers could omit it — and both callers passed the same constant
  anyway. A default that every caller overrides identically is a constant pretending to be a
  parameter; a default that no caller overrides is a landmine for the first one who should have.
- **Check the anchor before writing the code.** #2866's "two rows per franchise" would have made
  this path refuse. One query up front settled it (the double is under the *preseason* sport) and
  turned the biggest risk into the change's own justification.
- **Local `black` is 26.5.1; the repo pins `>=24.1.0` and CI does not run black at all.** Running
  it reformatted unrelated `text("""…""")` blocks across three files — 167 insertions where the
  real change is 118. Reverted and re-applied by hand; re-deriving afterwards produced the
  **identical `plan_hash`**, which is how the revert was proven behaviour-neutral rather than
  hoped to be. Memory already said *black reformats the WHOLE file*; this is the version-skew
  form of it.
- **`git checkout -b <new> origin/master` with uncommitted work is safe only if the touched files
  match master.** Checked all three with `git diff --quiet HEAD origin/master -- <file>` before
  switching. That is the cheap version of the standing trap.
- **A forged credential travels by copy-paste between shells.** The rail fixed it and the script
  did not, and nothing detected the disagreement because no population had ever exercised it.
  When a module says "two producers must not drift", the drift to look for is in what they
  *claim*, not only in what they compute.

## 11. Standing

`#3070` OPEN (row B still filed). `#2867` / D50's flip clock still pinned at zero until the apply.
PR #3090, CERT-947 staged via `tools/stage-cert.sh`. Merge gates 13 + 18 apply before any merge —
CERT-947 must bank a `TOKEN GRANTED` row and no later row may name it after `supersedes`.

---

## 12. CI, after the fact

**Full CI green at `89eb6642`**, merge state CLEAN, 1:3xpm PT: 4/4 backend shards,
`frontend-build`, `search-recall`, `shard-completeness`, browser-audit fixtures, CodeQL (both
analyses), gitleaks, Vercel. `deploy` SKIPPED — correct on a PR.

That matters most for the one change with real blast radius, the `NamedTuple` swap: a missed
2-tuple unpack anywhere in `backend/` would have failed a shard. The local sweep found only
`test_create_events_from_truth_consumer.py:685` and it still works; 4/4 green is the evidence the
sweep was complete, which a grep alone is not.

Recorded on the PR at `#3090#issuecomment-5544860691`. CERT-947 ungraded at session end.
