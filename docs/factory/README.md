# The Factory

Pillar — FORMATTING. Ship — `/factory` lets a reader follow a change from its first lines to delivery.

## Master-only publication

`factory.yml` listens to requested/completed CI, review and TestFlight workflows, master pushes, NOW #12779 comments, comments beginning `**Fable`, completed Vercel/TestFlight statuses, and manual dispatch. Every job requires `refs/heads/master`. It has no pull request trigger or schedule.

The preflight job has read permissions and checks out only the current `scripts/factory` folder. It reads the public snapshot and the complete open-change membership. If that membership matches and the snapshot is under three minutes old, publication is skipped. An opened, merged or closed change bypasses that delay. Its paginated GraphQL read includes the remaining GraphQL budget in the same response.

The publisher receives write permission only after preflight admits a refresh. It checks out master, reads the commit graph without historical file blobs, and runs the master collector. The collector also checks the runtime ref, event and checked-out commit before publishing. `factory-tests.yml` is a separate read-only workflow with the sole pull request path filter `scripts/factory/**`.

Every preflight and collection prints `FACTORY_METRICS` with API calls, public reads and rate limit remaining. The collector also reports calls by resource and elapsed time. API upload, rename, deletion and metering requests are included. The busy-hour verification records its replay window and distinguishes replay traffic from production traffic.

## Public assets

The `factory-data` prerelease holds two assets. `factory.json` contains the floor, observations and jam intervals. `factory-cache.json` contains the reusable collector metadata. The public URL is `https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json`.

Each asset is uploaded before its stable-name replacement. The cache is replaced first. Matching generation timestamps bind it to the public snapshot. An interrupted replacement with mismatched generations causes a metadata reread while the last published floor retains its observation history. The first revised publication migrates the earlier combined asset.

Release-asset replacement creates no source commit or push. The repository's existing workflows have no release trigger. The unrestricted gitleaks push trigger and Vercel's source build hook therefore receive no source update. Publication uses the built-in GitHub token.

## Evidence and display

Checks and bot approval bind to the current head. A trusted comment beginning `**Fable` can clear the final look with `ACCEPT` or `no look needed`, provided it follows the last non-merge commit. A description saying `Fable: not needed` also clears that look. OWNER, MEMBER and COLLABORATOR are the accepted associations.

A live status still requires the merge commit to be included in that line's deployment. Merge-to-live timing includes only changes merged since the first observation. Earlier deliveries still count as delivered, and their elapsed time is omitted. Jam intervals start from observed events and keep the Pacific-day boundary.

A failed, invalid or unavailable live read displays “The floor can't be read right now” with the last good time known to the server or returning reader. The browser retains only that timestamp. A first-time reader with no successful read sees that no good copy has been read. No bundled inventory substitutes for a failed live read. The old `initial.json` lives in test fixtures.

Bays size to their contents. Only a bay holding at least ten waiting changes gets the amber outline. System jams can pulse their own lamp. Earlier branch families are labelled “Earlier work.” Reduced motion disables the belts, lamps and moving crates.

## Verification

```sh
python3 -m unittest discover -s scripts/factory/tests -v
node --test scripts/factory/tests/preflight.test.cjs
cd frontend
npx jest --runInBand --testPathPatterns='factoryData|factoryUnavailable'
npm run build
npm run typecheck
```

The review draft links new 390px and 1280px renders on a separate image branch. The source tree holds the browser and gate receipts. Rendering uses a current read-only collector response through the local test transport, with the production page code. Source changes and image publication are separate commits.
