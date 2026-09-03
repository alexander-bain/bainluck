# CAL-P989 post-merge runbook — the catch-up, the sync, and the after-needle

Written BEFORE the token lands so the sequence is not improvised at deploy time.
Nothing here has been executed. `futures_markets.expiration_time` does not exist on
production yet, so step 0 is not optional — it is the thing that makes the rest possible.

## Preconditions, all three, in this order

1. `CERT-768` banked **GREEN — TOKEN GRANTED** in `CODEX-CERT-LOG.md` for
   `048389a854b555d9eb68c3afa42d95e722db9825`. A cert id is not a verdict:

       grep 048389a8 ~/bainluck/.claude/handoff/CODEX-CERT-LOG.md | grep -q 'TOKEN GRANTED'

2. Integrator merges and pushes master under `.claude/handoff/LANE-integrator.lock`
   (ruling 017). **This lane does not push master.**
3. Heroku release runs the migration. Confirm the column actually exists before
   running anything else — the release phase can succeed while an earlier failure
   leaves the head un-upgraded:

       SELECT column_name FROM information_schema.columns
       WHERE table_name='futures_markets' AND column_name='expiration_time'

   Expect exactly one row. Zero rows means STOP: the catch-up would select the whole
   population on a NULL predicate that is NULL for a different reason.

## Step 1 — dry run, small, and READ IT

    heroku run:detached -a bainluck -- \
      python3 backend/scripts/backfill_kalshi_resolution_window.py --limit 200

Non-detached `heroku run` silently no-ops in this sandbox (gotcha #48) — use
`run:detached` and verify side effects ~60s later. Never trust the empty stdout.

What the report must show before anything is applied:

| field | what a healthy first run looks like | what it means if it doesn't |
|---|---|---|
| `eligible_total` | thousands | 0 ⇒ the migration did not run, or the column is already populated |
| `excluded_purged` | a large minority | equal to `eligible_total` ⇒ the recoverable population is exhausted |
| `candidates` | 200 | 0 ⇒ read `zero_yield_reason`, do not re-run blindly |
| `writes_prepared` | most of `candidates` | 0 ⇒ ZERO YIELD; a 200-with-no-markets is the retention cliff wearing the shape of "no such event" (gotcha #53) |
| `newly_past` | the number that matters | this is the count of cards that stop reading as live |
| `batch_fully_unresolvable` | absent | present ⇒ advance `--offset`, do not re-run into the same stuck prefix |

`newly_past_samples` names up to 15 rows with was/now dates. Spot-check two against
the venue by hand before applying to thousands.

## Step 2 — apply, in bounded batches, tier-first

    ... --limit 500 --apply --out /tmp/p989-apply-1.json

Tier 1–2 first is deliberate: it is the order that retires Discover page-one dead
cards fastest. Re-run until `candidates` reaches 0 or `excluded_purged` accounts for
the remainder. **A written row leaves the population** (`expiration_time IS NULL` is
the durable progress marker), so the sweep converges — that is guarded by
`test_an_already_repaired_row_is_not_reselected`.

The script writes ONLY `resolution_date`, `expiration_time`, `updated_at`. Not
`status`, not `is_winner`. A wrong date and a wrong grade are different defects and
moving both at once is how #1852 happened.

## Step 3 — the settlement sync over the newly-visible population

#1818's repair (`status != 'resolved' AND past resolution_date`) needs no code change
— it was correct code fed a wrong date. Once step 2 lands, the population it can see
grows from **3** to whatever the backfill moved into the past. Re-measure first,
then let `_backfill_from_settled_events` run its ordinary cadence and check it drains.

## Step 4 — the after-needle, both halves

**DB half** — re-run the exact before-queries in `before-needle.json`:

    -- was 9,938
    SELECT count(*) FROM futures_markets
    WHERE source='kalshi' AND status='open' AND external_id LIKE 'KX%'
      AND resolution_date > now();
    -- was 3
    SELECT count(*) FROM futures_markets
    WHERE source='kalshi' AND status <> 'resolved' AND resolution_date < now();

**Surface half** — the one that is actually the ship. `GET /api/feed?limit=20`, count
the Kalshi cards, check each against the venue, and LOOK-screenshot page one.

    ~/bainluck/tools/look.sh https://bainluck.com/ /tmp/p989-after-pageone.png

Expected: `KXWTA-26MONTER` gone. **The FRESH needle does not reach 0**, and the report
must not claim it does — `KXIPHONERELEASE-IPHONE18` is partially finalized with
`max(close_time)` in 2027, so no date field reaches it. Report the number that moved
and name the one that didn't.

## What stays open after all four steps

- **#2644** — tier-1 futures publish the backstop in both slots; only
  `expected_expiration_time` carries the real date. Separate ship, separate hazard
  (13 markets where "expected" is LATER than what we store).
- **#1818, the last 20%** — 10 of 49 sampled events finalized *early*, so close_time
  is still in the future for them. Only venue status reaches those.
- **Polymarket** — same shape, untouched. Two of the four dead Sabalenka cards are
  Polymarket.
- **Venue-unresolvable rows inside the floor** — they keep their slot across runs
  because this script may not write `status`. `--offset` is the operator's lever.
