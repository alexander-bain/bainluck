# Release packaging for the iPhone app — the archive/upload handoff

Written by native/089, 2026-09-09, as the D106 release-push deliverable that follows the
SHOWABLE-1 gates. Everything below was **measured on this machine**, not read off a guide.

## The headline

**Before this branch the app could not be archived at all.** `xcodebuild archive` on master
`421bdc36` crashed the Swift compiler twice and produced no binary — and exited **0** while
doing it. TestFlight was not "not set up yet"; it was blocked by a build failure nothing in the
repo could see, because CI compiles no Swift (standing notice 10) and every Swift gate we run is
a Debug build that runs no optimizer.

Fixed here. `** ARCHIVE SUCCEEDED **`, 0 crashes, a real signed `.app`. Details in
[the cause section](#the-cause-swift-633-and-generic-class-deinits).

## What works today, measured

| thing | state |
|---|---|
| `xcodebuild archive` | ✅ works on this branch |
| Artifact | `Bain Luck.app`, `CFBundleShortVersionString` **1.0**, `CFBundleVersion` **7** |
| Signing | `Apple Development: Alex Bain (ZSTGL24PX4)`, `TeamIdentifier=J893F72P4R` |
| Embedded | `PlugIns/BainLuckWidget.appex` |
| Watch app | **not embedded** — the watch complication target is still unwired (CLAUDE.md) |
| Gate | `tools/native-release-check.sh` — archives and grades the ARTIFACT |

## What is NOT set up, and what Alex has to supply

**1. A distribution certificate.** The archive signs with **Apple Development**. TestFlight needs
**Apple Distribution** plus an App Store provisioning profile for `com.bainluck.Bain-Luck` *and*
for `com.bainluck.Bain-Luck.BainLuckWidget`. That is an Apple Developer account action; no
amount of repo work substitutes for it. Automatic signing (`CODE_SIGN_STYLE = Automatic`,
`DEVELOPMENT_TEAM = J893F72P4R`) will fetch them once the account has them.

**2. An App Store Connect app record.** Bundle id `com.bainluck.Bain-Luck` must exist there
before any upload is accepted.

**3. An API key for unattended upload**, if we ever want this to run without Alex. Uploading
needs either Xcode Organizer (attended, ~2 minutes of clicking) or an App Store Connect API key
(`.p8` + issuer id + key id). The key is a **credential** — under the standing credential rule it
goes in `~/.claude/.env` or Actions secrets, never in this repo.

**4. `CFBundleVersion` is a hand-set literal (`7`).** App Store Connect refuses a build number it
has already seen, so this must increment per upload. Nothing increments it today. Whoever does
the first upload should decide between bumping it by hand and wiring
`CURRENT_PROJECT_VERSION` to a CI counter — do not automate it before the first successful
upload proves the rest of the chain.

## The two commands, once the certificate exists

```bash
# 1. Archive and grade it. Exit 0 only if a real .app came out.
tools/native-release-check.sh

# 2. Export for the App Store. ExportOptions.plist is NOT in the repo yet —
#    it is written at the first upload, when we know which profile name the
#    account issues. Shape:
#      method = app-store-connect, teamID = J893F72P4R,
#      signingStyle = automatic, uploadSymbols = true
xcodebuild -exportArchive \
  -archivePath /tmp/BainLuck-release-check.xcarchive \
  -exportOptionsPlist ios/ExportOptions.plist \
  -exportPath /tmp/BainLuck-export
```

Then upload via Xcode Organizer, or `xcrun altool --upload-app` with the API key.

I deliberately did **not** invent `ExportOptions.plist`. A guessed `provisioningProfiles` map
fails at export with a profile-name mismatch, and the honest name is only knowable once the
account issues one. Writing a plausible one would look like progress and cost the next session an
hour.

## The cause: Swift 6.3.3 and generic-class deinits

`EarlyPerfInliner` crashes while inlining into the **synthesized** deallocating destructor of a
generic class. It reproduces only at `-O`, so:

* every simulator build passed,
* `BainLuckTests` passed,
* CI was green,
* `xcodebuild archive` produced nothing.

Two crashes, one per generic class in the target — `MemoizedPresentation<Value>`
(`Utilities/DiscoverPresentation.swift`) and `SportsSiblingMerge<T>`
(`Utilities/SportsSiblingMerge.swift`). They are the *only* two generic classes in the app target.

The fix is to write each destructor out by hand: an explicit `deinit` releasing exactly the
stored properties the synthesized one released. No behaviour change — it is a codegen workaround
and both deinits say so in a comment, because a future reader will otherwise delete them as
redundant.

They crash **one at a time**: fixing `MemoizedPresentation` moved the crash to
`SportsSiblingMerge`. If a third generic class is ever added, expect the same, and expect the
tests and CI to stay green while it happens.

### Guards

* `ReleaseBuildArchivabilityTests` — asserts every generic class in the target declares an
  explicit `deinit`. Written as an invariant over whatever generic classes exist rather than an
  allowlist of today's two, so a third fails until it carries one.
* `tools/native-release-check.sh` — the only true test is an `-O` build. Run it before any
  release, and after any change that adds a generic class.

## The trap, worth keeping

`xcodebuild archive` **exited 0 on the crashing build.** The same log said
`Archiving project Bain Luck with scheme Bain Luck` and `(2 failures)`, and there was no
`.xcarchive` on disk. A wrapper that checked `$?` would have called the broken tree green — which
is gotcha #124 in a new place: read the artifact, not the exit code. `native-release-check.sh` is
built around this: it greps the log for `Stack dump` independently, and its pass condition is the
existence of the `.app` and its `Info.plist`, never the status.
