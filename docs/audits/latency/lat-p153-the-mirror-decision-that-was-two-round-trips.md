# LAT-P153 — the mirror decision that was two round trips

**Pillar: FORMATTING.** **Ship: an NFL team's page stops making you wait twelve seconds and
then showing you nothing** — the same ship as LAT-P145, unblocked. This queue did not pick a
new endpoint. It repaired the one defect that was standing between a built, graded, sound fix
and production.

> Subject: `program/latency-130`. Predecessor: **CERT-480 — BLOCK, token withheld** for
> `7b01db4f`. This document covers only what changed after that verdict; the ship itself, its
> measurement and its trade are documented in
> `lat-p145-twelve-seconds-to-be-shown-nothing.md` and are unchanged.

---

## 1. Why a blocked branch was the right thing to take

The standing directive ranks the production slow-event ring and takes the top *un-banked* path.
The ranking on 2026-08-30 said:

```
     67  p50  8,272  /api/events/typeahead              LANDED (-128)
     47  p50  7,426  /api/events/{id}/related-futures   CERT-486, staged, pending
     34  p50 12,077  /api/teams/{id}/prop-families      🔴 CERT-480 BLOCK
     ...
      5  p50  7,937  /api/futures                       un-banked
      4  p50 12,337  /api/events                        un-banked
```

`prop-families` is the **highest-count unfixed path on the board** — eight times the traffic of
the best un-banked candidate — and its fix was already written, already gated, and already
graded sound on every substantive axis. LAT-P152 legislated the step-0 rule that produced this
choice: read the BLOCK reason before ranking anything, and distinguish a branch blocked on a
*gate* from one blocked on a *defect*. This one was blocked on a defect, so it was sized as a
real build rather than a lint sweep — but it was still by a wide margin the cheapest ship
available.

**The defect is still live in production.** Re-measured 2026-08-30 ~19:0x UTC, unchanged from
the numbers CERT-480 was staged on:

```
new-york-giants    wall=12,650 ms  db=576  app=12,074  q=3  unfinished=1  0 families  NO envelope
green-bay-packers  wall=12,394 ms  db=327  app=12,068  q=3  unfinished=1  0 families  NO envelope
```

