"""Curated search aliases for major teams — the durable data-side backfill for
`teams.alternate_names` (Queue #246 Item 1a).

Why this exists: bare colloquial nicknames ("pats", "revs") are how casual fans
type a team, but they are NOT in the ESPN/odds-provider alt-name sets, so search
misses them. The ESPN syncs UNION into `alternate_names` (they never overwrite an
existing entry — see `espn_helpers.upsert_team` / `espn_sync._backfill_team_logos`),
so curated aliases added here survive routine syncs.

Keyed by **(sport_key, canonical_team_name)** on purpose — there are multiple
"Patriots" (NFL New England, NCAA George Mason / Dallas Baptist), so a bare
"pats" must attach to the NFL franchise ONLY, never fan out across leagues.

Extend this map (that is its job) — add the (sport_key, name) → [aliases] rows,
then re-run `scripts/backfill_curated_team_aliases.py --apply`. Keep aliases
UNAMBIGUOUS: an alias that matches two franchises makes search worse, not better.
"""

# (sport_key, canonical_team_name) -> list of lowercase colloquial aliases.
CURATED_TEAM_ALIASES: dict[tuple[str, str], list[str]] = {
    ("americanfootball_nfl", "New England Patriots"): ["pats"],
    ("soccer_usa_mls", "New England Revolution"): ["revs"],
    ("americanfootball_nfl", "San Francisco 49ers"): ["niners", "9ers"],
    ("americanfootball_nfl", "Tampa Bay Buccaneers"): ["bucs"],
    ("basketball_nba", "Philadelphia 76ers"): ["sixers"],
    # #9080 — three more, measured on production 2026-09-27 07:1xZ. Before:
    # `phins`, `stros` and `halos` each returned 0 games from /api/events/search
    # while Dolphins–Chiefs, Athletics–Astros and Mariners–Angels were on today.
    # Each last-word token names exactly ONE club in its sport over 120 days of
    # events (Dolphins: Miami, NFL; Astros: Houston and Angels: Los Angeles, MLB),
    # and every open baseball futures market holding `Astros` (18) or `Angels`
    # (34) is that club's. The sport scope is what drops the namesakes: NRL's
    # Dolphins, Tonbridge Angels FC, an Anaheim Angels naming bill (politics) and
    # a basketball Astros. Refused: `friars` — production already sends it to the
    # Providence Friars, whose actual name it is.
    # #9263 — `fins`, measured 2026-09-28 02:1xZ. Before: `fins` served Finland,
    # Finnentrop/Bamenohl and five Finland soccer games — no Dolphins at all,
    # because `fins` is not spelled inside `Dolphins` the way `phins` is.
    ("americanfootball_nfl", "Miami Dolphins"): ["phins", "fins"],
    ("baseball_mlb", "Houston Astros"): ["stros"],
    ("baseball_mlb", "Los Angeles Angels"): ["halos"],
    # #9263 — `dubs`, measured on production 2026-09-28 02:1xZ. Before: `dubs`
    # served Dubai Basketball and Shelbourne Dublin, 0 Warriors games. `Warriors`
    # names exactly ONE basketball_nba club over 120 days of events. Open markets
    # in the futures arm's category (`basketball`): 4/6 are Golden State's, the
    # other two Shinshu Brave Warriors (Japan's B.League). Kept: today `dubs`
    # reaches 0 Warriors rows and the literal `warriors` leads its markets with a
    # South African rugby side and Honor of Kings esports, so 4/6 is the best
    # answer the query has had. Refused in the same pass: `avs` (#8685 — AVS
    # Futebol), `celts` (Celtic FC are "the Celts" too), `bolts`.
    ("basketball_nba", "Golden State Warriors"): ["dubs"],
    # #9263 — `avs`, measured on production 2026-09-30 10:2xZ. Before: the TEAMS
    # card held only AVS Futebol SAD and the markets list one Taça de Portugal
    # market; 0 of the 37 open `hockey` markets naming `Avalanche` (every one is
    # Colorado's — all 30 non-"Colorado" titles pair it with an NHL club).
    # `Avalanche` names exactly ONE icehockey_nhl club over 120 days of events.
    # Refused twice before (#8685, #9263 r1) under the two-franchise rule, which
    # does not reach it: that rule protects a club that would LOSE the word, and
    # AVS Futebol keeps it — `avs` is its own name, matched by the card's full text
    # and the plain rails, and every arm here is additive. It stays on the card,
    # second. `caps`/`cavs`/`canes`/`bolts`/`wolves` are in neither club's name,
    # so they stay refused.
    ("icehockey_nhl", "Colorado Avalanche"): ["avs"],
    # #9272 — four MLB nicknames, measured on production 2026-09-28 02:5xZ.
    # Before: `o's` served O Elvas CAD, O'Higgins and a boxing bout, `a's` and
    # `rox` served nothing at all, and `m's` served four "A&M" schools and Texas
    # A&M football. Each last-word token names exactly ONE baseball_mlb club over
    # 120 days of events (Orioles 115, Athletics 113, Mariners 107, Rockies 110);
    # Central Coast Mariners (A-League) and the NCAA/other-league "Athletics" rows
    # sit outside the scope. Open baseball markets: Orioles 9/9 Baltimore's, the
    # other three have none open. Both apostrophes, because a phone keyboard types
    # the curly one. The apostrophe forms are why the TEAMS card needed
    # `team_nickname_team_rows` too: under the English text config `a's` reduces
    # to no lexeme at all and `m's` to `m`, so no row can match them by FTS — the
    # Athletics row already held `A's` and still carded nothing.
    # Refused: `chisox` (token `Sox` is the Red Sox too), `os` (Os Marialvas).
    ("baseball_mlb", "Baltimore Orioles"): ["o's", "o\u2019s"],
    ("baseball_mlb", "Athletics"): ["a's", "a\u2019s"],
    ("baseball_mlb", "Seattle Mariners"): ["m's", "m\u2019s"],
    ("baseball_mlb", "Colorado Rockies"): ["rox"],
    # #8685 — eleven more nicknames fans type, each measured on production
    # 2026-09-25 before it was added. Every open market in the franchise's sport
    # whose name holds the canonical token was read, and every one of them is the
    # franchise's own (a city-less "Senators vs. Canadiens" game title, never a
    # namesake): Canadiens 23/23, Yankees 47/47, Mavericks 2/2, Nationals 34/34,
    # Penguins 25/25, Senators 27/27, Jaguars 32/32, Phillies 39/39, Cubs 36/36.
    # Before this, `habs` served no game and no market (its only answer was the
    # Belgian club Habay La Neuve) and `yanks`/`mavs`/`jags`/`phils` served no
    # market. `dbacks` and `nucks` are spelled inside their tokens, so the futures
    # rail already reached them by ILIKE and skips them; they are here for the
    # GAME rail, which word-matches and returned 0 games for both.
    # `nats` also names the VALORANT pro nAts; the arm is additive (a UNION), so
    # the esports row that answers today still does.
    ("icehockey_nhl", "Montreal Canadiens"): ["habs"],
    ("icehockey_nhl", "Pittsburgh Penguins"): ["pens"],
    ("icehockey_nhl", "Ottawa Senators"): ["sens"],
    ("icehockey_nhl", "Vancouver Canucks"): ["nucks"],
    ("baseball_mlb", "New York Yankees"): ["yanks"],
    ("baseball_mlb", "Washington Nationals"): ["nats"],
    ("baseball_mlb", "Philadelphia Phillies"): ["phils"],
    ("baseball_mlb", "Chicago Cubs"): ["cubbies"],
    ("baseball_mlb", "Arizona Diamondbacks"): ["dbacks"],
    ("basketball_nba", "Dallas Mavericks"): ["mavs"],
    ("americanfootball_nfl", "Jacksonville Jaguars"): ["jags"],
    # #9076 — five college football nicknames, measured on production 2026-09-27
    # 06:3xZ. Before: `noles` served no Florida State team or game, `horns` served
    # Portland Thorns FC and a novel, `bama` five Alabama politics markets ahead of
    # the Alabama game, `vols` only the Icelandic club Volsungur. Each last-word
    # token names exactly ONE ncaaf club over 120 days of events, and no open
    # football futures market carries `Tide`/`Volunteers` in another club's name.
    # FOOTBALL ONLY, on purpose: the same school in basketball_ncaab is a second
    # claimant, and `_alias_claim_counts` refuses a contested alias in both maps.
    # Refused: `canes` (see #8685), `dawgs` (four schools), `zags` (its token
    # would be `Bulldogs`), `cuse` (token `Orange` reaches Orange Bowl markets).
    ("americanfootball_ncaaf", "Florida State Seminoles"): ["noles"],
    ("americanfootball_ncaaf", "Texas Longhorns"): ["horns"],
    ("americanfootball_ncaaf", "Alabama Crimson Tide"): ["bama"],
    ("americanfootball_ncaaf", "Tennessee Volunteers"): ["vols"],
    ("americanfootball_ncaaf", "Nebraska Cornhuskers"): ["huskers"],
    # #8084 — NOT a colloquial nickname: the school's own formal name. Our row is
    # spelled `NC State Wolfpack`, the college feeds spell it `North Carolina St.`,
    # and nothing anywhere holds the form in between. Measured on production
    # 2026-09-22 across the 398 rows the 13 warm grids serve: `North Carolina St.`
    # is one of 11 rows resolving to NO metadata, on TWO grids —
    # /playoffs/ncaa-women-basketball and /playoffs/ncaa-football — where it renders
    # as bare text beside 68 crested rows. `normalize_team_name_for_matching`
    # already expands it to `north carolina state` (arm C), so the read side is
    # waiting on a key no row holds; this is the alias that mints it.
    #
    # THREE ROWS, ONE CLUB, VERIFIED BY ANCHOR AND NOT BY NAME. `teams` holds four
    # rows named `NC State Wolfpack`: 4 (ncaaf), 232 (ncaab), 735 (wncaab) all carry
    # espn_id 152 and NC State's crest, colours and record. Row 3211
    # (`baseball_ncaa`) carries espn_id **95** and a different primary colour, and is
    # deliberately EXCLUDED — that sport's rows are where #7727's specimen lives
    # (14627 is named `Ohio State` while holding Penn State's espn 414), so its
    # anchor is not one this issue verified. A name is not an id.
    ("basketball_wncaab", "NC State Wolfpack"): ["north carolina state"],
    ("americanfootball_ncaaf", "NC State Wolfpack"): ["north carolina state"],
    ("basketball_ncaab", "NC State Wolfpack"): ["north carolina state"],
}


