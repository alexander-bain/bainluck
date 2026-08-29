# LAT-P118 — the probe that bought a warm slot

**Cycle 90 · 2026-08-28 23:2x PDT – 2026-08-29 0x:xx PDT · identity `LAT-P118-20260829-w68144` ·
branch `program/latency-103`, cut from CURRENT master `c47b25a5`**

Ran from Fable's runner directive (`runner-inbox/latency/023-coldpath-conveyor.md`), staged under
Alex's standing authorization. Lane lock claimed **exit 0**, prior owner explicitly RELEASED — no
takeover, no MALFORMED repair, the second cycle running that needed neither.

**Pillar: TRUTH. Ship: a search term our own measurement scripts typed can no longer take one of
the 40 slots that decide which searches are fast.**

**NEEDLE: latency 20 ms @ 2026-08-29T06:27:21Z open → 20 ms @ 06:56:39Z CLOSE** (7/7 served both,
all 3 graded surfaces, exit 0 both). `DIAG: latency-build 852 ms` at open — **published**, after
four consecutive nights of REFUSED — and REFUSED again at close (2/7 cold, floor 4).

🔴 **The number did not move and could not; what this ship protects is its HONESTY.** The needle is
the median of seven per-path p50s (12, 16, 18, **20**, 41, 47, 401 at close) and `search_cold` is
the MAXIMUM, 8.5× the next member, so a win there moves the median by zero. But `search_cold`'s
samples ARE the probe terms, one of which had already bought warm slot 40 of 40 — left running, the
warmer would have kept those terms hot and that member would have collapsed toward 12 ms, dropping
the published needle by roughly twenty-fold **with nothing having got faster**.

---

## The queue head named P117-3, and P117-3 turned out to be half of a bigger thing

LAT-P117 closed by naming the next ship: *give `/search` a suppression channel that is NOT also a
cache bypass and IS reachable over HTTP, since the polluter is.* That is a correct instruction and
this cycle carried it out. What it did not say — because nobody had looked — is that the
contamination had already reached the head.

The needle run that opened this cycle declares its own pollution, as it is built to:

```
/api/events/search        6 — one `search_query_logs` row each (#1916). Forced on: cold search is a graded surface.
```

Six rows a run, unavoidably, on a graded surface. That reads like an accounting nuisance. Then the
warmer's own head query was run against production.

---

## 🔴 THE MEASUREMENT: `cremonese` HOLDS SLOT 40 OF 40

`typeahead_warmer.resolve_head(session, DEFAULT_HEAD_SIZE=40)` blends two arms, one of which is
`_head_from_query_log` — verbatim, the top 40 of `search_query_logs` over 30 days, grouped by
`lower(btrim(query))`, length-filtered 2..200. Run as the warmer runs it, production, 2026-08-29:

```
  1  masters winner               112        20  grand prix                   46
  2  stanley cup                  110        ...
  3  world series                 102        37  heisman                      44
  4  red sox                      101        38  nba rookie of the year       44
  5  world cup                    101        39  lakers                       44
  6  nba champion                  99        40  cremonese                    42   <-- HARNESS PROBE
  ...                                        ----------------- the 40-slot cut -----------------
 19  aaron rodgers                 49        41  president                    42
                                             42  nba finals                   41
                                             43  sandhagen                    40   <-- harness
                                             44  osasuna                      40   <-- harness
```

`cremonese` is a Serie A club. Nobody searched for it. All 42 of its rows were written by this
program's own cold-path probes inside a **two-hour window** on 2026-08-28 (UTC hours 23 and 00
carry 271 rows across 12–21 distinct queries; every one of these terms has `first_seen =
2026-08-28`, `sessions = 0`, `attested = 0`). Two hours of probing out-voted **thirty days** of
everything except the top nineteen terms, and bought a warm slot from `president` and
`nba finals`.

Three more probe terms — `sandhagen`, `osasuna`, `pyrenees` — sit **two votes** below the cut,
against a block of twelve real intents tied at 44.

### Why that is a latency bug and not an analytics one

The head decides what stays hot. A slot spent on `cremonese` is a slot not spent on a query a
person will type, and the whole point of LAT-P090's response cache is that the common-word head
*cannot* be fixed by any string index — it can only be answered before it is asked.

### 🔴 And the instrument was on course to eat its own number

