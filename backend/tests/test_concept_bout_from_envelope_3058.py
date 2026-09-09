"""#3058 coverage half — a fight card names BOTH fighters, not just the favourite.

ux/1070 item 2 gave the concept card its main event as a bout and fixed the loud
half of #3058: the card no longer leads with the most lopsided fight of the night.
`test_concept_headline_bout_1070.py` pins that. What it did not fix is REACH.
`_attach_headline_bouts` keys on `main_event_id`, and `list_card_concepts` only
sets that on the Kalshi branch — an events-table-only card gets ``None``
(`event_combat.py`), so it can never be attached.

Measured on production 2026-09-09, `GET /api/feed?limit=250`, edition
`65262ed88e6057a7`: **2 of 9** UFC concept cards carried a `headline_bout`. The
other seven printed one name and one percentage for a two-participant question —
Alex's original sentence, *"a two-fighter bout rendered as a one-line outright
card"*, still true after the wrong-fight half was fixed:

    Manel Kape vs Joshua Van          card printed "Manel Kape 62%"
    Alex Volkanovski vs Movsar Evloev card printed "Alex Volkanovski 50%"

and yet each card's cached envelope, which `_resolve_concept_leader` had ALREADY
read to produce that very number, held both priced sides:

    event:ufc:26dec27  Manel Kape 0.6211 / Joshua Van 0.3789    (sums to 1.0000)
    event:ufc:26oct25  Volkanovski 0.5043 / Evloev 0.4957       (sums to 1.0000)

So the complement was being computed and discarded. These tests pin that it is
kept, that keeping it does not change any card that already had a bout, and that
the archetype gate holds — a field is not a bout however few entries it has.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    _bout_from_competitors,
    _resolve_concept_leader,
    _score_event_concepts,
)

# The real `primary.kind` a combat concept publishes. `event_combat.py` is the
# only producer of it, and its `competitors` ARE the main event's two sides
# ("label": "Main event") — which is what makes this derivation legitimate
# rather than a guess about which fight the list belongs to.
COMBAT_KIND = "co_equal_list"

#: Verbatim from `GET /api/event/event:ufc:26dec27`, production 2026-09-09.
#: This card is one of the seven: it had NO `headline_bout` and printed one name.
KAPE_VAN = [
    {"name": "Manel Kape", "probability": 0.6211},
    {"name": "Joshua Van", "probability": 0.3789},
]


def _envelope(competitors, kind=COMBAT_KIND):
    return {"primary": {"kind": kind, "label": "Main event", "competitors": competitors}}


class TestTheDerivation:
    """`_bout_from_competitors` — the pure half."""

    def test_the_measured_production_shape_becomes_a_bout(self):
        bout = _bout_from_competitors(_envelope(KAPE_VAN)["primary"], KAPE_VAN)
        assert bout == {
            "competitors": [
                {"name": "Manel Kape", "probability": 0.6211},
                {"name": "Joshua Van", "probability": 0.3789},
            ],
            "commence_time": None,
        }

    def test_the_favourite_leads_even_when_the_envelope_does_not(self):
        """Same rule the leader follows: take the max, never trust the order.

        An adapter that changed its sort would otherwise make the card lead with
        the underdog — #1860's "the top line reads as the answer, and the answer
        is the complement"."""
        underdog_first = list(reversed(KAPE_VAN))
        bout = _bout_from_competitors({"kind": COMBAT_KIND}, underdog_first)
        assert [c["name"] for c in bout["competitors"]] == ["Manel Kape", "Joshua Van"]

    def test_a_field_is_not_a_bout_however_small_it_gets(self):
        """The archetype gate, and the reason it is not just `len == 2`.

        `event:f1:italian-grand-prix-2026` published `winner_field` with 22
        drivers on production 2026-09-09. A Grand Prix, a Grand Tour or a golf
        major is an outright even on a day its priced field thins to two, and
        rendering it as a bout is Queue #250's "0 fights on the card" mistake in
        the other direction."""
        assert _bout_from_competitors({"kind": "winner_field"}, KAPE_VAN) is None

    def test_a_card_of_many_priced_entries_is_not_a_bout(self):
        three = KAPE_VAN + [{"name": "Tai Tuivasa", "probability": 0.84}]
        assert _bout_from_competitors({"kind": COMBAT_KIND}, three) is None
        assert _bout_from_competitors({"kind": COMBAT_KIND}, KAPE_VAN[:1]) is None

    def test_one_fighter_read_twice_is_not_a_bout(self):
        """"Kape 62% / Kape 38%" is worse than the one-line card it replaces."""
        doubled = [
            {"name": "Manel Kape", "probability": 0.6211},
            {"name": "manel  kape", "probability": 0.3789},
        ]
        assert _bout_from_competitors({"kind": COMBAT_KIND}, doubled) is None

    def test_an_unnamed_or_impossible_side_is_refused(self):
        """The same admission test both renderers apply, applied before serving."""
        assert (
            _bout_from_competitors(
                {"kind": COMBAT_KIND},
                [{"name": "  ", "probability": 0.6}, {"name": "B", "probability": 0.4}],
            )
            is None
        )
        # gotcha #23: an independent-binary field can sum past 100%; a single
        # side over 1.0 is corrupt rather than merely confident.
        assert (
            _bout_from_competitors(
                {"kind": COMBAT_KIND},
                [{"name": "A", "probability": 1.4}, {"name": "B", "probability": 0.4}],
            )
            is None
        )


