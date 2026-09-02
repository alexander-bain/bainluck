"""ESPN soccer league coverage — the two ESPN maps must agree, key by key.

Why this file exists (measured 2026-09-01, production `c1397139`):

`soccer_brazil_campeonato` had **281 ingested events and 0 `espn_id`**, not
because ESPN lacks the league — `soccer/bra.1` served 21 fixtures in a ±1 week
window — but because the key was absent from the ESPN maps, so no fetch was
ever attempted.

The trap is that there are *two* maps and they do different jobs:

  * ``ESPN_SPORT_MAPPING``  is the **gate**    — ``_sync_espn_live_events``
    skips any sport key not present here (``if k in ESPN_SPORT_MAPPING``).
  * ``SPORT_LEAGUE_MAP``    is the **fetcher** — ``ESPNAPIService.get_scoreboard``
    resolves the scoreboard URL through ``_get_espn_path``, which reads this
    dict and returns ``[]`` when the key is missing.

A league added to only one of them is silently never synced: no error, no log
line, just a permanent 0% attach rate for that league. That is the class of bug
these tests catch.
"""

from app.utils.sport_keys import (
    ESPN_SPORT_MAPPING,
    EXPECTED_GAME_STATE_INDICATORS,
    SPORT_LEAGUE_MAP,
)


def _soccer_keys(mapping) -> set[str]:
    return {k for k in mapping if k.startswith("soccer_")}


class TestBrazilSerieAIsMapped:
    """The named ship: a Brazil Série A fixture can acquire an espn_id."""

    def test_brazil_serie_a_in_sport_league_map(self):
        assert SPORT_LEAGUE_MAP.get("soccer_brazil_campeonato") == ("soccer", "bra.1")

    def test_brazil_serie_a_in_espn_sport_mapping(self):
        # The gate. Without this, _sync_espn_live_events never fetches the league.
        assert ESPN_SPORT_MAPPING.get("soccer_brazil_campeonato") == "soccer/bra.1"

    def test_brazil_serie_a_has_expected_game_state(self):
        # Soccer is two halves; the admin completeness grid reads this.
        assert EXPECTED_GAME_STATE_INDICATORS.get("soccer_brazil_campeonato") == 2


class TestEspnSoccerMapsAgree:
    """The class guard — a soccer league in one ESPN map must be in the other.

    These would have been green before Brazil was added (the maps happened to
    agree on soccer); they exist so the NEXT one-map addition goes red instead
    of shipping a league that is silently never polled.
    """

    def test_every_soccer_key_in_sport_league_map_is_gated_in(self):
        missing = sorted(_soccer_keys(SPORT_LEAGUE_MAP) - _soccer_keys(ESPN_SPORT_MAPPING))
        assert not missing, (
            "soccer keys in SPORT_LEAGUE_MAP but not ESPN_SPORT_MAPPING — "
            f"_sync_espn_live_events will never fetch them: {missing}"
        )

    def test_every_gated_in_soccer_key_can_resolve_a_url(self):
        missing = sorted(_soccer_keys(ESPN_SPORT_MAPPING) - _soccer_keys(SPORT_LEAGUE_MAP))
        assert not missing, (
            "soccer keys in ESPN_SPORT_MAPPING but not SPORT_LEAGUE_MAP — "
            f"get_scoreboard resolves no path and returns []: {missing}"
        )

    def test_the_two_maps_name_the_same_espn_path(self):
        disagreements = {}
        for key in _soccer_keys(SPORT_LEAGUE_MAP) & _soccer_keys(ESPN_SPORT_MAPPING):
            sport, league = SPORT_LEAGUE_MAP[key]
            if f"{sport}/{league}" != ESPN_SPORT_MAPPING[key]:
                disagreements[key] = (f"{sport}/{league}", ESPN_SPORT_MAPPING[key])
        assert not disagreements, f"maps disagree on the ESPN path: {disagreements}"

    def test_every_mapped_soccer_league_grades_two_halves(self):
        missing = sorted(
            k for k in _soccer_keys(SPORT_LEAGUE_MAP)
            if k not in EXPECTED_GAME_STATE_INDICATORS
        )
        assert not missing, (
            f"mapped soccer leagues absent from EXPECTED_GAME_STATE_INDICATORS: {missing}"
        )


class TestControl:
    """Control — green in both arms; proves the suite runs against real maps."""

    def test_an_already_mapped_league_is_unaffected(self):
        assert SPORT_LEAGUE_MAP["soccer_epl"] == ("soccer", "eng.1")
        assert ESPN_SPORT_MAPPING["soccer_epl"] == "soccer/eng.1"

    def test_sport_keys_module_still_imports_nothing_from_the_app(self):
        # Gotcha #3 — sport_keys must stay circular-import safe.
        import pathlib

        src = pathlib.Path(
            __import__("app.utils.sport_keys", fromlist=["x"]).__file__
        ).read_text()
        assert "from app." not in src and "import app." not in src
