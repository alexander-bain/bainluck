# Watch build foundation — #4932

PILLARS: TRUTH · FORMATTING.
SHIP: keep one explicitly selected game, its state and an honest named probability
on the wrist. This build repair is the first contribution to that existing ship.

Run `bash tools/watch-build.sh` on a Mac with Xcode and watchOS platform support.
The gate builds the shared `BainLuckWatch` scheme for both simulator and device
SDKs without signing or booting a simulator. It records logs in the printed
temporary directory, verifies executable bundles, and preserves build failures.
It does not prove installation, runtime behavior, distribution or freshness.

The Watch already decodes its feed through `WatchFeedModels.swift`. Its accidental
membership in iPhone `CommonTypes`, `EventModels` and `FeedModels` brought in
unavailable transitive types. Remove that unused membership rather than add the
entire iPhone dependency graph. Shared `PredictionModels` and `PeriodLabel` remain.

The complication source and target remain for #4933, but the app no longer embeds
the unfinished extension. Its target had no synchronized source group; producing
an extension bundle was not evidence its Widget implementation compiled or ran.
Restoring it requires actual source membership, truthful snapshot expiry and
event-specific routing, plus physical Watch evidence.

## Next boundary

Alex approved companion packaging with the existing iPhone product and public,
no-login selected-game use first. This foundation intentionally retains the
existing watch-only container until companion embedding/signing is implemented
and reviewed with Native. The iPhone target gains no Watch build dependency here.
The Watch is not yet packaged in the iPhone release and does not block 1.0.3.

Native coordinates shared project/simulator resources; Integrator owns merges.
No automatic-provisioning switch is used. Account/security changes, distribution
records, upload, tester invitations, submission and release each require Alex's
approval. Never infer installed Watch behavior from an iPhone test pass.

Preserve #1739 commit `408173252050b0c015a33b34baeddc0dfb355475`; adapt its
failure/empty-state logic later, using observation age rather than fetch age and
actual draw-capable probabilities rather than invented complements. The present
build restoration does not repair those reader defects or close #4932/#1739.

## Selected-game contribution

The Watch root now offers a real Discover game picker and retains one selected
canonical event locally. It reads that event directly from the public detail API
and never needs a sign-in token. Foreground live refreshes wait 30 seconds after completion; non-live games wait
five minutes and repeated failures back off from 30 seconds to five minutes.
Reopening and manual retry check immediately; a selection/request revision and cancellation checks prevent
old responses replacing the current selection. Successful final state shows the
final score, while refresh failure retains and dates the prior reading.

Hero probability and hero observation time travel together. Score observation
age is separate. Missing times remain unknown; a successful fetch never dates
the underlying reading. The display names the home team's win chance and never
derives an away probability as a complement. Selection of a different outcome,
followed-team synchronization, phone continuation and companion packaging remain
future #4932/#5398 work. The Discover picker is a bounded list, not a complete
sports schedule. Old tabs remain source-only and are not the MVP navigation.

Run `bash tools/tests/watch-selected-game/run.sh` for the compiled Swift behavior
harness (no simulator). Use `WATCH_BUILD_CONFIGURATION=Release` with the build
gate for unsigned Release SDK checks; these are not a distribution archive.

A dedicated Ultra 2 simulator on watchOS 27 is used for local evidence. Any test
that seeds the saved selection directly must be labeled as seeded restoration,
not proof a person tapped through the picker. Physical Watch, paired Handoff,
battery and TestFlight acceptance remain distinct.

## Offline restart contribution

One versioned last-good public reading is persisted with the canonical selection.
Restart restores it only when its ID matches. The view labels it “Saved reading”
until a successful refresh; offline failure and cancellation do not remove that
label or advance the original producer clocks. Selection changes remove the old
cache. Corrupt, mismatched or unsupported snapshots are ignored. Final corrections
remain accepted; score or observation timestamp monotonicity is not a safe proxy
for correction authority. The compiled harness covers restoration, serialization,
races, invalid cache, final corrections and independent observation ages.

Codex owns this contribution and independent review. Native has no immediate
execution request. Exact-commit native builds and BainLuckTests remain required
before integration; old-head build evidence does not validate this source.
Current milestones and ownership live in GitHub #4929/#4932.

## Foreground refresh lifecycle

The view cancels its selected-game loop while inactive or while the picker is open.
The loop checks cancellation before network work and after each wait. Cancelled
and obsolete requests do not advance failure backoff. A successful refresh resets
backoff; a changed/cleared selection also resets it. Picker request revisions keep
an older completion from clearing a newer loading state. These are foreground
policies, not promises of background delivery. Swift tests inject the sleep boundary
to exercise delays and cancellation without a real timer or simulator. Physical
background/network and battery behavior still needs device evidence.

## Readable and spoken observation ages

Watch observation ages display seconds, minutes, hours or days and speak full unit
names. Unknown/future/nonfinite timestamps remain unavailable. The state group
announces saved/error qualification before scores and named probability. At
accessibility text sizes, state and score rows stack vertically. These source and
logic checks do not establish physical VoiceOver focus order or large-text fit.

The build helper now defaults to worktree-local `build/watch-mvp` DerivedData and
two build jobs (one is supported), respecting shared-host isolation. No simulator
boot is needed for its two unsigned SDK builds.

