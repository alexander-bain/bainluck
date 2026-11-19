# The Factory

Pillar — FORMATTING. Ship — `/factory` lets a reader follow a change from its first lines to delivery.

## Master-only publication

`factory.yml` runs when CI completes, on a five-minute timer, a push to master, or manual dispatch. CI completion always runs in the master context and checks out master. Its single job requires `refs/heads/master`, checks out master and reads the commit graph without historical file blobs. It collects once, compares the visible floor with the published snapshot, and uploads only when that floor changes. Publication is serialized with `cancel-in-progress: false`.

Comparison ignores the collection timestamp and incidental API ordering. Changes to stations, crates, live evidence, side tracks, diagnostics or jam intervals produce a new publication. The collector also checks the runtime ref, event and checked-out commit before publishing. The Factory-specific pull request workflow is removed. The rules run in the existing backend CI check through `backend/tests/test_factory_rules.py`. The collector has a five-minute job timeout.

Every run prints `FACTORY_METRICS` with API calls by resource, public reads, remaining budget and elapsed time, including a run whose floor is unchanged. Upload, rename, deletion and metering requests are counted.

The expected rate is 12 timer runs per hour plus one per completed CI run and master push. The November 18 warm-cache read made 29 API requests in 34.56 seconds. Reading the published release adds one, and replacing both assets adds eight. Budget about 30 requests for an unchanged floor and 38 for a changed floor. In the recorded 7–8 AM PT hour, six CI runs completed and master had no pushes, giving 18 expected collections and about 540–684 API calls. Add 30–38 per master push or manual dispatch. New heads and pagination add work. The legacy-cache migration made 101 requests in 61.60 seconds, with 3,644 core requests remaining. Every request and public read is metered.

## Signals and motion

The collector records station transfers and five stoppage conditions. A merge line with waiting changes and no merge for 30 minutes stops. The newest merging announcement stops after 15 minutes if none of its changes merged. A HOLD persists until a later live line for that delivery line. The latest completed master CI failure stops Test. A Review wait over two hours is amber. Announcement records contain only line, time and change numbers.

The page shows “Not updating,” keeps the last verified floor and pauses motion when a refresh fails or the copy is more than 15 minutes old. An unavailable or invalid file with no verified floor shows the unreadable state.

| Motion | Evidence |
|---|---|
| Conveyor segment | A recorded transfer crossed that segment within 15 minutes, with neither endpoint stopped |
| Crate travel | Its station differs between reads and the collector has a recent transfer for that number |
| Worker hands | Crate activity or a transfer at the occupied station within 15 minutes |
| Steady green lamp | A recent transfer at that station |
| Red turning beacon | Active red stop at that station |
| Amber pulse | At least ten visible changes in the bay, or a qualified recorded jam |
| Live truck and counter tick | A newly observed transfer into Live |

Reduced motion disables animations. A hidden tab pauses them. Original SVG workers keep their state readable in a still frame. Live bays show eight crates and the earlier-today count. Bot approval and Fable acceptance survive verified test-only commits and merges of master. Unverified commit evidence keeps the earlier review station.

## Public assets

The `factory-data` prerelease holds two assets. `factory.json` contains the floor, observations and jam intervals. `factory-cache.json` contains the reusable collector metadata. The public URL is `https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json`.

Each asset is uploaded before its stable-name replacement. The cache is replaced first. Matching generation timestamps bind it to the public snapshot. An interrupted replacement with mismatched generations causes a metadata reread while the last published floor retains its observation history. The first revised publication migrates the earlier combined asset.

Release-asset replacement creates no source commit or push. The repository's existing workflows have no release trigger. The unrestricted gitleaks push trigger and Vercel's source build hook therefore receive no source update. Publication uses the built-in GitHub token.

## Evidence and display

Checks bind to the current head. Bot approval carries across verified test-only commits and merges of master. A trusted comment beginning `**Fable` can clear the final look with `ACCEPT` or `no look needed`, provided it follows the last non-merge commit. A description saying `Fable: not needed` also clears that look. OWNER, MEMBER and COLLABORATOR are the accepted associations.

A live status still requires the merge commit to be included in that line's deployment. Merge-to-live timing includes only changes merged since the first observation. Earlier deliveries still count as delivered, and their elapsed time is omitted. Jam intervals start from observed events and keep the Pacific-day boundary.

Each GitHub read has a four-second limit and one retry. On November 18, 15 direct Node reads that followed the redirect and parsed the file took 34–517 ms. Fable measured 320–620 ms from a cloud machine and reported five production reads cut off at the old 800 ms limit. The four-second limit gives those two-hop reads room to finish during publication. Each attempt logs its duration, outcome and HTTP status when available.

Next's 60-second Data Cache stores verified copies. A failed refresh leaves the previous entry available. An open page also keeps its displayed floor when the next render has no copy. The browser saves the last good timestamp between visits.

Bays size to their contents. Only a bay holding at least ten waiting changes gets the amber outline. System jams can pulse their own lamp. Earlier branch families are labelled “Earlier work.” Reduced motion disables the belts, lamps and moving crates.

## Verification

```sh
python3 -m unittest discover -s scripts/factory/tests -v
cd frontend
npx jest --runInBand --testPathPatterns='factoryData|factoryUnavailable|factoryActivity'
npm run build
npm run typecheck
```

The review draft links new 390px and 1280px renders on a separate image branch. The source tree holds the browser and gate receipts. Rendering uses a current read-only collector response through the local test transport, with the production page code. Source changes and image publication are separate commits.
