"""A fresh market row is not a fresh price (lane1 Q502).

Alex, 2026-09-01: the "bridesmaids" card is *"WICKED stale. The wedding was like
July 1st."* — and it still rendered as a live, open question.

Root cause, measured in production on `futures_markets` 12194657 ("Who will Taylor
Swift's bridesmaids be?"):

    market.updated_at        = 2026-09-01 18:30Z   (today — poller touched the row)
    max(outcome.last_updated)= 2026-07-04 18:16Z   (59 days — no price has moved)

`_market_runtime_filter_trace` measured staleness off ``market.updated_at``, which
the poller bumps on every pass whether or not a single price changed. So the market
scored ``days_stale ~= 0`` and every staleness blocker stayed silent, while the
number on the card was two months old. None of the *other* blockers caught it
either: the parent's Yes/No pair still reads 64.5/35.5, so it is not
``all_outcomes_settled``, not ``locked_market``, not ``all_outcomes_zero``, and its
``resolution_date`` is 2027-06-30 so it is not ``past_resolution_date``.

The class, not the card: freshness must be measured on the prices the card
DISPLAYS, not on the row the poller happens to touch. Production census at the
time of the fix: 799 open, unexpired markets whose row was written inside 2 days
but whose newest price was older than 2 days — every one of them invisible to the
staleness gate.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.feed import _market_runtime_filter_trace

NOW = datetime(2026, 9, 1, 18, 45, tzinfo=timezone.utc)


def _outcome(
    name: str,
    probability: float | None,
    *,
    probability_change_24h: float | None = None,
    opening_probability: float | None = None,
    last_updated: datetime | None = None,
) -> dict:
    outcome = {
        "name": name,
        "probability": probability,
        "probability_change_24h": probability_change_24h,
        "opening_probability": opening_probability,
        "rank": None,
        "rank_change_24h": None,
    }
    if last_updated is not None:
        outcome["last_updated"] = last_updated
    return outcome


def _market(
    *, updated_at: datetime, resolution_date: datetime | None
) -> SimpleNamespace:
    return SimpleNamespace(
        status="open",
        updated_at=updated_at,
        resolution_date=resolution_date,
        commence_time=None,
        name="Who will Taylor Swift's bridesmaids be?",
        event_id=None,
    )


def _bridesmaids_outcomes(price_written_at: datetime) -> list[dict]:
    """The real production shape: a live-looking Yes/No pair plus dead candidate legs.

    The 64.5/35.5 pair is what keeps `all_outcomes_settled` from firing, which is
    why price freshness is the only signal that can catch this card.
    """
    return [
        _outcome("No", 0.645, last_updated=price_written_at),
        _outcome("Yes", 0.355, last_updated=price_written_at),
        _outcome("Gigi Hadid", 0.0035, last_updated=price_written_at),
        _outcome("Blake Lively", 0.0005, last_updated=price_written_at),
        _outcome("Selena Gomez", 0.0005, last_updated=price_written_at),
    ]


def test_bridesmaids_card_is_blocked_when_prices_stopped_moving():
    """RED-FIRST: the exact production row must be refused by the staleness gate.

    Before the fix this returns ``eligible=True`` with an empty blocker list.
    """
    trace = _market_runtime_filter_trace(
        _market(
            updated_at=NOW - timedelta(minutes=15),
            resolution_date=datetime(2027, 6, 30, tzinfo=timezone.utc),
        ),
        _bridesmaids_outcomes(NOW - timedelta(days=59)),
        "No",
        0.645,
        NOW,
        "entertainment",
        stale_no_movement_days=2,
        no_resolution_stale_days=5,
    )

    assert trace["eligible"] is False, (
        "a card whose prices have not been written in 59 days must not surface as "
        f"a live question; blockers={trace['blockers']}"
    )
    assert "stale_no_movement" in trace["blockers"]
    # The gate must report the age of the PRICES, not the age of the row.
    assert trace["checks"]["days_stale"] >= 58


def test_fresh_row_does_not_certify_a_stale_price():
    """The row timestamp alone must never be able to clear the staleness gate."""
    stale_prices = _bridesmaids_outcomes(NOW - timedelta(days=30))

    just_written_row = _market_runtime_filter_trace(
        _market(updated_at=NOW, resolution_date=None),
        stale_prices,
        "No",
        0.645,
        NOW,
        "entertainment",
        stale_no_movement_days=2,
        no_resolution_stale_days=5,
    )
    assert just_written_row["eligible"] is False
    assert just_written_row["checks"]["days_stale"] >= 29


def test_a_genuinely_fresh_market_still_surfaces():
    """CONTROL: the fix must not blanket-block. Fresh prices stay eligible.

    Without this arm the fix would pass by refusing everything.
    """
    trace = _market_runtime_filter_trace(
        _market(updated_at=NOW - timedelta(minutes=5), resolution_date=None),
        [
            _outcome(
                "No",
                0.645,
                probability_change_24h=0.02,
                opening_probability=0.60,
                last_updated=NOW - timedelta(minutes=5),
            ),
            _outcome(
                "Yes",
                0.355,
                probability_change_24h=-0.02,
                opening_probability=0.40,
                last_updated=NOW - timedelta(minutes=5),
            ),
        ],
        "No",
        0.645,
        NOW,
        "entertainment",
        stale_no_movement_days=2,
        no_resolution_stale_days=5,
    )

    assert trace["eligible"] is True, trace["blockers"]
    assert trace["checks"]["days_stale"] < 1


def test_price_newer_than_row_is_read_as_fresh():
    """Freshness is the newest PRICE, not `min(row, price)`.

    A market whose outcomes were rewritten after its row must read as fresh —
    otherwise the fix would trade one wrong answer for the mirror-image wrong one.
    """
    trace = _market_runtime_filter_trace(
        _market(updated_at=NOW - timedelta(days=40), resolution_date=None),
        [
            _outcome(
                "No",
                0.645,
                probability_change_24h=0.03,
                opening_probability=0.60,
                last_updated=NOW - timedelta(hours=1),
            ),
            _outcome(
                "Yes",
                0.355,
                probability_change_24h=-0.03,
                opening_probability=0.40,
                last_updated=NOW - timedelta(hours=1),
            ),
        ],
        "No",
        0.645,
        NOW,
        "entertainment",
        stale_no_movement_days=2,
        no_resolution_stale_days=5,
    )

    assert trace["eligible"] is True, trace["blockers"]
    assert trace["checks"]["days_stale"] < 1


def test_outcomes_without_last_updated_fall_back_to_the_row():
    """Payloads that carry no per-outcome timestamp keep the old behaviour."""
    no_timestamps = [
        _outcome("No", 0.645, probability_change_24h=0.02, opening_probability=0.60),
        _outcome("Yes", 0.355, probability_change_24h=-0.02, opening_probability=0.40),
    ]

    fresh_row = _market_runtime_filter_trace(
        _market(updated_at=NOW - timedelta(hours=2), resolution_date=None),
        no_timestamps,
        "No",
        0.645,
        NOW,
        "entertainment",
        stale_no_movement_days=2,
        no_resolution_stale_days=5,
    )
    assert fresh_row["eligible"] is True, fresh_row["blockers"]

    stale_row = _market_runtime_filter_trace(
        _market(updated_at=NOW - timedelta(days=30), resolution_date=None),
        no_timestamps,
        "No",
        0.645,
        NOW,
        "entertainment",
        stale_no_movement_days=2,
        no_resolution_stale_days=5,
    )
    assert stale_row["eligible"] is False
    assert "stale_movement_evidence" in stale_row["blockers"]


def test_strict_verdict_also_reads_the_price_clock():
    """The #1090 broaden pass must not re-open the card the strict pass refuses."""
    trace = _market_runtime_filter_trace(
        _market(updated_at=NOW, resolution_date=None),
        _bridesmaids_outcomes(NOW - timedelta(days=10)),
        "No",
        0.645,
        NOW,
        "entertainment",
        # Relaxed thresholds (the #1090 broaden pass) still exceeded by a 10-day price.
        stale_no_movement_days=7,
        no_resolution_stale_days=14,
        strict_no_movement_days=2,
        strict_no_resolution_stale_days=5,
    )

    assert trace["eligible"] is False
    assert trace["eligible_strict"] is False


def test_outcome_last_updated_is_eager_loaded_not_lazy():
    """`last_updated` must be inside every `load_only` that feeds the gate.

    The two scoring routes narrow `FuturesOutcome` with `load_only`; a column left
    out of that list lazy-loads per outcome and crashes the async route. The gate
    now reads `last_updated`, so it has to be listed — this guard fails if a future
    edit drops it.
    """
    import inspect

    from app.routes import feed as feed_module

    source = inspect.getsource(feed_module)
    load_only_blocks = source.count("selectinload(FuturesMarket.outcomes).load_only(")
    assert load_only_blocks >= 2, "scoring routes changed shape; re-derive this guard"
    assert (
        source.count("FuturesOutcome.last_updated") >= load_only_blocks
    ), "every FuturesOutcome.load_only list feeding the staleness gate must include last_updated"
