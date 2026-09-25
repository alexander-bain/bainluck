"""Which competition the VENUE says a Polymarket game belongs to (#8636).

A Polymarket game event's slug begins with the venue's own league code —
``bun-moe-mai-2026-09-19`` is a Bundesliga game, ``clf-vfb-fch-2026-09-25`` is a
Club Friendly, ``vbeuro-ger2-bul2-2026-09-19`` is the Volleyball European
Championship. The vocabulary is Gamma's own ``GET /sports`` listing (469 codes,
read 2026-09-25), so this is the venue's structure, not a guess about it.

WHY THIS EXISTS. A Polymarket game market carries no ticker, so the create path
can only key it to the family catch-all (``soccer_other``), and #5576's
:func:`placeable_league_for_matchup` then relabels it with the league BOTH clubs
play in. Club membership is a fact about the clubs, not about the fixture:
Stuttgart and Heidenheim are both Bundesliga clubs, so their September club
friendly was filed as a Bundesliga game and served as the top Discover card,
"BUNDESLIGA · LIVE". Measured on production 2026-09-25 over every
Polymarket-created soccer row the placer moved out of ``soccer_other`` in the
last 60 days, read against each row's Gamma slug:

    44 placed   33 agree with the venue's code
                11 do not —
                   clf     Club Friendlies           -> Bundesliga       (the specimen)
                   fif     FIFA Friendlies           -> UEFA Nations League
                   vbeuro  Volleyball Euro Champ. x5 -> UEFA Nations League
                   u20wwc  FIFA U-20 Women's WC      -> UEFA Nations League
                   uwcl    UEFA Women's Champ. Lg.   -> UEFA Champions League
                   argcopa Copa Argentina            -> Argentina Primera División
                   col1    Colombia's Primera A      -> Copa Sudamericana

Outside soccer the same read found 62 placed rows (NPB, Liiga, EuroLeague, NBL)
and 0 disagreements, which is why the check is scoped to the soccer family: the
defect lives where one club plays in many competitions, and a refusal elsewhere
would spend correct placements to buy nothing.

THE MAP IS ONE-DIRECTIONAL AND EXACT. It lists, for each soccer league the
placer can land in (every soccer key ``teams`` holds clubs for), the venue codes
that ARE that league. A code is compared as a whole token: ``col`` is the UEFA
Conference League and ``col1`` is Colombia's Primera A, and a prefix test would
file the second as the first. A league with no entry here (the venue lists no
such competition — Frauen-Bundesliga, 3. Liga, UEFA World Cup qualifying) can
still be placed into when the market carries no code, and is refused when it
carries one: the venue named a competition and it was not this one.
"""

from __future__ import annotations

import re
from typing import Optional

#: The metadata key the Polymarket ingest stamps the Gamma event slug under,
#: on the parent row and on every decomposed sub-market (the sub-market is the
#: row an event is minted from — #6073).
POLYMARKET_EVENT_SLUG_KEY = "polymarket_event_slug"

#: ``<code>-<side>-<side>-YYYY-MM-DD``, optionally followed by a market suffix
#: (``-more-markets``, ``-total-corners``, ``-first-half-exact-score``). Futures
#: and questions (``bundesliga-2027-champion-…``, ``will-cristiano-…``) do not
#: have this shape and yield no code.
_GAME_SLUG = re.compile(r"^([a-z0-9]+)-[a-z0-9]+-[a-z0-9]+-\d{4}-\d{2}-\d{2}(?:-|$)")

