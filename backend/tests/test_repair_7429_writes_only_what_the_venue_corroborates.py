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
    classify,
    forward_fix_refusal,
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
    def __init__(self, apply=False, backup=False):
        self.apply = apply
        self.backup = backup


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
