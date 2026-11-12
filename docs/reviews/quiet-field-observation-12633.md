# Quiet fields get real price rechecks (#12633)

Pillar: TRUTH. Ship: the Governor market opened on an installed iPhone regains
its current number when the ordinary writer checks the venue, instead of
remaining “Open” indefinitely behind chart keepalives.

## Cause and retained example

The saved November 12 Governor field has 24 outcomes. Kansas's stored raw
probability is 0.9545; the existing full-field display rule serves 0.91822992.
The venue lists all 24 legs as active; election day did not settle this market.
Recent socket keepalives create chart points without observing a new quote.
The hourly refresher treats those points as evidence of a recent price read,
so it skips the field while the outcome observation clocks become stale.

A bounded read-only snapshot at 7:18:55 AM PT found this stored symptom in
1,339 of 3,734 open standalone Kalshi fields, including Governor. All 1,339
have no settlement date; 1,336 also pass the refresher's current date bound.
This is not a venue-confirmed active count or proof every affected page is blank.
The full result and query limits are on #12633.

## Writer correction

A recent chart point suppresses a recheck only when the same outcome also
has a recent price-observation clock. A missing or old outcome clock remains
eligible. The same predicate applies to class, registered, served, category,
in-play and Series selection, the remaining-stale count and the matching
admin freshness guard. Generic market metadata updates are not price evidence.

The existing writer already advances `futures_outcomes.last_updated` after a
real unchanged quote while preserving `price_changed_at` and grades. A changed
quote follows the ordinary repricing path. This change repairs eligibility;
it does not add a page-read venue request, backfill or manual data repair.
Existing pools, attempt markers, cadence, rate and runtime budgets stay intact.

The job remains hourly at :50 with its 420-second loop deadline and 0.15-second
pause. Its normal selection budget is 500; existing identity priority can exceed
that count, so it is not a hard HTTP cap. Each event-fetch call may make up to
three HTTP attempts under the existing client retry policy. The separate
60-market delisted check is unchanged. Catch-up is bounded by those existing
rules, not promised in a fixed number of runs.

The rejected detail-route helper and its tests are retained in pushed commit
`15654b7063be40295a3d0a3c6cab5fad26f3792c`; the final PR removes them. The saved
Governor fixture is retained for the actual PostgreSQL selector/writer checks.

## Verification and delivery limits

The PostgreSQL tests use the real keepalive INSERT and every selector arm.
Old observation clocks must be selected despite recent points;
a genuinely fresh quote must stay skipped. Both freshness guard populations
must report the same distinction. The real venue parser and writer replay the
24-leg Governor fixture unchanged and with Kansas moved to 0.92. They require
an advanced observation, unchanged grades, and a movement clock that advances
only on the changed price. The initial six selector failures and expanded
eight-failure/ten-pass baseline are retained in the local receipt folder.
Both CI workflows run the complete PostgreSQL test file, including these
18 cases; no workflow edit or skipped-only gate is needed.

The existing job is hourly. Identity eligibility/attempt windows are 45 minutes,
category two hours and class six hours, while the installed phone withholds
after 30 minutes. Removing permanent suppression does not promise continuous
sub-30-minute freshness. Decision 170-A gives Builder C the phone's age wording
(“As of …”) and a separately proposed hard limit; neither that reader change
nor a cadence change is part of this PR. The population age table requested on
#12633 is due November 13, after this writer correction. Two hours after the
fix begins running, the follow-up counts real reads inside 30 minutes, two
hours and six hours. The writer fix alone does not close the phone failure.

Validation: the complete PostgreSQL 17 file passes all 70 cases, including all
18 new controls. The related backend band passes 131 checks including startup;
all 112 unit cases pass at all twelve clock points. Frontend build and typecheck
pass (65 baseline errors, no new errors). The initial full-file attempt used
PostgreSQL 14: 37 cases passed and 33 could not create a pre-existing
`NULLS NOT DISTINCT` index. That harness failure is retained; PostgreSQL 17
runs the whole file without skips.

Speed released both files at 9:21 AM PT on #12647. Delivery still requires green
CI, exact-head bot approval, Fable ACCEPT and the assigned merge slot. After
deployment, record the first scheduled pass's processed count and `task_memory`
peak. The scheduled writer must produce a real read and the served Governor
detail must carry its number and honest clock. The 390 px page, Back/Refresh and
installed-phone result are separate proof obligations.
