# Bounded CI recovery

PILLARS: TRUTH / FORMATTING.
SHIP: a reviewed Live or Watch fix resumes after a diagnosed CI infrastructure
failure without discarding successful evidence or treating an unrun gate as green.

Issue #10710, under #10707. Integrator retains recovery and merge authority.
`tools/ci_recovery.py` is an offline, read-only addition to the existing merge-gate
diagnostic path. It does not call GitHub, retry a job, cancel a run, edit a check,
or authorize a merge. The ordinary `tools/merge-gate.sh` remains mandatory.

## Obtain one complete subject

Pin the repository, full candidate SHA, run ID and attempt. Retain the run record
and the **attempt-specific** jobs from GitHub, not a mixture of latest jobs from
different attempts. The endpoints are:

```text
GET /repos/{owner}/{repo}/actions/runs/{run_id}
GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}
```

Fetch all pages until the number of jobs equals `total_count`; a failed or
inconsistent page is unavailable evidence. Preserve job ID, run ID, run attempt,
head SHA, name, status and conclusion. Recheck the run attempt after pagination;
if it changed, discard this snapshot and obtain a coherent one. Never convert an
API error, rate limit or empty response into an empty job list.

Use the current PR head/state, or current branch head for a push, to establish
source eligibility. Check for active duplicate attempts/recovery and consult the
existing owner directive and recovery history. A missing no-retry policy is
unknown, not permission. Required job names come from the candidate's actual
required contexts and existing workflow dependency contract, including stable
aggregates such as `search-recall`. This tool does not select or reduce tests.
Do not list deliberately conditional deployment jobs as required PR jobs.

The snapshot envelope is:

```json
{
  "repository": "alexander-bain/bainluck",
  "expected_head": "FULL_40_CHARACTER_SHA",
  "current_head": "FULL_40_CHARACTER_SHA",
  "expected_run_id": 123,
  "expected_attempt": 1,
  "source_open": true,
  "active_duplicate": false,
  "read_errors": [],
  "required_jobs": ["search-recall"],
  "policy": {
    "recoveries_used": 0,
    "retry_prohibited": true,
    "provider_cause_confirmed": false,
    "recovery_authorized": false
  },
  "run": {"...": "complete GitHub run object"},
  "jobs": {"total_count": 0, "jobs": []}
}
```

This illustrates the envelope, not a valid live subject. The retained fixture
`backend/tests/fixtures/ci_recovery_10710.json` contains the actual historical
run #37651724603, attempt 1, with its 13 observed jobs and missing `search-recall`.
Its eligibility/policy fields replay the incident; they are **not** current
authorization to rerun that old PR. No recovery was performed for the fixture.

```sh
python3 tools/ci_recovery.py /absolute/path/to/snapshot.json
```

Exit 0 means a typed disposition was produced, including a hold or failure.
Exit 2 means unknown/incomplete evidence. Neither exit means merge GO.
Every result explicitly denies merge authorization and automated recovery.

## Recovery matrix

| Observed state | Integrator action | Bound / stop |
|---|---|---|
| Pending run | Wait for that run; retain completed results | No competing run |
| Wrong head, closed PR or superseded source | Use the current candidate's checks | No retry of stale source |
| Wrong attempt, partial pagination, API failure or unknown duplicate/policy | Obtain coherent current evidence | Remain held; never clear another claim |
| Job failure, timeout or action required | Inspect exact job/step and fix its demonstrated cause | Do not infer provider failure or blanket retry |
| GitHub `startup_failure` | Owner may authorize one failed-jobs recovery after diagnosing the provider failure | Fresh identity/attempt/duplicate check immediately before action; stop on recurrence |
| Required job absent, executed siblings passed | Inspect workflow/provider evidence; keep required-check hold | Failed-jobs rerun cannot target an absent job; whole-run recovery needs separately confirmed provider cause and owner authorization |
| Cancelled run/job | Obtain owner's disposition and cause | No blind retry, no cancellation of a successful/active release |
| Required job skipped/neutral, or inconsistent aggregate/result | Inspect required-job contract and dependency outcome | Never synthesize a passing status |
| Required jobs and workflow succeeded | Return to the existing merge gate | No waiver of review, security, composition, deployment or reader acceptance |

The optional proposed command is a **plan**, never executable authorization.
For a missing job, the owner must separately establish provider cause and record
`provider_cause_confirmed: true` before even a whole-run command is proposed.
Successful siblings alone do not establish that cause.
GitHub's `gh run rerun RUN --failed --repo OWNER/REPO` targets failed jobs;
`gh run rerun RUN --repo OWNER/REPO` reruns the run. Both act on the run's current
state, so immediately recheck head, latest attempt, PR eligibility, duplicate
state and owner policy before using either. An immutable past snapshot cannot
authorize an action later. The tool deliberately never executes these commands.

At most one explicitly authorized recovery is allowed for this incident.
An existing stricter no-retry directive wins even when another authorization flag
is set. A recurrence, source change or inability to reconstruct the required
check returns to Integrator with the specific blocker. Do not churn source merely
to trigger CI, retry unchanged full suites speculatively, weaken branch protection,
or erase passed evidence. Independent Watch evidence remains credited only under
its existing source/configuration compatibility rules.

## Handoff and acceptance

Retain the subject, provider evidence, classification time, owner disposition,
authorized action (if any), next attempt/check IDs and final required-check
readback in the existing issue/receipt. Report classification and handoff time
from existing timestamps on the next applicable natural incident. Do not create
an incident census, timer, watcher or artificial live failure for this check.

Source acceptance uses the retained real missing-job incident and negative
fixtures for wrong identity, partial evidence, duplicate work, failure/timeout,
stale source, forbidden retry and recurrence. Hosted adoption and actual recovery
are separate from these offline tests. Deployment or device success is still
owned by the original product issue.
