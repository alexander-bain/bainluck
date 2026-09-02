"""#2560: the frontend never links to a tournament hub the backend will not serve.

`frontend/lib/tournamentHubs.ts` is a hard-coded map of showcase-event name ->
hub slug, and `/sport/tennis` uses it to turn the "US Open" Grand Slam tile into
a link during the tournament instead of a card reading *"Date TBD — odds
available closer to the event"*.

A constant is the right shape for it — servable slugs are an allowlist
(`REGISTERED_TOURNAMENTS` here) with no endpoint that publishes them, and adding
a hub is a backend deploy that writes that allowlist, so the two move together.
"Move together" is a claim, and this file is the thing that makes it one: a slug
in the TypeScript map that is not in the Python allowlist is a link straight to
a 404, and it would ship green in every frontend gate because nothing on that
side can see this dict.

THE PARSE RAISES. A guard that shrugs when it cannot read the map is a guard
that goes quiet the first time somebody reformats the file — the zero-yield
failure this suite would otherwise have. If the map cannot be found or comes
back empty, that is a failure here, not a pass.
"""

import re
from pathlib import Path

import pytest

from app.routes.tournaments import REGISTERED_TOURNAMENTS

HUBS_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "tournamentHubs.ts"
)

_ENTRY = re.compile(r'"([^"]+)"\s*:\s*"([a-z0-9-]+)"')


def _frontend_map() -> dict[str, str]:
    assert HUBS_TS.is_file(), (
        f"{HUBS_TS} is gone. If the hub map moved, move this guard with it — "
        "do not delete it: the thing it prevents is a link to a slug this "
        "service does not serve."
    )
    source = HUBS_TS.read_text()
    marker = "export const TOURNAMENT_HUB_SLUGS"
    start = source.find(marker)
    assert start != -1, (
        f"could not find `{marker}` in {HUBS_TS.name}. The guard cannot read "
        "the map, so it cannot check it — this is a failure, not a skip."
    )
    body = source[start : source.index("}", start)]
    entries = dict(_ENTRY.findall(body))
    assert entries, (
        "parsed the map and found no entries. Either the literal changed shape "
        "or the regex stopped matching it; either way nothing was checked."
    )
    return entries


def test_the_guard_can_read_the_map_it_guards():
    """The control. Without it every assertion below is vacuously true."""
    entries = _frontend_map()
    assert "US Open" in entries
    assert entries["US Open"] == "us-open"


def test_every_frontend_hub_slug_is_servable():
    for name, slug in _frontend_map().items():
        assert slug in REGISTERED_TOURNAMENTS, (
            f"frontend/lib/tournamentHubs.ts routes {name!r} to "
            f"/tournaments/{slug}, which this service does not serve. "
            f"Servable: {sorted(REGISTERED_TOURNAMENTS)}"
        )


def test_a_removed_hub_is_caught_rather_than_shipped(monkeypatch):
    """RED-FIRST: retire the hub and the guard goes red.

    The failure this file exists for is asymmetric — the backend deletes a
    tournament when its season ends, and nothing on the frontend notices.
    """
    monkeypatch.setattr(
        "app.routes.tournaments.REGISTERED_TOURNAMENTS", {}, raising=True
    )
    from app.routes import tournaments as tournaments_module

    with pytest.raises(AssertionError):
        for name, slug in _frontend_map().items():
            assert slug in tournaments_module.REGISTERED_TOURNAMENTS, name
