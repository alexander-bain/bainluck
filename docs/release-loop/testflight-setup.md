# TestFlight release setup

The action starts at **00:00 Pacific on Tuesday, November 3, 2026**. Before that,
master pushes run controller tests and classify their commits, but cannot dispatch
a release, load signing secrets, take ownership, archive or upload. Merging remains held until
Alex writes "master is current".

## Existing native assets required in Actions

The existing native lane uses `ASC_KEY_ID`, `ASC_ISSUER_ID` and `ASC_KEY_PATH`
(`tools/native-upload.sh`, `tools/asc-builds.py`). Reuse that API key. An API key
lets the action query Apple and upload; the current native tools also require an
Apple Distribution certificate with its private key and valid Store provisioning
profiles. The hosted runner does not inherit the native Mac's keychain.

Set these repository Actions secrets:

| Secret | Source |
| --- | --- |
| `ASC_KEY_ID` | Existing native lane key ID |
| `ASC_ISSUER_ID` | Existing native lane issuer ID |
| `ASC_PRIVATE_KEY` | Full PEM text from the existing `ASC_KEY_PATH` file |
| `IOS_SIGNING_P12_BASE64` | Base64 of the existing Apple Distribution identity exported with its private key as a `.p12` |
| `IOS_SIGNING_P12_PASSWORD` | Password used for that `.p12` export |
| `IOS_PROVISIONING_PROFILES_BASE64` | Base64 of a flat zip of the native Mac's valid App Store `.mobileprovision` files |

The profiles must belong to team `J893F72P4R` and cover at least the app
(`com.bainluck.Bain-Luck`) and widget (`com.bainluck.Bain-Luck.BainLuckWidget`).
Include Store profiles for any additional embedded app or extension, including
Watch targets, that the source commit embeds. Development profiles with a device
list are refused. The P12 must include the private key associated with those
profiles; exporting a certificate without its private key cannot sign a build.

On the native Mac, use Keychain Access to export the **existing** distribution
identity and its private key to a file outside the repository. Zip the matching
Store profiles with `zip -j` so the archive contains only profile basenames.
Upload each value with `gh secret set NAME --repo alexander-bain/bainluck`, using
stdin or an untracked input file. Do not paste any credential into a PR, issue,
document or tracked file. Do not mint a replacement API key to enable this path.

Secret presence and an actual signed hosted archive could not be checked in the
internet-disabled implementation session. **This is an activation dependency.**
Before relying on Tuesday's automatic builds, verify those six Actions secrets
exist and review the first hosted run's archive, upload and Apple receipt. The
workflow reports missing secret *names* before building and fails on bad signing,
missing or mismatched bundles, upload errors or failed Apple processing.

## What runs for each merge

The intake action walks every new first-parent commit in a master push, checks
that commit against its own first parent, and dispatches a separate source release
for each one touching `ios/**`. This preserves intermediate merges in a batch and
changes later reverted within the same push; it does not rely on GitHub's first
300 changed paths or a matrix-size limit. Feature commits inside a merge are not
separate master releases. Each dispatched run has a `source_sha` input, which must
be a full SHA on the current master first-parent chain and must itself change iOS.
PRs run only controller contracts and receive no signing secrets. A manually
dispatched run with a blank source uses current master if that commit changes iOS.

The release controller is checked out from trusted master, and the app is checked
out separately at the exact selected source. Earlier commits in a batch therefore
do not need to contain the newly introduced controller scripts. The hosted
toolchain matches the existing Watch action: macOS 15 / Xcode 26.3.

The separate `testflight-release-lock` ref coordinates release ownership. It is
never master and does not trigger a master deploy. Its commits carry only lease
state and keep a constant source tree; a fast-forward update lets exactly one
waiter own the next build. Initial ownership waiting runs on Ubuntu. No Actions
concurrency group drops intermediate pending merges. A controller that waits five hours fails visibly and can be retried.
A waiting controller recovers ownership only after the owner's
**specific workflow attempt** is completed. The macOS release independently
acquires ownership with its actual `run_attempt` before allocating a number and
validates again before upload. GitHub's "re-run failed jobs" can retain a successful
Ubuntu queue job's old output; that old token never authorizes a retry. Cleanup
uses the fresh attempt token and cannot unlock another run. Retried releases can
wait on the hosted Mac up to four hours; archive/upload keeps its 90-minute limit. The gitleaks push trigger excludes only this internal state branch; master,
other source pushes, PRs and the weekly source scan retain their existing scans.
Do not force or delete this ref:
fast-forward updates are what keep an old waiter from unlocking a new owner.

While owning the release, the action queries every Apple build page for the source
version and reads the highest build number recorded by current master. The next
number is one higher than `max(99, master, Apple)`. If Apple still holds only build
99 and master records no higher number, the first automatic build is **100**.
Build 99 is never uploaded again. Any unknown build-number or version shape fails
rather than supplying an unsafe guess. Source marketing version has a `1.0.5`
floor to bridge the stale `1.0` project settings in today's checkout, then follows
higher versions recorded in the source project. Every embedded app and extension
must carry the allocated version and number after both archive and export.

The action keeps ownership until Apple reports the uploaded build `VALID`, or
until the run fails. A 30-minute processing timeout fails the run; rerun that
failed workflow after inspecting its receipt and logs. It takes a fresh number
from Apple and does not reuse an accepted upload's number. Each run retains its
IPA, receipt and logs for seven days; signing material is stored outside the
checkout and removed from the hosted runner.

This action creates a TestFlight build. It does not submit an App Store release
or change the existing tester-group settings.

## Verification

```bash
python3 -m pytest tools/tests/test_testflight_release_loop.py -q
bash -n tools/testflight/build.sh
```

The controller contracts run under Python 3.11 on PRs and master. They exercise
Tuesday timing, real multi-commit and net-revert git histories, first-parent source
validation, separate dispatches, version/build-number floors, Apple pagination,
artifact version mismatches, upload success, signing profiles, failed-job-only
retry ownership, lease recovery and competing owners. Signed archive and Apple delivery remain
live gates in the hosted release job, not claims made by the offline tests.
