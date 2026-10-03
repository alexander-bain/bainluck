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
