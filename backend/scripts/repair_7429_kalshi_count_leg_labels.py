"""#7429 — the historical cleanup: count markets stop reading `E48 · E49 · E50`.

THE SHIP: on `https://bainluck.com/futures/25923847` — "How many Senate seats
will Republicans hold after the Midterms?" — the rows and the chart legend read
`E45 … E57` instead of `45 … 57`. Every one of those is a question that asks
*how many*, answered with a ticker fragment. The same defect is on 148 other
Kalshi count events (House seats by state, redistricting, Knesset seats).

    PREVENTION SHIPPED FIRST — `_exact_count_label` (#7429, `f4d1e2b36` +
    `97c6052be`) is step 2 of `_kalshi_outcome_name`'s ladder and is live on
    the producer app: `bainluck-heavy` v60 = `704cdc47`, content-read
    `git show 704cdc47:backend/app/tasks/kalshi.py | grep -c _EXACT_COUNT_LEG_RE`
    = 2. This script is the owed DATA REPAIR for the rows written before it.

WHY A BACKFILL IS OWED AT ALL — the forward fix writes `name` on every upsert
(`update_set["name"] = outcome_name`), so it would drain these rows if the poll
reached them. It does not. `_poll_kalshi_markets` is a BOUNDED DISCOVERY SCAN:
Kalshi's listing is >28K events against a 240s fetch budget and a 480s upsert
deadline, and `_partition_new_events_first` deliberately defers EXISTING events
to the tail, where the deadline cuts them. That is #2199's measured starvation
("900 of 907 tier-1 high-value futures were price-dark, some for 32 days"),
named in `kalshi.py`'s own comment. The task built to cover existing rows —
`futures_price_refresh`, which addresses known markets BY ID and never
paginates — writes prices and has no name rail at all.

    🔴 AND THAT IS WHY `last_updated` IS NOT THE WITNESS. 74 of these rows
    carry a `last_updated` inside today's poll window and still read `E<n>`,
    which reads exactly like "the forward fix is broken". It is not: those
    stamps are `futures_price_refresh`'s `last_updated=func.now()`, written
    beside a price with `name` untouched. The banked control is what settles it
    — 114 rows at 10:58Z (pre-deploy), 114 at 13:05Z (deployed, pre-poll), 114
    at 14:51Z and 114 at 14:58Z (post-poll), `artifacts-lane1-497` and
    `artifacts-lane1-522`. A whole poll cycle moved nothing.

THE REPAIR IS NOT SELF-UNDOING, and that is worth stating because the sibling
rail in this same file is. `kalshi.py`'s `llm_sport_category` comment warns that
"a repair backfill run against still-open rows is self-undoing: the poll simply
re-guesses on top of it". Here the poll and the repair AGREE — both run
`_exact_count_label` over the same venue fields — so a row the poll later
reaches is rewritten to the value this script already wrote.

------------------------------------------------------------------------------
THE SELECTOR IS A CANDIDATE FINDER. IT IS NOT THE LOCK.
------------------------------------------------------------------------------

The obvious predicate — `name ~ '^E[0-9]+$' AND external_id ~ ('-'||name||'$')`
— looks like the two-signal corroboration `_exact_count_label` performs. It is
NOT, and mistaking it for one is the whole hazard of this repair. `external_id`
IS the ticker and `name` came FROM the ticker, so that second clause is
satisfied by construction for every ticker-derived `E<n>` label. It restates
the defect; it corroborates nothing.

The real lock is the venue saying the same number twice in two independently
authored fields — the `-E<n>` leg AND `yes_sub_title` — and `yes_sub_title` is
not a column we store. So this script cannot decide from our own tables, and it
does not try: it ASKS KALSHI for every candidate's market and pushes the
venue's own payload through the DEPLOYED `_exact_count_label`. Same function,
same `KalshiMarket` object the poll passes it, no reimplementation. A repair
that re-derives the predicate is a second copy that can disagree with the one
that ships.

Measured against the live venue 2026-09-20 ~15:5xZ, whole population of 252
candidate rows over 149 events, no sampling:

    venue corroborates  -> REPAIRED             127
    venue REFUSES       -> left alone             2
    venue is silent     -> left alone           123

So the naive selector would have rewritten 125 rows the venue does not stand
behind. The 2 refusals are the ones that matter, because they are the arm the
forward fix's cert could only kill mutants against:

    KXSPOTIFY2D-26MAR23-E85   yes_sub_title = 'E85'
    KXSPOTIFY2D-26MAR24-E85   yes_sub_title = 'E85'

Kalshi's own label for those legs IS the obfuscated string. `E85` on the screen
is what the venue said, and rewriting it to `85` would assert a number nobody
published. Those two rows are this repair's live proof that the second lock
refuses — a production specimen the forward fix never had.

The 123 silent rows are Spotify/Billboard chart events from March and April.
Kalshi purges MARKET data at >=74/<86 days (gotcha #35, `kalshi_retention.py`),
so the venue can no longer be asked. Uncorroborated is uncorroborated whatever
the reason: they stay as they are, and they are reported as `VENUE_SILENT`
rather than folded into the refusals, because "we could not ask" and "we asked
and the answer was no" are different facts (gotcha #53).

------------------------------------------------------------------------------
SAFETY
------------------------------------------------------------------------------

Under D51(b): `--backup` copies every in-scope row's current `name` into
`backup_7429_outcome_names` and `--apply` refuses unless the backup covers the
whole plan. The undo is one command:

        python3 scripts/restore_7429_kalshi_count_leg_labels.py --apply

Runtime DDL, attended invocation only — `CREATE TABLE IF NOT EXISTS backup_*`
behind `--backup`, on the named app, run by a person (notice 47(c)): nothing
here executes as a consequence of merge or release.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

#: `app.tasks.poll_kalshi_markets` is a member of `HEAVY_TASKS`, so the code
#: that writes these names is what is deployed to the heavy app, not the main
#: one. Re-derived here rather than copied from a sibling repair —
#: repair_6126's producer is `bainluck` because its writers are all absent from
#: that set, and the answer differs per population.
PRODUCER_APP = "bainluck-heavy"

BACKUP_TABLE = "backup_7429_outcome_names"

#: Pages of `/markets` to follow per event before giving up. See `_venue_labels`.
_MAX_PAGES = 10

#: Courtesy gap between events, and the 429 retry budget. See
#: `_venue_labels_paced` for why this lives here and not in `get_markets`.
_VENUE_GAP_S = 0.25
_VENUE_BACKOFF_S = 3.0
_VENUE_RETRIES = 4

#: Bound to the module so `_venue_labels_paced` can be handed a fake clock.
_asyncio_sleep = asyncio.sleep

#: A candidate is a Kalshi outcome whose stored name is a bare `E<n>` that its
#: own ticker ends with. Deliberately WIDE: it is the shape the defect wears,
#: and every one of these rows is then put to the venue. Narrowing it here
#: would silently drop rows the venue could have corroborated.
_CANDIDATES_SQL = """
SELECT o.id, o.name, o.external_id, m.external_id AS event_ticker
  FROM futures_outcomes o
  JOIN futures_markets m ON m.id = o.market_id
 WHERE m.source = 'kalshi'
   AND o.name ~ '^E[0-9]+$'
   AND o.external_id ~ ('-' || o.name || '$')
 ORDER BY m.external_id, o.external_id
