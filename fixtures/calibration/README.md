# Shared calibration fixtures — language-neutral, one copy

These files belong to neither client. They live at the repo root, outside `frontend/` and `ios/`,
because both surfaces are graded against them and a fixture that lives inside one client's tree
inevitably becomes that client's fixture with a copy taken by the other.

## Why this directory exists (#1643, codex C236)

`frontend/e2e/contract/calibrationSurfaceParity.contract.test.js` was a **vacuous gate**. The test
named *"the native fixture records the same production response web's fixture does"* opened the
native fixture and compared it against constants declared beside it in the same file. It never
opened web's fixture, never ran web code, and never read a web-computed value. Both clients could
disagree completely while it stayed green — and it was cited as coverage for calibration exit-exam
item 5.

The root cause was structural, not a missing assertion: the same 68-row production payload existed
as **two hand-maintained copies** in two languages, and there was no artifact either client could be
held against. Two copies cannot be compared by a test that only has one of them.

## The files

| File | What it is |
|------|-----------|
| `prod-2026-08-02.json` | The 2026-08-02 production `/api/calibration` response, losslessly compacted to 68 rows. The single authoritative copy. |
| `parity-record-2026-08-02.json` | The complete parity record both surfaces must reproduce from that payload, for **both** cohort-toggle states. |

### `prod-2026-08-02.json`

Frozen deliberately. It is a record of one real server response, not a live feed; regenerating it
whenever production moves destroys the only thing it is for.

The compaction is lossless for everything asserted against it. The live payload is 1,606 buckets
keyed by `(source, category, price_moved, bucket_idx)`, and every non-per-category metric is a sum
of `n` / `winners` / `sum_prob` / `sum_sq_err` into `bucket_idx` bins, so pre-summing the category
dimension away leaves those numbers bit-identical at 68 rows.

**What it therefore CANNOT prove**, stated so nobody reads more into it: `category` reads `"agg"` on
every row, so the per-category rollup and the sample gate are out of its reach. Those are covered by
the synthetic fixtures in `CalibrationSurfaceTests` and `calibrationMatchedBuckets.test.ts`.

### `parity-record-2026-08-02.json`

The record is what makes a cross-language comparison possible at all. Native's figures can only be
computed by running Swift and web's only by running TypeScript, so the two can never meet inside one
process. They meet here instead: each side asserts, in its own language and its own test runner,
that it reproduces this record exactly.

Neither client can drift without going red, and changing the record to match a drifted client turns
the *other* client red. That is the property the old gate did not have.

`ece`, `mce` and `brier` are compared with a 1e-6 tolerance — they are floating point crossing a
language boundary, and pinning bit patterns would make an FP-ordering change look like a parity
failure, which is how gates get deleted.

## Who reads these, and what each one proves

| Reader | Language | What it asserts |
|--------|----------|-----------------|
| `frontend/__tests__/lib/calibrationSurfaceParity.test.ts` | TypeScript (jest, a deploy gate) | `buildCalibrationParity()` — the **production** function the page renders from — reproduces the record on both cohort states |
| `ios/Bain Luck/BainLuckTests/CalibrationParityTests.swift` | Swift (xcodebuild) | The real `CalibrationViewModel.parity` reproduces the record on both cohort states |
| `frontend/e2e/contract/calibrationSurfaceParity.contract.test.js` | Plain JS (`node --test`) | Recomputes the record from the payload with its **own independent arithmetic**, and asserts both clients are still bound to it |
| `frontend/__tests__/lib/calibrationProdFixture.ts` | TypeScript | Re-exports the payload; web has no second copy |

## The one copy that remains, and why

`ios/Bain Luck/BainLuckTests/CalibrationProdFixture.swift` still embeds the payload as a Swift
string literal rather than reading this JSON off disk. That is deliberate: an XCTest reading a
`#filePath`-relative file is host-filesystem-dependent, and trading a verifiable duplicate for an
unverifiable load path is a bad trade.

So the duplicate is **checked instead of hoped**: the contract test parses both the Swift embed and
this JSON and asserts they are deeply equal. A drifted copy fails loudly and by name. If the iOS
test target ever gains a resource bundle, the embed can be deleted and that check with it.

## Regenerating

Don't, for `prod-2026-08-02.json` — see above. If a NEW frozen response is ever needed, add it
alongside under its own date and migrate readers deliberately; do not edit this one in place.

The record is derived from the payload by four independent implementations that agree
(`CalibrationMath` in Swift, `calibrationParity.ts` in TypeScript, the contract test's own JS, and
the Python that first produced it). If you change a metric definition, the record changes and all
four go red together — which is the intended cost of changing what a published number means.
