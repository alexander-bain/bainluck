"""A venue's whole-name spelling of a club we store under another name. #8100.

THE SHIP. Friday's Perth Wildcats v S.E. Melbourne Phoenix (NBL, 2026-10-02
11:30Z) was served twice on ``/search?q=Perth Wildcats``: ``15319245``, the row
Polymarket's market minted, in ``basketball_other`` with the Polymarket price,
and ``15320512``, the Odds API row ``/api/leagues/basketball_nbl`` serves, with
sportsbooks only. The other nine NBL clubs do not do this. Their Polymarket rows
are placed in ``basketball_nbl`` and the anchored-claim kickoff fold joins each
one to its Odds API row (Tasmania v Melbourne ``15320510`` serves Kalshi,
Polymarket and sportsbooks on one card). The Phoenix is the odd one out because
Polymarket writes ``South East Melbourne Phoenix`` and ``teams`` 2919 is
``S.E. Melbourne Phoenix``, so it misses at three places:

  * placement (``leagues_by_side_for_matchup``) resolves the side to nothing and
    the row lands in the catch-all;
  * the twin fold keys on the squashed name, and ``semelbournephoenix`` is not
    ``southeastmelbournephoenix``;
  * ``_fuzzy_team_match`` refuses it (``s e`` is not a subset of
    ``south east``), so a Polymarket market cannot link to the Odds API row.

No structural rule may bridge ``S.E.`` to ``South East``. A rule that expands
initials also expands ``S.C.`` and ``F.C.``, and it would do so on every sport.
So this is a table of statements about named clubs, the same shape as
``_STATE_QUALIFIED_SCHOOL_NAMES`` and ``AUTHORITY_SYNONYMS``: exact, whole
name, and each entry earned by a row that was actually served twice.

NOT SPORT-KEYED, ON PURPOSE. The fold's squash has no sport in hand. The keys
are two COMPLETE club names, so for an entry to fuse two clubs, some other sport
would need a team literally named ``South East Melbourne Phoenix`` that meant
something else (the ``_CLUB_SYNONYM_PAIRS`` argument).

Imports nothing, so every consumer can read it without a cycle.
"""

#: Venue spelling -> the name ``teams`` stores. Whole names, compared after
#: each consumer's own normalisation (squash, matching-normalise, lower-case).
VENUE_CLUB_SPELLINGS: dict[str, str] = {
    # #8100: Polymarket's NBL listings (Gamma, 2026-09) vs teams 2919, the
    # Odds API's spelling. Swept all ten NBL clubs on 2026-09-30 against the
    # names Polymarket-born rows carry: the other nine are byte-equal.
    "South East Melbourne Phoenix": "S.E. Melbourne Phoenix",
    # #13238: Bundesliga exonym — ESPN/Polymarket/Kalshi "FC Cologne" vs Odds API
    # "1. FC Köln" (production pair 15351899 / 15342140 on 2026-11-20).
    "FC Cologne": "1. FC Köln",
    # #13238: EuroLeague multi-word venue spellings vs Odds API club names
    # (production pairs 15349594 / 15350188, 15348466 / 15350189, and
    # 15351534 on 2026-11-20).
    "Besiktas JK": "Beşiktaş J.K.",
    "KK Partizan Belgrade": "KK Partizan NIS",
    "BC Olympiakos Piraeus": "Olympiacos B.C.",
    "FC Bayern München": "Bayern Munich",
    # #13238: Remaining EuroLeague club spellings (production pairs 15351540 /
    # 15352078 and 15351920 / 15352631 on 2026-11-23).
    "Pallacanestro Olimpia Milano": "Olimpia Milano",
    "Baskonia Vitoria-Gasteiz": "Saski Baskonia",
    "Anadolu Efes SK": "Anadolu Efes",
    "Maccabi Tel-Aviv": "Maccabi Tel Aviv",
    "Hapoel Tel-Aviv": "Hapoel Tel Aviv",
    "ASVEL Lyon-Villeurbanne": "ASVEL Lyon Villeurbanne",
    # #13142: Women's college basketball spelling — Polymarket "Little Rock Trojans"
    # vs Odds API "Arkansas-Little Rock Trojans" (pair 15347844 / 15351848).
    "Little Rock Trojans": "Arkansas-Little Rock Trojans",
    # #13594: UEFA Europa League / Conference League club spellings (>=2 words each side)
    # split across Odds API, Polymarket, Kalshi, and ESPN. Single-word club names live
    # in LEAGUE_CLUB_SPELLINGS below (#8100 TestTheTable).
    "PFK Levski Sofia": "PFC Levski Sofia",
    "Olympiakós SFP": "Olympiakos Piraeus",
    "RU Saint-Gilloise": "Union Saint-Gilloise",
    "KKS Lech Poznań": "Lech Poznań",
    "AC Sparta Praha": "Sparta Prague",
    "Qairat FK": "FC Kairat",
    "FC København": "FC Copenhagen",
    "Crvena Zvezda": "Red Star Belgrade",
    "Kuopion PS": "KuPS Kuopio",
    "K. Sint-Truidense VV": "Sint Truiden",
    "HNK Hajduk Split": "Hajduk Split",
    "Omonia Nicosia": "Omonoia FC",
}