def _alias_claim_counts() -> dict[str, int]:
    """`alias -> how many (sport_key, team_name) entries claim it`.

    THE MAP'S KEY CAN EXPRESS A MULTI-SPORT ALIAS AND ITS TWO DERIVED MAPS CANNOT
    (#8084). Both expansion functions below build `expansions[alias] = (...)`, so
    an alias claimed by several entries does not collide loudly — the last one
    written silently wins, and which one that is depends on nothing but insertion
    order. While every alias belonged to exactly one franchise that was invisible;
    `north carolina state` is the first alias to belong to one SCHOOL in three
    sports, which is the same shape as belonging to two different franchises as far
    as a dict keyed on the alias alone can tell.

    So the ambiguity is refused rather than resolved, which is this file's existing
    rule ("an alias that matches two franchises makes search worse, not better")
    applied to its own derived output. A contested alias yields NO search or
    game-card expansion: those rails then behave exactly as they do today, while the
    TEAMS rail — `alternate_names`, which is keyed per row and has no such
    collision — still resolves the alias for all three rows. That is the rail #8084
    needs, so the refusal costs the issue nothing.

    Fail-closed, not last-wins: guessing a scope here re-creates the cross-league
    fan-out the `(sport_key, name)` key was chosen to prevent.
    """
    counts: dict[str, int] = {}
    for aliases in CURATED_TEAM_ALIASES.values():
        for alias in aliases:
            counts[alias.lower()] = counts.get(alias.lower(), 0) + 1
    return counts


