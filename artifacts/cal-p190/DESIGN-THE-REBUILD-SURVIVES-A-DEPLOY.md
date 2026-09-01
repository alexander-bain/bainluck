# CAL-P190 (#1978, #2052) — DESIGN: the staged rebuild survives a deploy

**Session:** CAL-P190, 2026-09-01, ~16:00–17:xxZ / ~09:00–10:xx am PT
**Lane:** calibration (build lane)
**Directive:** `runner-inbox/calibration/920-freeze-window-design-work.md` ITEM 1 (Fable-5, mtime
`09-01 08:58` PT) — *"DESIGN the durable fix: the staged rebuild must survive a deploy (persist
staged work / resume from checkpoint). Design + tests on a branch; DO NOT merge until after the
publish."*
**Branch:** `program/calibration-190-the-rebuild-survives-a-deploy` (off `origin/master` `35c50d48`)
**Shipped / deployed:** nothing. D-G's default freeze holds and was honoured.

**PILLAR: TRUTH. SHIP: the calibration page stops freezing for days at a time — a reader sees a
curve that reflects what we actually shipped, instead of one from before the last three fixes.**

---

## 0. THE ONE PARAGRAPH

The rebuild is wiped whenever `_main_input_fingerprint()` moves, and it moves on any edit to four
functions' *source text* — a proxy for "did the banked rows change" that is both too wide (it sees
comment and renderer edits) and too narrow (it cannot see its own callees, a hole this codebase has
now patched five separate times by hand). **I measured the proxy against the thing it stands for,
across every commit that touched the calibration SQL between 08-08 and 08-31 — 42 usable commits,
26 fingerprint moves — and the answer decomposes cleanly into three layers, each with its own
number.** 23% of the wipes changed no SQL at all. A further 35% changed the SQL but not the banked
row's *shape*. The remaining 42% changed the shape — and **five of those eleven, including all three
of the ships that froze the curve this week (RULE E, rank 1, and the CERT-647 disclosure repair),
were purely ADDITIVE to the SELECT list over an unchanged group key, verified by set-diff and not by
counting columns.** 🟢 **So a three-layer fix would have carried the bank through the entire current
outage.** 🔴 **And the honest converse: layer 1 alone buys 23% and layer 2 alone buys 58% — neither
is "the rebuild survives a deploy", and shipping either on its own and calling it that would be the
overstatement this design exists to avoid.**

---

## 1. THE MECHANISM, IN FOUR LINES OF PRODUCTION CODE

`app/utils/calibration_staged_futures.py:1633-1637`:

```python
if raw.get("input_fingerprint") != expected_input_fingerprint:
    # THE one that fires in practice. A deploy touching any SQL function in
    # ``_main_input_fingerprint`` lands here and costs every banked unit.
    return blank, INVALIDATE, REASON_INPUT_FINGERPRINT
```

`expected_input_fingerprint` is `_main_input_fingerprint()`
(`app/tasks/precompute_calibration.py:6514`), which hashes:

* `inspect.getsource()` of **four** functions — `compute_calibration_payload`,
  `_calibration_population_ctes`, `_virtual_market_ctes`, `_main_futures_sql`;
* **six** values — `CALIBRATION_POPULATION_VERSION`, `REPRESENTATIVE_TIE_AUTHORITY`,
  `COVERAGE_CENSUS_ENABLED`, `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`, `MEX_NORMALIZE_THRESHOLD`,
  `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS`.

Its own docstring records that list growing **five times**, each time because a value was
interpolated into the SQL but only the f-string *template* was hashed, or because a callee shaped
the statement and `inspect.getsource` "returns a function's own text, not its callees'". The
docstring calls this "the general rule this keeps re-teaching". **It keeps re-teaching it because
the digest hashes a proxy for the statement instead of the statement.**

### 1.1 What actually shapes a banked unit's rows — measured, not assumed

`precompute_calibration.py:4603` and `:4658-4670`:

```python
chunk_sql = text(sql_builder(frozen=True))          # sql_builder is _main_futures_sql
...
with runner.stage("read:futures_unit"):
    result = await db.execute(chunk_sql, {…roster params…})
    unit_rows = result.all()
```

**One statement, built once per beat, executed per unit.** The banked rows are a pure function of
that statement's text plus the roster params. `compute_calibration_payload`'s own source — the
largest and most-edited of the four hashed functions — is the CONSUMER of the folded accumulator,
not the producer of the rows. It is hashed anyway, and that is the single widest hole in the proxy.

