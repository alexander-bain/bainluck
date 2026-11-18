# The Factory

Pillar — FORMATTING. Ship — `/factory` lets a reader follow a change from its first lines to delivery.

## Master-only publication

`factory.yml` runs on a five-minute timer, a push to master, or manual dispatch. Its single job requires `refs/heads/master`, checks out master and reads the commit graph without historical file blobs. It collects once, compares the visible floor with the published snapshot, and uploads only when that floor changes. Publication is serialized with `cancel-in-progress: false`.

Comparison ignores the collection timestamp and incidental API ordering. Changes to stations, crates, live evidence, side tracks, diagnostics or jam intervals produce a new publication. The collector also checks the runtime ref, event and checked-out commit before publishing. `factory-tests.yml` remains a separate read-only workflow with the sole pull request path filter `scripts/factory/**`.

Every run prints `FACTORY_METRICS` with API calls by resource, public reads, remaining budget and elapsed time, including a run whose floor is unchanged. Upload, rename, deletion and metering requests are counted.

The expected rate is about 12 timer runs per hour plus one per master push, with manual dispatches added separately. The preceding busy-hour measurement gives a warm collection median of 19 API requests. Reading the published release adds one, and replacing both assets adds eight. That is approximately 20 requests for an unchanged floor or 28 for a changed floor, or 240–336 requests per timer-only hour. Each master push adds approximately 20–28 requests. New heads, pagination, initial cache population and recovery can add calls. These are estimates from measured reads and the publisher's request paths, rather than a production-hour measurement of this unmerged revision.

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
cd frontend
npx jest --runInBand --testPathPatterns='factoryData|factoryUnavailable'
npm run build
npm run typecheck
```

The review draft links new 390px and 1280px renders on a separate image branch. The source tree holds the browser and gate receipts. Rendering uses a current read-only collector response through the local test transport, with the production page code. Source changes and image publication are separate commits.
