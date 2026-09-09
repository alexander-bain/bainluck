"""#4000 — a leg the venue quotes NO price for must not keep the price we gave it.

Declining to write is not the same as withdrawing what is written. Every guard in
the ingest already refuses to *store* a price it cannot stand behind
(``_is_placeholder_outcome``, the #151 evidence gate, ``field_is_incoherent``), and
all of them work. None of them touches the number that is already in the row, so a
value written once survives every subsequent refusal — forever.

Measured on production 2026-09-09 with the filer's own predicate (open markets, >=5
sub-1.0 outcomes summing 0.90-1.10, >=2 outcomes at exactly 1.0):

    source        markets   rows at 1.000   tier 1-2
    polymarket        104           2,542         83
    kalshi              1               3          1

Every one of the 84 tier-1/2 markets is ``mutually_exclusive`` + ``market_type =
'field'`` + polymarket. The freeze is total and it is old:

    market 112897 "Presidential Election Winner 2028"
      52 legs   last_updated 2026-09-08 22:53Z   price_changed_at 2026-09-08 22:53Z
      76 legs   last_updated 2026-05-12 17:15Z   price_changed_at NULL   prob 1.000000

120 days without a write, and ``opening_probability`` is 1.000000 on the same rows —
exactly the permanent damage ``winner_field_coherence``'s docstring predicts.

What Gamma serves for those legs, on every pass (verbatim, ``GET /events/31552``,
2026-09-09; the leg is NOT delisted — it sits in the same 128-market payload as the
live ones, and ``?condition_ids=`` returns 0 rows for it only because that filter
defaults to active-only, gotcha #53)::

    Will Person BG win the 2028 US Presidential Election?
      active=false  outcomePrices=None  bestBid=0  bestAsk=1
      lastTradePrice=0  volume=0

The reader-visible cost, on the search surface, is not the raw 1.0 — it is what the
1.0 does to two defences that are each working correctly in isolation. Served
``/api/events/search?q=Presidential Election Winner 2028`` on 2026-09-09:

    top_outcomes: JD Vance 0.152 | "Other" 0.633 | AOC 0.084 | ...

``_build_search_top_outcomes`` name-filters the 76 "Person XX" rows, but "Other" is
a real name carrying a frozen 1.000. The top-5 slice then sums to 1.578 — under
``_FIELD_SUM_MAX`` (1.60) by 0.022 — so the #23 squeeze runs and divides by 1.578:

  * JD Vance's true 0.241 is served as **0.152** (and every candidate is deflated
    by the same 1.586x), and
  * "Other" is deflated 1.000 -> 0.633, which drops it under
    ``_FIELD_DOMINANT_MIN`` (0.9), so ``_drop_dominant_field_outcomes`` — the guard
    that exists precisely to remove a field row printed at 100% — never fires.

One frozen row defeats both guards, in opposite directions.
"""

from app.tasks.polymarket import _parent_outcome_data, _unpriced_leg_external_ids


def _market(**kwargs):
    """A PolymarketMarket with sensible defaults, overridden by kwargs."""
    from app.services.polymarket_api import PolymarketMarket

    defaults = {
        "condition_id": "0xtest",
        "question": "Test?",
        "outcomes": ["Yes", "No"],
        "outcome_prices": [],
        "best_bid": None,
        "best_ask": None,
        "last_trade_price": None,
    }
    defaults.update(kwargs)
    return PolymarketMarket(**defaults)


def _frozen_leg(condition_id="0xd8b6cb1a", name="Person BG"):
    """Market 112897's specimen, verbatim from Gamma 2026-09-09.

    No price, an empty book at its widest (bid 0 / ask 1), never traded.
    """
    return _market(
        condition_id=condition_id,
        question=f"Will {name} win the 2028 US Presidential Election?",
        active=False,
        outcome_prices=[],
        best_bid=0,
        best_ask=1,
        last_trade_price=0,
    )


def _live_leg(condition_id="0x7ad403c3", name="JD Vance", price=0.2405):
    """The control, also verbatim: a leg the venue really is quoting."""
    return _market(
        condition_id=condition_id,
        question=f"Will {name} win the 2028 US Presidential Election?",
        outcome_prices=[price, round(1 - price, 4)],
        best_bid=price - 0.001,
        best_ask=price + 0.0005,
        last_trade_price=price,
    )


def _event(markets, neg_risk=True, event_id="31552"):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(
        id=event_id,
        title="Presidential Election Winner 2028",
        neg_risk=neg_risk,
        markets=markets,
    )


class TestTheSpecimenIsIdentified:
    """The frozen leg is named, and the live one is not."""

    def test_the_frozen_leg_is_returned_for_retirement(self):
        event = _event([_live_leg(), _frozen_leg()])
        assert _unpriced_leg_external_ids(event) == ["0xd8b6cb1a"]

    def test_the_priced_control_is_never_retired(self):
        """The whole point: JD Vance's 24.1% must survive untouched."""
        event = _event([_live_leg()])
        assert _unpriced_leg_external_ids(event) == []

    def test_the_frozen_leg_is_still_absent_from_the_write_set(self):
        """The producer is unchanged — retirement is additive, not a pricing change.

        ``_parent_outcome_data`` must still decline to write a price for the frozen
        leg. If this ever starts returning it, the fix has become the bug it fixes.
        """
        event = _event([_live_leg(), _frozen_leg()])
        written = {od["external_id"] for od in _parent_outcome_data(event)}
        assert written == {"0x7ad403c3"}

    def test_the_whole_112897_shape(self):
        """52 priced legs written, 76 frozen legs retired, nothing in both sets."""
        live = [
            _live_leg(f"0xlive{i}", f"Candidate {i}", 0.01 + i * 0.001)
            for i in range(52)
        ]
        frozen = [_frozen_leg(f"0xfrozen{i}", f"Person {i}") for i in range(76)]
        event = _event(live + frozen)

        retired = set(_unpriced_leg_external_ids(event))
        written = {od["external_id"] for od in _parent_outcome_data(event)}

        assert len(retired) == 76
        assert len(written) == 52
        assert retired.isdisjoint(written)


