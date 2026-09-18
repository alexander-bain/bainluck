"""#6919 — the drain may never close a market the venue still lists as open.

THE CLASS THIS GUARDS. `repair_6919_stranded_settled_polymarket_markets.py`
selects candidates with the same structural predicate the rail uses — every leg
carries a `resolution_source` — and that predicate is NOT a statement that the
question has been answered. Measured on production 2026-09-18: it returns 7
markets, and 2 of them are live tier-2 ladders. "Will Russia enter Pokrovskoe
by...?" has four passed sub-deadlines graded No and a December leg still trading
at 0.17; "Next Prime Minister of Romania?" has 49 graded legs, zero winners, and
the venue has closed none of them. Closing either retires a live market from the
site.

So the tests below are written against those two rows as fixtures, plus one of
the five that SHOULD drain. A change that widens the gate has to make one of
these fail.
"""
from types import SimpleNamespace

import pytest

from scripts.repair_6919_stranded_settled_polymarket_markets import (
    backup_is_exact,
    classify,
    venue_event,
    venue_says_settled,
    wrong_app_refusal,
)


def _row(winners, market_id=1, status="open"):
    return SimpleNamespace(id=market_id, winners=winners, status=status,
                           market_tier=5, legs=1, name="x", external_id="1",
                           settled_at=None)


def _venue(closed, children, children_closed, active=True, reachable=True):
    return {"reachable": reachable, "event_closed": closed, "children": children,
            "children_closed": children_closed, "event_active": active,
            "reason": "" if reachable else "unreachable"}


# --- the settled baseball specimen -----------------------------------------

def test_drains_a_venue_closed_market_with_a_winner():
    """60755454: venue closed, 1/1 children closed, one winning leg."""
    bucket, _ = classify(_row(winners=1), _venue(True, 1, 1))
    assert bucket == "drain"


# --- the two live ladders that must survive --------------------------------

def test_refuses_pokrovskoe_a_partly_closed_live_event():
    """128775: 4 of 5 children closed, event OPEN, no winner. Must not drain."""
    bucket, why = classify(_row(winners=0), _venue(False, 5, 4))
    assert bucket == "refused"
    assert "still lists this as open" in why


def test_refuses_romania_49_graded_legs_and_no_winner():
    """16634605: every leg graded, ZERO closed at the venue. Must not drain."""
    bucket, _ = classify(_row(winners=0), _venue(False, 49, 0))
    assert bucket == "refused"


def test_a_partly_closed_event_is_never_settled_even_with_a_winner():
    """4/5 is a live question wearing settled sub-deadlines, not a rounding error."""
    assert venue_says_settled(_venue(True, 5, 4)) is False


# --- the specific misreadings that would drain everything ------------------

def test_active_is_not_the_discriminator():
    """All 7 production candidates are active:true, both refusals included.

    A gate keyed on `active` drains the live ladders, so `active` must not be
    able to carry a verdict on its own.
    """
    assert venue_says_settled(_venue(False, 49, 0, active=True)) is False
    assert venue_says_settled(_venue(True, 1, 1, active=True)) is True


def test_an_event_with_no_children_is_not_settled():
    """`children_closed == children` is vacuously true at 0 == 0.

    That is the same empty-`all()` trap `backup_is_exact` guards, and here it
    would drain any event whose market list came back empty — including one the
    venue simply declined to enumerate (gotcha #53).
    """
    assert venue_says_settled(_venue(True, 0, 0)) is False


def test_an_unreachable_venue_never_authorises_a_close():
    """A failed read is a response shape, not permission."""
    assert venue_says_settled(_venue(True, 1, 1, reachable=False)) is False
    bucket, _ = classify(_row(winners=1), _venue(True, 1, 1, reachable=False))
    assert bucket == "refused"


# --- the second signal, and disagreement -----------------------------------

@pytest.mark.parametrize(
    "winners, venue, expected",
    [
        (0, _venue(True, 1, 1), "disagreed"),   # venue closed, nobody won
        (1, _venue(False, 5, 4), "disagreed"),  # a winner, venue still open
    ],
)
def test_conflicting_signals_are_reported_not_tie_broken(winners, venue, expected):
    """Two gates exist to produce this warning; preferring one discards it."""
    bucket, why = classify(_row(winners=winners), venue)
    assert bucket == expected
    assert "disagree" in why


def test_zero_winner_market_is_never_drained_by_either_route():
    """`status='resolved'` is calibration's population gate.

    A family the venue voided by resolving every bucket "No" must not enter the
    accuracy curve as a question nobody won, whatever the venue's closed flag
    says. Neither `drain` is reachable with winners=0.
    """
    for venue in (_venue(True, 1, 1), _venue(False, 5, 4), _venue(True, 3, 3)):
        bucket, _ = classify(_row(winners=0), venue)
        assert bucket != "drain"


# --- fail-closed on what cannot be verified --------------------------------

def test_a_non_numeric_external_id_is_refused_without_a_network_call():
    """A 64-hex condition is not addressable at /events/{id}.

    `/markets?condition_ids=` omits closed markets unless `&closed=true`, so a
    naive fallback would read "settled" as an empty list. Refuse by name instead.
    """
    v = venue_event("0x41bec5ebc5302804aa")
    assert v["reachable"] is False
    assert "unverifiable" in v["reason"]


def test_an_empty_external_id_is_refused():
    assert venue_event("")["reachable"] is False


def test_the_venue_call_carries_a_user_agent_gamma_will_serve(monkeypatch):
    """Gamma answers urllib's default `Python-urllib/3.x` with 403 Forbidden.

    Notice 39 routes every outbound call through `tagged()`, and for a
    third-party host that correctly returns `{}` — so `headers=tagged(url)`
    alone leaves the default UA in place and every venue read fails. Measured:
    it degraded all seven candidates to `reachable: False`. Fail-closed, so it
    could not drain anything wrong, but the drain would do nothing at all, and
    the CI tag guard cannot see it because it reads the call site, not the
    response. The two-argument form of `tagged()` MERGES, which is why it is
    used here; this test is what stops someone "simplifying" it back.
    """
    import urllib.request as ur

    from scripts import repair_6919_stranded_settled_polymarket_markets as mod

    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        raise OSError("stop here — the header is what is under test")

    monkeypatch.setattr(ur, "urlopen", fake_urlopen)
    mod.venue_event("1004380")

    assert seen.get("ua"), "no User-Agent was set on the venue request"
    assert "python-urllib" not in seen["ua"].lower()


# --- D51 and notice 47(c) ---------------------------------------------------

def test_backup_is_exact_refuses_a_reconciliation_that_checked_nothing():
    assert backup_is_exact({}) is False
    assert backup_is_exact({"futures_markets": 0}) is True
    assert backup_is_exact({"futures_markets": 3}) is False


def test_write_refused_off_the_named_app(monkeypatch):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert wrong_app_refusal(SimpleNamespace(apply=True, backup=False))
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert wrong_app_refusal(SimpleNamespace(apply=False, backup=True))
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert wrong_app_refusal(SimpleNamespace(apply=True, backup=False)) is None


def test_a_dry_run_is_permitted_anywhere(monkeypatch):
    """Plan-only reads nothing it may not read, so it must not need a dyno."""
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert wrong_app_refusal(SimpleNamespace(apply=False, backup=False)) is None
