# Historical Backfill Heuristic — dry-run, attended-apply only (never unattended rewrites)

*For `discover_interactions.provenance` backfill. This artifact is the **classifier**; it is not the migration. Pre-column rows are NULL/unknown — this heuristic re-estimates which `unknown` are plausibly `warmer` / `sentinel` from the 89% / 23.6% fingerprints proven in search — and it runs only as a **dry-run report** (`--dry-run`) that an attended operator then applies explicitly (`--apply`).*

*Prompt requirement: use your own 89%/23.6% fingerprints as the classifier.*

---

## Fingerprints (provenance of the fingerprints themselves)

| Fingerprint | Source | Value | How measured |
|---|---|---|---|
| **Warmer echo** | `typeahead_warmer.py:116` `search:trending:24h` `/typeahead` writes on every typeahead | `~89%` warmer | Redis zset `search:trending:24h` is ~89% the warmer echoing its own writes, not users (#1916) |
| **Sentinel admixture** | `flow_sentinel.py:76` gold set `44` + `flow_sentinel` 6 flows × daily beat (search gold set, duplicate events, etc.) | `23.6%` sentinel | Query/search logs are `23.6%` sentinel traffic from the sentinel's own `GET /api/events/typeahead` / `/api/events/search` / `category_discover` reads — counted in the same logs that would be used for “real” distribution |

Both are **instrumentation that reads the store it then pollutes** — the canonical pre-training pollution shape: the instrumentation's taste is written as if it were the user's.

---

## What the heuristic does (and does not do)

* **Does:** re-estimate a legacy `unknown` row as `warmer / sentinel / admin / gold_session` **only when two independent signals agree** (time fingerprint + behavioral fingerprint). No single signal is enough — an unvalidated single-signal rewrite would impersonate the valuable class (silent-default lesson).
* **Does not:** ever write `user`. `unknown → user` is the one transition the heuristic is forbidden to infer (the same silent-default lesson as the live column: absence must not impersonate `user`). `unknown` stays `unknown` unless the census says “this slice is 89% cleaner as warmer.”
* **Does not run unattended.** The migration that adds the column (`add_disc_interactions_provenance.py`) sets every existing row to `unknown`. This heuristic produces a **report**; the operator then runs `--apply` with an explicit allowlist of provenance values, and the apply is bounded (`--limit`).

---

## Classifier — two-signal rule per provenance

A legacy `unknown` row is re-estimated as:

| Provenance | Time fingerprint (89%/23.6%) | Behavioral fingerprint | Both needed? |
|---|---|---|---|
| `warmer` | `created_at` within ±60s of a `typeahead_warmer` beat (30s cadence, `typeahead_warmer.py:30s`), and `source` is `scored_query`/`typeahead` or action is high-rate burst lacking `session_id`/`user_id` | High-rate `impression` bursts with identical `session_id` lacking entropy, or `source` literal `warmer`/`typeahead_warmer`, or `surface != web` with bot UA | **Yes** — burst timing + bulk-source pattern. A lone high-rate row is not enough; a lone `warmer`-named source at a non-beat time is not enough. |
| `sentinel` | `created_at` within ±120s of the `flow_sentinel` daily window (07:10 UTC ± jitter, plus canary mode `canary=True` synthetic `CANARY_QUERY = "zzqx nonexistent sentinel canary entity 99"` `flow_sentinel.py:113`) or `calibration_sentinel`/`grid_sentinel` beats | `item_id` is a sentinel gold-set entity ID (one of the 44, or `zzqx…` canary), or query `q` is one of the sentinel's 44 `typeahead` probes (e.g., `super bowl`, `british open` where the sentinel is known to probe), measured as `gold_set_regressions`/`transport` path (`flow_sentinel.py:247:269`) | **Yes** — beat window + gold-probe query/entity. Sentinel probes real user query strings, so time alone would alias real `super bowl` traffic. |
| `gold_session` | `created_at` within a `gold_session` labeling window (Alex's 250 labels are batched; session spans are bounded hours, not all day) and `source` is `gold_session` / `admin_label_pass` | Action is `detail_click`/`like`/`group_expand` on a sampled candidate whose `candidate_snapshot_id` joins `discover_candidate_snapshots` (the labeling sampler's snapshot) — proves the row came from a sampler, not the live feed | **Yes** — both. |
| `admin` | `created_at` during an `ADMIN_TOKEN`-bearing request window (admin tools / `GET /api/feed` with `Authorization: Bearer $ADMIN_TOKEN`) | `user_id` is an admin user or `session_id` is `admin-*` or `source=admin` | Either — admin leaves an authenticated trace. |
| `unknown` (stay) | Default — no two signals agreed | — | — |

`user` is **never** produced by the heuristic.

---

## Dry-run report shape (read the report, do not apply it)

```json
{
  "dry_run": true,
  "legacy_unknown": 12345,
  "estimates": {
    "warmer": {"n": 8234, "pct": 66.7, "evidence": "burst at :00/:30 beat + source typeahead"},
    "sentinel": {"n": 2341, "pct": 19.0, "evidence": "gold probe q at sentinel window"},
    "gold_session": {"n": 112, "pct": 0.9, "evidence": "gold_session source + snapshot join"},
    "admin": {"n": 89, "pct": 0.7, "evidence": "admin Bearer window"},
    "remain_unknown": {"n": 1569, "pct": 12.7, "evidence": "no two-signal agreement, leave unknown"}
  },
  "invariants": {
    "unknown_to_user": 0,
    "single_signal_quarantined": 412
  }
}
```

`single_signal_quarantined` is the count whose one signal fired but the second did not — kept as `unknown`, not guessed.

---

## Attended-apply pattern (the live run)

```bash
# 1. Dry-run — produces artifacts/provenance/BACKFILL_REPORT.json, no writes:
python backend/scripts/backfill_provenance.py --dry-run --since 30d > artifacts/provenance/BACKFILL_REPORT.json

# 2. Attended operator reads the report, chooses allowlist (never includes user):
python backend/scripts/backfill_provenance.py --apply --only warmer --limit 10000
python backend/scripts/backfill_provenance.py --apply --only sentinel --limit 10000
# Each --apply is bounded and logged; the gate is the operator, not the cron.
```

Never `python ... --apply --all` unattended. Each provenance is applied as its own bounded, logged pass so a mis-estimated slice is rolled back by slice.

---

## Why two signals, and why not unattended

The **single-signal precedents** in this repo that went wrong are the exact shape this re-does: `repr(frozenset)` bare f-string on a fingerprint gave every worker a different digest (gotcha #127 CAL-P045) — one signal (the value) was not enough, the negative-control second signal was what made it meaningful; Ruling 048's earlier thresholds tuned by one signal and each remade the duplicate/absorption trade into a new specimen class. The attended-apply is the same lesson as `#1091` caps — an unattended heuristic that moves a class at scale deserves the same scrutiny as the model it feeds.

---

## Provenance of this artifact

Classifier fingerprints: `flow_sentinel.py:76/113/247` (gold set 44, canary `zzqx…`) and `typeahead_warmer.py:24/283` (warm, trending zset). The attended-apply shape mirrors `scripts/backfill_provenance.py`'s dry-run/apply split already used for the calibration curve's capture-age backfill. The `unknown→never user` prohibition mirrors `DiscoverInteraction.provenance` default `unknown` and the migration's `NULL→unknown`.

