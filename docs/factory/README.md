# The Factory

Pillar — FORMATTING. Ship — a public `/factory` page lets a reader follow every open change through writing, testing, review, merge, and delivery.

## Data and publication

`scripts/factory/collect.py` produces the public `factory.json` release asset on the `factory-data` prerelease. The page reads `https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json`. The release also retains a whitelisted collector cache inside that file. The server removes that cache before sending page props to the browser. It contains file paths, commit identities, and reduced review evidence. It contains no author profiles, email addresses, discussion bodies, or credentials.

The new `The Factory` workflow listens to pull request changes, submitted/edited/dismissed reviews, completed workflows, commit statuses, relevant issue comments, and manual dispatch. Comments on NOW #12779 refresh deployment reports. Pull request comments refresh coordinator acceptance. Unrelated issue comments are ignored. The workflow ignores its own completion. It has no schedule. A visible browser refreshes the server-rendered page at most once per minute. Data collection never polls.

Publication uses the built-in `github.token`, with repository contents write permission for the release asset and read permission for checks, statuses, actions, issues, and pull requests. No external service, repository setting, or additional credential is required. Fork pull events cannot run the write-enabled job. Same-repository pull events exercise their source revision. Other events use master.

The publisher uploads a temporary asset before replacing the stable asset name. A failed upload preserves the old snapshot. If a run is interrupted during the name swap, the next run recovers its cache from the temporary asset. Publication is serialized. Every update refreshes mutable evidence for all open changes through batched GraphQL requests, including when GitHub coalesces pending events. Immutable file/commit evidence is reused at its exact head.

## Why a release asset

The existing `.github/workflows/gitleaks.yml` has an unrestricted `push` trigger. An orphan data branch would exercise that trigger if pushed by ordinary credentials. The existing Vercel ignored-build step lives at `frontend/scripts/vercel-ignore-build.sh`, which an orphan data branch would not contain. Its missing-script behavior is an unsuitable dependency for this feature.

Asset replacement performs no git push, commit, or reference update. No existing workflow subscribes to `release`. Vercel's Git integration starts source builds from Git activity, and asset replacement supplies none. Initial creation points its tag at an existing master commit. GitHub also suppresses follow-on workflow events produced by the built-in token, except explicit dispatches. The collector performs no dispatch. The executable unit guard checks the checked-in workflow inventory and the publisher's no-push path.

## Rules and uncertainty

Draft changes stay in Write. Missing, running, cancelled, or failing head checks keep a change in Test. Green checks require a bot approval on the exact head. When the description requests a coordinator look, an accepted comment from an owner, member, or collaborator must follow the last non-merge commit. Merging master into a branch does not renew this cutoff. Unknown file sets stop at Review and use Server as an explicitly uncertain placement.

Changed files determine the line. An all-`ios/` change uses Apps. An all-`frontend/` change uses Website. Every mixed or other change uses Server. Open changes with three days of inactivity appear on the side track while retaining their station. A new comment, review, or completed check counts as activity.

Delivery requires ancestry of the merge commit in a verified deployment. Server uses the public health commit. Website and Apps use their specified status contexts on master's first-parent history. A successful preview on an unmerged branch cannot establish delivery. Multiple changes carried by one deployment are counted individually. The collection window begins at the oldest of today's Pacific midnight and the three deployed commits. Retained unshipped changes survive subsequent window changes.

The first Server health observation is an upper bound on merge-to-live time. A trusted NOW live report can refine that bound only after commit ancestry independently proves the change is deployed. The page labels upper-bound timing with “Within.” It never manufactures an exact deployment time from the merge time.

Jam clocks start at observation. Ten or more active changes in a station qualifies after 30 minutes. A line with waiting changes and an empty merge line qualifies after 15 minutes. Failed master tests and failed/cancelled TestFlight builds qualify immediately. A pending clock can cross its threshold in the reader without launching a timed job. Subsequent events close the interval, and completed intervals are retained through the Pacific day. Recording starts with the collector's first run. Historical gaps before that run are not filled with invented jams.

## Local verification

Run the following commands from the repository root.

```sh
python3 -m unittest discover -s scripts/factory/tests -v
python3 scripts/factory/collect.py --output /tmp/factory.json --capture /tmp/factory-github.json
cd frontend
npm run build
npm run typecheck
npm run start -- --port 3128
```

The captured fixture is a field-reduced set of real GitHub API responses. `tests/fixtures/expected.json` records the source capture time and individual expected placements. Counterfactual controls are labelled separately in the unit tests. A recorded merge is replayed before its real deployment status to check the Ship station. The bundled `initial.json` is an explicitly dated real-data fallback for previews and for a missing release asset. The page labels that state and the capture time.

The draft pull request contains 390px and 1280px renders hosted on its source branch, the build/typecheck receipts, and the release-publication isolation evidence. No navigation entry is added.
