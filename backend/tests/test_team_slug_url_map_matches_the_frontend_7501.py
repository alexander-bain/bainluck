"""#7501 — the ported league map cannot drift from the TypeScript it mirrors.

`URL_LEAGUE_SEGMENT` is the league half of `SPORT_KEY_TO_PATH` in
`frontend/lib/teamUrls.ts`, copied into Python because the backend has to mint a
slug the frontend's URL will resolve and there is no shared source for that map.
A copy with no guard is a copy that is right on the day it is written.

The failure this catches is silent in both directions. Add `soccer_italy_serie_a`
to the TS map with league `seriea` and the fill keeps suffixing `italy_serie_a`:
every Serie A club gets a non-NULL slug, the census reads the ship as delivered,
and not one of their pages resolves. Delete a key from the TS map and the reverse
happens. Neither shows up in a route test, because the route is asked for the
slug the fill wrote.

Same device as `shippedCopyBans`: the guard reads the other stack's file.
"""

import re
from pathlib import Path

import pytest

from app.utils.team_slug import URL_LEAGUE_SEGMENT, url_league_segment

TEAM_URLS_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "teamUrls.ts"
)

#: `soccer_epl: { sport: "soccer", league: "epl" },`
_ENTRY = re.compile(
    r'(?P<key>[a-z0-9_]+)\s*:\s*\{\s*sport:\s*"(?P<sport>[^"]+)"\s*,'
    r'\s*league:\s*"(?P<league>[^"]+)"\s*,?\s*\}'
)


def _frontend_map() -> dict[str, str]:
    source = TEAM_URLS_TS.read_text(encoding="utf-8")
    block = source.split("SPORT_KEY_TO_PATH", 1)[1].split("};", 1)[0]
    return {m["key"]: m["league"] for m in _ENTRY.finditer(block)}


class TestTheMapIsInSync:
    def test_the_frontend_file_is_where_we_think_it_is(self):
        """The anti-vacuous arm. A moved or renamed `teamUrls.ts` would make
        `_frontend_map()` raise or return `{}`, and a comparison against an
        empty dict is a guard that passes by knowing nothing."""
        assert TEAM_URLS_TS.is_file(), TEAM_URLS_TS
        assert "buildTeamPageUrl" in TEAM_URLS_TS.read_text(encoding="utf-8")

    def test_the_parser_reads_the_whole_map(self):
        """Second anti-vacuous arm: the regex must actually match. A tweak to
        the TS formatting that broke it would otherwise silently shrink both
        sides of the comparison below to nothing."""
        parsed = _frontend_map()
        assert len(parsed) >= 15, parsed
        assert parsed["soccer_uefa_champs_league"] == "ucl"

    def test_every_frontend_key_has_the_same_league_segment_here(self):
        assert _frontend_map() == URL_LEAGUE_SEGMENT

    @pytest.mark.parametrize(
        "sport_key,expected",
        [
            ("soccer_efl_champ", "efl_champ"),
            ("tennis_atp_us_open", "atp_us_open"),
            ("baseball_npb", "npb"),
        ],
    )
    def test_the_unmapped_fallback_matches_the_frontends(self, sport_key, expected):
        """`buildTeamPageUrl`'s second branch: `parts.slice(1).join("_")`.
        Most of the 4,004 slug-less rows sit on keys that are NOT in the map, so
        the fallback carries more of this ship than the map does."""
        assert url_league_segment(sport_key) == expected