*(Those two reads are this queue's own probes. They are in the slow-event ring and should be
discounted from any later count — LAT-P151's rule that on a quiet endpoint most of the "slow
requests" are us.)*

---

## 2. The finding, and why the existing 59 guards could not see it

CERT-480 withheld its token for one thing:

> **A concurrent partial build can overwrite a full 24-hour mirror.** The protection is a
> non-atomic read-then-write across `_mirror_is_full(...)` and `write_payload(...)`.

The rule the code was trying to express is *"store this partial unless something better is
already there"*. That was implemented as a decision taken in one Redis round trip and acted on
in another:

```python
write_payload(..., mirror=not _mirror_is_full(rc, keys))   # read ..... then write
```

On two web dynos with no lock between them, this ordering is legal:

```
partial worker   GET mirror -> absent / partial, decides "publish"
full  worker                    SETEX primary + SETEX mirror = FULL
partial worker   SETEX mirror ------------------------------> PARTIAL over the full
```

The mirror is then partial for a full 24 hours — the exact downgrade the guard was written to
prevent, arrived at without anything going wrong.

**Why the suite missed it.** All seven mirror guards in section 5 drive a single worker, so
they can only construct *sequential* orderings: full-then-partial, partial-then-partial. There
is no ordering a one-worker test can write in which the value changes *between* a read and the
write that depends on it. The hole was not a missing assertion about a case the tests knew
about; it was a whole class of schedule the harness could not express.

---

## 3. The fix — the same lesson the module had already learned once

`event_concept_cache.py` already contained a compare-and-delete Lua primitive, and its comment
already stated this exact principle:

> *"`am I the holder?` and `delete it` are one atomic step — a plain GET-then-DELETE is the same
> check-then-act race this primitive exists to close."*

So the remedy is not an invention, it is an application. Three changes:

**`read_slot_raw(rc, key) -> (raw, payload)`** — `read_slot`'s verdict plus the exact bytes it
judged, from ONE read. `read_slot` is now a one-line wrapper over it, so the payload a reader
accepts and the payload a conditional writer judges cannot drift.

**`setex_if_unchanged(rc, key, expected, ttl, value)`** — a Lua compare-and-set. `expected=None`
means "only while the key is still absent", carried in its own `ARGV` rather than an in-band
sentinel. Fails **closed**, exactly like `release_refresh_lock`: if the CAS cannot run, the
stored value is left alone.

```lua
local current = redis.call('get', KEYS[1])
if ARGV[1] == '1' then
    if current then return 0 end
elseif current ~= ARGV[2] then
    return 0
end
redis.call('setex', KEYS[1], ARGV[3], ARGV[4])
return 1
```

**The caller takes both halves from one observation.** `_stored_mirror()` returns
`(bytes, is_full)`; the primary is written unconditionally and first (it is what ends the
rebuild loop and is uncontested), and the mirror is settled separately by a CAS anchored to the
very bytes the decision was taken on.

### Why the precondition is BYTES and not "is it still full"

Comparing stored bytes needs no knowledge of the payload codec, so the Lua can never drift from
`encode_payload`. And *"nothing changed since I looked"* is strictly **stronger** than *"it is
still not full"*: it also declines to clobber a fresher *partial* written by someone else, which
is harmless. Every way this errs, it errs toward leaving the stored value alone.

`_mirror_is_full()` survives as the predicate alone, with a docstring that says a **writer** must
not use it — the answer can be false by the time it is acted on, and that is the whole defect.

---

## 4. Proof the new guards are not vacuous

A race guard that passes against the broken code proves nothing. The two interleaving guards
were run against the **true pre-fix source** (`git checkout --` of the route, i.e. the exact
bytes CERT-480 graded):

```
FAILED ... test_a_full_landing_mid_decision_survives_when_the_mirror_was_absent
FAILED ... test_a_full_landing_mid_decision_survives_over_a_stale_partial
3 failed, 79 passed
```

and against the fixed source: **86 passed**.

> ⚠️ **The first attempt at this check was itself vacuous, and that is worth recording.** The
> mutation initially left the new single-read call in place above the restored two-trip write.
> `_stored_mirror` consumed the injected race, so the second read saw the full mirror and
> correctly declined — 5 of 6 guards passed and the battery *looked* fine. A reproduction of
> "the old code" that keeps any part of the new code is not a reproduction. The tell was the
> same one LAT-P152 named: **the check agreed with me too easily.**

`_RacingRedis` injects the concurrent full build *inside* the mirror `GET` itself, exactly once,
and returns the pre-race value to the caller. Once only, so a fix cannot pass by re-reading in a
loop.

---

## 5. Gates

| gate | result |
|---|---|
| `test_prop_families_partial_lat_p145.py` | **86 passed** (59 inherited, all unchanged, + 27 new) |
| same suite vs pre-fix source | **3 failed** — the two race guards + the new helper |
| `prop_families_partial_mutations.py` | **27/27 killed**, 0 survived; both targets byte-identical after |
| `prop_families_cache_mutations.py` (inherited LAT-P138) | **29/29 killed**; all 4 targets byte-identical |
| `scan_mutation_residue.py` | **CLEAN** — 371 needles, 2,232 broad checks, 0 residual mutants |
| `ruff` | exit 0 |
| import smoke | `from app.main import app` OK |
| frontend | **not touched** — `git diff origin/master...program/latency-130 -- frontend/ ios/` is empty |

Six new mutants target the atomicity specifically: **M22** restores the two-round-trip
check-then-act, **M23** anchors the CAS to `None` instead of the judged bytes, **M24** collapses
the absent-key arm into the byte comparison, **M25** makes an unrunnable CAS report success,
**M26** hides unreadable bytes from the conditional write, **M27** deletes the Lua guard
entirely.

---

## 6. What these guards do NOT prove — stated, not buried

**The Lua body is pinned only by shape.** The test doubles dispatch on script *identity* and
re-implement Redis's semantics in Python, so they exercise the *contract*, never the Lua. A
semantic Lua edit is invisible to them. `TestTheLuaScriptItself` therefore asserts structure —
the key is read before it is written, both `return 0` arms precede the single `setex`, both
preconditions are present — which is enough to kill M27 but is **not** a proof of correctness.
A live-Redis integration test is the thing that would close this, and it does not exist.

**The race is closed, not the concurrency.** Nothing here serialises same-key cold builds; it
makes the loser of the race harmless. The `logger.info` on a declined publish is the only
observable footprint, and a flood of it would mean single-flighting has broken.

**#2320 must still NOT be closed on merge.** CERT-480's H5 and H1 are untouched by this repair:
the per-branch budget is 12,000 ms and there are three branches, so a pathological team page can
still occupy a worker for ~36 s, and the first read still goes 12.4 s → ~14.2 s. **P145-1 (the
request-level total budget) is what makes the first read acceptable and is not in this branch.**

**The first-read trade is unchanged and was graded defensible, not good.** CERT-480 accepted it:
~14.2 s with real content once, then ~30 ms, beats 12.4 s with no content forever. That
remains the argument, and 285 of 367 rostered teams are outside the warmer's reach, so for most
teams the first read is what most readers get.

---

## 7. Lane hygiene done in the same session

LAT-P152 observed that the Integrator's sweep
(`grep -l '^status: ready_for_integration' READY-latency-*.md`) returned nine files of which
seven named already-merged branches, and left the question open. Cleared: `LAT-P141`, `-P142`,
`-P143`, `-P146`, `-P147`, `-P148`, `-P151` now read `status: merged`, each verified **two
independent ways** — listed by `git branch --merged origin/master`, and an empty
`git diff origin/master...<branch>`. The tokens are annotated, not deleted; they are the
reports' own record. The sweep now returns exactly the two genuinely-unmerged branches
(`LAT-P145` → `-130`, `LAT-P152` → `-129`).