# #4728 — the SECOND consumer of the map above, and the reason it is keyed by sport.
#
# The backfill puts these aliases into `teams.alternate_names`, which is enough for
# the TEAM row to resolve: production 2026-09-10 answers `?q=pats` with the New
# England Patriots team, `?q=revs` with the Revolution, `?q=niners` with the 49ers.
# It is NOT enough for the team's MARKETS, because market names come from the venue
# and no venue writes "pats". Measured the same morning on open futures:
#
#     query    markets whose name contains the query   the team's real markets
#     pats     3   (all Kor*pats*ch WTA doubles)       31
#     revs     0                                       15
#     niners   0                                       36
#     bucs     5   (all Cristina *Bucs*a WTA tennis)   41
#
# So a fan typing their team's nickname gets ZERO of their team and, worse, a
# handful of unrelated tennis players whose surname happens to contain it.
#
# WHY A SPORT SCOPE, AND WHY IT IS NOT OPTIONAL. The obvious repair — expand `pats`
# to `patriots` — re-creates exactly the fan-out this map's key was designed to
# prevent. Of 53 open `%patriot%` markets on 2026-09-10 only 31 are New England's;
# the other 22 are Caribbean Premier League cricket (St. Kitts and Nevis Patriots),
# Boyaca Patriotas, and the Patriot League. Matching the PLURAL token drops the
# Patriotas and the League on spelling alone, but 15 cricket rows survive it — a
# 15/46 false-positive rate served to a Patriots fan. Scoping the arm to the
# franchise's own sport takes it to 0/31. `revs`, `niners` and `bucs` measured 0
# false positives either way; the scope costs them nothing and is what makes the
# mechanism safe to extend to the next nickname, which may not be so lucky.
#
# NOT A PREFIX ARM. `pat:*` would match `patriot` — and also `federico` for `fed`,
# the defect LAT-P033/LAT-P034 closed and LAT-P037 refuses in full. This is a
# curated, name-only, franchise-anchored alias: no prefix, no stemmer change.


