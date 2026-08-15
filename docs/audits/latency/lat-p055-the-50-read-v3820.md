# LAT-P055's pre-registered read, taken — and the null held EXACTLY

**Owed for four windows.** `-50` never deployed, so the read could never be taken; each declining
window emitted a receipt rather than an argument (ruling 066). The exit condition fired this
window: `-48`, `-49` and `-50` all merged and deployed as Heroku **v3820 / `cabc791a`**.

**Taken:** 2026-08-14, ~17:46–17:55 PDT, production **v3820 / `cabc791a`** (verified against
`GET /api/health` → `{"commit":"cabc791a"}`, never assumed from `heroku releases`).
**Method:** unchanged and not re-derived. Producer blob pinned at
**`61de6598ef77ef543a4cab0dcb5cb81bdaba674b`** — the exact blob the queue required.

---

## 1. The prediction, as registered

> **39/44, MRR 0.8913043478260869, 0 of 46 dispositions differing. Any movement HALTS.**

Declared null under rulings 050 (a null read is still a read, and must be taken) and 064 (measured
on its own deploy, read against a control ARMED before the change shipped).

## 2. The result

| | predicted | **measured on v3820** | |
|---|---|---|---|
| probes graded | 46 | **46** | ✅ |
| `pass` | 39 | **39** | ✅ |
| `fail` | 5 | **5** | ✅ |
| `xfail` / `xpass` | 2 / 0 | **2 / 0** | ✅ |
| `regression` | 0 | **0** | ✅ |
| `entity_top_1_rate` | 0.8478260869565217 | **0.8478260869565217** | ✅ |
| MRR | 0.8913043478260869 | **0.8913043478260869** | ✅ exact to 16 digits |
| coverage / `unmeasured` | 1.0 / 0 | **1.0 / 0** | ✅ |
| `fetch_ok` / `fetch_failed` | — | **46 / 0** | ✅ |
| `evidence_fidelity` | `exact` | **`exact`** | ✅ |

**Per-probe, against the retained v3817 capture** (`capture-lat-p051-gold-read-v3817.graded.json`,
held on `program/latency-52`):

```
probe sets identical      : True (46 / 46)
DISPOSITIONS DIFFERING    : 0
actual_top DIFFERING      : 0
```

Not merely the aggregate — **every one of the 46 top-1 answers is identical across two genuinely
distinct captures, on two different deploys, taken four hours apart.** That is the strongest form
the null can take, and it is the third clean firing of the armed control (ruling 064's doctrine).

Captures retained and hashed: `capture-lat-p055-gold-read-v3820.results.json` (13k lines of raw
ranked rows) and `.graded.json`, plus `gold-producer-v3820.log`. See `SHA256SUMS.txt`.

## 3. What this read can and cannot attribute — stated, not glossed

⚠️ **`-50` did not deploy alone.** v3817 → v3820 carries **three** merged branches, not one:

| branch | what it ships | ranking surface |
|---|---|---|
| `-48` | the outcome-evidence canary probe class (#1861) | registry/eval only |
| `-49` | LAT-P053's three real-Postgres `search-recall` cases | tests only |
| `-50` | `?debug_timing=1` on `/typeahead` | a debug parameter |

So ruling 046 — *a stacked change is measured on its own deploy* — was **overtaken by events**: the
deploy that carried `-50` also carried two siblings, and `-50`'s solo read is now unobtainable. It
cannot be re-taken; that is recorded rather than worked around.

**What the read does support.** The null is graded over the BUNDLE, and the bundle moved nothing.
Since no probe's disposition and no probe's `actual_top` changed, no member of the bundle changed
any of them either — the only escape is exact mutual cancellation across three independent changes
on all 46 probes simultaneously, which is not a credible reading of 46 byte-identical top-1 strings.

**What it does not support.** A claim that `-50` was measured in isolation. It was not, and nothing
in this program should later cite it as though it had been.

## 4. Grader exit code

`search_gold_eval.py` returned **1**, which is correct and expected: the grader exits non-zero
whenever `entity_top_1_rate < 1.0`, and the set has 5 known `fail` probes plus 2 `xfail`. Exit 1
here means "Search is not perfect", not "the run broke" — `unmeasured = 0` and `coverage = 1.0` are
the fields that say the run was sound (LAT-P029's three-state separation, gotcha #53's lesson
applied to a grader).

## 5. Still owed after this window

**Item 1 — the `-51` warmer read. BLOCKED, with a receipt (ruling 066).** Not an argument that it
should wait; the machine-checkable fact that it must:

```
git cherry origin/master program/latency-51 | grep -c '^+'   ->  5
curl -s "$BAINLUCK_API/api/health"                           ->  {"commit":"cabc791a", ...}
```

Five commits unmerged, and the deployed commit is master. The warmer is not running in production,
so `excluded_pre_warmed`, the segment pin and the tail control are all unmeasurable. Exit condition:
`-51` merges and deploys. Its full criteria are preserved verbatim in
`PROGRAM-LATENCY-NEXT.consumed-P057-self-staged.md` and are unchanged.