"""


def forward_fix_refusal():
    """Why this deploy may not run the repair, or None if it may.

    repair_2871's lesson — never repair with the tap on — and like repair_6126
    this does not take the deploy on trust from a version string. It re-enacts
    BOTH arms of the defect in the interpreter that is about to write, using
    the real `KalshiMarket` type the poll hands the function:

      * a corroborated leg must come back as the bare number. If this fails the
        forward fix is not on this dyno, every new count market is still born
        broken, and repairing the old ones just hides a live producer.

      * an UNCORROBORATED leg must come back `None`. Without this control the
        check passes vacuously against a stub that returns the ticker leg for
        everything — which is precisely the wrong answer this repair exists to
        remove, and it would authorise rewriting all 252 rows.

    The refusal control is not hypothetical: it is `KXSPOTIFY2D-26MAR23-E85`'s
    real venue payload, `yes_sub_title = 'E85'`, verbatim.
    """
    from app.services.kalshi_api import KalshiMarket
    from app.tasks.kalshi import _exact_count_label

    corroborated = KalshiMarket(
        ticker="KXHOUSEWINSTATE-AZD-E3",
        event_ticker="KXHOUSEWINSTATE-AZD",
        title="How many House seats will Democrats win in Arizona?",
        yes_sub_title="3",
        status="active",
    )
    uncorroborated = KalshiMarket(
        ticker="KXSPOTIFY2D-26MAR23-E85",
        event_ticker="KXSPOTIFY2D-26MAR23",
        title="Spotify Top Song rank",
        yes_sub_title="E85",
        status="closed",
    )

    got = _exact_count_label(corroborated)
    if got != "3":
        return (
            "REFUSING: the deployed `_exact_count_label` returned "
            f"{got!r} for a corroborated leg, not '3'. The forward fix "
            "(#7429) is not live in this interpreter, so every new count "
            "market is still being born with a ticker-fragment label. Repair "
            "the producer first — the historical rows are the smaller half."
        )

    got = _exact_count_label(uncorroborated)
    if got is not None:
        return (
            "REFUSING: the deployed `_exact_count_label` returned "
            f"{got!r} for a leg the venue does NOT corroborate "
            "(yes_sub_title='E85'), not None. Its second signal is not "
            "holding, so this run would rewrite rows on the ticker alone and "
            "publish numbers Kalshi never said."
        )
    return None


def unreadable_refusal(args, unreadable, candidates):
    """Why this invocation may not WRITE given an incomplete venue read.

    Measured 2026-09-20 20:09Z, and this gate exists because of it: the probe
    fired 149 serial `/markets` reads in 11 seconds, Kalshi 429'd from about
    the fourth second on, and the run printed

        corroborated -> REPAIR      59
        refused      -> left alone  0
        silent       -> left alone  193

    which reads as "the venue has purged three quarters of this population".
    It had purged none of it. `RSENATESEATS-27` — the event this whole repair
    is NAMED for — was one of the 429s, so that plan would have written 59
    rows, left `/futures/25923847` reading `E45 … E57`, and reported success.
    Worse, both `E85` control legs 429'd too, so `refused` was 0: the one
    bucket that proves the corroboration lock is doing anything was empty, and
    an empty control cannot fail.

    So an unreadable event is not a smaller population, it is a BLIND SPOT,
    and the two are indistinguishable downstream (gotcha #53 — "it returned"
    is not "it worked"). The row-level reason was always recorded; it was
    folded into `silent` one line later and never surfaced. Fail closed.

    `--allow-unreadable` is the deliberate-partial escape hatch, because a
    genuinely dead event should not be able to block the whole repair forever.
    It is opt-in, it is printed, and it is never what a first run should need.
    """
    if not args.apply:
        return None
    if not unreadable:
        return None
    if args.allow_unreadable:
        return None

    events = sorted({tkr for _, tkr, _ in unreadable})
    return (
        f"REFUSING --apply: {len(unreadable)} of {candidates} candidate rows "
        f"({len(events)} events) could not be read from the venue at all. "
        "A row we could not ask about is not a row the venue declined — "
        "applying now writes a partial repair and reports it as a whole one. "
        "Re-run when the venue answers; pass --allow-unreadable to write the "
        "corroborated rows anyway and accept a partial. "
        f"First unreadable events: {', '.join(events[:5])}"
    )


def wrong_app_refusal(args):
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere. A write must happen on the
    producer's app, because that is the only place where `forward_fix_refusal`
    is inspecting the code that can re-mint these names.

    Unset means we are not on a dyno at all — a laptop pointed at the
    production database with whatever happens to be checked out, which is
    exactly the case this gate exists to stop, so it refuses too rather than
    falling through.
    """
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        "`app.tasks.poll_kalshi_markets` is in HEAVY_TASKS, so the writer of "
        f"these names is what is deployed to '{PRODUCER_APP}'. Run from "
        "anywhere else and the forward-fix check above passes against the "
        "wrong interpreter while the real producer keeps writing. Re-run with "
        f"`heroku run:detached -a {PRODUCER_APP}`."
    )


