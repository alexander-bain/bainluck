"""A fight card holding ONE fight yields to that fight's own event card (#2620).

Served on production `/sports`, 2026-10-02 12:55Z, `fc4305f9`:

    GET /api/feed?mode=sports&limit=20            type:event   15321791
        Mohammad Fahmi vs Ahmed El Sisy           Fahmi 0.5628 / El Sisy 0.4372
    GET /api/feed?mode=sports&limit=20&offset=20  type:concept event:ufc:26oct02
        fight_count 1, headline_bout              Fahmi 0.5628 / El Sisy 0.4372

The same question twice, at the same price to four places. The fixtures below
are those two payloads; the harness drives the REAL `apply_discover_display_chain`.
"""

from datetime import datetime, timedelta, timezone

from app.routes.feed import (
    PersonalizationContext,
    _drop_single_fight_concepts_shown_as_events,
    apply_discover_display_chain,
)

#: Gotcha #44 — offset from the clock, never a literal date.
_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)
_FIGHT_AT = (_NOW + timedelta(hours=6)).replace(minute=0, second=0)


def _event(
    *,
    home="Ahmed El Sisy",
    away="Mohammad Fahmi",
    sport="mma_mixed_martial_arts",
    commence=None,
    score=72,
    event_id=15321791,
):
    return {
        "type": "event",
        "score": score,
        "reason": "Close matchup",
        "data": {
            "id": event_id,
            "sport": sport,
            "home_team": home,
            "away_team": away,
            "commence_time": (commence or _FIGHT_AT).isoformat(),
            "status": "scheduled",
            "current_home_prob": 0.4372,
            "current_away_prob": 0.5628,
        },
        "_sort_time": (commence or _FIGHT_AT).timestamp(),
    }


def _concept(*, fight_count=1, key=None, start_date=None, is_marquee=False, pin=False):
    key = key or "event:ufc:" + _FIGHT_AT.strftime("%y%b%d").lower()
    return {
        "type": "concept",
        "score": 60,
        "reason": "",
        "headline": "Tomorrow",
        "data": {
            "key": key,
            "name": "Mohammad Fahmi vs Ahmed El Sisy",
            "domain": "ufc",
            "status": "open",
            "start_date": start_date,
            "is_major": False,
            "fight_count": fight_count,
            "entry_count": 0,
            "is_marquee": is_marquee,
            "marquee_whathit": False,
            "price_observed_at": None,
            "headline_bout": {
                "competitors": [
                    {"name": "Mohammad Fahmi", "probability": 0.5628},
                    {"name": "Ahmed El Sisy", "probability": 0.4372},
                ],
                "commence_time": _FIGHT_AT.isoformat(),
            },
        },
        "_marquee_pin": pin,
        "_sort_time": _FIGHT_AT.timestamp(),
    }


def _types(items):
    return [it["type"] for it in items]


def _kept(items):
    return _types(_drop_single_fight_concepts_shown_as_events(items))


def _chain(items, **kw):
    out, _meta = apply_discover_display_chain(
        items, limit=40, ctx=PersonalizationContext(), now=_NOW, **kw
    )
    return out


class TestTheProductionSpecimen:
    def test_sports_serves_the_bout_once(self):
        out = _chain([_event(), _concept()], event_pct=None, sports_mode=True)
        assert _types(out).count("concept") == 0
        assert [it["data"]["id"] for it in out if it["type"] == "event"] == [15321791]

    def test_the_event_card_is_the_one_kept(self):
        assert _kept([_concept(), _event()]) == ["event"]

    def test_start_date_is_read_when_present(self):
        concept = _concept(key="event:ufc:unreadable", start_date=_FIGHT_AT.isoformat())
        assert _kept([_event(), concept]) == ["event"]


class TestTheOtherDirection:
    """#43 — the drop must not empty the fight off a surface."""

    def test_discover_keeps_the_concept_when_the_noise_filter_took_the_event(self):
        # Discover demotes an ordinary no-media game and its noise filter deletes
        # it; the concept is then the only card for the bout and must survive.
        out = _chain([_event(score=40), _concept()], event_pct=0.15)
        assert "event" not in _types(out)
        assert _types(out).count("concept") == 1

    def test_no_event_card_keeps_the_concept(self):
        assert _kept([_concept()]) == ["concept"]


class TestNarrowness:
    def test_a_card_with_more_fights_is_kept(self):
        assert _kept([_event(), _concept(fight_count=2)]) == ["event", "concept"]

    def test_an_unknown_fight_count_is_kept(self):
        assert _kept([_event(), _concept(fight_count=0)]) == ["event", "concept"]

    def test_a_different_bout_is_kept(self):
        other = _event(home="Christian Echols", away="Martin Kozák")
        assert _kept([other, _concept()]) == ["event", "concept"]

    def test_a_non_mma_event_with_the_same_names_is_kept(self):
        assert _kept([_event(sport="boxing_boxing"), _concept()]) == [
            "event",
            "concept",
        ]

    def test_a_rematch_on_another_night_is_kept(self):
        later = _event(commence=_FIGHT_AT + timedelta(days=30))
        assert _kept([later, _concept()]) == ["event", "concept"]

    def test_a_marquee_card_is_kept(self):
        assert _kept([_event(), _concept(is_marquee=True)]) == ["event", "concept"]
        assert _kept([_event(), _concept(pin=True)]) == ["event", "concept"]

    def test_an_unreadable_date_is_kept(self):
        concept = _concept(key="event:ufc:unreadable", start_date=None)
        assert _kept([_event(), concept]) == ["event", "concept"]


class TestOneBadItem:
    def test_an_unreadable_event_does_not_wipe_the_pass(self):
        broken = {"type": "event", "data": "not-a-dict"}
        assert _kept([broken, _event(), _concept()]) == ["event", "event"]

    def test_an_unreadable_concept_is_kept(self):
        broken = {"type": "concept", "data": "not-a-dict"}
        assert _kept([_event(), broken]) == ["event", "concept"]
