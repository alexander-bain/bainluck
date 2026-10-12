"""#5343: a leg the venue settled No is stored as a resolved row, not dropped.

Pure half. The writer half (the real sub-market loop against real Postgres) is
``tests/integration/test_polymarket_resolved_zero_legs_5343_real_postgres.py``.

Specimen: the retained Gamma ``GET /events/106884`` bytes (see the fixture's
PROVENANCE.md). Every negative below is one of its real resolved legs with ONE
field changed, so each refusal has its own failing arm.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks.polymarket import (
    RESOLVED_ZERO_LEG_DOMAINS,
    _resolve_market_probability_with_source,
    resolved_zero_leg_admitted,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "polymarket_resolved_zero_legs_5343"
    / "gamma-event-106884.json"
)
FIXTURE_SHA256 = "5ce0eea19067bd1691544f8d650a501bb3a3ef3b31fd2c8f630267883068c224"

#: The six legs Gamma reports closed + UMA-resolved at ["0","1"] (prefixes).
RESOLVED = {"0xc8929e80", "0xe7f239d7", "0x626d0441", "0x4d162a40", "0x02507350", "0xb4022c0b"}
#: The two of those six the resolver declines today (their last trade sits above
#: the 0.001 ask, so `book_refutes_price` refuses it). The other four price off
#: that last trade and are already written; the arm must not touch them.
DECLINED_TODAY = {"0x626d0441", "0x4d162a40"}


def _raw() -> dict:
    return json.loads(FIXTURE.read_bytes())


def _parse(raw: dict):
    svc = PolymarketAPIService.__new__(PolymarketAPIService)
    event = svc._parse_event(raw)
    assert event is not None
    return event


def _prefix(market) -> str:
    return market.condition_id[:10]


def _one_resolved_leg_changed(**changes):
    """The real 106884 event with ONE field changed on a declined resolved leg."""
    raw = _raw()
    target = next(m for m in raw["markets"] if m["conditionId"].startswith("0x626d0441"))
    target.update(changes)
    event = _parse(raw)
    leg = next(m for m in event.markets if _prefix(m) == "0x626d0441")
    return event, leg


def test_the_fixture_is_the_retained_capture():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256


# ── W4: the DTO keeps the venue's UMA status ────────────────────────────────


def test_the_dto_parses_uma_resolution_status_from_the_real_bytes():
    event = _parse(_raw())
    assert len(event.markets) == 13, "the parse must not drop a leg"
    statuses = {_prefix(m): m.uma_resolution_status for m in event.markets}
    assert {p for p, s in statuses.items() if s == "resolved"} == RESOLVED
    assert all(s is None for p, s in statuses.items() if p not in RESOLVED)


@pytest.mark.parametrize(
    "raw_value, parsed",
    [
        ("resolved", "resolved"),
        ("  Resolved ", "Resolved"),
        ("proposed", "proposed"),
        ("", None),
        ("   ", None),
        (None, None),
        (1, None),
        (["resolved"], None),
    ],
)
def test_a_malformed_uma_status_is_none_and_never_costs_the_market(raw_value, parsed):
    event, leg = _one_resolved_leg_changed(umaResolutionStatus=raw_value)
    assert len(event.markets) == 13
    assert leg.uma_resolution_status == parsed


def test_an_absent_uma_status_is_none():
    raw = _raw()
    for m in raw["markets"]:
        m.pop("umaResolutionStatus", None)
    assert all(m.uma_resolution_status is None for m in _parse(raw).markets)


# ── W3: the admission rule ──────────────────────────────────────────────────


def test_exactly_the_six_resolved_legs_are_admissible_on_the_real_bytes():
    event = _parse(_raw())
    admitted = {
        _prefix(m) for m in event.markets
        if resolved_zero_leg_admitted(event, m, "economics")
    }
    assert admitted == RESOLVED


def test_only_the_two_legs_the_resolver_declines_reach_the_arm():
    """The loop asks the rule only of a leg it would otherwise drop."""
    event = _parse(_raw())
    declined = {
        _prefix(m) for m in event.markets
        if _resolve_market_probability_with_source(m)[0] is None
    }
    reached = {
        p for p in declined
        if resolved_zero_leg_admitted(
            event, next(m for m in event.markets if _prefix(m) == p), "economics"
        )
    }
    assert reached == DECLINED_TODAY
    # The three open legs the empty-book gates refuse stay refused: this slice
    # does not make 106884's roster whole, and the test says so.
    assert declined - reached == {"0x8f6e229b", "0xee626bbe", "0xc55bf124"}


def test_the_domain_set_is_lane1s_supported_set():
    assert RESOLVED_ZERO_LEG_DOMAINS == frozenset(
        {"politics", "geopolitics", "economics", "tech", "entertainment"}
    )
    try:
        from app.utils.provider_event_collections import SUPPORTED_DOMAINS
    except ImportError:  # lane1's PR #10916 not landed yet
        return
    assert RESOLVED_ZERO_LEG_DOMAINS == SUPPORTED_DOMAINS


@pytest.mark.parametrize("domain", sorted(RESOLVED_ZERO_LEG_DOMAINS))
def test_every_supported_domain_admits(domain):
    event, leg = _one_resolved_leg_changed()
    assert resolved_zero_leg_admitted(event, leg, domain) is True


@pytest.mark.parametrize(
    "domain", ["football", "basketball", "tennis", "weather", "crypto", "other", "", None]
)
def test_an_unsupported_or_unknown_domain_refuses(domain):
    event, leg = _one_resolved_leg_changed()
    assert resolved_zero_leg_admitted(event, leg, domain) is False


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"umaResolutionStatus": "proposed"}, id="proposed"),
        pytest.param({"umaResolutionStatus": "disputed"}, id="disputed"),
        pytest.param({"umaResolutionStatus": None}, id="status-null"),
        pytest.param({"outcomePrices": '["0.002", "0.998"]'}, id="dust"),
        pytest.param({"outcomePrices": '["0", "0.999"]'}, id="not-exactly-one"),
        pytest.param({"outcomePrices": '["1", "0"]'}, id="resolved-yes"),
        pytest.param({"outcomePrices": '["0"]'}, id="one-price"),
        pytest.param({"outcomePrices": "[]"}, id="no-price"),
        pytest.param({"closed": False}, id="open-at-zero"),
        pytest.param({"negRisk": True}, id="negrisk-leg"),
        pytest.param(
            {"groupItemTitle": "Player AB", "question": "Will Player AB win?"},
            id="placeholder",
        ),
    ],
)
def test_one_changed_field_refuses(changes):
    event, leg = _one_resolved_leg_changed(**changes)
    assert resolved_zero_leg_admitted(event, leg, "economics") is False


def test_a_negrisk_event_refuses():
    raw = _raw()
    raw["negRisk"] = True
    event = _parse(raw)
    assert not any(resolved_zero_leg_admitted(event, m, "economics") for m in event.markets)


def test_a_single_market_event_refuses():
    raw = _raw()
    raw["markets"] = [m for m in raw["markets"] if m["conditionId"].startswith("0x626d0441")]
    event = _parse(raw)
    assert len(event.markets) == 1
    assert resolved_zero_leg_admitted(event, event.markets[0], "economics") is False
