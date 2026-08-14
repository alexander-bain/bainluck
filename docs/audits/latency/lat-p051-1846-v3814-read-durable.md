# LAT-P051 / #1846 — the v3814 read, made durable

**The debt as routed:** *"#1846 stays OPEN until the v3814 read exists as a durable issue comment
with a retained capture. A post-edited READY file is not its own oracle. Post it, then close
#1846."*

**State found, 2026-08-14 15:2x PDT — half of this was already discharged, and saying so is the
first honest step.**

| the debt | state |
|---|---|
| a durable issue comment carrying the v3814 read | ✅ **already existed** — posted on #1846 at `2026-08-14T19:41:32Z`, with the full three-row read table, the moved probe named, and acceptance graded box by box (including one box explicitly **left unticked**) |
| #1846 closed | ✅ **already closed** — `closedAt = 2026-08-14T19:41:33Z`, one second after that comment |
| a **retained capture** behind the numbers | ❌ **did not exist.** The handoff directory holds `ARTIFACT-LAT-P053-v3812-armed-control-r{1,2}.json` for the v3812 baseline and **nothing for v3814** |

So the C-PM audit's flag was right about the artifact and stale about the comment. The comment is
not a post-edited READY file — it is a timestamped, immutable-by-convention GitHub comment that
predates this window. What was missing is the capture, and a capture for **v3814 can never be
taken**: production is v3817, and Heroku releases are not re-servable.

**What is retained instead, and why it is worth more than a backfilled artifact would be:** an
independent re-read of the same 46 probes on **v3817**, with the capture kept. It cannot prove what
v3814 measured. It proves the thing anyone would actually want to know — that **#1846's fix is still
working in production, two deploys later, and did not quietly regress.**

---

## The v3817 re-read — retained

**Instrument, declared so it can be held constant next time:**

| | |
|---|---|
| producer | `backend/scripts/evals/search_results_producer.py`, git blob **`61de6598ef77ef543a4cab0dcb5cb81bdaba674b`** (master's copy; the same blob LAT-P056 used, *not* LAT-P051's `08265f0d`) |
| adapter | `typeahead-adapter/v2`, source `GET /api/events/typeahead` |
| registry / split | `backend/scripts/evals/search_gold_probes.json`, `--split test`, `--mode entity_top_1` |
| pacing | `--sleep 1.5` (public rate limit is 60/min) |
| target | v3817, `/api/health` `commit=f6dc46ca` |
| taken | 2026-08-14 ~15:38 PDT (22:38 UTC) |

**Result:**

```
total 46 · measured 46 · unmeasured 0 · coverage 1.0
fetch_ok 46 · fetch_failed 0 · evidence_fidelity "exact"

entity_top_1_rate     0.8478260869565217      (39/46 scored → 39/44 excluding 2 xfail)
mean_reciprocal_rank  0.8913043478260869
lifecycle_counts      {pass 39, fail 5, xfail 2, xpass 0, regression 0}
```

**Byte-identical to the v3814 read and to LAT-P056's `da5e7992` read.** `origin/master` moved
`da5e7992 → f6dc46ca` between them, so this is also a clean **0-of-46 control** on that deploy.

**The probe this issue is about:**

```
search-gold-us-open-001   query_class ambiguity
  code PASS · disposition pass · reciprocal_rank 1.0
  actual_top  concept:event:tennis:2026-women-s-us-open-winner-tennis  (surface concept)
```

On v3806 this probe was `ENTITY_NOT_TOP / fail`, `rr 0.0`, top `market:114160`. It is `PASS` at
rank 1 on v3817. **#1846's fix is confirmed live by an independent instrument, not by the lane's own
account of itself.**

Retained files (SHA256 in `SHA256SUMS.txt`):

- `capture-lat-p051-gold-read-v3817.results.json` — the 46 fetched probe result sets
- `capture-lat-p051-gold-read-v3817.graded.json` — the scorer's full output, all 46 dispositions
- `gold-producer-v3817.log` — the producer run log

The 5 `fail` and 2 `xfail` probes are unchanged and pre-existing (`ai`, `hurricane`, `inflation`,
`nba finals`, `president`; xfail `fed`, `taylor swift wedding`). None is #1846's class.

---

## One thing the closing comment could not have known

#1846's acceptance box 1 — *"`tour de france` returns the cycling concept from `/typeahead`"* — was
correctly left **unticked** because the specimen had expired (all 29 Tour de France markets are
`resolved`). LAT-P054 substituted the tennis specimen and declared the substitution. That was right.

This window substituted a **live cycling** specimen as well — `Vuelta a Espana 2026: Winner`, open
until 2026-09-20 — and it does **not** behave like tennis:

- `/api/events/search?q=vuelta a espana` → `event_concepts[0]` = **`event:cycling:vuelta-2026`**
- `/api/events/typeahead?q=vuelta a espana` → **no concept row**, under every phrasing tried
  (`vuelta`, `vuelta a espana`, `vuelta a espana 2026`)

Because it is absent under **every** phrasing — including the one that most exactly names the
concept — this is **not** #1846's provenance drop, which is phrasing-sensitive by construction and
which the `us open` control shows working at ranks 1–3. It reads as a **concept-pool discovery gap**:
the cycling concept is built on the `/search` path and is not built on the `/typeahead` path at all.

**#1846 stays closed.** Its mechanism — the blanket `_derived` flag — is measurably fixed. The
cycling gap is a different defect and is filed separately rather than smuggled back into a closed
issue.

Full detail and the raw captures: `lat-p049-search-deploy-checks-2026-08-14.md` in this directory.
