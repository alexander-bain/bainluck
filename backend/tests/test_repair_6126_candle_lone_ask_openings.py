"""Guards for the #6126 historical cleanup (authority).

This repair DELETES rows from `futures_odds_snapshots` and rewrites
`opening_probability` on production under D51(b). It runs on a one-off dyno
whose stdout is awkward to read (gotcha #48), so a mistake in it is invisible
until a reader sees a wrong curve. Everything here exists because the
corresponding mistake is cheap to make and expensive to find:

* the population predicate drifting back onto the WITHDRAWN fingerprint
  (`opening_probability = 0.99 AND opening_source IS NULL`), which over-counted
  this population by 4,611 to 4,402 and would repair 4,275 Kalshi poller legs
  and 123 Polymarket legs this rail never wrote
* `tap_is_off` passing VACUOUSLY — a misspelled candle carries no readable
  price, both reducers answer `None` for want of data, and the interlock then
  green-lights a write against a deploy that re-mints it an hour later
* a leg being repaired on the SUM test in a market whose outcomes are not
  mutually exclusive (gotcha #23), where two legs at 0.99 is legal
* SERIES coming back as an authority to write (CERT-2855's required repair).
  The candle rail stores no book, so a real 0.99 trade and the venue's
  untraded default are identical in our data and "its next point is 0.89"
  reports only that the price moved
* the refusal cohort quietly becoming repairable, which is how a
  "withhold and count" gate turns into a "guess and write" one
* the delete running past the leading run, taking a genuine later move to 99%
"""

import importlib.util
import pathlib
import re
import types

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_6126_candle_lone_ask_openings")
restore = _load("restore_6126_candle_lone_ask_openings")