def _canonical_market_token(team_name: str) -> str:
    """The word a venue actually prints for a franchise: the last of its name.

    "New England Patriots" -> "Patriots", "San Francisco 49ers" -> "49ers". Venues
    name games "Jets vs. Patriots" and "SF 49ers vs LA Rams" — the CITY is the part
    they drop, so the last word is the token that reaches market names. Pinned
    value-by-value in `tests/test_search_team_nickname_aliases_4728.py` so a future
    entry whose last word is wrong fails a test rather than quietly under-matching.
    """
    return team_name.split()[-1]


def team_nickname_search_expansions() -> dict[str, tuple[str, str]]:
    """`alias -> (canonical market token, llm_sport_category)` for search recall.

    Derived from `CURATED_TEAM_ALIASES` so there is ONE place to add a nickname.
    Pure — no DB, no I/O — so the guard tests pin it directly.

    Aliases that are already a SUBSTRING of their token are skipped: `9ers` is
    inside `49ers`, so the plain ILIKE arm already reaches those rows (verified on
    production — `?q=9ers` returns 10 real 49ers markets today, while `?q=niners`
    returns 0). An arm for them would be duplicate work for zero extra recall, the
    same reasoning `_phrase_alias_alternatives` applies to identical alternatives.

    **The skip is correct HERE and wrong in the event sibling — do not harmonise
    them.** It is sound only because this rail's matcher is a plain ILIKE.
    :func:`team_nickname_event_expansions` matches with `_event_name_match`, which
    AND-s an FTS whole-word test onto the ILIKE, and `9ers` is not a lexeme of
    `San Francisco 49ers`; copying this skip there returned zero game cards for
    `9ers` and was the repair CERT-2527 required. That function's docstring carries
    the measurement.
    """

    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

    contested = _alias_claim_counts()
    expansions: dict[str, tuple[str, str]] = {}
    for (sport_key, team_name), aliases in CURATED_TEAM_ALIASES.items():
        category = SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_key.split("_")[0])
        if not category:
            # An unmapped sport prefix means we cannot scope the arm, and an
            # UNSCOPED arm is the fan-out this map exists to prevent. Skip it:
            # the alias keeps working for the team row via `alternate_names`.
            continue
        token = _canonical_market_token(team_name)
        for alias in aliases:
            alias = alias.lower()
            if alias in token.lower():
                continue
            if contested.get(alias, 0) > 1:
                continue  # see `_alias_claim_counts` — refused, not guessed
            expansions[alias] = (token, category)
    return expansions