def classify(candidates, venue, label_fn):
    """Sort one event's candidate rows into the four outcomes.

    Pure, and lifted out of `run` on purpose: this is the only place the
    repair DECIDES anything, and a decision buried inside a coroutine that
    needs a database and the network is a decision no test can reach. The
    hazard this repair exists to avoid — writing on the selector's shape
    rather than the venue's word — lives here and nowhere else.

    `label_fn` is injected rather than imported so a test can substitute a
    stub and prove the refusal actually routes to `refused`. Production passes
    the deployed `_exact_count_label`; nothing else ever should.

    `candidates` is an iterable of `(id, name, ticker)`. `venue` maps ticker ->
    `KalshiMarket` for the legs the venue still serves.

    Four buckets, and the split between the last two is deliberate (gotcha
    #53): `refused` is "we asked and the venue's answer was no", `silent` is
    "we could not ask". Both leave the row alone, but only the first is
    evidence about the venue.
    """
    plan, refused, silent, already = [], [], [], []
    for oid, name, ticker in candidates:
        market = venue.get(ticker)
        if market is None:
            silent.append((oid, ticker, "not_served"))
            continue
        label = label_fn(market)
        if label is None:
            refused.append((oid, ticker, market.yes_sub_title))
        elif label == name:
            already.append((oid, ticker))
        else:
            plan.append((oid, ticker, name, label))
    return plan, refused, silent, already