🟢 **The emitted statement is deterministic across processes.** Four `PYTHONHASHSEED` values
(`0`, `1`, `12345`, `99991`), same digest `bbd9a0fa527b0471866714b3df8a0f15`, 81,990 chars. This is
load-bearing twice over: the design pins the text, and a `frozenset`/`set` interpolated unsorted
would have made *today's* fingerprint unstable across dynos too. Pinned by
`test_frozen_futures_sql_is_deterministic_across_processes` on this branch.

---

## 2. 🔴 THE MEASUREMENT — the proxy against the thing it stands for

**Method.** `git worktree add --detach`, checked out each of the 54 commits on `origin/master`
between 2026-08-01 and 2026-09-01 that touch `precompute_calibration.py`,
`calibration_staged_futures.py` or `calibration_coverage_bridge.py`, in chronological order, and at
each one computed three digests in-process:

| digest | what it is | what it stands for |
|---|---|---|
| `wide` | `_main_input_fingerprint()` | **what invalidates the bank today** |
| `sql` | `md5(_main_futures_sql(frozen=True))` | what actually shapes a banked unit's rows |
| `cols` | `md5(final SELECT list, comments stripped, whitespace collapsed)` | what shapes the banked row's **shape** |

**12 of the 54 are holes and are reported as holes, not as "no change"** — six pre-date
`_main_input_fingerprint` and six pre-date `_main_futures_sql` (both were introduced inside the
window). They break the chain, so no transition is scored across them. **42 usable commits, 26
transitions in which `wide` moved.**

### 2.1 The result

| class | n | share of the 26 wipes | absorbed by |
|---|--:|--:|---|
| `wide` moved, `sql` did **not** | **6** | **23%** | **layer 1** (narrow the digest) |
| `wide` + `sql` moved, `cols` did **not** | **9** | **35%** | **layer 2** (pin the statement) |
| `wide` + `sql` + `cols` all moved | **11** | **42%** | layer 3, **partially** — see §2.3 |
| *(nothing moved: 15 more transitions)* | 15 | — | — |

🟢 **`sql` moved while `wide` did not: ZERO, across all 42.** Narrowing the digest to the emitted
statement therefore **never loses a signal** in this corpus. That is the safety half of layer 1 and
it is the reason layer 1 can be shipped on its own.

### 2.2 The six that changed no SQL at all — layer 1's whole population

```
08-08 13:42  ebcc14f7  CAL-P012: publish the purged count, not just the tier
08-12 14:14  4a402f46  CAL-P045(a): the documented idiom for closing the fold
08-12 14:38  03665448  CAL-P045(d): the bump is ~80 seconds of darkness
08-18 10:30  5b00f4f8  CAL-P070: a count cannot say WHY it moved, so the gate asks
08-30 10:43  2472b7e8  CAL-P150 D21: the reader that turned a dead writer into a silent 96K
08-30 10:45  4ce014d3  CAL-P150 D22: a diagnostic that feeds nothing the gate reads
```

Every one is a payload / disclosure / diagnostic edit. **Six 26-hour rebuilds thrown away to publish
a count and rename a reader.**

### 2.3 🔴 The eleven that changed the row shape — and the five that matter

"Column count grew" is not "additive"; a change can add three and drop one. So the five most
load-bearing transitions were re-measured by **set-diff of the final SELECT's alias set**, not by
counting:

| transition | aliases added | aliases removed | additive? |
|---|---|---|:--:|
| `c845cb26 → 3432dd4f` (P156) | `ungraded_lone_claim_excluded`, `…_markets` | — | ✅ |
| `3432dd4f → 855b7569` (P156 revert of a dead rung) | — | those same two | 🔴 no |
| `855b7569 → 6be79cd0` **(P162, RULE E — ranks 2+3)** | `nxb_cell_0`, `nxb_cell_1`, `nxb_cell_esports` | — | ✅ |
| `6be79cd0 → f8126c8c` **(P168, rank 1)** | `player_props_placeholder_excluded`, `…_markets`, `pp_cell_0` | — | ✅ |
| `f8126c8c → 9f1aacc8` **(P170, CERT-647 disclosure repair)** | `player_props_placeholder_temporary_excluded`, `…_markets` | — | ✅ |

🟢 **And the group key never moved.** `bare = [bucket_idx, source, category, price_moved,
is_nonexclusive_bundle]` is byte-identical at all six commits. That is `GROUP_KEY_COLUMNS`, the key
the fold merges on — so an accumulator banked under any of these six is *joinable* by any of the
others. It is the precondition layer 3 needs and it holds.