#: Sport-scoped whole-name spellings where one side is a single city or club
#: word (e.g. EuroLeague "Barcelona" vs "FC Barcelona Bàsquet"). Scoped by
#: ``sport_key`` so folding EuroLeague rows never alters another sport's club
#: (such as La Liga "FC Barcelona"). #13238.
LEAGUE_CLUB_SPELLINGS: dict[str, dict[str, str]] = {
    "basketball_euroleague": {
        "FC Barcelona Bàsquet": "Barcelona",
        "Beşiktaş J.K.": "Besiktas",
        "Besiktas JK": "Besiktas",
        "KK Partizan NIS": "Partizan",
        "KK Partizan Belgrade": "Partizan",
        "Olympiacos B.C.": "Olympiacos",
        "BC Olympiakos Piraeus": "Olympiacos",
        "Fenerbahce SK": "Fenerbahce",
        "FC Bayern München": "Bayern Munich",
        "Pallacanestro Olimpia Milano": "Olimpia Milano",
        "Saski Baskonia": "Baskonia",
        "Baskonia Vitoria-Gasteiz": "Baskonia",
        "Anadolu Efes SK": "Anadolu Efes",
        "Maccabi Tel-Aviv": "Maccabi Tel Aviv",
        "Hapoel Tel-Aviv": "Hapoel Tel Aviv",
        "ASVEL Lyon-Villeurbanne": "ASVEL Lyon Villeurbanne",
    },
    "soccer_uefa_champs_league": {
        "Internazionale": "Inter Milan",
        "Olympique de Marseille": "Marseille",
        "Ferencvarosi": "Ferencváros TC",
        "AS Monaco": "Monaco",
        "AS Monaco FC": "Monaco",
    },
    "soccer_italy_serie_a": {
        "Internazionale": "Inter Milan",
    },
    "soccer_uefa_europa_league": {
        "AZ": "AZ Alkmaar",
        "Olympiacos": "Olympiakos Piraeus",
        "Milan": "AC Milan",
        "Olympique de Marseille": "Marseille",
        "Ferencvarosi": "Ferencváros TC",
        "AS Monaco": "Monaco",
        "AS Monaco FC": "Monaco",
    },
    "soccer_uefa_europa_conference_league": {
        "Heart of Midlothian": "Hearts",
        "Heart of Midlothian FC": "Hearts",
        "AS Monaco": "Monaco",
        "AS Monaco FC": "Monaco",
        "Ferencvarosi": "Ferencváros TC",
    },
    "soccer_france_ligue_one": {
        "Olympique de Marseille": "Marseille",
        "AS Monaco": "Monaco",
        "AS Monaco FC": "Monaco",
    },
    "soccer_spl": {
        "Heart of Midlothian": "Hearts",
        "Heart of Midlothian FC": "Hearts",
    },
    "soccer_netherlands_eredivisie": {
        "AZ": "AZ Alkmaar",
    },
    "soccer_greece_super_league": {
        "Olympiacos": "Olympiakos Piraeus",
    },
}


def venue_spellings_of(
    stored_name: object, *, sport_key: str | None = None
) -> frozenset[str]:
    """The lower-cased venue spellings of a club stored as ``stored_name``.

    For the exact-name resolvers, which compare ``lower()`` strings. Empty when
    the table names no spelling for it.
    """
    if not isinstance(stored_name, str) or not stored_name.strip():
        return frozenset()
    ours = stored_name.strip().lower()
    spellings = {
        venue.lower()
        for venue, stored in VENUE_CLUB_SPELLINGS.items()
        if stored.lower() == ours
    }
    if sport_key:
        league_map = LEAGUE_CLUB_SPELLINGS.get(sport_key, {})
        for left, right in league_map.items():
            if left.lower() == ours:
                spellings.add(right.lower())
            elif right.lower() == ours:
                spellings.add(left.lower())
    return frozenset(spellings)
