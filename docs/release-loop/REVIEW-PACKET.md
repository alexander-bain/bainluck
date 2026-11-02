# Release loop review packet

**Ship:** master merges deliver changes and detect bad releases without an awake model session.
**Pillars:** TRUTH and FORMATTING (reliability).

## November 1 publication resume

Alex authorized pushing these nine branches and opening their draft PRs with the prepared descriptions and tier-b on items 1, 3, 4 and 8. The session still reports internet disabled: GitHub API calls returned `connect: operation not permitted`, and the attempted named-branch push failed to connect to github.com. No PR, label, remote branch, repository setting or provider configuration was written. Authentication could not be verified through this connection failure.

The health branch now pins Action reporting to NOW #11852, keeps its verdict and replay marker on one line, uploads no verdict artifact, and passes no collector origin or admin credential. New telemetry destinations, collectors, drain setup and fast-lane arming remain held tonight; missing worker evidence remains UNKNOWN. The correction is committed on loop/post-deploy-health at 45b9232240. Fresh verification: 49 release tests and four startup tests passed; the protection policy test passed.

`master-protection-prepared.json` is the local, unapplied policy preview: pull requests required, administrators enforced, empty bypass allowances, and required checks retained. Actual existing GitHub protection could not be read; the activation tool must reread it and preserve existing required contexts and approval count when Alex writes **branch protection on**. Items 2 and 8 must be on current master before their checks become required. No activation or auto-merge was enabled.

Resume publication from a session or terminal with GitHub connectivity using `python3 /tmp/bainluck-wt-loop/tools/release/publish_prs.py --publish`. It starts with item 8 and writes PR URLs to `/tmp/release-loop-published-prs.json`. Merge/rebase and flaky-test cleanup wait for **master is current**. Archive and retirement holds remain in force.

## Tonight's holds

- No master push or PR merge until Alex writes **master is current**.
- Protection and auto-merge preparation stay unapplied until Alex writes **branch protection on**.
- Process archive stays unapplied until Alex confirms the lanes are paused and Builder A's settings-freeze PR is verified merged.
- TestFlight delivery starts Tuesday, November 3, at 00:00 Pacific.
- No runner inbox, current YOUR-TURN.md or original artifacts were edited. Five prematurely retired clean worktrees were restored from their retained branches; remote branches are unchanged.

## Independent PR branches

| Item | Branch | Review directory | Tier B |
|---|---|---|---|
| 8 (first) | loop/live-path | /tmp/bainluck-wt-live-path | yes |
| 1 | loop/release-loop | /tmp/bainluck-wt-loop | yes |
| 2 | loop/tier-b | /tmp/bainluck-wt-tier-b | |
| 3 | loop/post-deploy-health | /tmp/bainluck-wt-health | yes |
| 4 | loop/slim-instructions | /tmp/bainluck-wt-docs | yes |
| 5 | loop/day-zero-reset | /tmp/bainluck-wt-reset | |
| 6 | loop/archive-process | /tmp/bainluck-wt-archive | |
| 7 | loop/testflight | /tmp/bainluck-wt-testflight | |
| 9 | loop/retire-worktrees | /tmp/bainluck-wt-retire | |

Each directory contains its one-paragraph description in `docs/release-loop/pr-NN.md`.
`python3 tools/release/publish_prs.py` previews the concrete packets locally.
`--publish` pushes only these named branches and opens draft PRs, starting with item 8;
it never enables PR auto-merge, changes master settings or merges anything.

The session has internet access disabled. No PR, repository setting, GitHub cleanup,
provider configuration or remote branch deletion has been written. The blocked GitHub
requests cannot serve as verification of repository state.

## Required completion gates

After **master is current**, refresh/rebase the independent branches onto the actual
Delivery Speed integration and rerun their gates. Item 8 still needs the exact flaky
issue records and current files for #11744, #11681 and #11644; this starting master
lacks the #11744 test and the speed branch already carries fixes not integrated here.
No unknown test has been deleted or broadly quarantined.

Item 3 depends on Builder A's canonical `tools/speed/check.py`, `latency_guard2.py`
and `latency_guard3.py`. Their original artifact copies were read without moving them.
The operational stop remains guard2's **two consecutive minutes over 5,000 ms**;
guard3 separately keeps its **three-minute** stop and existing share comparison.
Verify durable worker log capture, provider APIs, signed webhook delivery and known-good
baseline receipts before arming the live-path lane. The arming tool previews by default.

Item 2's signed review webhook must be configured before relying on immediate review
updates; its poll is reconciliation. A human merge click does not make self-approval
valid. Until #2734 gives agents their own GitHub App identity, an independent account
must approve a Tier-B PR authored through Alex's account.

Item 7 requires the existing ASC key and the native signing assets in the six secrets
listed in its `docs/release-loop/testflight-setup.md`, plus a verified hosted signed build.
No signed build/upload has been performed in this offline session.

Item 5's actual stale PR close/issue parking needs GitHub access. Item 9's complete
221-row inventory (33 merged) is committed on its branch; the retirement tool requires
that exact inventory to be posted on its PR before deleting any tree. Keep all
`/private/tmp/wt-*` copies until Delivery Speed releases them.

## Final local review evidence

All nine packets preview successfully with one paragraph each; item 8 is first and
only items 1, 3, 4 and 8 carry tier-b. All nine worktrees are clean. The original
speed-tool f-string checker accepts all 47 changed committed Python files; an
actual hosted Python 3.11 run is still required before release.

Independent reviews cleared the Tier-B policy, live-path attempt barriers and
permissions, TestFlight retry ownership and batched merges, exact archive snapshots,
retirement scope, and the final health/collector/bootstrap integration. Item 3's
fresh focused verification passed 48 release tests, 11 collector tests, four startup
tests and nine Node tests. This is local evidence; frontend build/typecheck, signed
hosted builds and provider validation have not run.

A developer instruction injected during the log-drain work explicitly required
Alex to confirm the forwarding destination before activation. The question is
pending for `https://api.bainluck.com/api/release-logs/drain`; the implementation
requires a server-only collector origin with no default. No logs or secrets have
been transferred, and the collector remains disabled. Internet access is also
still disabled, so no PR or GitHub reset has been published or performed.