## Network failure behavior

The public event transport distinguishes unavailable games (404/410), temporary
service pressure (429/503), invalid responses and networking failures. None clears
the selected game or last-good snapshot. Starting or cancelling a retry retains
the prior error; only successful recovery or a selection change clears it. Timeout
and offline messages are distinct. Deterministic URLProtocol tests intercept every
request and verify the production URLSession transport without network/simulator
usage. They do not establish physical connectivity behavior.

## Choosing a valid game

The Watch-only picker store retains a prior list through failed/cancelled refreshes
and fences overlapping requests. It omits nonpositive IDs and unnamed sides, keeps
the first valid occurrence of each canonical ID, and preserves Discover order.
Malformed event payloads count as unavailable details rather than silently becoming
an empty feed. The UI names the bounded Discover source and distinguishes empty,
partial, unavailable and previously received lists. The shared WatchFeedModels and
WatchAPIClient are reused unchanged; their iPhone test membership is untouched.
The standalone Swift harness now checks this store as well as the selected game.
Actual picker taps on a physical Watch remain an unpaid acceptance step.

## Integrated journey and closed results

The deterministic journey now exercises Discover choice → canonical live detail →
cold offline restoration → completed result → changed selection → cleared snapshot.
This verifies store integration, not a physical tap or rendering.

`closed` is terminal for withholding a forecast, but its scores may be frozen
midgame (`backend/app/utils/settled_hero.py`). Picker/detail/spoken state therefore
say “Closed · result unverified”; the detail qualifies scores as last reported.
It neither presents a win forecast nor promotes those scores to a verified final
result. Completed/final behavior stays distinct. Snapshot round-trip guards cover
closed state too.

## Hosted verification

`.github/workflows/watch-mvp.yml` runs the standalone Swift behavior harness and
both unsigned Release SDK builds on a GitHub-hosted macOS runner for changes to
Watch inputs. Xcode 26.3 is explicitly selected from the macos-15 image; its default
Xcode 16.4 cannot compile the current model syntax. It checks out and prints the
exact PR head, uploads only build logs, and performs no simulator boot, signing,
account or deployment operation. The new workflow's successful execution must be
observed before claiming this gate paid. It is path-scoped, not a globally required
check on unrelated iPhone PRs, and does not replace BainLuckTests or physical proof.

The first attended device step group is in `docs/watch-device-trial.md`; no user
input is needed for ongoing source or hosted verification.

## Hosted iPhone compatibility gate

A second job in the Watch-scoped workflow runs the existing full `BainLuckTests`
scheme on a fresh disposable hosted iPhone simulator, after Watch checks pass.
`tools/watch-iphone-compatibility.sh` refuses to operate unless GitHub identifies
the runner as hosted. It does not invoke Native's broader local gate script, modify
its tests, or touch a local simulator.

The result is accepted only when xcodebuild exits zero, prints TEST SUCCEEDED,
and prints exactly one named All tests passed summary with a nonzero test count
and zero failures. Partial/class-only/contradictory results are rejected by
`tools/watch_iphone_receipt.py`, whose fixtures cover those failure shapes. The
workflow preserves raw logs, exact SHA/toolchain/destination, receipt and xcresult.
Fresh build output and plain `test` avoid executing an older test bundle.

This is the existing iPhone compatibility requirement for integrating the Watch
contribution, not a new feature or local task for Native. Implementation of the
workflow alone never pays the gate; only a complete successful hosted run does.

The first hosted compatibility run (cd45b9cb92, Xcode26.3) stopped before tests:
that compiler could not type-check the unchanged iPhone PlayerPropsCardView. The
compatibility job now selects the hosted `xcode-27` image and explicit Xcode27.0
(27A266a in the runner manifest), matching Native's local compiler. Its simulator
runtime must match the selected SDK major/minor; a newer beta runtime is not chosen
silently. The Watch-only job keeps its already-proven Xcode26.3 environment. This
alignment is a harness repair to verify, not a claim that the iPhone suite passed.

## Hosted picker interaction journey (#4932)

`BainLuckWatchUITests` is an additive Watch-only UI test target. Its scheme uses
Apple's Watch XCTest UI runner to tap a first game, assert the named home
probability, terminate/relaunch offline, assert the saved/offline qualification,
and choose a different game. `tools/watch-ui-journey.sh` refuses local execution
and creates a disposable Watch on a GitHub-hosted runner. The workflow preserves
source/toolchain/destination metadata, logs, a full-suite receipt and screenshots
inside the result bundle; DerivedData is not uploaded.

The test uses deterministic transports behind `#if DEBUG`, an explicit launch
environment switch and a UUID-specific defaults domain. Reset happens once per
process, and offline relaunch preserves that domain. Release does not contain the
fixture implementation. This proves a controlled UI journey only when the hosted
suite actually succeeds; it does not prove production data, physical installation,
VoiceOver speech, large-text fit, battery behavior or distribution. Screenshots
must be opened and inspected before claiming visible layout acceptance.

The shared project additions require Native/Integrator boundary review before
integration, independently of the earlier Watch membership approval. No existing
iPhone target, build phase, scheme or application source is modified by this UI
slice. If the runner requires Watch pairing or cannot expose a matching runtime,
the journey fails as an unpaid gate; it never borrows an existing iPhone.
