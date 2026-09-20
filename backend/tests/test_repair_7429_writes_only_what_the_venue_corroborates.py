"""#7429's repair may only rewrite a label the VENUE corroborates.

THE CLASS THIS GUARDS is not "count labels" — it is **a repair whose selector
restates the defect instead of corroborating it**. `repair_7429`'s SQL picks
rows where `name ~ '^E[0-9]+$' AND external_id ~ ('-'||name||'$')`, which reads
like the two-signal lock `_exact_count_label` performs and is not one:
`external_id` IS the ticker and `name` came from the ticker, so that clause is
true by construction for every ticker-derived label. Measured against the live
venue 2026-09-20, the selector matched 252 rows of which only 127 were
corroborated — 123 the venue no longer serves and 2 it actively contradicts.

So these tests assert the repair decides on the venue's word, and — the half
that actually bites — that a decision procedure which has stopped discriminating
is REFUSED rather than trusted.
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..")
)

from app.services.kalshi_api import KalshiMarket  # noqa: E402
from app.tasks.kalshi import _exact_count_label  # noqa: E402
from scripts.repair_7429_kalshi_count_leg_labels import (  # noqa: E402
    bucket_event,
    classify,
    forward_fix_refusal,
    is_rate_limited,
    unreadable_refusal,
    wrong_app_refusal,
)


def mk(ticker, yes_sub_title, status="active"):
    return KalshiMarket(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title="How many?",
        yes_sub_title=yes_sub_title,
        status=status,
    )


class _Args:
    def __init__(self, apply=False, backup=False, allow_unreadable=False):
        self.apply = apply
        self.backup = backup
        self.allow_unreadable = allow_unreadable


# --------------------------------------------------------------------------
# classify: the venue's word, not the selector's shape
# --------------------------------------------------------------------------


def test_corroborated_leg_is_repaired():
    """The venue says `3` twice — the ticker leg and `yes_sub_title`."""
    venue = {"KXHOUSEWINSTATE-AZD-E3": mk("KXHOUSEWINSTATE-AZD-E3", "3")}
    plan, refused, silent, already = classify(
        [(1, "E3", "KXHOUSEWINSTATE-AZD-E3")], venue, _exact_count_label
    )
    assert plan == [(1, "KXHOUSEWINSTATE-AZD-E3", "E3", "3")]
    assert (refused, silent, already) == ([], [], [])


def test_leg_the_venue_contradicts_is_refused_not_repaired():
    """The production specimen, verbatim: Kalshi's own label IS `E85`.

    `KXSPOTIFY2D-26MAR23-E85` carries `yes_sub_title='E85'` at the venue
    (read 2026-09-20). The ticker satisfies the repair's SQL selector
    perfectly, so this row is only saved by the corroboration check. Rewriting
    it to `85` would publish a number nobody published.
    """
    tkr = "KXSPOTIFY2D-26MAR23-E85"
    venue = {tkr: mk(tkr, "E85", status="closed")}
    plan, refused, silent, already = classify(
        [(2, "E85", tkr)], venue, _exact_count_label
    )
    assert plan == []
    assert refused == [(2, tkr, "E85")]


def test_leg_the_venue_no_longer_serves_is_silent_not_refused():
    """"We could not ask" is not "the answer was no" (gotcha #53).

    Kalshi purges MARKET data at >=74/<86 days, so 123 of the 252 candidates
    are unanswerable. They must be reported as their own state — folding them
    into the refusals would let a venue outage read as evidence about labels.
    """
    plan, refused, silent, already = classify(
        [(3, "E12", "KXSPOTIFYD-26APR01-E12")], {}, _exact_count_label
    )
    assert plan == [] and refused == []
    assert silent == [(3, "KXSPOTIFYD-26APR01-E12", "not_served")]


def test_already_correct_leg_is_not_rewritten():
    """A row the poll already drained produces no write."""
    venue = {"KXNUMREDISTRICTING-26NOV03-E5": mk(
        "KXNUMREDISTRICTING-26NOV03-E5", "5"
    )}
    plan, refused, silent, already = classify(
        [(4, "5", "KXNUMREDISTRICTING-26NOV03-E5")], venue, _exact_count_label
    )
    assert plan == []
    assert already == [(4, "KXNUMREDISTRICTING-26NOV03-E5")]


def test_a_mixed_event_repairs_only_its_corroborated_legs():
    """The whole point, on one event: the selector matches all three."""
    good = "KXHOUSEWINSTATE-AZD-E3"
    bad = "KXHOUSEWINSTATE-AZD-E4"
    gone = "KXHOUSEWINSTATE-AZD-E6"
    venue = {good: mk(good, "3"), bad: mk(bad, "E4")}
    plan, refused, silent, _ = classify(
        [(1, "E3", good), (2, "E4", bad), (3, "E6", gone)],
        venue,
        _exact_count_label,
    )
    assert [p[1] for p in plan] == [good]
    assert [r[1] for r in refused] == [bad]
    assert [s[1] for s in silent] == [gone]


# --------------------------------------------------------------------------
# forward_fix_refusal: the gate must not pass vacuously
# --------------------------------------------------------------------------


def test_forward_fix_gate_passes_against_the_deployed_code():
    assert forward_fix_refusal() is None


def test_gate_refuses_a_decider_that_never_refuses(monkeypatch):
    """The vacuity guard, and the reason the gate has two arms.

    A `_exact_count_label` that hands back the ticker leg for everything
    satisfies "the fix is live" on the corroborated arm alone — while being
    exactly the wrong answer this repair exists to remove. It would authorise
    rewriting all 252 rows, the 2 contradicted ones included.
    """
    import scripts.repair_7429_kalshi_count_leg_labels as mod

    monkeypatch.setattr(
        "app.tasks.kalshi._exact_count_label",
        lambda m: m.ticker.rsplit("-E", 1)[-1],
    )
    refusal = mod.forward_fix_refusal()
    assert refusal is not None
    assert "does NOT corroborate" in refusal


def test_gate_refuses_a_decider_that_always_refuses(monkeypatch):
    """The other direction: a fix that is absent, or stubbed to None."""
    import scripts.repair_7429_kalshi_count_leg_labels as mod

    monkeypatch.setattr("app.tasks.kalshi._exact_count_label", lambda m: None)
    refusal = mod.forward_fix_refusal()
    assert refusal is not None
    assert "not live in this interpreter" in refusal


# --------------------------------------------------------------------------
# wrong_app_refusal: writes happen on the producer's app only
# --------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["apply", "backup"])
def test_write_refuses_off_the_producer_app(monkeypatch, flag):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert wrong_app_refusal(_Args(**{flag: True})) is not None

    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    refusal = wrong_app_refusal(_Args(**{flag: True}))
    assert refusal is not None and "bainluck-heavy" in refusal


@pytest.mark.parametrize("flag", ["apply", "backup"])
def test_write_allowed_on_the_producer_app(monkeypatch, flag):
    """`poll_kalshi_markets` is in HEAVY_TASKS, so heavy is the producer."""
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert wrong_app_refusal(_Args(**{flag: True})) is None


def test_dry_run_reads_anywhere(monkeypatch):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert wrong_app_refusal(_Args()) is None


def test_producer_app_is_heavy_because_the_poll_routes_to_the_heavy_queue():
    """Pin the derivation on the ROUTING, not on set membership or a string.

    repair_6126's producer is the MAIN app for the same venue, because its
    writers are absent from `HEAVY_TASKS`. The answer differs per population
    and copying it from a sibling is one mistake this asserts against.

    The other is subtler and cost authority/871 a wrong ledger row on
    2026-09-20: `HEAVY_TASKS` membership is not itself the test of which app
    runs a thing. The `scheduler` dyno — celery beat — runs on
    `bainluck-heavy` while `worker-background` runs on `bainluck`, so a task
    can be absent from `HEAVY_TASKS` and still depend on the heavy app. What
    makes THIS population heavy is the routing: `HEAVY_TASKS` writes
    `task_routes[...] = {"queue": "heavy"}`, and `worker-heavy` — the only
    consumer of that queue — runs on `bainluck-heavy` (verified against
    `heroku ps` 2026-09-20, not inferred from the constant).
    """
    from app.tasks import celery_app
    from scripts.repair_7429_kalshi_count_leg_labels import PRODUCER_APP

    route = celery_app.conf.task_routes.get("app.tasks.poll_kalshi_markets")
    assert route == {"queue": "heavy"}, (
        "poll_kalshi_markets no longer routes to the heavy queue — "
        f"PRODUCER_APP={PRODUCER_APP!r} is now a guess. Re-derive it against "
        "`heroku ps` before this repair writes anything."
    )
    assert PRODUCER_APP == "bainluck-heavy"


# --------------------------------------------------------------------------
# an unreadable venue is a blind spot, not a smaller population
#
# Every test below is a regression of one measured production run: 2026-09-20
# 20:09Z, `run.4750` on bainluck-heavy. The probe fired 149 serial `/markets`
# reads in 11 seconds, Kalshi 429'd from the fourth second on, and the run
# printed REPAIR 59 / REFUSED 0 / SILENT 193 over a population that had lost
# nothing. `RSENATESEATS-27` — the event `/futures/25923847` renders, the one
# this repair is named for — was among the 429s, and so were both `E85`
# control legs, which is why REFUSED read 0.
# --------------------------------------------------------------------------


def test_unreadable_events_block_apply():
    """The measured run's own shape: a plan is not a plan with holes in it."""
    unreadable = [(1, "RSENATESEATS-27", "venue_error")]
    refusal = unreadable_refusal(_Args(apply=True), unreadable, 252)
    assert refusal is not None
    assert "RSENATESEATS-27" in refusal
    assert "partial" in refusal


def test_a_clean_read_does_not_block_apply():
    """The gate must not be a permanent stop — this is the whole point."""
    assert unreadable_refusal(_Args(apply=True), [], 252) is None


def test_allow_unreadable_is_the_deliberate_partial():
    """A genuinely dead event must not block the repair forever."""
    unreadable = [(1, "RSENATESEATS-27", "venue_error")]
    args = _Args(apply=True, allow_unreadable=True)
    assert unreadable_refusal(args, unreadable, 252) is None


def test_backup_alone_is_not_gated_on_readability():
    """`--backup` writes no outcome rows, so it may run on a partial read.

    Stated as a test because the refusal is CALLED on the backup path too
    (it guards the manifest), and a gate that refused a plain `--backup`
    would make the diagnostic run impossible on exactly the bad afternoon
    you need it.
    """
    unreadable = [(1, "RSENATESEATS-27", "venue_error")]
    assert unreadable_refusal(_Args(backup=True), unreadable, 252) is None


def test_unreadable_rows_are_not_in_the_silent_bucket():
    """`classify` must never be the thing that reports a venue error.

    The regression was one line in `run`, not in `classify`: the unreadable
    rows were `.extend`ed onto `silent`. This pins the invariant from the
    other side — the only reason `classify` can ever emit is `not_served`,
    so any `venue_error` a reader sees came from the caller's own bucket.
    """
    venue = {}
    _, _, silent, _ = classify(
        [(3, "E12", "KXSPOTIFYD-26APR01-E12")], venue, _exact_count_label
    )
    assert [s[2] for s in silent] == ["not_served"]


@pytest.mark.parametrize(
    "message",
    [
        "Client error '429 Too Many Requests' for url 'https://api.kalshi.com'",
        "429",
    ],
)
def test_rate_limit_is_recognised(message):
    assert is_rate_limited(Exception(message))


@pytest.mark.parametrize(
    "message",
    ["Client error '404 Not Found'", "connection reset", "500 Server Error"],
)
def test_other_failures_are_not_rate_limits(message):
    """A 429 is retried; everything else must propagate on the first try."""
    assert not is_rate_limited(Exception(message))


@pytest.mark.asyncio
async def test_paced_read_retries_a_429_and_then_succeeds():
    """The retry is what turns the measured run's 193 blind rows back into data."""
    from scripts import repair_7429_kalshi_count_leg_labels as mod

    calls = {"n": 0}
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    class _Svc:
        async def get_markets(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("Client error '429 Too Many Requests' for url 'x'")
            return [], None

        def parse_markets(self, raw):
            return []

    out = await mod._venue_labels_paced(_Svc(), "RSENATESEATS-27", sleep=fake_sleep)
    assert out == {}
    assert calls["n"] == 2, "the 429 was not retried"
    assert slept[0] == mod._VENUE_BACKOFF_S, "retried without backing off"


@pytest.mark.asyncio
async def test_paced_read_gives_up_and_raises_rather_than_returning_empty():
    """Exhausted retries must RAISE, so the caller buckets it unreadable.

    Returning `{}` here would be the original defect wearing a fix: an empty
    venue map classifies every leg as `not_served` — silent, not unreadable —
    and the run would once again report a rate-limited afternoon as a purge.
    """
    from scripts import repair_7429_kalshi_count_leg_labels as mod

    async def fake_sleep(s):
        pass

    class _Svc:
        async def get_markets(self, **kw):
            raise Exception("Client error '429 Too Many Requests' for url 'x'")

        def parse_markets(self, raw):
            return []

    with pytest.raises(Exception, match="429"):
        await mod._venue_labels_paced(_Svc(), "RSENATESEATS-27", sleep=fake_sleep)


@pytest.mark.asyncio
async def test_a_non_429_failure_is_not_retried():
    from scripts import repair_7429_kalshi_count_leg_labels as mod

    calls = {"n": 0}

    async def fake_sleep(s):
        pass

    class _Svc:
        async def get_markets(self, **kw):
            calls["n"] += 1
            raise Exception("Client error '404 Not Found' for url 'x'")

        def parse_markets(self, raw):
            return []

    with pytest.raises(Exception, match="404"):
        await mod._venue_labels_paced(_Svc(), "KXDEAD-1", sleep=fake_sleep)
    assert calls["n"] == 1, "a 404 burned the retry budget meant for 429s"


class _Row:
    """A candidate row as `run`'s SQL hands it over."""

    def __init__(self, id, name, external_id):
        self.id = id
        self.name = name
        self.external_id = external_id


def test_a_failed_venue_read_buckets_unreadable_and_never_silent():
    """THE regression, at the exact line that had it.

    `run` tagged these rows `venue_error` and then appended them to `silent`,
    so the distinction existed in the data and died in the count. This is the
    measured production case: `RSENATESEATS-27` 429'd, and the run reported it
    among 193 "silent" rows as though Kalshi had purged the event.
    """
    rows = [_Row(1, "E45", "RSENATESEATS-27-E45")]
    plan, refused, silent, already, unreadable = bucket_event(
        rows, None, _exact_count_label, error=Exception("429 Too Many Requests")
    )
    assert unreadable == [(1, "RSENATESEATS-27-E45", "venue_error")]
    assert silent == [], "a read we never got is being reported as the venue's answer"
    assert (plan, refused, already) == ([], [], [])


def test_an_answered_event_still_routes_through_the_four_venue_buckets():
    """The other arm: `bucket_event` must not swallow a real answer."""
    good = "KXHOUSEWINSTATE-AZD-E3"
    gone = "KXHOUSEWINSTATE-AZD-E6"
    rows = [_Row(1, "E3", good), _Row(3, "E6", gone)]
    plan, refused, silent, already, unreadable = bucket_event(
        rows, {good: mk(good, "3")}, _exact_count_label
    )
    assert [p[1] for p in plan] == [good]
    assert [s[1] for s in silent] == [gone]
    assert unreadable == [], "an answered event must contribute no blind spot"
