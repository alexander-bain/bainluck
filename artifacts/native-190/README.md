# native/190 — the D48 walk, #6544, and the two things it found

**Read this before citing any PNG here.** `tools/native-walk.sh` terminates and launches; it does
**not** install. A shot therefore records whatever binary was last installed on the simulator, and a
successful `xcodebuild build` two minutes earlier does not change that (native/189's README is where
that cost twenty minutes). Every shot below was taken after an explicit `xcrun simctl install` with
the installed binary's mtime read back against the build product's.

| file | binary | what it is |
|---|---|---|
| `01-discover.png` · `02-search-chiefs.png` · `03-event-nfl-settled.png` · `03b-…-plus40s.png` · `04-…-scrolled.png` · `05-event-nfl-upcoming.png` | **master `95794d896`**, installed 11:33Z (binary mtime `Sep 16 04:33:38`) | the walk. `05` is the specimen cited by #6544; `03` + `03b` are the pair cited by #6546 |
| `06-AFTER-event-nfl-upcoming.png` · `07-AFTER-event-live.png` · `08-AFTER-event-final.png` | **the fix `3072da26d`**, installed 11:54Z (mtime `Sep 16 04:53:38`) | the three hero states after |

`05` → `06` is the before/after pair. `07` and `08` exist because the fix moves the status chip
inside a `TimelineView`, and the chip's other two arms — the live red pulse and the grey FINAL —
had to be seen rendering, not reasoned about. The chip sits at the same x/y in `05` and `06`, which
is the layout half of the same check.

## The route the walk took

Discover → Search ("chiefs") → a settled marquee event → the same event scrolled → an upcoming
marquee event → (after the fix) a live event. Search, the settled hero, the period table and the
completed chart all read correctly; the two findings are below.

## What it found

**#6544 (fixed here).** The upcoming event hero printed `In 4d 12h` twice, 250pt apart — the
`StatusBadge` chip and a bare `Text` in the centre column. One `formatCountdown`, one
`commenceTime`, so the two copies could not disagree. Reasoning, and the frozen-chip regression the
deletion could have shipped, are in the commit message and PR #6547.

**#6546 (filed and routed, not fixed).** `GET /api/events/{id}/history` serves **2.69 MB in 4.65 s**
for one finished NFL game (measured from production twice: 4.65 s / 4.83 s, 2,691,217 B), of which
the phone draws one line — so a marquee game's chart is a blank half-screen with a spinner for
~30 s. `03` is that blank at 13.5 s; `03b` is the same page filled ~40 s later. Photographed before
*and* after #6544 on the same page, so it is not a regression of it. Routed to latency under
notice 41; `runner-inbox/latency/FROM-native-190-1205Z-…`.

## The mutation battery

`mutants.sh` → `mutants-out.txt`. Ten mutants across four files plus a clean-head control, run last.
It inherits native/189's **pass 2** verdict logic, which is the corrected one, and the reasons are
worth keeping in view: `xcodebuild` exits 65 for a compile error and for a test failure alike, and a
run killed on a hang leaves a partial log whose per-class `Executed N tests` line reads exactly like
a kill. So a verdict needs rc **and** the log, every run is bounded (a hang reports `REFUSED-HUNG`),
a needle that does not apply reports `REFUSED`, and `INT`/`TERM` restore all four files.

**One correction made mid-run and kept here rather than quietly fixed.** The first attempt's
attribution column listed *every* test in the class for M1, which reads like a rout and is
meaningless: xcodebuild prints the same `-[Class testName]` shape for `started`, `passed` and
`failed`, so a grep on the class name matches all three. The run was stopped, `killers()` narrowed
to `]' failed`, and `outsiders()` added so that a mutant killed only by a pre-existing test
somewhere else in the suite cannot be banked as evidence about this guard. The battery below is the
re-run.