def _servable(payload: dict) -> str:
    from app.utils.event_concept_cache import stamp_envelope

    return json.dumps(
        stamp_envelope(
            payload,
            # Offset from now, never a pinned hour (gotcha #44) — the mirror tier
            # is age-bounded, so a pinned date would re-decide its own verdict.
            created_at=datetime.now(timezone.utc) - timedelta(seconds=30),
            lifecycle_watermark=None,
        ),
        default=str,
    )


@pytest.fixture
def cached_envelope(monkeypatch):
    """Serve one envelope out of Redis, the way production serves it.

    Deliberately built on the real `co_equal_list` kind rather than the
    `head_to_head` string the older leader fixtures use — `head_to_head` is a
    `competitive_structure` in `event_taxonomy.py` and is never a `primary.kind`,
    so a fixture using it cannot reach this path at all.
    """

    def _install(envelope):
        import app.utils.event_concept as ec
        import app.utils.request_cache as rc

        monkeypatch.setattr(ec, "parse_event_key", lambda key: ("ufc", "slug"))
        raw = _servable(envelope)

        class _Result:
            is_ok = True
            value = [raw, None]

        async def _bounded(_fn):
            return _Result()

        async def _shared():
            return object()

        monkeypatch.setattr(rc, "bounded_redis_call", _bounded)
        monkeypatch.setattr(rc, "get_shared_async_redis", _shared)

    return _install


class TestTheResolverReturnsBoth:
    async def test_the_seven_cards_now_carry_their_bout(self, cached_envelope):
        cached_envelope(_envelope(KAPE_VAN))
        leader, bout = await _resolve_concept_leader(None, "event:ufc:26dec27")
        assert leader["name"] == "Manel Kape"
        assert [c["name"] for c in bout["competitors"]] == ["Manel Kape", "Joshua Van"]
        # One list, one envelope, one source — so the pair cannot be assembled
        # into a sum that is not 100 (#2582's class).
        assert sum(c["probability"] for c in bout["competitors"]) == pytest.approx(1.0)

    async def test_an_outright_still_resolves_a_leader_and_no_bout(
        self, cached_envelope
    ):
        cached_envelope(_envelope(KAPE_VAN, kind="winner_field"))
        leader, bout = await _resolve_concept_leader(None, "event:f1:gp")
        assert leader is not None and leader["name"] == "Manel Kape"
        assert bout is None, "a two-driver Grand Prix is still an outright"


def _concept(key, name, *, bout=None, status="upcoming", when=None):
    c = {
        "key": key,
        "name": name,
        "domain": "ufc",
        "status": status,
        "is_major": False,
        "fight_count": 3,
        "entry_count": 0,
        "start_date": when.isoformat(),
        "latest_commence": when,
    }
    if bout is not None:
        c["headline_bout"] = bout
    return c