#: Our soccer league key -> the Polymarket league codes that ARE that league.
#: Codes and names transcribed from Gamma ``GET /sports`` on 2026-09-25; keys are
#: every soccer league ``teams`` holds clubs for on that date. Two codes for one
#: league are the venue's own duplicates (``jap``/``j1100`` both "J1 League",
#: ``ire``/``irl1`` both "League of Ireland Premier Division").
POLYMARKET_LEAGUE_CODES: dict[str, frozenset[str]] = {
    "soccer_argentina_primera_division": frozenset({"arg"}),
    "soccer_australia_aleague": frozenset({"aus"}),
    "soccer_austria_bundesliga": frozenset({"aut"}),
    "soccer_belgium_first_div": frozenset({"bel1"}),
    "soccer_brazil_campeonato": frozenset({"bra"}),
    "soccer_brazil_serie_b": frozenset({"bra2"}),
    "soccer_chile_campeonato": frozenset({"chi1"}),
    "soccer_china_superleague": frozenset({"chi"}),
    "soccer_concacaf_leagues_cup": frozenset({"lec"}),
    "soccer_conmebol_copa_libertadores": frozenset({"lib"}),
    "soccer_conmebol_copa_sudamericana": frozenset({"sud"}),
    "soccer_denmark_superliga": frozenset({"den"}),
    "soccer_efl_champ": frozenset({"elc"}),
    "soccer_england_efl_cup": frozenset({"efl"}),
    "soccer_england_league1": frozenset({"el1"}),
    "soccer_england_league2": frozenset({"el2"}),
    "soccer_epl": frozenset({"epl"}),
    "soccer_fa_cup": frozenset({"efa"}),
    "soccer_fifa_world_cup": frozenset({"fifwc"}),
    "soccer_finland_veikkausliiga": frozenset({"fin1"}),
    "soccer_france_coupe_de_france": frozenset({"cde"}),
    "soccer_france_ligue_one": frozenset({"fl1"}),
    "soccer_france_ligue_two": frozenset({"fr2"}),
    "soccer_germany_bundesliga": frozenset({"bun"}),
    "soccer_germany_bundesliga2": frozenset({"bl2"}),
    "soccer_germany_dfb_pokal": frozenset({"dfb"}),
    "soccer_greece_super_league": frozenset({"gre1"}),
    "soccer_italy_coppa_italia": frozenset({"itc"}),
    "soccer_italy_serie_a": frozenset({"sea"}),
    "soccer_italy_serie_b": frozenset({"itsb"}),
    "soccer_japan_j_league": frozenset({"jap", "j1100"}),
    "soccer_korea_kleague1": frozenset({"kor"}),
    "soccer_league_of_ireland": frozenset({"ire", "irl1"}),
    "soccer_mexico_ligamx": frozenset({"mex"}),
    "soccer_netherlands_eredivisie": frozenset({"ere"}),
    "soccer_norway_eliteserien": frozenset({"nor"}),
    "soccer_poland_ekstraklasa": frozenset({"pol"}),
    "soccer_portugal_primeira_liga": frozenset({"por"}),
    "soccer_russia_premier_league": frozenset({"rus"}),
    "soccer_saudi_arabia_pro_league": frozenset({"spl"}),
    "soccer_spain_copa_del_rey": frozenset({"cdr"}),
    "soccer_spain_la_liga": frozenset({"lal"}),
    "soccer_spain_segunda_division": frozenset({"es2"}),
    "soccer_spl": frozenset({"scop"}),
    "soccer_sweden_allsvenskan": frozenset({"swe"}),
    "soccer_sweden_superettan": frozenset({"swe2"}),
    "soccer_switzerland_superleague": frozenset({"sui"}),
    "soccer_turkey_super_league": frozenset({"tur"}),
    # Qualifying rounds are listed under the competition's own code.
    "soccer_uefa_champs_league": frozenset({"ucl"}),
    "soccer_uefa_champs_league_qualification": frozenset({"ucl"}),
    "soccer_uefa_champs_league_women": frozenset({"uwcl"}),
    "soccer_uefa_europa_conference_league": frozenset({"col"}),
    "soccer_uefa_europa_league": frozenset({"uel"}),
    "soccer_uefa_nations_league": frozenset({"unl"}),
    "soccer_usa_mls": frozenset({"mls"}),
}


def polymarket_league_code(slug: object) -> Optional[str]:
    """The venue league code a Polymarket GAME slug starts with, or None."""
    if not isinstance(slug, str):
        return None
    match = _GAME_SLUG.match(slug.strip().lower())
    return match.group(1) if match else None


def venue_refuses_placement(
    market_metadata: object, placed_league: str
) -> Optional[str]:
    """The venue league code that contradicts placing a row in ``placed_league``.

    Returns the code when the market's own Polymarket slug names a competition
    that is not ``placed_league``; None when the venue agrees, when the league is
    outside the soccer family, or when there is no code to read (a Kalshi
    market, a futures slug, a row ingested before the slug was stamped). The
    no-code case fails OPEN on purpose — it is today's behaviour, and a guard
    that refused on absence would un-place every row the stamp has not reached.
    """
    if not placed_league or not placed_league.startswith("soccer_"):
        return None
    if not isinstance(market_metadata, dict):
        return None
    code = polymarket_league_code(market_metadata.get(POLYMARKET_EVENT_SLUG_KEY))
    if code is None:
        return None
    if code in POLYMARKET_LEAGUE_CODES.get(placed_league, frozenset()):
        return None
    return code