`search_cold` is the **largest member of the needle pool** — 287 ms this run against a 20 ms
median, 503.5 ms at LAT-P117's close. Its samples are exactly these terms. Once a probe term wins
a warm slot the warmer keeps it hot, `search_cold` starts returning cache hits, and **the
published needle falls with nothing whatsoever having got faster.** The instrument would have
measured its own warm cache and reported it as progress.

That is the same closed loop as #1866 and #2117, arriving for the third time on the third
surface, and this time through the measuring equipment rather than through a warmer.

---

## The ship: an HTTP origin channel that is not a cache bypass

`X-Bainluck-Origin` — a private header a caller sets to say *I am not a person*. It suppresses the
`search_query_logs` write on `/search` and the `search:trending:24h` vote on `/typeahead`, and it
touches **no cache, on either side, on either route**.

This is #1916's design step 1, which asks for exactly this header and exactly these values.

**Why a header at all.** `_suppress_search_log` (#1866/#2211) is a ContextVar, readable only inside
the API process, so it reaches exactly one caller — the warmer, which invokes the route function
directly. Every other automated writer arrives over HTTP: the Flow Sentinel via `httpx` from a
Celery worker, and these harnesses from a laptop. LAT-P117 measured the result: 4,244 unattested
rows out of 4,257. **The suppression that existed covered the one polluter that was never the big
one.**

### The value rule, and it is asymmetric on purpose

| header | verdict |
|---|---|
| absent | **logged** — a person's browser sends no such header |
| `` (empty) | **logged** — an empty value is a middlebox artefact, not a claim (gotcha #53 at the header level) |
| `user` (any case, any padding) | **logged** — honoured as a positive assertion |
| anything else | **suppressed** |

The header is private, non-standard and sent by nobody's browser, so the only way it arrives is a
caller asserting machine-ness. An unrecognised value there is overwhelmingly a typo in a new
harness, and of the two failure directions only one hides: a typo that keeps voting pollutes the
head silently, while a typo that stops voting costs one uncounted probe.

`user` is honoured but **not recorded** — recording it needs the `origin` column #1916 also asks
for, which is DDL and is not in this ship. Parked **P118-1**, stated rather than left to be read
as a ticked box.

---

## 🔴 FOUR CANDIDATES DISPROVED FIRST, AND THE DISPROOFS ARE THE FINDING

### (a) `?debug_timing=1` — the obvious reach, and it would pin the needle cold for ever

The flag already suppresses the trending vote on `/typeahead`, so having the harness pass it to
`/search` looks like a one-line fix. Read the route:

```python
_search_cache_readable = (not debug_timing and search_response_cache_enabled())   # READ side
if not degraded and not debug_timing:                                             # WRITE side
```

It bypasses the response cache in **both** directions, deliberately, for a reason that has nothing
to do with logging — a cached body carries no timing block, so serving one would answer a timing
request with silence. A harness using it to stop voting would therefore pin `search_cold`, the
largest member of the needle pool, to a **forced cold build for ever**, and the number could never
show a warmer reaching that surface.

**Suppressing a write and bypassing a cache are two different asks and they must not share one
flag.** Inherited from LAT-P117 (a); re-derived here by reading the two conditions, not taken on
trust. `test_the_origin_header_is_not_a_cache_bypass` and
`test_debug_timing_still_is_one_which_is_why_it_could_not_be_the_channel` are the pair that pins
the distinction, and neither may be deleted without the other.

### (b) Suppress the Flow Sentinel too — REFUSED, and it would make search slower

The sentinel is 18 of the top 25 terms. Removing it is the tidy move and LAT-P117 already measured
the consequence: the attested head is **one row** (`red sox`, 2 sessions) out of 40 slots, and
without `MIN_HEAD_SESSIONS` it is seven queries, several of them other harnesses' probes. There is
no organic slack to take up the difference.

And the sentinel's gold set was *chosen to be representative user intents*, so it is by accident a
defensible warm list. `cremonese` is defensible as nothing at all. **The distinction this ship
draws is not machine-vs-human, it is meaningful-vs-noise**, and it is drawn where the evidence
supports it rather than where the category boundary is. Re-parked **P118-3**, behind a demand
signal; the header makes it a one-line change on the day that signal exists.

### (c) Prune the head by attestation — disproved by (b), same number

Same one-row head. Already parked P117-2; re-checked against today's census (`sessions` is 0 for
43 of the top 45 terms) rather than inherited.

### (d) 🔴 THE ONE THAT WOULD HAVE SHIPPED AS A WIN — dedupe the write

"One row per query per session per hour" is one principled predicate, needs no header, catches
*every* polluter including ones that never heard of this channel, and would have cut `cremonese`
from 42 to about 2. It is the fix a reasonable person reaches for.

**It would have broken the head's only real job.** `session_id` is NULL on 43 of the top 45 terms —
99.7 % of the table is unattested — so "per session" collapses to "per query", globally. A term
searched by five hundred people in an hour and a term typed once by a script would then record
**the same one row**. The head exists to detect demand; the dedupe deletes demand and keeps
presence. Same shape as LAT-P116's `OFFSET 0` fence and LAT-P117's `result_count = 0` prune: a
principled-looking number, a worse product.

**Disproof (d) is why the fix is a channel and not a predicate.**

---

## What shipped

| file | change |
|---|---|
| `app/routes/events.py` | `_ORIGIN_HEADER`, `_ORIGIN_USER`, `_request_is_automation()`; the guard inside `_record_search_query`; the set-only `/typeahead` trending guard; `request: Request = None` on `typeahead_search` |
| 8 harness scripts | declare `X-Bainluck-Origin: harness` — `cold_path_snapshot`, `done_bar_snapshot`, `needle_latency` (via the snapshot), `probe_search_userfelt`, `probe_typeahead_userfelt`, `probe_typeahead_segments`, `probe_typeahead_warm_effect`, `evals/search_bucket_producer`, `evals/search_results_producer` |
| `tests/test_search_origin_channel_p118.py` | 19 tests, new file |
| `scripts/evals/search_origin_channel_mutations.py` | 10 mutants, new file |
| `scripts/evals/scan_mutation_residue.py` | one `SHAPES` entry, at its alphabetical position |

**The route itself never consults the channel.** `_request_is_automation` is called only from
`_record_search_query` and from `/typeahead`'s trending guard, never from anything that computes a
cache condition — so the channel cannot *become* a cache bypass by a later edit.
`test_the_route_never_consults_the_origin_channel_itself` makes that topological rather than a
promise about today's boolean.

---

## 🔴 THREE THINGS THE GATES CAUGHT THAT ARGUMENT WOULD NOT HAVE

### 1. `Optional[Request] = None` KILLS THE APP AT IMPORT, and the safer-looking annotation is the broken one

`typeahead_search` had no `request` parameter. Adding one with `Optional[Request] = None` — the
obviously-correct annotation for a parameter that may be absent — fails at import:

```
fastapi.exceptions.FastAPIError: Invalid args for response field!
Hint: check that typing.Optional[starlette.requests.Request] is a valid Pydantic field type
```

FastAPI special-cases the Request type by `lenient_issubclass`, which a `Union` fails, so
`Optional[Request]` is routed to the pydantic field builder instead of the injector. The
annotation must be **bare `Request`**; the default is what makes it optional. Caught in the first
run of the new suite, by the test written specifically to ask whether injection happens at all
(`test_fastapi_really_injects_the_request_despite_the_default`, asserted against FastAPI's own
`get_dependant`). **A channel that never receives a request suppresses nothing and looks exactly
like a clean table.** Offered as a gotcha.

### 2. THE CLASS GUARD'S FIRST PREDICATE UNDER-SCANNED BY TWO FILES, AND PASSED

The scan over `backend/scripts/` initially keyed on *transport* — "the file contains `urlopen(` or
`httpx`". It reported one offender and looked thorough. `probe_typeahead_segments.py` and
`probe_typeahead_warm_effect.py` shell out to `curl` through `subprocess`; they matched neither
token, so the guard had simply **not looked at them** and said CLEAN.

The predicate now keys on the **URL** (`/api/events/(search|typeahead)?`), which is
transport-agnostic by construction: however a request is eventually sent, it has to be addressed
first. A second test pins the eight files the census implicated **by name**, because a regex that
stops matching fails silent and green — `checked` shrinks, `offenders` stays empty, and a narrowed
denominator prints as a full one.

### 3. A FULL-SUITE RUN WAS KILLED AT 9 % ON PURPOSE

It was launched immediately after the first commit and the mutation harness and three more tests
landed while it ran. `inspect.getsource` re-reads files at call time, so a suite that spans a
source edit reports failures belonging to neither tree. Killed **by pid** (not `pkill -f`, which
would have taken the calibration lane's suite running in the same minute) and re-taken against the
final tree. Reported rather than quietly re-run.

---

## Gates

| gate | result |
|---|---|
| full suite | **21,235 passed / 0 failed / 124 skipped / 61 xfailed**, 845.64 s, run against the FINAL tree |
| suite exit code | **0 — READ BY VALUE** (`PYTEST EXIT CODE: 0`, captured to file, not inferred from the summary line) |
| suite ↔ collect | 21,235 + 124 + 61 = **21,420 = collected, exactly** |
| collect | **21,420** on the branch · master `c47b25a5` **21,396** (LAT-P117's measured figure at this same SHA, itself corroborated by LAT-P115) → **+24, enumerated AND measured**: 19 unit + 5 integration, each file's own collected count |
| smoke (`test_startup.py`) | **4 passed, EXIT 0** |
| targeted | LAT-P118's two files **24 passed, EXIT 0** · neighbours (`test_search_response_cache`, `test_typeahead_trending_cache_hit_2117`, `test_typeahead_eval_calls_do_not_vote`, `test_search_latency_contract`, `test_search_trending_window_2072`) **168 passed, EXIT 0** |
| mutants | **10/10 killed, EXIT 0** — and measured to bite from the INTEGRATION oracle standing alone on M1, M7, M9 |
| residue | **CLEAN, exit 0** — 165 needles, **1,568 broad checks**, run on a COMMIT (P117-5) |
| ruff | finding set **byte-identical** to master's over the changed files (**46 = 46, diffed not counted**) |
| `py_compile` | all 9 edited scripts, **EXIT 0** — and it caught a real `IndentationError` a bulk edit introduced |

### Ordering: three open latency branches, and all six orders agree

`-101` (LAT-P116), `-102` (LAT-P117) and `-103` (this) are all open — ancestry re-derived per
branch on **LOCAL** refs (`origin/program/<b>` does not exist and reads as "NOT MERGED").

All **six** permutations merge sequentially from `origin/master` with **exit 0** and the
**identical final tree `59e56455`**.

🔴 **And all three modify `backend/app/routes/events.py`, so the clean exit was not taken on
trust.** The merged tree was READ: it carries `-101`'s `_STALE_SERVE_CEILING`, `-102`'s
`_answered_result_count` *and* its recorder wiring, and this branch's `_ORIGIN_HEADER` and both
guards — with `-102`'s count fix at merged line 2899 sitting inside the same function as this
branch's guard at 2889, ten lines apart and semantically independent. `-101` and `-103` also both
add a `SHAPES` entry to `scan_mutation_residue.py`; both survive, at lines 64 and 84, because each
was placed at its **alphabetical** position rather than appended.

---

## Parked

- **P118-1** — the `origin` COLUMN. `user` is honoured but not recorded, so #1916's "positive
  assertion" acceptance box is not ticked by this ship. DDL; wants a migration slot.
- **P118-2** — the Flow Sentinel does not set the header. Deliberate (disproof b), not an
  oversight. One line on the day a demand signal exists.
- **P118-3** — `search:trending:24h`'s reset mechanism is still unidentified (#1866 §4). A key
  whose retention nobody can name is not an instrument, and the origin channel does not fix that.
- **P118-4** — inherited, not this branch's: `typeahead_warmer_mutations` **M4 and M6 needles have
  DRIFTED** and are silently inert. Verified absent on master `c47b25a5` too, so they score
  NOT-APPLIED rather than false-killing. Re-parked from P117-6, now two cycles old.
- **P118-5** — the runner directive still names needle **option b**; the tree's harness is
  **option c** (ruling 127). **FOURTH consecutive cycle to flag it.** Parked P116-6 → P117 → here.
  Not this lane's file to edit, and long past wanting a ruling rather than another park.

## Issues

**#1916** — design step 1 landed (the header, both sinks). Left **OPEN**: the column, the zset
split and the retention mystery are all still owed, and the head re-measure its acceptance asks
for cannot be taken until the channel has been deployed long enough for the 30-day window to heal.
`search_query_logs` is forward-only.

**None closed.** Nothing here has production evidence of a user-visible change yet — the branch is
undeployed, and `cremonese` keeps its slot until the window rolls.
