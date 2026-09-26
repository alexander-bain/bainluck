"""The taxonomy refresh must not erase `provenance:` tags it does not own. #8422.

Production, 2026-09-25/26: `odds_api_reissued_twin_sweep` tagged Fleetwood Town
v Arsenal's ghost (15313977) `provenance:duplicate-of:15314731` at 23:51Z;
`update_event_tags` (piggybacked on `discover_events`, ~every 30 min) REPLACED
the row's tags with `compute_event_tags(...)` at 00:07Z and the label was gone —
so /search?q=arsenal printed the fixture twice for ~45 of every 60 minutes.
The refresh arm selects the 500 farthest-future scheduled rows, so every
sweep's label on a fixture ≥ ~3 weeks out was wiped the same way.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import pytest

import app.tasks.taxonomy as mod
from app.utils.event_taxonomy import PROVENANCE_TAG_PREFIX, carry_provenance_tags

# The production specimen's stored tags, 23:51Z, and what `compute_event_tags`
# returned for it at 00:07Z.
GHOST_TAGS = [
    "class:other", "gender:men", "importance:playoff", "level:professional",
    "signal:blowout", "sport:soccer", "status:scheduled", "tier:4",
    "provenance:duplicate-of:15314731",
]
COMPUTED = [
    "class:other", "gender:men", "importance:playoff", "level:professional",
    "signal:blowout", "sport:soccer", "status:scheduled", "tier:4",
]


class TestCarryProvenanceTags:
    def test_the_specimens_duplicate_label_survives_the_refresh(self):
        out = carry_provenance_tags(GHOST_TAGS, COMPUTED)
        assert "provenance:duplicate-of:15314731" in out
        assert out[: len(COMPUTED)] == COMPUTED

    def test_every_provenance_kind_is_carried_in_order(self):
        existing = [
            "sport:soccer", "provenance:source:odds_api", "tier:4",
            "provenance:unanchored", "provenance:duplicate-of:9",
        ]
        out = carry_provenance_tags(existing, ["sport:soccer"])
        assert out == [
            "sport:soccer", "provenance:source:odds_api",
            "provenance:unanchored", "provenance:duplicate-of:9",
        ]

    def test_non_provenance_tags_are_still_replaced(self):
        # A stale status/signal must not ride along — the refresh is still a refresh.
        existing = ["status:scheduled", "signal:blowout", "provenance:unanchored"]
        out = carry_provenance_tags(existing, ["status:live"])
        assert out == ["status:live", "provenance:unanchored"]

    def test_no_duplicate_element_when_computed_already_has_it(self):
        out = carry_provenance_tags(
            ["provenance:unanchored", "provenance:unanchored"],
            ["provenance:unanchored"],
        )
        assert out == ["provenance:unanchored"]

    @pytest.mark.parametrize("existing", [None, [], "provenance:unanchored", {"a": 1}])
    def test_absent_or_malformed_existing_carries_nothing(self, existing):
        assert carry_provenance_tags(existing, ["sport:soccer"]) == ["sport:soccer"]

    def test_non_string_elements_are_ignored(self):
        assert carry_provenance_tags([None, 7, "provenance:x"], []) == ["provenance:x"]

    def test_the_prefix_is_the_vocabulary_the_sweeps_write(self):
        from app.services.anchor_channel import DUPLICATE_TAG_PREFIX

        assert DUPLICATE_TAG_PREFIX.startswith(PROVENANCE_TAG_PREFIX)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    async def execute(self, stmt):
        return _Result(self.rows)

    async def commit(self):
        self.commits += 1


def _run_refresh(events, monkeypatch):
    session = _Session(events)

    @contextlib.asynccontextmanager
    async def _fake():
        yield session

    async def _zero(*a, **kw):
        return 0

    async def _empty(*a, **kw):
        return {}

    # Bound names on `mod` (the task imports them into its own namespace).
    monkeypatch.setattr(mod, "get_task_session", _fake)
    monkeypatch.setattr(mod, "_update_market_tags", _zero)
    monkeypatch.setattr(mod, "_drain_missing_tags_oldest_first", _empty)
    monkeypatch.setattr(mod, "_reconcile_disagreeing_market_tags", _empty)
    monkeypatch.setattr(mod, "_tag_event", lambda event: list(COMPUTED))
    out = asyncio.run(mod._update_event_tags_impl(limit=500))
    return out, session


class TestTheRefreshArmCarriesProvenance:
    def test_the_specimen_keeps_its_label_through_update_event_tags(self, monkeypatch):
        ghost = SimpleNamespace(id=15313977, event_tags=list(GHOST_TAGS))
        out, session = _run_refresh([ghost], monkeypatch)
        assert out["events_tagged"] == 1
        assert session.commits >= 1
        assert "provenance:duplicate-of:15314731" in ghost.event_tags

    def test_a_row_with_no_provenance_gets_exactly_the_computed_set(self, monkeypatch):
        canonical = SimpleNamespace(id=15314731, event_tags=["status:live", "tier:4"])
        _run_refresh([canonical], monkeypatch)
        assert canonical.event_tags == COMPUTED