def _leg(**kw):
    """One row as `_POPULATION_SQL` returns it."""
    base = dict(
        id=1,
        market_id=9,
        name="Alexander Bublik",
        ts=None,
        opening_source=None,
        sum_refutes=False,
        venue_exclusive=False,
        price_exclusive=True,
        next_p=None,
        series_refutes=False,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# The interlock
# ---------------------------------------------------------------------------


def test_the_tap_check_reads_the_venues_real_payload_spelling():
    """Kalshi publishes candle prices ONLY as `*_dollars` STRINGS.

    This is the vacuity guard and it is the most important test in the file. A
    fixture written with the cents spelling (`{"yes_ask": {"close": 99}}`)
    carries no price either reducer can read, both correctly answer `None` for
    want of data, and `tap_is_off()` then returns True against a COMPLETELY
    UNFIXED deploy — green-lighting a repair the next backfill re-mints.

    So the fixture must actually be readable: the venue's own default book has
    to produce 0.99 under the OLD rule, which is exactly what
    `_dollars(..., "close_dollars")` recovering both sides proves.
    """
    from app.utils.kalshi_candle_price import _dollars

    bid = _dollars(repair.VENUE_DEFAULT_CANDLE.get("yes_bid"), "close_dollars")
    ask = _dollars(repair.VENUE_DEFAULT_CANDLE.get("yes_ask"), "close_dollars")
    assert bid == 0.0, "the venue's zero bid must be readable, not absent"
    assert ask == 0.99, "the venue's 0.99 ask must be readable, not absent"


def test_tap_is_off_requires_both_a_refusal_and_a_surviving_price():
    """A refusal alone is satisfied by a reducer that prices NOTHING.

    `tap_is_off` must be falsifiable in both directions, or it is decoration: it
    has to see the venue's default book refused AND a real 0.99 trade still
    priced. Stubbing either half alone must flip it to False.
    """
    assert repair.tap_is_off() is True

    import app.tasks.event_chart_backfill as chart
    import app.utils.kalshi_candle_price as cal

    # Half 1 broken: a reducer that refuses everything, including real trades.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cal, "candle_yes_price", lambda c: None)
        mp.setattr(chart, "normalize_candle", lambda c: None)
        assert repair.tap_is_off() is False, (
            "a reducer that prices nothing at all must not read as 'fixed'"
        )

    # Half 2 broken: the pre-fix rule, which prices the default book at 0.99.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cal, "candle_yes_price", lambda c: 0.99)
        mp.setattr(chart, "normalize_candle", lambda c: 0.99)
        assert repair.tap_is_off() is False, (
            "the unfixed reducer must not read as 'fixed'"
        )


def test_a_write_is_refused_off_the_producer_app_and_a_dry_run_is_not(monkeypatch):
    """Reads run anywhere; writes only on the app whose code could re-mint."""
    dry = types.SimpleNamespace(apply=False, backup=False)
    write = types.SimpleNamespace(apply=True, backup=False)

    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert repair.wrong_app_refusal(dry) is None
    assert "REFUSING" in repair.wrong_app_refusal(write)

    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert "REFUSING" in repair.wrong_app_refusal(write), (
        "the reducers' callers are not HEAVY_TASKS, so the heavy app is the "
        "wrong interpreter for this population"
    )

    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
    assert repair.wrong_app_refusal(write) is None


def test_the_producer_app_is_the_main_app_because_no_caller_is_heavy():
    """The answer differs per population, so it is derived, not copied.

    repair_5621 names `bainluck-heavy` because its producer IS a heavy task.
    Here every caller of the two reducers is absent from `HEAVY_TASKS`, so the
    main app is the one that can re-mint. If a reducer's caller is ever promoted
    to heavy, this fails and `PRODUCER_APP` has to be re-derived with it.
    """
    from app.tasks import HEAVY_TASKS

    assert repair.PRODUCER_APP == "bainluck"
    assert "app.tasks.backfill_kalshi_history" not in HEAVY_TASKS
    assert "app.tasks.backfill_event_chart_history" not in HEAVY_TASKS


# ---------------------------------------------------------------------------
# The population predicate
# ---------------------------------------------------------------------------


def test_the_population_keys_on_timestamp_precision_not_the_withdrawn_pair():
    """The discriminator is the TIMESTAMP, and it must stay in the SQL.

    `opening_probability = 0.99 AND opening_source IS NULL` is NOT this rail's
    fingerprint — it returns 4,611 legs where the rail wrote 4,402, sweeping in
    4,275 Kalshi poller legs and 123 Polymarket ones. What separates them is
    that a candle's `end_period_ts` lands exactly on the hour while the poller's
    `now` carries microseconds.
    """
    sql = repair._POPULATION_SQL
    assert "date_part('minute'" in sql and "date_part('second'" in sql, (
        "without the exact-hour predicate this is the withdrawn 4,611 count"
    )
    assert "m.source = 'kalshi'" in sql, "Polymarket legs are not this rail's"


def test_the_leading_run_stops_at_the_first_honest_point():
    """A 0.99 LATER in a series is a genuine move and must survive.

    The run is deleted only up to the first row that is not the bad shape, which
    is what the `cutoff` CTE is for. Losing that bound would delete real
    near-certainty points from the middle of a curve.
    """
    sql = repair._LEADING_RUN_SQL
    assert "cutoff" in sql
    assert "s.captured_at < c.ts" in sql, (
        "the delete must be bounded above by the first non-default row"
    )
    assert re.search(r"NOT \(.*bookmaker = 'kalshi'", sql, re.S), (
        "the cutoff must be the first row that is NOT the bad shape"
    )


def test_the_bad_shape_requires_an_absent_book_not_merely_a_099():
    """The candle rail stores NO book; a poller row at 0.99 has one.

    This is also why `kalshi_empty_book.lone_ask_on_empty_book_sql` cannot see
    these rows — it tests `yes_bid`, which is NULL here.
    """
    assert "yes_bid IS NULL" in repair._BAD_SHAPE
    assert "yes_ask IS NULL" in repair._BAD_SHAPE
    assert "probability = 0.99" in repair._BAD_SHAPE


# ---------------------------------------------------------------------------
# classify() — what is repaired, and what is refused and counted
# ---------------------------------------------------------------------------


def test_series_only_real_099_trade_is_refused_without_venue_proof_6126():
    """CERT-2855's required repair. SERIES IS NOT AN AUTHORITY TO WRITE.

    The candle rail stores a price and a time and NO book, so a genuine 0.99
    trade and Kalshi's untraded bid-0.00/ask-0.99 default are byte-identical in
    our data. "Its next point is 0.89" says only that the price moved, and
    price movement does not refute a prior probability — the first version of
    this script deleted a real trade followed by 0.89 while refusing the same
    trade followed by 0.95, on a cliff at 0.90 that nothing at the venue puts
    there. 127 live legs sat in that cohort when this was written.

    Both arms of the withdrawn test are pinned here, because the persisting
    arm (next == exactly 0.99) is the same inference wearing a different face.
    """
    real_trade_then_stable = _leg(series_refutes=True, next_p=0.99)
    real_trade_then_drop = _leg(series_refutes=True, next_p=0.89)

    for row in (real_trade_then_stable, real_trade_then_drop):
        why = repair.classify(row)
        assert why is not None, (
            "a series-only leg has no venue proof and must be refused, not "
            f"repaired (next_p={row.next_p})"
        )
        assert "series-only" in why, "the refusal must be countable by name"

    # ...and it stays refused in an exclusive market, so nobody can read the
    # refusal as gotcha #23 doing the work.
    assert repair.classify(
        _leg(series_refutes=True, next_p=0.89, price_exclusive=True)
    ) is not None

    # THE NAMED WITNESS STILL REPAIRS. US Open Men's Singles (market 34277822,
    # `/futures/34277822`): 48 outcomes, one winner, current probabilities
    # summing to exactly 1.000 — and Bublik, Norrie and Prizmic share one
    # opening instant at 0.99. Three exclusive legs at 0.99 is 2.97. That is
    # SUM, it refutes itself on the row, and it is the reader-visible ship.
    for name in ("Alexander Bublik", "Cameron Norrie", "Dino Prizmic"):
        assert classify_ok(
            _leg(
                name=name,
                market_id=34277822,
                sum_refutes=True,
                price_exclusive=True,
                next_p=0.13,
                series_refutes=True,
            )
        ), f"the ship's own witness ({name}) must survive the strict gate"


def test_sum_is_the_only_authority_and_series_never_short_circuits_it():
    """The mutation this file exists to kill: `if row.series_refutes: return None`.

    Restoring that line — anywhere ahead of the SUM branch — would repair every
    leg below on price movement alone. Each of these is refused for a DIFFERENT
    reason, so a partial restoration cannot slip through on one of them.
    """
    assert repair.classify(_leg(series_refutes=True, next_p=0.99)) is not None
    assert repair.classify(_leg(series_refutes=True, next_p=0.13)) is not None
    assert (
        repair.classify(
            _leg(series_refutes=True, next_p=0.13, price_exclusive=False)
        )
        is not None
    ), "a non-exclusive market must not become repairable via SERIES"
    assert (
        repair.classify(
            _leg(sum_refutes=True, price_exclusive=False, series_refutes=True,
                 next_p=0.13)
        )
        is not None
    ), "SERIES must not rescue a SUM leg that failed exclusivity"


def test_a_sum_refuted_leg_is_repaired_only_where_the_market_is_exclusive():
    """Two legs at 0.99 is 1.98 — impossible, but only if they are exclusive.

    Gotcha #23: a futures market can hold independent binaries that legitimately
    sum well over 100%. So SUM alone is not permission to write.
    """
    assert classify_ok(_leg(sum_refutes=True, price_exclusive=True, next_p=0.95))

    why = repair.classify(
        _leg(sum_refutes=True, price_exclusive=False, next_p=0.95)
    )
    assert why is not None and "gotcha #23" in why


def test_a_singleton_with_nothing_refuting_it_is_refused_and_named():
    """The 87 legs this script will not touch, and why.

    A lone leg at 0.99 whose next point is 0.95 is exactly what a genuine heavy
    favourite looks like. Nothing in our own data separates it from the venue's
    default book, so the script withholds a correction and counts it — the same
    choice the shipped reducer makes.
    """
    why = repair.classify(_leg(next_p=0.95))
    assert why is not None and "[0.90, 0.99)" in why

    why_none = repair.classify(_leg(next_p=None))
    assert why_none is not None and "no later point" in why_none


def test_a_refusal_reason_is_a_stable_bucket_not_a_per_row_sentence():
    """The dry run tallies refusals BY REASON, and that tally is the proof.

    An attended operator authorises `--apply` off four numbers. Interpolating
    `next_p` into the reason — which the first version did — shatters one
    cohort of 87 into eighty-odd buckets of 1 and the split stops being
    readable at exactly the moment it is being relied on.
    """
    reasons = {repair.classify(_leg(next_p=p)) for p in (0.91, 0.95, 0.98)}
    assert len(reasons) == 1, f"one cohort must be one bucket, got {reasons}"

    series = {
        repair.classify(_leg(series_refutes=True, next_p=p))
        for p in (0.99, 0.89, 0.13)
    }
    assert len(series) == 1, f"one cohort must be one bucket, got {series}"


def test_a_market_with_no_current_prices_cannot_satisfy_the_sum_test():
    """`price_exclusive` is NULL when the market has no priced outcomes.

    A NULL must not read as permission: SQL's `BETWEEN` yields NULL, not False,
    and `row.price_exclusive` on a NULL is falsey only by luck of the
    driver. Pinned so a future refactor cannot turn "unknown" into "yes".

    Both witnesses must be unknown/absent for the leg to be refused, which is
    the point: `or` short-circuits, so a NULL price screen next to a TRUE venue
    flag is a REPAIR and is covered by its own test below.
    """
    why = repair.classify(
        _leg(sum_refutes=True, price_exclusive=None, venue_exclusive=False, next_p=0.95)
    )
    assert why is not None, "an unknown exclusivity must refuse, not repair"


# ---------------------------------------------------------------------------
# The venue witness (#6126 rung 3)
# ---------------------------------------------------------------------------


def test_the_venue_flag_repairs_the_partitions_the_price_screen_is_blind_to():
    """The 734 legs the price screen rejects BECAUSE of the defect it screens.

    An untraded market's frozen 0.99 default book is also its current price, so
    `sum(current_probability)` is enormous and the market screens out as "not
    exclusive". The witness is the one a reader can open: `/futures/25927225`,
    *Austrian Alpine Open presented by Kitzbühel Tirol Winner*
    (`KXDPWORLDTOUR-AUAOPBKT26`), settled, 159 outcomes, current sum 2.76 — so
    `price_exclusive` is FALSE — while Kalshi's own event payload says
    `mutually_exclusive: true` (read at the venue 2026-09-14 12:10Z, with all 57
    markets this arm admits — table in the cert body).

    Photographed on production 12:25Z: the winner Kota Kaneko shows OPEN 12%,
    the runner-up OPEN 19%, and Gregorio De Leo, Brandon Robinson-Thompson,
    Alexander Levy, Austin Bautista, Jason Scrivener, Darius Van Driel and Fred
    Biondi each read OPEN 99% beside "Lost · 0%". A tournament has ONE winner.

    The market is deliberately NOT the widest one: 45 of the 57 already have
    their whole opening column withheld by #5539's serve-time coherence rule,
    so a leg count is not a reader count. See the module docstring.
    """
    assert classify_ok(
        _leg(
            name="Gregorio De Leo",
            market_id=25927225,
            sum_refutes=True,
            venue_exclusive=True,
            price_exclusive=False,
        )
    ), "the venue's own exclusivity flag must be an authority on its own"

    # ...including where the market has no priced outcomes at all, which is the
    # 8-leg / 4-market corner the price screen can only answer NULL for.
    assert classify_ok(
        _leg(sum_refutes=True, venue_exclusive=True, price_exclusive=None)
    )


def test_the_venue_flag_may_never_refuse_and_the_two_witnesses_are_or_not_and():
    """The mutation this test exists to kill: `and` between the two witnesses.

    Kalshi sets `mutually_exclusive: false` on plain partitions — `KXDJI`
    price buckets, `KXTEMPAUSH` temperature buckets, and
    `KXMLBINNINGTOTAL-...-8`, whose TWO outcomes sum to exactly 1.00 (all three
    read FALSE at the venue 2026-09-14 12:10Z). The flag is therefore sound
    only in the TRUE direction. An `and` would silently delete the 83 legs the
    price arm carries — the arm CERT-2857 graded — and would read as a tidy-up.
    """
    assert classify_ok(
        _leg(
            name="Over 8.5",
            market_id=1,
            sum_refutes=True,
            venue_exclusive=False,
            price_exclusive=True,
        )
    ), "a venue FALSE may never veto a leg the price screen admits"

    # And neither witness is permission on its own without SUM: a single leg at
    # 0.99 in an exclusive market is just a favourite.
    assert (
        repair.classify(
            _leg(sum_refutes=False, venue_exclusive=True, price_exclusive=True)
        )
        is not None
    ), "exclusivity is a qualifier on SUM, never an authority by itself"


def test_the_population_sql_carries_both_witnesses_under_the_names_classify_reads():
    """A gate is only as wide as the row the query hands it.

    `classify` reads `venue_exclusive` and `price_exclusive`. If the SELECT list
    stops aliasing either one, every row raises `AttributeError` at apply time
    rather than repairing — or, worse, a rename drifts and the arm silently
    stops existing. Asserted against the shipped statement, and paired with the
    NULL-safety of `IS TRUE` (a market row whose flag was never written is
    NULL, and NULL must not read as exclusive).
    """
    sql = repair._POPULATION_SQL
    assert "AS venue_exclusive" in sql and "AS price_exclusive" in sql
    assert "b.mutually_exclusive IS TRUE" in sql, (
        "`= true` would let a NULL flag through as unknown-is-yes"
    )
    assert "m.mutually_exclusive" in sql, "the band must carry the market flag"


def classify_ok(row):
    return repair.classify(row) is None


# ---------------------------------------------------------------------------
# The undo
# ---------------------------------------------------------------------------


def test_the_restore_reinserts_snapshots_under_their_original_ids():
    """A re-insert under a fresh id restores a row nothing else references."""
    src = (_SCRIPTS / "restore_6126_candle_lone_ask_openings.py").read_text()
    assert "INSERT INTO futures_odds_snapshots (id," in src
    assert "b.id, b.outcome_id" in src
    assert "ON CONFLICT (id) DO NOTHING" in src


def test_the_restore_skips_rows_whose_outcome_is_gone_rather_than_failing():
    """The FK would refuse them and take the whole statement with it."""
    src = (_SCRIPTS / "restore_6126_candle_lone_ask_openings.py").read_text()
    assert "JOIN futures_outcomes o ON o.id = b.outcome_id" in src
    assert "orphan_snap" in src, "the skipped rows must be counted, not swallowed"


def test_the_restore_carries_no_tap_or_app_gate():
    """An undo writes the OLD state; the repair's interlocks argue about the NEW
    one. Being refused by them at the moment you need an undo is the failure.

    Asserted against the module's NAMESPACE, not its text. The first version of
    this guard grepped the source and failed on the docstring that explains the
    absence — a source-scan cannot tell a gate from a sentence about a gate.
    """
    assert not hasattr(restore, "tap_is_off")
    assert not hasattr(restore, "wrong_app_refusal")
    assert not hasattr(restore, "PRODUCER_APP")
    # And the repair genuinely has all three, so the contrast is real rather
    # than two modules that both happen to lack a name.
    assert hasattr(repair, "tap_is_off")
    assert hasattr(repair, "wrong_app_refusal")
    assert hasattr(repair, "PRODUCER_APP")


def test_the_repair_refuses_to_apply_without_a_covering_backup():
    """D51(b): the undo has to exist before the write does."""
    src = (_SCRIPTS / "repair_6126_candle_lone_ask_openings.py").read_text()
    assert "REFUSING to apply: backup covers" in src
    assert "SELECT count(*) FROM backup_6126_openings" in src