**Consequence, stated as plainly as it deserves: the three deploys that froze the calibration page
for twenty-four sessions — P162, P168, P170 — are all purely additive over an unchanged group key.**
A design that tolerates an additive column change carries the bank through all three.

**Coverage, cumulative and honest:**

| ship | absorbs | cumulative |
|---|--:|--:|
| layer 1 alone | 6/26 | **23%** |
| layers 1+2 | 15/26 | **58%** |
| layers 1+2+3 | 20/26 | **77%** |

🔴 **The residual 6/26 (23%) MUST still wipe and the design must not pretend otherwise**: two
column *removals* and four same-count *redefinitions* (`CAL-P045(b)`, `CAL-P048(a)`, the
calibration-43 merge and its revert). A removed or redefined column means the banked value no longer
means what the consumer thinks it means. Wiping is correct there.

---

## 3. THE DESIGN — three layers, shippable in that order, each with its own gate

### Layer 1 — the staged cursor keys off the EMITTED STATEMENT, not four functions' source

Add, next to the other two digests and deliberately not merged with them (the same reasoning
`population_predicate_fingerprint`'s docstring already gives for staying narrower than
`_main_input_fingerprint`):

```python
def staged_unit_fingerprint() -> str:
    """The BYTES the staged units actually ran, in one digest.

    Not a proxy for the statement — the statement. `inspect.getsource` covers a
    function and never its callees, which is why the wide digest has had six
    values bolted onto it by hand, one incident at a time.
    """
    return input_fingerprint(
        md5(_main_futures_sql(frozen=True)),
        CALIBRATION_POPULATION_VERSION,       # see below — NOT in the statement
        REPRESENTATIVE_TIE_AUTHORITY,         # see below — NOT in the statement
    )
```

🔴 **Four of the six, not all six — measured, not assumed.** Each of the six hand-added values was
mutated and the emitted statement re-digested:

| value | mutating it moves the statement? | covered by |
|---|:--:|---|
| `COVERAGE_CENSUS_ENABLED` | ✅ | the statement digest, by construction |
| `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS` | ✅ | the statement digest, by construction |
| `MEX_NORMALIZE_THRESHOLD` | ✅ | the statement digest, by construction |
| `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS` | ✅ | the statement digest, by construction |
| `CALIBRATION_POPULATION_VERSION` | 🔴 **no** | **already its own branch** in `decode_staged_cursor` (`REASON_POPULATION_VERSION`) — needs nothing new |
| `REPRESENTATIVE_TIE_AUTHORITY` | 🔴 **no** | hashed explicitly. It does not shape a banked ROW; it is stamped on the published artifact, so it is a *disclosure* input |

So the four that are row-shaping become uncloseable holes rather than a list that grows by one per
incident, and the two that are not are named as declarations instead of being smuggled in beside
them. Pinned in **both** directions by
`test_which_fingerprint_inputs_the_emitted_statement_actually_covers` — a value that starts shaping
the SQL, or stops, reds the table rather than silently changing the coverage claim.

`decode_staged_cursor` compares against **this**; `decode_main_checkpoint` (carried *phase* outputs,
a different and much cheaper thing) keeps the wide digest.

🔴 **The cutover must cost ZERO wipes, and that is a real constraint, not a nicety.** Naively, the
first beat after this deploys finds a cursor stamped with the old wide digest, mismatches, and
throws away the bank — the exact harm the change exists to prevent, paid once. Avoid it by:

1. **not editing any of the four hashed functions**, so `_main_input_fingerprint()` computed by the
   new code equals the value already stored (verified by a pin, see §4);
2. accepting a cursor whose `input_fingerprint` equals **either** the new narrow digest **or** the
   legacy wide digest, recording `REASON_LEGACY_FINGERPRINT_ACCEPTED` when it is the latter;
3. re-stamping with the narrow digest on the next `save_staged_cursor`, so the compatibility branch
   is self-draining and can be deleted one generation later.

### Layer 2 — the generation PINS its statement; a deploy does not change the SQL a running rebuild runs

Store the emitted statement once per generation in its own durable row —
`calibration:main:pinned_sql:{digest}` — and carry only `pinned_sql_digest` in the cursor. 82 KB
written once per generation, not per beat.

Each beat then executes **the statement its generation pinned**, not the statement the current
deploy would emit. A digest mismatch stops being a wipe and becomes a recorded advisory on the
artifact: *this generation is building against the code as of `<sha>`*.