def bucket_event(rows, venue, label_fn, error=None):
    """One event's candidate rows into the FIVE buckets, including the error.

    Lifted out of `run` for the same reason `classify` was, and the reason is
    in `classify`'s own docstring: a decision buried inside a coroutine that
    needs a database and the network is a decision no test can reach. The
    bucketing of a failed venue read was exactly such a decision, it was
    wrong, and nothing could see it — the rows were `.extend`ed onto `silent`
    one line after being correctly tagged `venue_error`.

    `rows` are the candidate rows for ONE event; `error` is the exception the
    venue read raised, or None if it answered.
    """
    if error is not None:
        return [], [], [], [], [(r.id, r.external_id, "venue_error") for r in rows]

    plan, refused, silent, already = classify(
        [(r.id, r.name, r.external_id) for r in rows], venue, label_fn
    )
    return plan, refused, silent, already, []


async def _venue_labels(service, event_ticker):
    """Every leg the venue still serves for one event, as `KalshiMarket`s.

    `status=None` on purpose. The default is `'open'`, and two of the three
    legs this repair must REFUSE are `closed` — asking only for open markets
    would drop them into `VENUE_SILENT` and lose the refusal evidence
    entirely. A settled count event is also still worth repairing: settled
    means settled, and its rows are read on the page like any other.
    """
    raw, cursor = await service.get_markets(
        status=None, event_ticker=event_ticker, limit=1000
    )
    # One event's legs fit in one 1000-row page many times over (the widest
    # here is 13), so the loop is belt-and-braces — and it is bounded for the
    # same reason: Kalshi can hand back a non-empty cursor on the last page, so
    # "follow the cursor until it is falsy" is not by itself a terminating
    # condition. An empty page ends it; `_MAX_PAGES` ends it if the venue ever
    # returns a cursor that cycles. A repair that hangs mid-population leaves
    # the backup half-written, which is worse than a short read we can see.
    pages = 1
    while cursor and pages < _MAX_PAGES:
        page, cursor = await service.get_markets(
            status=None, event_ticker=event_ticker, limit=1000, cursor=cursor
        )
        if not page:
            break
        raw.extend(page)
        pages += 1
    return {m.ticker: m for m in service.parse_markets(raw)}


