# Quiet production evals, Nov 3, 2026 — ruling E

Pillar: TRUTH. Ship: quiet GitHub reporting is distinguishable from a green eval, so a red reliability result reaches the work list.

Read-only evidence captured from this Mac during the Nov 3 evening, using existing Heroku logs, stored `/last` payloads and task metrics, Actions history, and issues. No task was dispatched, no production configuration changed, no repair performed, no failed workflow rerun. All times below are Pacific Standard Time (UTC−8). Source paths below are at `54470c89fd`; the selected raw fields are in [the evidence record](quiet-evals-evidence-2026-11.json).

| Eval | Execution and last evidence | Why GitHub is quiet | Verdict / work filed |
|---|---|---|---|
| Matching Drift | Nov 3 8:47:49 PM: 4 checks completed, 1 RED, 3 unmeasurable; golden still has 25 findings | Comment on #2728 returns HTTP 403; its issue timestamp is Sep 29 | Running RED, reporting STOPPED — [#11958](https://github.com/alexander-bain/bainluck/issues/11958) |
| Grid Sentinel | Nov 2 11:42:59 PM: 1 red league, 2 green; within daily cadence | Issue creation returns HTTP 403; last filed issue #10032 is closed | Running RED, reporting STOPPED — [#11959](https://github.com/alexander-bain/bainluck/issues/11959) |
| Flow Sentinel | Nov 2 11:19:56 PM: 11 pass, 4 fail, 2 unknown of 17 flows; within daily cadence | All four filing attempts return HTTP 403; last auto-filed Flow issue #10781 was Oct 9 | Running RED, reporting STOPPED — [#11960](https://github.com/alexander-bain/bainluck/issues/11960) |
| Browser audit | [Nov 2 9:23 AM run](https://github.com/alexander-bain/bainluck/actions/runs/41490775406): valid manifests; 24/26 deploy/consent and 4/18 tournament journeys fail. Oct 31/Nov 1 also failed | It is not silent: [filer run](https://github.com/alexander-bain/bainluck/actions/runs/41492667045) succeeded and acted on 43 findings from 2 manifests, commenting on existing issues | Running RED, reporting active — existing #1611, #11222 and consent findings; no stopped-eval issue |
| Discover LLM judge | Nov 3 1:36:58 AM: 50 graded, 45 proposals, 20 email misses, 0 errors | Advisory proposals are stored for admin review, not auto-filed to GitHub | Running; execution green-and-silent. Judge accuracy remains uncalibrated; no stopped-eval issue |

The requested two-way distinction has a third real state: **running red with a muted reporting channel**. Calling that green would erase findings; calling the scheduler stopped would misdiagnose it. Each stopped reporting rail has its own issue. Browser audit's lack of a newly opened issue is deduplication, not missing execution or missing filing. No weekly-summary issue was identified, but these runs prove its ordinary issue-comment rail is active.

Evidence and owning sources:

- Matching: `backend/app/tasks/matching_reconciliation.py:921-970`, `backend/app/tasks/__init__.py:6092-6109` and `:7764-7772`. Heavy log contains `matching_reconciliation: 4 check(s), 1 RED, 3 unmeasurable` and `comment failed on #2728: ... 403 Forbidden`. The receipt-coverage query times out; subsequent checks encounter the aborted transaction.
- Grid: `backend/app/routes/admin.py:1919-1932`, `backend/app/tasks/grid_sentinel.py:931-1054`, `backend/app/tasks/__init__.py:8705-8716`. The red finding is MLB's missing `pennant` column. Redis evidence is readable; the durable fallback reports `ChecksumMismatch`, which is not a healthy fallback.
- Flow: `backend/app/routes/admin.py:1855-1868`, `backend/app/tasks/flow_sentinel.py:2848-2923`, `backend/app/tasks/__init__.py:8695-8704`. Failing flows are event completeness, category/Discover, unlinked held markets and team identity duplicates. Two skipped flows remain unknown. The 24-hour expiring counters read zero despite an explicit completed run; they are not proof of stoppage.
- Shared reporting: `backend/app/tasks/sentinel_filing.py:411-490`. HTTP 403 does not distinguish an expired token from insufficient permissions; that cause remains to be diagnosed by the repair owner. This audit does not expose or modify credentials.
- Browser: `.github/workflows/browser-audit.yml:31-34`; Actions run/job logs above. The manifest validator correctly says `manifest valid ... result=fail`; “Validate the evidence manifest” being a failed step is a negative evaluation result, not necessarily malformed evidence. Filer log: `2 manifest(s), 43 finding(s) acted on`, with `comment` actions.
- Judge: `backend/app/tasks/__init__.py:2733-2737` and `:8141-8144`, `backend/app/tasks/enrich_markets.py:2079-2097`, `backend/app/routes/admin_celery.py:437-447`. Last-result fields show actual work and no errors; the generic `last_verdict: unverified` is also preserved. A successful task is not evidence of judge accuracy.

The five-line status and three issue links are posted as a comment on NOW #11852. No NOW body edit or assignment was made.
