# LAT-P064 §G — the gold read, THIRD window owed, TAKEN — and ruling 073's attribution branch fires for the first time

**Taken:** 2026-08-17, latency lane cycle 36, against deployed **`5542f8c4`** (**v3836**, released
23:44:10 UTC, settled ~39 min at capture).
**Artifacts:** `capture-lat-p064-gold-read-v3836.results.json` (raw),
`capture-lat-p064-gold-read-v3836.graded.json` (graded), `gold-producer-v3836.txt` (fidelity header).
**Compared against:** `capture-lat-p062-gold-read-v3829.graded.json`.

---

## §G1 — Verdict

**Producer:** 46 probes, `fetch_ok: 46`, `fetch_failed: 0`, `evidence_fidelity: "exact"`,
`adapter_version: typeahead-adapter/v2`. No degraded capture.

**Grader exit code `2`. That is a RESULT, not a harness failure** — `search_gold_eval.py:603`
returns 2 specifically for CORPUS-MOVED, distinct from `1` (a real failing disposition) and `0`
(clean). Checked in the source before reading it, per gotcha #54's amendment.

```
CORPUS-MOVED: 1 disposition change(s) quarantined; the banked baseline does NOT move.
Re-baseline explicitly, naming the expired specimens.
```

| | LAT-P062 (v3829) | LAT-P064 (v3836) |
|---|---|---|
| `entity_top_1_rate` | **0.9130434782608695** | 0.8913043478260869 |
| `mean_reciprocal_rank` | **0.9347826086956522** | 0.9021739130434783 |
| lifecycle | 41 / 3 / 1 / 1 / **0** | 40 / 4 / 1 / 1 / **0** |
| coverage | 46/46 | 46/46 |

**`regression: 0`. The banked baseline stays at 41/3/1/1/0 and 0.9130434782608695 /
0.9347826086956522** — `baseline_may_move: false`.

## §G2 — This is the first paired read in which the attribution branch was actually exercised

LAT-P062 took ruling 073's first paired read and reported `changed: 0`, stating plainly that the
attribution branch had therefore **never run**. It has now.

```json
{
  "code_changed": false, "changed": 1,
  "real": 0, "corpus_moved": 1, "confounded": 0, "unattributable": 0,
  "baseline_may_move": false,
  "changes": [{
    "probe_key": "search-gold-2026-nba-champion-001",
    "verdict": "CORPUS-MOVED", "before": "pass", "after": "fail",
    "pool_size_before": 3, "pool_size_after": 2,
    "expected_eligible_before": true, "expected_eligible_after": false,
    "left_pool": ["market:350"], "entered_pool": [],
    "top_before": "market:350", "top_after": "market:52755817"
  }]
}
```

**`--code-changed` was NOT passed, and that was a decision, not a default.** The deployed commit
moved `1eb968ee` → `5542f8c4` across five releases, so the question had to be answered rather than
assumed. Diffed: the only search-adjacent file touched is `app/tasks/typeahead_warmer.py`, and its
change is LAT-P062's cadence/floor work (`MIN_PASS_PERIOD_SECONDS`, the last-pass Redis key) — it
governs **when the cache is warmed, not what order results come back in**. No ranking code changed,
so a moved disposition is a corpus event and is quarantined. That is the correct branch.

**Confirmed independently, so the classification is not taken on the tool's word:**

```sql
SELECT id, name, status FROM futures_markets WHERE id = 350
-- 350 | "2026 Pro Basketball Champion" | resolved
```

The expected market **resolved**. It did not get out-ranked; it stopped being an eligible answer.
`left_pool: ["market:350"]`, `entered_pool: []`, and `expected_eligible_after: false` all say the
same thing, and the database agrees.

## §G3 — What this means, said carefully

**Search did not get worse.** 41 of the 46 top-1 answers are unchanged, `regression: 0`, and the one
lost pass is a specimen whose correct answer expired out of the world. The headline rate falling
0.9130 → 0.8913 is **arithmetic on a shrinking corpus**, and the whole point of ruling 073 is that
this must not be allowed to move a banked bar.

**The re-baseline is OWED and deliberately NOT taken here.** The tool's own instruction is *"re-baseline
explicitly, naming the expired specimens"* — explicitly, by someone who has looked at the specimen and
decided what should replace it. `search-gold-2026-nba-champion-001` needs either a live successor
question (the 2027 champion market) or removal from the `test` split with a note. Doing that silently
inside a latency window, at the end of a window, would be exactly the quiet re-baseline the ruling
exists to prevent.

**Registered for whoever re-baselines:** the corpus will keep doing this. A gold set of dated
championship questions expires on a schedule the sport sets, and four more of these probes are
season-shaped. Consider whether the `test` split should prefer questions with rolling successors
over dated ones — that is a corpus-design question, not a ranking one, and it belongs to #993.
