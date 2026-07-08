"""#999 slice 1: generic event-concept core (key parsing + golf envelope)."""

from app.utils.event_concept import (
    parse_event_key,
    golf_detail_to_envelope,
    get_adapter,
    registered_domains,
)


class TestParseEventKey:
    def test_canonical_form(self):
        assert parse_event_key("event:golf:2026-masters") == ("golf", "2026-masters")
        assert parse_event_key("event:tennis:wimbledon-2026") == ("tennis", "wimbledon-2026")

    def test_domain_slug_form(self):
        assert parse_event_key("golf:2026-masters") == ("golf", "2026-masters")

    def test_slug_may_contain_colons(self):
        # only the domain segment is split off
        assert parse_event_key("event:ufc:ufc-310:main") == ("ufc", "ufc-310:main")

    def test_bare_slug_defaults_to_golf(self):
        assert parse_event_key("2026-masters") == ("golf", "2026-masters")


class TestRegistry:
    def test_golf_adapter_registered(self):
        assert "golf" in registered_domains()
        adapter = get_adapter("golf")
        assert adapter is not None and adapter.domain == "golf"

    def test_unknown_domain_returns_none(self):
        assert get_adapter("tennis") is None  # future slice


def _golf_fixture():
    return {
        "tournament": {
            "name": "The Masters",
            "key": "masters",
            "is_major": True,
            "is_womens": False,
            "start_date": "2026-04-09",
            "end_date": "2026-04-12",
            "venue": "Augusta National",
            "location": "Augusta, GA",
            "schedule_status": "completed",
        },
        "golfers": [{"name": "Scottie Scheffler", "probability": 0.22}],
        "markets": [{"type": "winner", "label": "Winner", "market_ids": [1]}],
        "related_futures": [{"market_id": 5, "market_name": "H2H: A vs B"}],
        "evolution_market_id": 1,
        "biggest_movers": [{"name": "Rory", "change": 0.05}],
    }


class TestGolfEnvelope:
    def test_maps_to_generic_envelope(self):
        env = golf_detail_to_envelope("event:golf:the-masters", "the-masters", _golf_fixture())
        assert env["event"]["domain"] == "golf"
        assert env["event"]["name"] == "The Masters"
        assert env["event"]["status"] == "settled"      # completed -> settled
        assert env["event"]["venue"] == "Augusta National"
        assert env["event"]["is_major"] is True
        assert env["primary"]["kind"] == "winner_field"
        assert env["primary"]["competitors"][0]["name"] == "Scottie Scheffler"
        assert env["primary"]["evolution_market_id"] == 1
        assert env["sections"][0]["type"] == "winner"
        assert env["children"][0]["market_name"] == "H2H: A vs B"
        assert env["movers"][0]["name"] == "Rory"

    def test_status_normalization(self):
        def status(raw):
            f = _golf_fixture(); f["tournament"]["schedule_status"] = raw
            return golf_detail_to_envelope("k", "s", f)["event"]["status"]
        assert status("in_progress") == "live"
        assert status("upcoming") == "upcoming"
        assert status("") == "upcoming"
        assert status("resolved") == "settled"

    def test_key_defaults_when_bare(self):
        env = golf_detail_to_envelope("the-masters", "the-masters", _golf_fixture())
        assert env["event"]["key"] == "event:golf:the-masters"

    def test_missing_fields_safe(self):
        env = golf_detail_to_envelope("event:golf:x", "x", {"tournament": {}})
        assert env["primary"]["competitors"] == []
        assert env["sections"] == []
        assert env["children"] == []