def team_nickname_event_expansions() -> dict[str, tuple[str, str]]:
    """`alias -> (canonical team token, sport_key)` for GAME-CARD recall (#4809).

    The third consumer of the map above, and the one that needed no new data at
    all — only the key this file has been carrying since it was written.

    #4728 gave the nickname the TEAMS rail (via `teams.alternate_names`) and the
    FUTURES rail (via :func:`team_nickname_search_expansions`). It could not give
    it the game-card rail, because that rail matches the DENORMALISED
    `Event.home_team_name`/`away_team_name` text and never joins `teams`, so an
    alias living on the team row is invisible to it. Measured on production
    2026-09-10, after #4728 was live::

        query     team row   futures   GAME CARDS
        pats      ✓          10        0
        revs      ✓          10        0
        niners    ✓          10        2   <- both are UTEP MINERS

    `niners` is the sharpest of the three: the empty game rail sent the query to
    the fuzzy "did you mean" fallback, which corrected it to the nearest team
    NAME by trigram similarity — `UTEP Miners` — and filled the rail with two
    college football games that have nothing to do with San Francisco.

    **The scope is a `sport_key`, not an `llm_sport_category`, and that is the
    only difference from the sibling.** Events carry no category column; they
    reach their sport through `sport_id -> sports.key`, which the search query
    already joins. `CURATED_TEAM_ALIASES` is keyed by the sport key directly, so
    this needs no inversion of `SPORT_PREFIX_TO_LLM_CATEGORY` and cannot drift
    from it.

    **The scope is not optional here either, and for a sharper reason than on the
    futures side.** Event team names are the same words venues print, so the bare
    token `Patriots` reaches `St Kitts & Nevis Patriots` — a Caribbean Premier
    League cricket side that is a genuine whole-word match and a wrong answer to
    `pats`. `Sport.key == 'americanfootball_nfl'` takes that to zero without
    touching what the literal query `patriots` returns.

    **NO SUBSTRING SKIP, and this is the one place the two siblings genuinely
    differ.** :func:`team_nickname_search_expansions` skips an alias that is
    already spelled inside its token — `9ers` inside `49ers` — because the futures
    rail's matcher is a plain ILIKE (`_build_expanded_ilike` on
    `FuturesMarket.name`), so `%9ers%` reaches those rows unaided and an arm would
    be duplicate work.

    That reasoning does not survive the trip to the event rail, because the event
    matcher is not an ILIKE. :func:`app.routes.events._event_name_match` is
    ``ILIKE AND (no-lexemes OR FTS word match)`` — LAT-P034's judgment that a query
    is about an event when it names a WHOLE WORD of a team, not when it happens to
    be spelled inside one. For `9ers` the two arms disagree::

        ILIKE  '%9ers%'  vs 'San Francisco 49ers'   -> TRUE
        FTS    to_tsvector('San Francisco 49ers')   -> 'san' 'francisco' '49ers'
               plainto_tsquery('9ers')              -> '9ers'   -> FALSE

    AND-ed, that is FALSE, so the substring the futures rail relies on buys exactly
    nothing here. Measured on production 2026-09-10 with the first cut of #4809
    live: `?q=9ers` returned the 49ers team row and 10 correct 49ers markets and
    **zero game cards** — the same hole this issue was filed to close, surviving in
    the fix for it, for the one alias the skip removed.

    Expanding it to the whole token `49ers` makes both arms agree and inherits the
    NFL scope like every other alias. `9ers` is the only entry in
    `CURATED_TEAM_ALIASES` the skip ever removed (`pats` is not inside `Patriots`,
    `bucs` not inside `Buccaneers`, `sixers` not inside `76ers`, `niners` not
    inside `49ers`), so dropping it here changes exactly one alias's behaviour and
    leaves the sibling's optimisation intact where it is still true.
    """

    contested = _alias_claim_counts()
    expansions: dict[str, tuple[str, str]] = {}
    for (sport_key, team_name), aliases in CURATED_TEAM_ALIASES.items():
        token = _canonical_market_token(team_name)
        for alias in aliases:
            if contested.get(alias.lower(), 0) > 1:
                continue  # see `_alias_claim_counts` — refused, not guessed
            expansions[alias.lower()] = (token, sport_key)
    return expansions


def team_nickname_team_rows() -> dict[str, tuple[str, str]]:
    """`alias -> (sport_key, canonical team name)` for the TEAMS card (#9272).

    The fourth consumer of the map, and the one that lets a nickname reach the
    team row without waiting on `alternate_names`. The Teams card's recall is
    full-text over the row's name, abbreviation and aliases, so it can only find
    a nickname some row stores — which is why every earlier ship here carried a
    pinned repair script — and for an apostrophe nickname not even that works:
    `a's` reduces to no lexeme under the English config, so the Athletics row
    holding `A's` was carded for nothing (production 2026-09-28). The route
    recalls the named row by its (sport, name) key instead, the same key the map
    is written in.

    Contested aliases are refused exactly as in the siblings (`_alias_claim_counts`):
    naming one row for them would be a guess.
    """
    contested = _alias_claim_counts()
    rows: dict[str, tuple[str, str]] = {}
    for (sport_key, team_name), aliases in CURATED_TEAM_ALIASES.items():
        for alias in aliases:
            if contested.get(alias.lower(), 0) > 1:
                continue
            rows[alias.lower()] = (sport_key, team_name)
    return rows


def curated_team_aliases(sport_key: str | None, team_name: str | None) -> tuple[str, ...]:
    """The curated aliases of one team row, for the Teams card's ranking evidence.

    What `backfill_curated_team_aliases.py --apply` would have written into the
    row's `alternate_names`, read straight from the map, so a row recalled by
    `team_nickname_team_rows` is scored on the word the reader typed (#9272).
    Contested aliases are included on purpose: a row owning an alias is true per
    row, which is why the backfill writes them too.
    """
    return tuple(CURATED_TEAM_ALIASES.get((sport_key or "", team_name or ""), ()))