class TestTheKills:
    """Each of these, if it fails, means the fix withdraws a real price."""

    def test_a_leg_the_pass_did_not_cover_is_never_named(self):
        """A truncated payload must withdraw nothing.

        This is structural, not a heuristic: the retirement set is built from
        ``event.markets``, so a leg Gamma omitted this pass cannot appear in it.
        A database-sweep implementation would fail this test, which is why this
        one is keyed on the payload.
        """
        full = _event([_live_leg(), _frozen_leg("0xa", "A"), _frozen_leg("0xb", "B")])
        assert set(_unpriced_leg_external_ids(full)) == {"0xa", "0xb"}

        truncated = _event([_live_leg()])
        assert _unpriced_leg_external_ids(truncated) == []

    def test_a_leg_with_a_real_bid_is_not_retired(self, monkeypatch):
        """We refused it; the venue did not.

        Today ``_resolve_market_probability`` prices anything carrying a bid, so
        this branch is a SECOND, independent condition rather than the only one —
        and that is deliberate. The resolver is "permissive at the extremes on
        purpose" and has been retuned repeatedly (#151, #1578, #1200, #1201); the
        day one of those tunings makes it refuse a quote the venue really is
        making, retirement must not start blanking live rows behind it. Producer
        and detector must not be able to drift about what an ABSENT price is.

        So the refusal is forced here rather than fixtured: that is the only way to
        reach the branch, and pretending a fixture reaches it would be a guard that
        never fires.
        """
        monkeypatch.setattr(
            "app.tasks.polymarket._resolve_market_probability", lambda m: None
        )
        contested = _market(
            condition_id="0xbid",
            question="Will someone win?",
            outcome_prices=[],
            best_bid=0.30,
            best_ask=0.95,
            last_trade_price=None,
        )
        assert _unpriced_leg_external_ids(_event([contested, _live_leg()])) == []

    def test_a_leg_that_has_traded_is_not_retired(self, monkeypatch):
        """A trade is evidence, not an absence — even with an empty book now."""
        monkeypatch.setattr(
            "app.tasks.polymarket._resolve_market_probability", lambda m: None
        )
        traded = _market(
            condition_id="0xtraded",
            question="Will someone win?",
            outcome_prices=[],
            best_bid=0,
            best_ask=1,
            last_trade_price=0.04,
        )
        assert _unpriced_leg_external_ids(_event([traded, _live_leg()])) == []

    def test_the_forced_refusal_still_retires_a_truly_dead_leg(self, monkeypatch):
        """The control for the two tests above: the monkeypatch is not the reason.

        Same forced refusal, but a leg with no bid and no trade — it IS retired.
        Without this, both tests above would pass on a helper that returns [] for
        everything.
        """
        monkeypatch.setattr(
            "app.tasks.polymarket._resolve_market_probability", lambda m: None
        )
        assert _unpriced_leg_external_ids(_event([_frozen_leg(), _live_leg()])) == [
            "0xd8b6cb1a"
        ]

    def test_a_non_negrisk_event_is_out_of_scope(self):
        """Game events price through a different, deliberately less-gated path.

        Their refusals do not mean "the venue quotes nothing", so retiring on them
        would be a pricing change this ship has no evidence for.
        """
        event = _event([_live_leg(), _frozen_leg()], neg_risk=False)
        assert _unpriced_leg_external_ids(event) == []

    def test_a_single_market_event_is_out_of_scope(self):
        event = _event([_frozen_leg()], neg_risk=True)
        assert _unpriced_leg_external_ids(event) == []

    def test_a_leg_with_no_condition_id_is_skipped(self):
        """An id-less leg cannot address a row; naming it would widen the UPDATE."""
        event = _event([_live_leg(), _frozen_leg(condition_id="")])
        assert _unpriced_leg_external_ids(event) == []


class TestTheWriteIsNarrow:
    """What the UPDATE may and may not touch."""

    def test_it_withdraws_only_the_two_rendering_fields(self):
        """opening_probability is calibration-truth and stays out of this ship."""
        import inspect

        from app.tasks.polymarket import _retire_unpriced_legs

        src = inspect.getsource(_retire_unpriced_legs)
        values = src[src.index(".values(") :]
        assert "current_probability=None" in values
        assert "current_american_odds=None" in values
        assert "opening_probability" not in values
        assert "opening_captured_at" not in values

    def test_it_refuses_to_un_price_a_graded_leg(self):
        """A crowned leg's 1.0 is its settlement, not a quote."""
        import inspect

        from app.tasks.polymarket import _retire_unpriced_legs

        src = inspect.getsource(_retire_unpriced_legs)
        assert "is_winner.isnot(True)" in src

    def test_it_is_scoped_to_one_market(self):
        """external_id is not unique across markets — the UPDATE must be keyed."""
        import inspect

        from app.tasks.polymarket import _retire_unpriced_legs

        src = inspect.getsource(_retire_unpriced_legs)
        assert "FuturesOutcome.market_id == futures_market_id" in src

    def test_an_empty_retirement_set_issues_no_statement(self):
        """The common case is zero legs; it must not cost an UPDATE per event."""
        import inspect

        from app.tasks.polymarket import _retire_unpriced_legs

        src = inspect.getsource(_retire_unpriced_legs)
        assert "if not ids:" in src and "return 0" in src