@pytest.fixture
def served(monkeypatch):
    """Drive the SERVING path — `_score_event_concepts` — not just the helper.

    `test_feed_concept_no_inventory_counts_4066.py` records why: a guard on a
    helper is a guard on nothing until it also proves the helper is reached.
    Returns a callable taking the listed concepts and the (leader, bout) the
    resolver should produce, and giving back the serialized `data` dicts.
    """

    async def _run(listed, resolver_result, *, whathit=False):
        import app.utils.event_concept_population as pop
        import app.utils.majors_calendar as mc

        async def _fake_list_all_concepts(db, **_kw):
            return [dict(c) for c in listed]

        monkeypatch.setattr(pop, "list_all_concepts", _fake_list_all_concepts)

        async def _fake_leader(_db, _key):
            return resolver_result

        async def _fake_champion(_db, _key):
            return {"winner": "Manel Kape", "result_summary": "Won by KO"}

        monkeypatch.setattr("app.routes.feed._resolve_concept_leader", _fake_leader)
        monkeypatch.setattr("app.routes.feed._resolve_concept_champion", _fake_champion)

        # `marquee_pin_state` is imported inside `_score_event_concepts`, so the
        # patch has to land on its defining module.
        keys = {c["key"]: {"marquee": True} for c in listed}
        monkeypatch.setattr(
            mc, "calendar_entry_by_concept_key", lambda *a, **k: keys if whathit else {}
        )
        monkeypatch.setattr(
            mc,
            "marquee_pin_state",
            lambda *a, **k: "whathit" if whathit else None,
        )

        items = await _score_event_concepts(
            db=None, now=datetime.now(timezone.utc), sport_filter=None
        )
        return [i["data"] for i in items]

    return _run


LEADER = {"name": "Manel Kape", "probability": 0.6211, "field_size": 2}
ENVELOPE_BOUT = {"competitors": KAPE_VAN, "commence_time": None}


class TestTheFeedServesTheCoverage:
    async def test_the_ship_a_card_with_no_attached_bout_now_serves_one(self, served):
        """THE SHIP. `event:ufc:26dec27` as production listed it: no
        `headline_bout`, because its main event never came from Kalshi."""
        when = datetime.now(timezone.utc) + timedelta(hours=6)
        data = await served(
            [_concept("event:ufc:26dec27", "Manel Kape vs Joshua Van", when=when)],
            (LEADER, ENVELOPE_BOUT),
        )
        assert len(data) == 1
        assert [c["name"] for c in data[0]["headline_bout"]["competitors"]] == [
            "Manel Kape",
            "Joshua Van",
        ]

    async def test_the_control_no_envelope_bout_serves_no_bout(self, served):
        """Guard the guard.

        If the harness put a bout on every card, the test above would pass with
        the fix reverted. Same listed concept, same everything, resolver returns
        no bout — the key must be ABSENT (not null): the payload uses presence as
        the renderer's test, and every shipped iOS build ignores what it has not
        learned.
        """
        when = datetime.now(timezone.utc) + timedelta(hours=6)
        data = await served(
            [_concept("event:ufc:26dec27", "Manel Kape vs Joshua Van", when=when)],
            (LEADER, None),
        )
        assert len(data) == 1
        assert "headline_bout" not in data[0]

    async def test_an_attached_bout_wins_and_keeps_its_commence_time(self, served):
        """A pure coverage change: no card that already had a bout is altered.

        The attached bout is the main event's own `futures_outcomes` pair and
        carries a real time; the envelope pair carries none, so preferring the
        envelope would replace a known bout time with the card's start date.
        """
        when = datetime.now(timezone.utc) + timedelta(hours=6)
        attached = {
            "competitors": [
                {"name": "Jean Silva", "probability": 0.78},
                {"name": "Jose Delgado", "probability": 0.215},
            ],
            "commence_time": "2026-09-13T03:40:00+00:00",
        }
        data = await served(
            [
                _concept(
                    "event:ufc:26sep12",
                    "Fight Night: Silva vs Delgado",
                    bout=attached,
                    when=when,
                )
            ],
            (LEADER, ENVELOPE_BOUT),
        )
        assert data[0]["headline_bout"] == attached
        assert data[0]["headline_bout"]["commence_time"] == "2026-09-13T03:40:00+00:00"

    async def test_settled_means_settled_a_whathit_card_serves_neither(self, served):
        """The behavioural half of `1070`'s exclusivity guard.

        A card in its WHAT-HIT window leads with the result. Both the leader and
        the bout are prices that are now history, and neither may appear —
        including the bout the envelope would happily supply.
        """
        when = datetime.now(timezone.utc) - timedelta(hours=6)
        data = await served(
            [
                _concept(
                    "event:ufc:26dec27",
                    "Manel Kape vs Joshua Van",
                    bout=ENVELOPE_BOUT,
                    status="settled",
                    when=when,
                )
            ],
            (LEADER, ENVELOPE_BOUT),
            whathit=True,
        )
        assert len(data) == 1, "the WHAT-HIT card itself must still be served"
        assert data[0]["marquee_whathit"] is True
        assert "headline_bout" not in data[0]
        assert "leader" not in data[0]
        assert data[0]["winner"] == "Manel Kape"