def is_rate_limited(exc):
    """Is this exception the venue asking us to slow down, rather than a no?

    Read as a string on purpose. `get_markets` ends a 429 with a bare
    `raise_for_status()`, so what reaches us is httpx's `HTTPStatusError`
    whose message is `Client error '429 Too Many Requests' for url ...`; the
    script must not import httpx to name the type, and every sibling read in
    `kalshi_api.py` already branches on the status code the same way.
    """
    return "429" in str(exc)


async def _venue_labels_paced(service, event_ticker, sleep=None):
    """`_venue_labels` with the venue's rate limit respected.

    `get_markets` is the ONE Kalshi read with no 429 handling of its own —
    every sibling in `kalshi_api.py` (`get_events`, the candlestick reads,
    the settlement reads) retries with a backoff, and this one ends a 429 with
    a bare `raise_for_status()`. Left unpaced, 149 serial events went out in
    about seven seconds — roughly 20 requests a second — and the venue refused
    essentially all of them after the fourth.

    Fixed here rather than in `get_markets` deliberately: that method is on
    the live poll's path (`_poll_live_prediction_market_prices` and the
    two-minute price rail), and changing its timing or its retry budget to
    suit a one-shot repair would be a shared-helper change whose blast radius
    is every Kalshi price on the site. The repair is the caller that is in a
    hurry, so the repair is where the patience belongs.

    `sleep` is injected so a test can prove the backoff without spending it.
    """
    if sleep is None:
        sleep = _asyncio_sleep

    last = None
    for attempt in range(_VENUE_RETRIES):
        try:
            labels = await _venue_labels(service, event_ticker)
        except Exception as exc:  # noqa: BLE001 — re-raised below
            last = exc
            if not is_rate_limited(exc):
                raise
            # Backoff, not a fixed nap: a 429 means the window is already
            # spent, so retrying at the same cadence just spends the next one.
            await sleep(_VENUE_BACKOFF_S * (attempt + 1))
            continue
        # The steady-state courtesy gap. Cheap next to a 429 storm: ~150
        # events at 0.25s is under a minute for a one-time repair.
        await sleep(_VENUE_GAP_S)
        return labels

    raise last


