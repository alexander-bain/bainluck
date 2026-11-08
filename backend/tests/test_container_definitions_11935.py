"""Awards ceremonies and the CFP successor use Atlas's one definition factory."""

import json

from app.utils import roundup_containers as roundups
from app.utils.awards_ceremony import awards_ceremony_definition
from app.utils.awards_occasion_finder import find_awards_occasions
from tests.test_field_selection_11935 import definition as selection_definition


def test_a_discovered_ceremony_registers_from_a_file_without_a_named_python_list(
    tmp_path, monkeypatch
):
    found = find_awards_occasions(
        [
            {
                "provider": "kalshi",
                "event_ticker": "KXNEW-FILM42",
                "markets": [
                    {"rules_primary": "If Film A wins at the 17th New Film Awards."}
                ],
            }
        ]
    )
    definition = awards_ceremony_definition(found.occasions[0].selector)
    (tmp_path / "new-ceremony.json").write_text(json.dumps(definition))
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {})
    registered = roundups.register_roundup_definitions_from_dir(tmp_path)
    producer = registered[definition["slug"]]
    assert producer.name == found.occasions[0].label
    assert producer.relations == ("same_event",)
    assert producer.level == "member"
    assert producer.enabled() is False
    assert producer.slug in roundups.ROUNDUP_PRODUCERS


def test_the_dated_cfp_successor_registers_through_the_same_folder(
    tmp_path, monkeypatch
):
    definition = selection_definition()
    (tmp_path / "selected-field.json").write_text(json.dumps(definition))
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {})
    producer = roundups.register_roundup_definitions_from_dir(tmp_path)[
        definition["slug"]
    ]
    assert producer.relations == ("same_event", "same_window")
    assert producer.level == "member"
    assert producer.valid_from is not None
    assert producer.enabled() is False
