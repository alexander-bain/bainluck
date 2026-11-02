# Release loop review packet

**Ship:** master merges deliver changes and detect bad releases without an awake model session.
**Pillars:** TRUTH and FORMATTING (reliability).

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
