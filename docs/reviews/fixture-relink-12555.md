Fable: needed (destructive)

Pillar: MATCHING. Ship: Rams–Cardinals markets leave the St. Louis baseball
page and reach the fixture's football clubs through the normal hourly linker.
Decision 146-A retires the hand-SQL repairs; no manual writer dispatch is part
of this change. Publication follows #12581's first slice.

PR #12622 follows the now-served #12581 slice. Fable's 2:00 PM review requires
committed-change receipts and a hold on clears. No merge before the Mac returns.

The same resolver now constrains new NULL links (#12589) and stored-link repair.
Both fixture sides need unique, known clubs of the right sport and gender, with
matching names or aliases. Explicit domestic-club FKs remain valid on cup games.
Names-only fallback requires a unique exact name in the fixture's competition.
A missing event, incomplete or contradictory fixture returns a named refusal
and cannot enter a category-wide fallback.

The repair selects stored links outside the fixture's explicit sides, including
open, resolved and closed markets. Separate resumable cursors reserve a settled
share of each run; at most 200 candidates enter the repair per task invocation.
Each pass walks at most ten descending ID ranges of 100,000 IDs, reading at most
10,000 outcome rows per range before checking eligibility. Empty and ineligible
ranges advance; a full candidate budget resumes below the last selected row.
There is no date cutoff. The real cohort therefore heals across resumed runs,
not an assumed single invocation; the guards retain all 42 targets and controls
through that progression.
Valid club IDs and NULL controls stay outside this repair. A verified fixture
permits a name/roster match to its own clubs. Otherwise the proposed clear is
counted and logged, but the stored link is unchanged: `_FIXTURE_CLEARS_ENABLED`
is false. Enabling it requires a separate reviewed PR after the first two natural
runs are classified by sport and market status, including 20 proposed clears
read by eye. Only team_id changes. Identity predicates refuse concurrent outcome,
market, event or club changes while permitting fresh prices. Older league,
conference and name repair passes exclude event-linked markets so they cannot
undo the fixture's decision or touch an unresolved fixture.

Each committed change logs outcome, market, fixture, old/new club, name/roster
match, sport and market status. Logs follow the unit's commit; a rolled-back unit
emits no committed-change claim. Held clears and fixture refusals have distinct
receipts, at most one per selected candidate (200 per invocation). Refusing open
markets are counted by reason within the selected run; this is not a whole-table
count, and repeated market IDs across runs must be deduplicated for the report.

Run forecast: the saved production scan head is 263,305,107 and the oldest of the
42 targets is 258,819,607. The scan can cross at most one million ID positions
per invocation, so reaching all 42 takes **at least five hourly runs** from that
head. Dense 10,000-row pages and the 150-open-candidate budget can make it longer;
refusals and already-correct candidates consume that budget too. The first two
natural runs' cursor progress will refine the forecast. No one-run claim or
fixed completion hour is supported by the current evidence.

Rejected outside-fixture candidate attempts log the outcome, market, fixture,
proposed club and allowed fixture clubs. The counter counts attempts, including
repeated attempts on the same outcome. The previously deployed #12570 emitted
only an aggregate counter, so its 15 refusals from the 6:50 AM run cannot be
turned into a historical per-outcome list. This logging pays that evidence gap
for future natural runs; it does not claim to reconstruct the past.

Local validation on Nov 11:

- 115 checks pass, including 21 new repair/refusal controls, existing matching,
  cursor/savepoint/row-lock guards, startup and the PostgreSQL CI wiring guard.
- The saved 42 targets change only team_id, with all 78 control outcomes and
  all captured market/event/team values identical, in open/resolved/closed runs.
  The same captured corpus also passes on real PostgreSQL below, not production.
- The two control-only parent markets were not captured in the retired SQL
  proposal snapshot. Their test contexts are explicitly synthetic non-game
  markets; the 78 outcome before-images themselves are preserved.
- A second pass does nothing. Refusals advance the cursor; settled rows retain
  their reserved share. Changed identities refuse; a new price survives.
- All ten real PostgreSQL cases pass, including the captured cohort in all
  three statuses and two concurrent-connection controls: a fresh price survives
  and an identity change refuses. Five new cases use the existing mandatory
  identity PG file; no CI workflow change. The first run's schema errors and
  the second run's misplaced test assertion remain in their logs. The assertion
  was restored to its original test before the passing run. A later disposable
  cluster initially used SQL_ASCII; its five fixture failures are retained, and
  the final UTF8 run passes all ten cases. The server stopped.
- All 21 repair controls pass all twelve clock points. Startup, frontend build
  and typecheck pass (65 baseline, no new errors). The first frontend launch
  lacked dependencies and exited 127; after verifying identical lockfiles, it
  used the existing local dependencies and passed.
- Earlier production timing attempts did not pass. The original wide selector and
  the materialized market-first variant timed out at two seconds. A 50,000-row
  primary-key page took 1,395 ms for open but timed out for resolved. A 10,000-
  row page passed at the head but timed out at the captured resume cursor.
  Adding an ID floor produced a 491 ms literal-bound read there. The final
  module-generated query proves both bounds are index conditions, and its head
  reads pass at 1,019 ms open / 371 ms resolved; its resume read nevertheless
  timed out. That version did not pass the gate; the final plain-bound result
  below is the correction, not a rerun of that query.
  All reads used READ ONLY, two-second statements and 250 ms lock limits;
  no selector or repair has been run as a production writer.
- The final plain-bound query passes the same bounded production read gate:
  open head 417.259 ms, resolved head 61.879 ms, captured resume 490.608 ms
  (19 result rows at the resume position). Planning took 195.248 / 9.461 /
  17.870 ms. All three READ ONLY transactions rolled back, with two-second
  statements and 250 ms locks; total command time was 5.204 s. The earlier
  timeouts remain recorded. This removes the repeated CTE around the bounds
  so both primary-key conditions are literal at planning time. No index added.
- After adding the per-attempt refusal log, all 39 focused matching and startup
  checks pass, including assertions for the recorded outcome, market, fixture,
  proposed club and permitted club IDs.
- Fable's held-clear/committed-log revision passes 119 matching/startup/wiring
  checks, all 25 fixture controls at twelve clock points, and 13 real PostgreSQL
  cases. The added PG cases preserve every captured outcome when no replacement
  matches, for open/resolved/closed markets. Log assertions cover all 42 committed
  replacements, both matching methods, and no committed log after rollback.
  Frontend build and typecheck pass again (65-error existing baseline).

Still required for delivery:

- Source review and hosted CI on the published head. An optional index-definition
  SELECT was blocked before execution by automatic approval review and was not
  retried; the final query uses the existing primary key. No schema change.
- #12581 first slice, own CI slot, actual bot approval, Fable ACCEPT, authorized
  serialized merge and served commit, then the natural hourly writer receipt.
- Re-read the same narrow count: 42 to zero, with fresh control comparisons and
  served game, Bigger Picture and team pages at 390 px. No manual task dispatch,
  retired SQL execution, new column or index has occurred.
- Classify the first two natural runs' held clears by sport/status, read 20
  proposed clears, and report distinct selected open markets on refusing fixtures
  by reason. Clears stay disabled until a separate reviewed PR enables them.