async def run(args):
    import collections

    from sqlalchemy import text

    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.base import get_task_session
    from app.tasks.kalshi import _exact_count_label

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    refusal = forward_fix_refusal()
    if refusal:
        print(refusal)
        return 2
    print(
        "forward fix: `_exact_count_label` corroborates '3' and refuses "
        "'E85' in this interpreter"
    )

    service = KalshiAPIService()

    async with get_task_session() as s:
        rows = (await s.execute(text(_CANDIDATES_SQL))).all()
        by_event = collections.defaultdict(list)
        for r in rows:
            by_event[r.event_ticker].append(r)
        print(
            f"\ncandidates: {len(rows)} rows over {len(by_event)} events "
            "(shape only — none of these is corroborated yet)"
        )

        plan = []
        refused, silent, already, unreadable = [], [], [], []
        for event_ticker in sorted(by_event):
            venue, error = None, None
            try:
                venue = await _venue_labels_paced(service, event_ticker)
            except Exception as exc:
                # A venue error is NOT a refusal — it is an unanswered
                # question, and folding the two would let a bad afternoon at
                # Kalshi read as "the venue says no" (gotcha #53). Report it
                # and repair nothing for this event.
                #
                # 🔴 And it is not SILENT either, which is what this list used
                # to be appended to. "The venue no longer serves this leg" and
                # "we never got to ask" are different facts about the world:
                # the first is evidence, the second is a hole where evidence
                # should be. They were distinguishable in the row reason
                # (`venue_error` vs `not_served`) and indistinguishable in the
                # count that anyone actually read. See `unreadable_refusal`.
                print(f"  ! {event_ticker}: venue read failed — {exc}")
                error = exc

            p, rf, sl, ok, un = bucket_event(
                by_event[event_ticker], venue, _exact_count_label, error=error
            )
            plan.extend(p)
            refused.extend(rf)
            silent.extend(sl)
            already.extend(ok)
            unreadable.extend(un)

        print("\n=== the venue's answer ===")
        print(f"  corroborated -> REPAIR      {len(plan)}")
        print(f"  refused      -> left alone  {len(refused)}")
        print(f"  silent       -> left alone  {len(silent)}")
        print(f"  already ok   -> no write    {len(already)}")
        # Printed last and separately because it is the only one of the five
        # that is a statement about US rather than about the venue.
        print(f"  UNREADABLE   -> blind spot  {len(unreadable)}")
        for oid, tkr, old, new in plan[: args.show]:
            print(f"    REPAIR  {tkr:<44} {old!r} -> {new!r}")
        for oid, tkr, sub in refused[: args.show]:
            print(f"    REFUSE  {tkr:<44} venue yes_sub_title={sub!r}")

        if not plan:
            print("\nnothing to repair")
            return 0

        if not (args.backup or args.apply):
            print("\ndry run — nothing written")
            return 0

        # Before the backup, not just before the write: a backup taken from a
        # blind-spotted plan is a manifest of the wrong set, and `--apply`
        # checks coverage against exactly that manifest, so a later reader
        # would find the two agreeing with each other and disagreeing with
        # the venue.
        refusal = unreadable_refusal(args, unreadable, len(rows))
        if refusal:
            print(f"\n{refusal}")
            return 2

        outcome_ids = [oid for oid, _, _, _ in plan]

        if args.backup:
            print("\n=== backup ===")
            await s.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} "
                    "(id bigint PRIMARY KEY, name text, set_name text)"
                )
            )
            # `set_name` is what makes this a MANIFEST and not just a snapshot,
            # and repair_6919/CERT-2439's lesson is why it is here. A snapshot
            # records only what a row WAS, so an undo built on it asks "does
            # this differ from its backup?" — true for a row this repair
            # rewrote AND for one the poll legitimately renamed afterwards,
            # and it would clobber the second. Recording the value we wrote
            # lets the restore compare-and-swap on it and leave anything that
            # has moved on since alone.
            await s.execute(
                text(
                    # DO UPDATE, not DO NOTHING: a second --backup after an
                    # unrelated writer moved a row must REFRESH it, or the undo
                    # restores a value that was never the one we overwrote.
                    f"INSERT INTO {BACKUP_TABLE} (id, name, set_name) "
                    "SELECT o.id, o.name, v.set_name FROM futures_outcomes o "
                    "JOIN unnest(CAST(:ids AS bigint[]), CAST(:news AS text[])) "
                    "  AS v(id, set_name) ON v.id = o.id "
                    "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
                    "set_name = EXCLUDED.set_name"
                ),
                {"ids": outcome_ids, "news": [new for _, _, _, new in plan]},
            )
            await s.commit()
            print(f"  copied {len(outcome_ids)} names into {BACKUP_TABLE}")

        if args.apply:
            covered = (
                await s.execute(
                    text(
                        f"SELECT count(*) FROM {BACKUP_TABLE} WHERE id = ANY(:ids)"
                    ),
                    {"ids": outcome_ids},
                )
            ).scalar()
            if covered != len(outcome_ids):
                print(
                    f"\nREFUSING --apply: the backup covers {covered} of "
                    f"{len(outcome_ids)} planned rows. Run --backup first."
                )
                return 2

            print("\n=== apply ===")
            for oid, tkr, old, new in plan:
                await s.execute(
                    text(
                        "UPDATE futures_outcomes SET name = :new WHERE id = :id"
                    ),
                    {"new": new, "id": oid},
                )
            await s.commit()
            print(f"  rewrote {len(plan)} names")
            print(
                "  undo: python3 scripts/"
                "restore_7429_kalshi_count_leg_labels.py --apply"
            )

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="read only (default)")
    p.add_argument("--backup", action="store_true", help="copy in-scope names")
    p.add_argument("--apply", action="store_true", help="write (needs a backup)")
    p.add_argument("--show", type=int, default=10, help="specimen lines to print")
    p.add_argument(
        "--allow-unreadable",
        action="store_true",
        help="apply the corroborated rows even though some events were "
        "unreadable (accepts a partial repair; see unreadable_refusal)",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
