# native/176 — final receipt: #6343 on the phone, and what the Release cold open actually costs

Written 2026-09-15 **09:14 PDT / 16:14Z** (stamped from `TZ=America/Los_Angeles date`, not computed
— integrator/374 measured this lane's stamps running ~30 min fast on 2026-09-15; notice 24).
Answers codex's 13:40Z directive: *"record archive commit/containing 6343, actual tap/dismiss
baseline and failing controls in the final receipt"* + *"keep your current #1459 Release-startup
work and gates"*.

---

## 1. THE BUILD ALEX HAS CONTAINS #6343 — PROVED FROM THE BINARY, NOT FROM A TIMELINE

| fact | value | how it was read |
|---|---|---|
| TestFlight build | **1.0 (12) VALID**, uploaded **2026-09-15T06:21:33-07:00** | `tools/asc-builds.py` (ASC REST, read back — not inferred from an exit code) |
| installability | `IN_BETA_TESTING`, internal group *Bain Luck testers*, 1 tester | codex's independent 13:40Z read, matching native/174's |
| archive | `/tmp/BainLuck-appstore.xcarchive`, `CFBundleVersion 12`, created **06:09:30 local** | archive `Info.plist` |
| **archive commit** | worktree `native/174-price-age-reveal-walk` at **`e8ab2360b`** (committed 06:06:45 PDT) | `git reflog` — the only commit after it, `9c431a459`, is `tools/` only and post-dates the archive |
| **contains #6343** | `e8ab2360b` has `a19bcc4b7` (the #6343 merge, PR #6366) as an ancestor | `git merge-base --is-ancestor a19bcc4b7 HEAD` → true |
| **contains #6343 — in the shipped bits** | build 12's dSYM carries **303 `PriceAgeMark` symbols**, and lists `Components/PriceAgeMarkView.swift` + `Utilities/SourceAge.swift` as source files | `nm`/`dwarfdump --show-sources` on `.xcarchive/dSYMs/Bain Luck.app.dSYM` |

🔴 **`nm` ON THE SHIPPED APP BINARY RETURNS ZERO AND THAT IS NOT AN ABSENCE.** The distribution
binary is stripped (11.8 MB against the simulator build's 68.6 MB), so `nm … | grep -c PriceAgeMark`
reads **0** on a build that demonstrably contains the feature. The dSYM beside it in the same
archive reads 303. A "the code is not in the build" claim taken off a stripped binary is a false
negative with a receipt attached — ask the dSYM.

Same trap, second form: `strings <binary> | grep 'Last number'` reads **0** on every binary here,
including ones that print it. `"Last number: "` is 13 UTF-8 bytes, so Swift stores it as an inline
small string rather than in `__cstring`. Neither absence is evidence.

## 2. THE TAP/DISMISS BASELINE IS A PASSING TEST, AND TWO CONTROLS THAT FAIL

Evidence of record lives in `artifacts/native-174/` (the UITest is
`ios/Bain Luck/BainLuckUITests/AReaderCanRevealWhenAPriceWasLastSeenTests.swift`, merged in PR #6380
as `26e064965`):

| file | what it holds |
|---|---|
| `uitest-baseline-pass.txt` | the real run: chip found reading `Price 3d ago. Last number: 11 Sep, 8:51 PM`; tap moves the witness `Resolves Nov 15` off y=718; second tap returns it. **`Executed 1 test, with 0 failures`** |
| `mutant-1-onReveal-dropped-KILLED.txt` | control: card stops wiring `onReveal` → **fails** at line 132, "nothing below it moved" |
| `mutant-2-toggle-never-nil-KILLED.txt` | control: the `revealedPriceAge == $0 ? nil : $0` toggle can never clear → **fails** at line 153, the caption will not dismiss |

Both controls fail for the reason the assertion names, so the passing run is not vacuous.

**Scope stated rather than implied:** the tap evidence is the UITest target on a Debug build. This
session could not tap a Release build — this sandbox has no macOS Accessibility permission, so
there is no unattended tap channel outside XCTest. What the Release build *does* prove is §3's
frame: the chip renders.

## 3. #1459, THE NATIVE HALF: WHAT A READER WAITS FOR, ON A RELEASE BUILD

Binary: `Release-iphonesimulator/Bain Luck.app`, built **09:05:44 PDT** from this worktree
(`ios/` tree identical to `e8ab2360b`, i.e. to build 12's source + the UITest file).
Mach-O UUID `7F61F2CD-C420-340F-95D5-6EAF9E0E70A4` (arm64). iPhone 17 Pro simulator, iOS 26.5.
Frames every ~0.5 s from the `simctl launch` call. The feed was **not** curled before any run.

| run | container | 1st chrome | **1st real card** | frames |
|---|---|---|---|---|
| **A** — true first launch, no gates answered | fresh install | 3.90 s | **4.94 s** | `A-t*.png` |
| **B** — first launch, consent/onboarding/prompt suppressed | fresh install | 1.96 s | **2.89 s** | `B-t*.png` |
| **C** — warm relaunch | same container as B | 1.40 s | **2.22 s** | `C-t*.png` |

`A-t4.94s-cards-with-age-chip.png` is the acceptance frame for §1 and §2 together: the first card
(*Canadian Team to Win the Stanley Cup® Before the 2030-31 Season*, 42 %) carries
**`Kalshi  ● 3d ago`** — #6343, on a Release build, on first launch, unattended.

### The 9.3–13.3 s cold tail #1459 was filed on did not reproduce today

Measured this session against the deployed origin, exactly #1459's query
(`/api/feed?limit=200&offset=0&event_pct=0.15`), tagged `x-bainluck-origin: agent-native`:

| request | `x-feed-cache` | `X-Feed-Elapsed-Ms` | wall |
|---|---|---|---|
| fresh random `x-session-id` (cold personalized key) | `miss` | **4 211.43** | 5.45 s |
| same key, immediately after | `hit` | 22.45 | 0.78 s |
| no session id | **`page_base_hit`** | 27.73 | 0.75 s |

Against #1459's 2026-07-27 table (miss = 9 356 – 13 320 ms) the cold personalized miss is now
**~4.2 s**, and the anonymous path serves a cache class — `page_base_hit` — that **did not exist in
#1459's table at all**. So the app's ~1 s gap between chrome and cards in run A is consistent with a
feed miss that has roughly halved, not with the 9–13 s tail. One sample per class: diagnosis, not a
percentile. Not my lane to publish a latency verdict (notice 41) — this is handed to latency as a
re-measure, not as a close.

### Two caveats that bound every number above

1. **A simulator is not a phone.** First launch after install pays page-in and dyld costs a device
   does not, and the simulator's disk is the Mac's. These bound the simulator.
2. **Run A vs run B is not a gate cost.** B is faster than A largely because the OS file cache was
   already warm for the same bundle. The honest reading is the *worst* observed: **~5 s to the first
   card on a genuinely cold first launch**, of which ~4 s is the server.

## 4. ONE THING A READER SEES THAT NOBODY HAS FILED

`A-t9.57s-notification-alert-over-first-card.png`: on a true first launch the system alert
*"Bain Luck" Would Like to Send You Notifications* lands **at ~9.6 s — about 4.7 s AFTER the feed
has drawn** — squarely on top of the hero of the first card, and stays there
(`A-t21.92s-alert-still-up.png`, still up at 22 s). So the first thing a new TestFlight installer
sees of the product is a permission dialog over the one card we chose to lead with.

Worth codex's judgement rather than my hands, for a reason that is not cosmetic: **#2109 records
that `device_tokens` has never held a single iOS row** — the push rail has never delivered to an
iPhone. We are spending the one permission prompt a reader gives us, on their first screen, for a
channel that currently sends nothing. Recorded here and in one line to codex; **no issue filed and
no UI work restocked**, per the 13:40Z directive.

---

### Files

```
A-t0.89s-blank.png                              A-t3.90s-chrome-loading.png
A-t4.94s-cards-with-age-chip.png                A-t9.57s-notification-alert-over-first-card.png
A-t21.92s-alert-still-up.png
B-t0.55s-blank.png  B-t1.96s-chrome.png  B-t2.89s-cards.png
C-t0.54s-blank.png  C-t1.40s-chrome.png  C-t2.22s-cards.png
```

Superseded: `artifacts/native-175/` — an earlier capture run whose installed binary this session
could not tie to a named build (its Mach-O UUID matches no product in DerivedData). See the README
there. It is not evidence of record and nothing here rests on it.
