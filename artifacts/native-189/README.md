# native/189 — #6528, and the phone walk that found it

**Read this before citing any PNG here.** `tools/native-walk.sh` terminates and launches; it does
**not** install. So a shot records whatever binary was last installed on the simulator, and a
successful `xcodebuild … build` two minutes earlier does not change that. I lost twenty minutes to
this: the first "after" shot showed the unfixed card and I began checking whether `SportCategoryView`
used a different component (it does not — `EventCardView`, line 300).

| file | binary it photographs | what it is |
|---|---|---|
| `01-discover.png` · `02-sports.png` · `03-team-redsox.png` · `04-settled-15312924.png` | **resident** (whatever was installed before this session; master-equivalent for every element below) | the D48 walk, 09:19Z. `02-sports.png` is the specimen photograph cited by #6528 and #6529 |
| `05-after-sports.png` | resident | the Sports tab ~90 min later — the suspended card had rotated out of the served feed, which is why the after-LOOK moved to `bainluck://category/mma` |
| `after-tennis.png` · `after-mma.png` | **resident — NOT the fix.** Kept because they are the shots that exposed the install gap | misleading on their own; superseded by the pair below |
| `before-mma-installed.png` | `origin/master`, built and `simctl install`ed at 03:36 PDT | the defect: chip wraps to two lines, right slot repeats it, no date |
| `after-mma-installed.png` | `174a311f5`, built and `simctl install`ed at 03:35 PDT | the fix: one chip, one line, right slot reads `Sep 15` |

Only the last two are a before/after pair. Both were taken after an explicit `xcrun simctl install`
with the binary's mtime read back.

## The mutation battery

`mutants.sh` → `mutants-out.txt` (pass 1) and `mutants-pass2.sh` → `mutants-pass2-out.txt` (pass 2).
Both are kept, because pass 1 is wrong in a way worth reading: it scored **8 killed** and only
**7** were real.

* **M3, M4** did not compile. `xcodebuild` exits **65** for a compile error and for a test failure
  alike, so a malformed mutant scores exactly like a kill.
* **M5** exited **143** — SIGTERM, my own kill, after the suite wedged on a live network read inside
  the app under test. Gotcha #124: only `0` and `65` are xcodebuild answering the question asked.
  Pass 1's classifier found a per-class `Executed N tests` line in the partial log and called it a kill.

Pass 2 takes the verdict from the log (a kill needs the build to have succeeded **and** a test to have
failed), bounds each run at 12 minutes so a hang reports `REFUSED-HUNG`, and refuses any rc outside
`{0,65}`. Final: **10 mutants, 10 killed, 0 survived, 0 ungraded**, clean-head control run last and
SURVIVED, tree byte-identical after every one.

Pass 1 also had no `INT`/`TERM` trap, so interrupting it left `StatusBadge.swift` carrying M10 in the
working tree. Found with `git status`, not by looking. Pass 2 restores on signal.