**The correctness invariant gets STRONGER, not weaker.** Today the guarantee is "every unit in a
payload was produced by code with the same digest". Pinned, it is "every unit in a payload was
produced by the same byte-identical statement". Digest equality is replaced by byte equality.

**The producer is pinned to the generation; the consumer is always current.** That separation is the
whole point, and it is what the wide digest conflates.

Three guards this needs, none optional:

* **Structural refusal.** The stored text must start with `WITH `, must contain the three roster
  bind params, and must not contain a DDL/DML verb. Stored SQL that fails any of these is refused
  with `REASON_PINNED_SQL_REFUSED`, not executed. (It came from our own code, but "came from our own
  code" is not a property the reader can check at read time; the checksum and the shape are.)
* **Checksum.** `sha256` stored beside the text and verified on read.
* **Schema drift.** A migration can invalidate a pinned statement (dropped column). On a *hard* SQL
  error — never on a statement timeout, which is the fence and is normal — invalidate the generation
  with `REASON_PINNED_SQL_INVALID`. That is today's behaviour, reached only when it is actually
  needed.

**Cost, stated up front:** the published curve can lag the deployed methodology by up to one
generation (~26 h). It must say so on the artifact. Given the page is currently **twenty-four
sessions** behind, this is a strict improvement — but it is a real change to what "published" means
and it belongs in the disclosure, not in a comment.

**Escape hatch:** an operator action that abandons the pinned generation and restarts. Deliberate,
named, and *not* the default — the default being "restart" is the defect.

### Layer 3 — an ADDITIVE census column does not discard the generation

🟢 **Most of this already exists.** `fold_unit_rows` runs an `UndeclaredColumnError` guard at bank
time against `DECLARED_CENSUS_COLUMNS` (`calibration_staged_futures.py:372`), which is a **mirror**
of the frozen module's declaration, pinned in both directions by a characterization test that reads
the frozen file as text. The shape contract is already explicit and already guarded.

What is missing is that the declaration is global rather than per-generation. That same docstring
states the assumption this layer replaces:

> *"A cursor therefore only ever sees ONE census set in its lifetime"*

— true only because the fingerprint invalidates. So:

* the generation's declared census set is **pinned into the cursor** alongside the SQL digest;
* at publish, the consumer computes `current_declared − generation_declared`. If that difference is
  **purely additive**, the payload is built with each missing column at its declared default and the
  artifact **names them**;
* if any column was **removed or redefined** — set difference in the other direction, or a changed
  digest for a retained column — invalidate, exactly as today, with
  `REASON_CENSUS_COLUMNS_INCOMPATIBLE`.

**The user-visible consequence of the additive branch is the good one.** On the P170 deploy, a
carried generation would have published the new curve with `temporary_excluded` absent; the page
already **gates** its temporary disclosure on `temporary_excluded > 0`, so the reader would have seen
the fresh curve *without* the new sentence, and the sentence one generation later. **A fresh curve
missing one bullet beats a 26-hour-stale curve with none of them.**

⚠️ **The one thing layer 3 must not do** is let an additive column be *silently* defaulted. A
defaulted census count is a zero, and a zero in a disclosure is a claim. It must appear on the
artifact by name, and the page must be able to tell "0 because none" from "0 because this
generation predates the column". That is the same trap CERT-647 blocked P168 for, and it fires here
in a new place.

---

## 4. THE TESTS — what is on this branch, and why these

Test-only; touches nothing under `app/`, so the fingerprint cannot move and the file is inert under
D-G. **Not merged**, per 920.

`backend/tests/test_staged_rebuild_survives_a_deploy.py`:

| test | what it protects | would it be vacuous? |
|---|---|---|
| `test_frozen_futures_sql_is_deterministic_across_processes` | layer 1 and layer 2 both pin TEXT; if the emitted statement varied by `PYTHONHASHSEED`, both are meaningless — **and today's fingerprint would be unstable across dynos**. Runs a real subprocess under four seeds. | no — it fails today if any interpolated `set` is ordered by hash |
| `test_which_fingerprint_inputs_the_emitted_statement_actually_covers` ×6 | §3 layer 1's coverage table. Mutates each of the six hand-added values and asserts whether the statement notices — **pinned in both directions**, so a value that becomes row-shaping, or stops being it, reds rather than silently moving the claim. | no — it is a mutation test, not an assertion about source text |
| `test_the_group_key_of_the_frozen_select_is_the_fold_key` | layer 3's precondition. The bare leading columns of the final SELECT must equal `GROUP_KEY_COLUMNS`. §2.3 measured this held across six commits; nothing pinned it. | no — it reads the emitted SQL, not a constant |
| `test_the_wide_fingerprint_is_unchanged_by_this_branch` | the §3 layer-1 cutover constraint, as a **live** pin: this branch must not move `_main_input_fingerprint()` away from the value production is currently running. | no — it compares against the digest measured live at `16:0xZ` |

🔴 **The fourth is a dated pin and it is deliberate.** It hard-codes
`e2040f90154fae876f0fb65f5abf74c3` — the fingerprint the live beat is running as of
2026-09-01 16:00Z, reproduced locally at this branch's HEAD. It will go red the moment anyone
legitimately changes the population, and **that is the point**: under D-G, a red here means someone
deployed calibration source during the freeze. It carries its own removal instruction. It is a
freeze-window instrument, not a permanent guard.

---

## 5. WHAT THIS DESIGN DOES NOT DO

* **It does not make the rebuild faster.** 128 units at ~5/beat is ~26 h and this changes none of it.
  P189 established that widening the unit fence cannot bank the ~2 cancelled units/beat — they
  consume the whole fence at every width tried. Separate problem, separate fix, still unsized.
* **It does not cover the residual 23%** (§2.3). A removed or redefined column still costs a
  rebuild, correctly.
* **It was not folded.** Every number in §2 is a static sweep over git history, measured this
  session; none of it is a live fold, and ruling 134 puts folds in the measurement lane.
* **The 26-commit corpus is one month of one lane's history.** It is the whole relevant population
  for the period, but a different month with fewer calibration ships would shift every share. The
  *classes* are the finding; the percentages are the period's.

---

## 6. PRE-REGISTERED, BEFORE ANY OF THIS SHIPS

1. **Layer 1 alone will absorb ~1 wipe per 4–5 calibration-source deploys.** Falsified if the first
   ten post-ship deploys that move `wide` all also move `sql`.
2. **The cutover costs zero banked units.** Falsified by a single `REASON_INPUT_FINGERPRINT` on the
   beat immediately after the layer-1 deploy. This is the one that must be watched, because getting
   it wrong costs exactly the thing the change is for.
3. **The group key will still be `(bucket_idx, source, category, price_moved,
   is_nonexclusive_bundle)`** when layer 3 ships. Falsified by the §4 guard going red for a reason
   other than a deliberate ruling.
4. 🔴 **The next purely-additive calibration ship after layer 3 will NOT reset `units_banked`.** That
   is the whole claim in one observable, and it is the one to grade.

---

## 7. THE BEAT LOG THIS SESSION BANKED (directive 920 ITEM 3)

| beat (UTC) | banked | attempts / completed / cancelled | worst completion | fence | binding term | publish gate |
|---|--:|---|--:|--:|---|---|
| `15:33:41` | 35 → **40** | 7 / 5 / 2 | 101,686 | **376,746** | beat-local (`101,686 × 4`) | **not evaluated** — `served_units 0`, cancelled before the gate |
| `16:32:11` | 40 → **45** | 7 / 5 / 2 | 68,314 | **353,754** | **seed** (`255,836 × 1.5`) | **not evaluated** — same |

🟢 **Both confirm CAL-P189's fence model; the second confirms it in a regime P189 never observed.**
At `15:33` the model predicted 376,744 and the ledger read **376,746 — a 2 ms miss**, with the two
cancellations at **+76** and **+105** over the fence. At `16:32` the beat's worst completion (68,314)
fell **below the 95,938 crossover**, the beat-local term dropped under the seed, and the fence
**returned to the 353,754 seed floor** — the first observation of it moving *down into* the floor
rather than up off it.

🔴 **Cumulative: nine cancellations, four fence levels spanning 66,420 ms, every death within 531 ms
of its own bound.** P189's conclusion is now confirmed rather than repeated: these units consume the
entire fence at every width tried, so **widening the unit bound cannot bank them.**

🆕 **The ring-entry-to-`unit_ms_worst` offset was 120 ms and 133 ms. P189's measured band was
56–130; it widens to 56–133.** Still the commit + cursor write, still structural, still bounded.

**Neither beat evaluated the publish gate** (`served_units 0` both times) — the beat cancels before
the gate, which is the `served_at_absent` mechanism CAL-P186/P188 already closed. **Nothing new, and
nothing to re-derive.**

**ETA `09-02T08:30–09:30Z`, confirmed an eighth time**: 45/128 at `16:32Z`, +5/beat dead steady
across eight readings, 122–127 completion band ⇒ ~16 beats.
