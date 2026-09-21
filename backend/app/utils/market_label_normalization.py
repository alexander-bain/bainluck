"""
Market label normalization for Related Futures.

Translates verbose/machine-readable market names (primarily from Kalshi)
into clean, human-readable labels, and assigns structured categories for
grouping and filtering.

Categories:
    playoff_path  — Playoff berth, conference champion, league champion
    conference     — Conference finals matchup, conference MVP
    award          — MVP, DPOY, 6MOY, MIP, All-Teams, trophies, draft picks
    season_stat    — PPG/RPG/APG leader, best/worst record, win totals, divisions
    game_prop      — Player stat props for a specific game
    trade          — "Player's Next Team" trade speculation
    novelty        — 2K cover, records, will-they-stay, tournament point totals
    ncaa           — NCAA tournament bracket rounds (Men's Round of X)
    other          — Uncategorized
"""

import logging
import re
from typing import Optional

# Pure module (re/logging/datetime/typing only), so this cannot cycle back.
from app.utils.futures_categorization import is_game_prop

logger = logging.getLogger(__name__)


# ── Label cleaning patterns ──────────────────────────────────────────────

# Kalshi uses "Pro Basketball" instead of "NBA", etc. Polymarket does too — the
# open-market census behind #7397 reads `Pro Football` 402 polymarket / 74 kalshi,
# `Pro Basketball` 32, `Pro Baseball` 26, so this is venue vocabulary in general
# and not one venue's quirk.
#
# Split in two because the two halves are safe on DIFFERENT surfaces (#7397):
#
# `_VENUE_LEAGUE_REWRITES` renames a league and nothing else, so it is sound
# anywhere, on any sport — but only once the QUALIFIED phrases below have had
# their turn. The first version of this list asserted that "a market called
# 'Pro Football' is an NFL market wherever it is printed"; that is false for
# basketball, and the counter-example is in production today.
#
# `\bPro Basketball\b` matches happily INSIDE `Women's Pro Basketball`, which is
# the venue's name for the WNBA — 58 markets, every one of them a real WNBA
# question, 23 of them on the `/sport/basketball/wnba` page. The bare rule turns
# "Women's Pro Basketball: Las Vegas Aces Total Wins" into "Women's NBA: Las
# Vegas Aces Total Wins" and tells a reader the Aces play in the NBA. A wrong
# league is a worse sentence than the venue's own jargon, which is the whole
# point of #7397, so the qualified phrases are matched FIRST and consume the
# text before a bare rule can see it. Order here is load-bearing, not cosmetic.
_QUALIFIED_VENUE_LEAGUE_REWRITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bWomen(?:['’]s|s)?\s+Pro Basketball\b", re.I), "WNBA"),
]

_VENUE_LEAGUE_REWRITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bPro Basketball\b", re.I), "NBA"),
    (re.compile(r"\bPro Football\b", re.I), "NFL"),
    (re.compile(r"\bPro Hockey\b", re.I), "NHL"),
    (re.compile(r"\bPro Baseball\b", re.I), "MLB"),
]

# An indefinite article in front of the phrase has to move WITH it. Every league
# in the bare list above is an initialism read letter-by-letter, and all four
# open on a vowel SOUND — "en-eff-ell", "en-bee-ay", "en-aitch-ell", "em-ell-bee"
# — so the article that was correct in front of the venue's words is wrong in
# front of ours: "a Pro Football game" is English, "a NFL game" is not.
#
# Spelling does not decide this, pronunciation does, which is why this is a named
# set and not `repl[0] not in "AEIOU"`. `WNBA` is the counter-example and it is
# already in production: "double-you-en-bee-ay" opens on a consonant, so it keeps
# "a". It reaches the text through `_QUALIFIED_VENUE_LEAGUE_REWRITES`, which does
# not consult this set at all — but it is named here so the next person adding a
# league asks the question instead of pattern-matching the first letter.
# `All-NBA` is likewise absent on purpose: it is a rewrite of `All-Pro`, the
# article in front of it belongs to "All-", and the safe failure is to leave it.
#
# MEASURED before writing it, on production `futures_markets` (#7397): exactly
# five open markets carry an article in front of the phrase — Aaron Donald and
# Jake Paul "to play in a Pro Football game", Ben Simmons "a Pro Basketball
# game", and Salt Lake City receiving "a Pro Baseball expansion team". It is a
# five-row class, not a long tail, and four of the five are novelty markets.
_VOWEL_SOUND_INITIALISMS = frozenset({"NBA", "NFL", "NHL", "MLB"})

# The backstop for the qualifier we have NOT met yet. A rule above can only
# rescue a phrase somebody has already seen; this decides what happens to the
# next one. If a league-changing qualifier sits immediately in front of the
# phrase and no qualified rule claimed it, we leave the venue's words alone —
# "Girls Pro Basketball" stays as it is rather than becoming "Girls NBA".
# Printing the venue's jargon is the bug we are fixing; printing the wrong
# league is a lie, and between the two the jargon is the safe failure.
#
# It has to be a NAMED list rather than "any preceding word", because the
# population says so: of the 363 names where the phrase is not at the start,
# 181 are preceded by `2026`, 10 by `2027`, and most of the rest by a city
# ("Milwaukee Pro Basketball…") or an article. Blocking on any prefix would
# refuse the 191 year-prefixed rows, which are ordinary NBA/NFL markets. The one
# league-changing qualifier that actually occurs today is `Women's`, and it is
# mapped above; everything here beyond it is the guard being early rather than
# clever, and each addition is cheap to make correct once a real row appears.
# The separator is `[-\s]+`, not `\s+`: in "Semi-Pro Football" the qualifier is
# "Semi-" and the hyphen IS the boundary, so a whitespace-only terminator reads
# that name as an ordinary one and returns "Semi-NFL". Caught by the guard's own
# test rather than by a reader.
_LEAGUE_CHANGING_QUALIFIER = re.compile(
    r"\b(?:women|womens|women['’]s|girls|ladies|college|collegiate|ncaa"
    r"|university|youth|junior|juniors|amateur|semi)[-\s]+$",
    re.I,
)

# `All-Pro` → `All-NBA`, by contrast, is only true once the surface has already
# filtered to basketball. "All-Pro" is an NFL term, and production carries four
# open football markets that this rule renames into the wrong sport:
# `Pro Football: All-Pro Second-Team Offense` (60473175, kalshi, football) comes
# out of `normalize_market_label` as `All-NBA Second-Team Offense`. That is
# survivable on the Related Futures rail — its only caller — because the rail is
# sport-scoped to the event, and it is not currently reader-visible there either
# (checked on the served payload: two NFL events' rails, 1020 and 996 rows, carry
# zero `All-`/`NBA` labels). It is NOT survivable on a search page, which is
# every sport at once. So it stays here, below the league rewrites, and out of
# the helper the unscoped surfaces call.
#
# Order is load-bearing and unchanged: `\bPro Basketball\b` fires first, so the
# genuinely-NBA `All-Pro Basketball Third Team Selections` becomes `All-NBA Third
# Team Selections` on both paths and never reaches the `All-Pro` rule.
_PRO_SPORT_REWRITES: list[tuple[re.Pattern, str]] = [
    *_VENUE_LEAGUE_REWRITES,
    (re.compile(r"\bAll-Pro\b", re.I), "All-NBA"),
]

# Strip "MLB: 2026 ..." or "NHL: ..." league-year prefixes
_LEAGUE_PREFIX_RE = re.compile(
    r"^(?:MLB|NHL|NFL|NBA|NCAAM|NCAAW):\s+(?:2\d{3}\s+)?", re.I
)

# Strip standalone year or year-range prefix: "2026 ...", "2025-2026 ..."
_YEAR_PREFIX_RE = re.compile(r"^2\d{3}[-\u2013]?(?:\d{2,4}\s+|\s+)")

# Verbose suffixes Kalshi adds
_VERBOSE_SUFFIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\s+Winner\??\s*$", re.I), ""),
    (re.compile(r"\s+Selections?\s*$", re.I), ""),
    (re.compile(r"\s+Qualifiers?\s*$", re.I), ""),
]

# Specific label rewrites (pattern → clean label). First match wins.
_LABEL_REWRITES: list[tuple[re.Pattern, str]] = [

    # ── NBA ──────────────────────────────────────────────────────────────

    # Championship
    (re.compile(r"^(?:2\d{3}\s+)?NBA\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I),
     "NBA Champion"),

    # Conference champions
    (re.compile(r"^(?:NBA\s+)?(Eastern|Western)\s+Conference\s+Champion\s*$", re.I),
     r"\1 Conference Champion"),

    # Conference finals matchup
    (re.compile(r"^(?:NBA\s+)?(Eastern|Western)\s+Conference\s+Finals\s+Matchup\s*$", re.I),
     r"\1 Conference Finals Matchup"),
    (re.compile(r"^NBA\s+Finals\s+Matchup\s*$", re.I), "NBA Finals Matchup"),

    # Conference finals MVP
    (re.compile(r"^(Eastern|Western)\s+Conference\s+Finals\s+MVP\s*(?:Winner)?\s*$", re.I),
     r"\1 Conf Finals MVP"),

    # Playoffs
    (re.compile(r"^Which teams will make the NBA Playoffs\??\s*$", re.I),
     "Make NBA Playoffs"),
    (re.compile(r"^NBA\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I), "NBA Playoff Qualifiers"),

    # Play-in
    (re.compile(r"^Teams to Make the (Eastern|Western) Conference Play-In.*$", re.I),
     r"\1 Conference Play-In"),

    # Win totals (generic — handles NBA, MLB, NHL, NFL after pro sport rewrite)
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Win\s+Totals?.*$", re.I), "Win Total"),
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Wins\s*$", re.I), "Win Total"),
    (re.compile(r"^(.+?)\s+(?:NBA|MLB|NHL|NFL)\s+wins\s+this\s+season\??\s*$", re.I),
     r"\1 Win Total"),
    (re.compile(r"^Regular\s+Season\s+Win\s+Totals?\s*$", re.I), "Win Total"),
    # Binary win total per team: "Boston Celtics 2025-26 Season Win Total Over 48.5"
    (re.compile(
        r"^(.+?)\s+\d{4}[-\u2013]\d{2,4}\s+(?:Season\s+)?Win\s+Total\s+(?:Over|Under)\s+[\d.]+\s*$",
        re.I,
    ), r"\1 Win Total"),

    # Win streak
    (re.compile(r"^How many games will (.+?) win in a row.*$", re.I),
     r"\1 Win Streak"),

    # Best/worst record (generic)
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Best\s+(?:Regular\s+Season\s+)?Record\s*$", re.I),
     "Best Record"),
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Worst\s+(?:Regular\s+Season\s+)?Record\s*$", re.I),
     "Worst Record"),

    # Seed
    (re.compile(r"^(?:NBA\s+)?(Eastern|Western)\s+Conference\s+#1\s+Seed\s*$", re.I),
     r"\1 Conference #1 Seed"),

    # Division winner (generic — handles NBA, NHL after prefix strip)
    (re.compile(r"^(?:(?:NBA|NHL|NFL)[\s:]+)?(\w+)\s+Division\s+(?:Winner)?\s*$", re.I),
     r"\1 Division Winner"),

    # Stats leaders
    (re.compile(r"^NBA\s+Points?\s+Per\s+Game\s+Leader\s*$", re.I), "PPG Leader"),
    (re.compile(r"^NBA\s+Rebounds?\s+Per\s+Game\s+Leader\s*$", re.I), "RPG Leader"),
    (re.compile(r"^NBA\s+Assists?\s+Per\s+Game\s+Leader\s*$", re.I), "APG Leader"),
    (re.compile(r"^NBA\s+Steals?\s+Per\s+Game\s+Leader\s*$", re.I), "SPG Leader"),
    (re.compile(r"^NBA\s+Blocks?\s+Per\s+Game\s+Leader\s*$", re.I), "BPG Leader"),
    (re.compile(r"^NBA\s+Three\s+Pointers?\s+(?:Made\s+)?Per\s+Game\s+Leader\s*$", re.I),
     "3PM Leader"),

    # NBA Awards
    (re.compile(r"^(?:NBA\s+)?MVP\s*(?:Winner)?\s*$", re.I), "MVP"),
    (re.compile(r"^(?:NBA\s+)?Defensive\s+Player\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I),
     "DPOY"),
    (re.compile(r"^(?:NBA\s+)?Sixth\s+Man\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I),
     "6MOY"),
    (re.compile(r"^(?:NBA\s+)?Most\s+Improved\s+Player\s*(?:Winner)?\s*$", re.I), "MIP"),
    (re.compile(r"^(?:NBA\s+)?Clutch\s+Player\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I),
     "Clutch Player"),
    (re.compile(r"^Rookie\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I), "ROY"),
    (re.compile(r"^Finals\s+MVP\s*(?:Winner)?\s*$", re.I), "Finals MVP"),

    # All-teams
    (re.compile(r"^All-NBA\s+(1st|2nd|3rd)\s+Team\s*(?:Selections?)?\s*$", re.I),
     r"All-NBA \1 Team"),
    (re.compile(r"^NBA\s+All-Defensive\s+(1st|2nd|3rd)\s+Team\s*(?:Selections?)?\s*$", re.I),
     r"All-Defensive \1 Team"),

    # NBA Draft
    (re.compile(r"^NBA\s+Draft:\s+(1st|2nd|3rd)\s+Overall\s+[Pp]ick\s*$", re.I),
     r"NBA Draft \1 Pick"),
    (re.compile(r"^NBA\s+#(\d+)\s+Overall\s+Pick\s*$", re.I),
     r"NBA Draft #\1 Pick"),
    (re.compile(r"^NBA\s+Players\s+Drafted\s+Top\s+(\d+)\s*$", re.I),
     r"NBA Draft Top \1"),

    # ── NHL ──────────────────────────────────────────────────────────────

    # Stanley Cup
    (re.compile(r"^(?:2\d{3}\s+)?(?:NHL\s+)?Stanley\s+Cup[®]?\s*(?:Champion)?\??\s*$", re.I),
     "Stanley Cup Champion"),
    (re.compile(r"^NHL\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I),
     "Stanley Cup Champion"),

    # NHL Playoffs
    (re.compile(r"^Stanley\s+Cup[®]?\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I),
     "Make NHL Playoffs"),
    (re.compile(r"^Which teams will make the NHL Playoffs\??\s*$", re.I),
     "Make NHL Playoffs"),
    (re.compile(r"^NHL\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I),
     "Make NHL Playoffs"),

    # NHL Trophies
    (re.compile(r"^NHL\s+Hart\s+Memorial\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Hart Trophy"),
    (re.compile(r"^NHL\s+James\s+Norris\s+Memorial\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Norris Trophy"),
    (re.compile(r"^NHL\s+Vezina\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Vezina Trophy"),
    (re.compile(r"^NHL\s+Calder\s+Memorial\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Calder Trophy"),
    (re.compile(r"^NHL\s+Art\s+Ross\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Art Ross Trophy"),
    (re.compile(r"^NHL\s+Selke\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Selke Trophy"),
    (re.compile(r"^NHL\s+Conn\s+Smythe\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Conn Smythe Trophy"),
    # Maurice "Rocket" Richard (various quote styles)
    (re.compile(
        r"^NHL\s+Maurice\s+['\u2018\u2019\u201C\u201D\"]+Rocket['\u2018\u2019\u201C\u201D\"]+\s+"
        r"Richard\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Rocket Richard Trophy"),
    # Presidents' Trophy (various apostrophe placements)
    (re.compile(r"^NHL\s+President['\u2019]?s?['\u2019]?\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Presidents' Trophy"),

    # ── MLB ──────────────────────────────────────────────────────────────

    # World Series
    (re.compile(r"^(?:MLB\s+)?World\s+Series\s+(?:Champion|Winner)\s*(?:\d{4})?\s*$", re.I),
     "World Series Champion"),
    (re.compile(r"^MLB\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I),
     "World Series Champion"),

    # League champions
    (re.compile(r"^American\s+League\s+Champion\s*$", re.I), "AL Champion"),
    (re.compile(r"^National\s+League\s+Champion\s*$", re.I), "NL Champion"),

    # MLB divisions (AL/NL + direction + Division/Champion)
    (re.compile(r"^(AL|NL)\s+(East|West|Central)\s+(?:Division\s+)?(?:Champion|Winner)\s*$", re.I),
     r"\1 \2 Winner"),

    # MLB Playoffs
    (re.compile(r"^MLB\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I), "Make MLB Playoffs"),

    # World Series Matchup
    (re.compile(r"^MLB\s+Championship\s+Series\s+Matchup\s*$", re.I),
     "World Series Matchup"),

    # Streaks
    (re.compile(r"^Longest\s+(?:regular\s+season\s+)?(winning|losing)\s+streak\s*$", re.I),
     r"Longest \1 Streak"),

    # ── NCAA ─────────────────────────────────────────────────────────────

    # NCAA Championship
    (re.compile(r"^NCAAB\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I), "NCAAB Champion"),
    (re.compile(r"^NCAA\s+Tournament\s+Winner\s*$", re.I), "NCAA Champion"),

    # NCAA Tournament advancement (Polymarket style)
    (re.compile(r"^NCAA\s+Tournament:\s+Team\s+to\s+make\s+Semifinals?\s*$", re.I),
     "Make Final Four"),
    (re.compile(r"^NCAA\s+Tournament:\s+Team\s+to\s+make\s+National\s+Championship\s*$", re.I),
     "Make Championship Game"),
    (re.compile(r"^NCAA\s+Tournament:\s+Team\s+to\s+make\s+Sweet\s+Sixteen\s*$", re.I),
     "Make Sweet Sixteen"),

    # NCAA Tournament awards
    (re.compile(r"^(?:NCAA\s+Tournament:\s+)?Most\s+Outstanding\s+Player\s*$", re.I),
     "Most Outstanding Player"),
    (re.compile(
        r"^(?:Men's\s+)?College\s+Basketball\s+(?:Tournament\s+)?Most\s+Outstanding\s+Player\s*$",
        re.I),
     "Most Outstanding Player"),

    # Naismith awards
    (re.compile(
        r"^(?:College\s+Basketball\s+)?Naismith\s+(?:College\s+)?Player\s+of\s+the\s+Year\s*$",
        re.I),
     "Naismith Player of the Year"),
    (re.compile(
        r"^(?:NCAAM:\s+)?Naismith\s+Defensive\s+Player\s+of\s+the\s+Year\s*$", re.I),
     "Naismith DPOY"),

    # NCAA seeding
    (re.compile(r"^Men's\s+(\d+)\s+Seed\s*$", re.I), r"#\1 Seed"),

    # NCAA bracket rounds (Kalshi "Men's X Qualifiers" style) — keep as "Men's X"
    (re.compile(
        r"^(Men's|Women's)\s+(Round\s+of\s+\d+|Semifinals|Championship\s+Game)"
        r"\s*(?:Qualifiers?)?\s*$", re.I),
     r"\1 \2"),

    # "Team to Score the Most Points in ..." (tournament novelty prop)
    (re.compile(r"^Team\s+to\s+Score\s+the\s+Most\s+Points\s+in\s+the\s+(.+?)\s*$", re.I),
     r"Most Points in \1"),

    # ── Generic (all sports) ─────────────────────────────────────────────

    # Trade rumors (handle trailing "?")
    (re.compile(r"^(.+?)['\u2019]s?\s+[Nn]ext\s+[Tt]eam\??\s*$", re.I),
     r"\1 Trade Destination"),

    # Novelty
    (re.compile(r"^Who will be on the cover of NBA 2K\d+\??\s*$", re.I), "NBA 2K Cover"),
    (re.compile(r"^(.+?) play together on (.+?) again\??\s*$", re.I),
     r"\1 Stay in \2?"),

    # "When will X make/break/reach his Nth..." → "X: Milestone Description"
    (re.compile(
        r"^When will (.+?) (?:make|hit|reach|break|score|get) "
        r"(?:his|her|their)\s+(\d+)(?:st|nd|rd|th)\s+(.+?)(?:\s+\(.*\))?\??\s*$",
        re.I),
     r"\1: \2th \3"),

    # "Will X break/set the record for..." → "X: Record Name"
    (re.compile(
        r"^Will (.+?) (?:break|set|beat) (?:the )?"
        r"(?:record|all-time record) (?:for )?(.+?)\??\s*$",
        re.I),
     r"\1: \2 Record"),
]

# Game prop detection: "Team at/vs Team: Stat" or "Team vs. Team" (bare moneyline)
_GAME_STAT_PROP_RE = re.compile(
    r".+\s+(?:at|vs\.?)\s+.+:\s*(?:1H\s+)?(?:O/U\s+\d|"
    r"Points|Rebounds|Assists|Steals|Blocks|Three\s*Pointers?|"
    r"Turnovers|Double\s*Doubles?|Triple\s*Doubles?|First\s+Half\s+Winner|"
    r"Spread|Total\s*Points?|Team\s*Totals?|Moneyline|"
    # Polymarket player prop format: "Player: Stat O/U X"
    r"[A-Z][a-z]+\s+[A-Z])",
    re.IGNORECASE,
)

# Bare "Team vs. Team" markets (Polymarket moneyline, no stat qualifier)
_BARE_MATCHUP_RE = re.compile(
    r"^[A-Z0-9][\w\s.]+\s+vs\.?\s+[A-Z0-9][\w\s.]+$",
    re.IGNORECASE,
)

# NCAA bracket round detection
_NCAA_ROUND_RE = re.compile(
    r"(?:Men's|Women's)\s+(?:Round\s+of\s+\d+|Semifinals|Championship\s+Game|"
    r"College\s+Basketball\s+Champion)",
    re.IGNORECASE,
)

# Canadian Football League detection (#7851). The CFL shares our
# `americanfootball` prefix and the LLM files it under `llm_sport_category =
# 'football'`, which is the one arm of the related-futures sport net that admits
# a market carrying neither a US-league ticker nor a sport_id — so the Grey Cup
# reaches every NFL, NCAAF and FCS event page.
_CFL_MARKET_RE = re.compile(r"\bCFL\b|\bGrey\s+Cup\b|\bCanadian\s+Football\b", re.IGNORECASE)


# ── Category assignment ──────────────────────────────────────────────────

_CATEGORY_RULES: list[tuple[re.Pattern, str]] = [
    # Series markets (before game_prop — "Win Series – Team vs Team" contains "vs" pattern)
    (re.compile(r"\bwin\s+series\b|\bseries\s+winner\b|\bseries.*total\s+games\b|\bseries\s+exact\b", re.I),
     "series"),

    # Game props (highest priority — check before championship/conference patterns)
    (_GAME_STAT_PROP_RE, "game_prop"),
    (_BARE_MATCHUP_RE, "game_prop"),

    # NCAA bracket rounds
    (_NCAA_ROUND_RE, "ncaa"),

    # Trade destinations
    (re.compile(r"Trade Destination$|Next Team$|next team\??$", re.I), "trade"),

    # Novelty
    (re.compile(
        r"2K\s*Cover|play together|record.*three\s*pointer|breaking.*record|"
        r"Most Points in|Stay in .+\?|^\w.+:\s+\d+th\s+",
        re.I,
    ), "novelty"),

    # Playoff path (check specific before general)
    (re.compile(r"Champion$", re.I), "playoff_path"),
    (re.compile(r"Conference Champion$", re.I), "playoff_path"),
    (re.compile(r"^Make\s+", re.I), "playoff_path"),
    (re.compile(r"Playoff\s+(Qualifiers|Teams)", re.I), "playoff_path"),
    (re.compile(r"Play-In", re.I), "playoff_path"),
    (re.compile(r"#\d+\s+Seed", re.I), "playoff_path"),

    # Conference (must be before awards — "Conf Finals MVP" is conference, not award)
    (re.compile(r"Conf(?:erence)? Finals\b", re.I), "conference"),
    (re.compile(r"(?:NBA|World Series|Championship Series)\s+(?:Finals\s+)?Matchup", re.I),
     "conference"),

    # Awards — NHL trophies, NBA awards, NCAA awards, draft picks
    (re.compile(
        r"\bMVP\b|\bDPOY\b|\b6MOY\b|\bMIP\b|\bROY\b|Clutch Player|"
        r"All-NBA|All-Defensive|"
        r"Hart Trophy|Norris Trophy|Vezina Trophy|Calder Trophy|"
        r"Art Ross Trophy|Rocket Richard|Selke Trophy|Conn Smythe|"
        r"Most Outstanding Player|Naismith|"
        r"NBA Draft",
        re.I,
    ), "award"),

    # Season stats
    (re.compile(
        r"PPG|RPG|APG|SPG|BPG|3PM|Per Game Leader|"
        r"Best Record|Worst Record|Win Total|Win Streak|Division Winner|"
        r"Presidents['\u2019]?\s+Trophy|"
        r"Longest .+ Streak|"
        r"(AL|NL)\s+(East|West|Central)\s+Winner|"
        r"\b(Doubles|Triples|Stolen Bases|Home Run|Hits|RBI|Batting Average|ERA|Saves|Strikeouts?)\s+Leader\b|"
        r"\b\d+\+\s+Home Run\b|"
        r"Player of the (Week|Month)|Pitcher of the Month|Platinum Glove|Reliever of the Year",
        re.I,
    ), "season_stat"),
]


# ── Merge group assignment ───────────────────────────────────────────────

_MERGE_RULES: list[tuple[re.Pattern, str]] = [
    # NBA
    (re.compile(r"NBA Champion", re.I), "nba_champion"),
    (re.compile(r"(Eastern|Western) Conference Champion", re.I), r"\1_conf_champion"),
    (re.compile(r"Make NBA Playoffs|NBA Playoff Qualifiers", re.I), "make_playoffs"),
    (re.compile(r"(Eastern|Western) Conference #1 Seed", re.I), r"\1_conf_1_seed"),
    (re.compile(r"(Eastern|Western) Conference Play-In", re.I), r"\1_conf_playin"),
    (re.compile(r"^(?:NBA\s+|NHL\s+|MLB\s+|NFL\s+|MLS\s+)?MVP$", re.I), "mvp"),
    (re.compile(r"^(?:NBA\s+|NHL\s+|MLB\s+|NFL\s+)?Finals MVP$", re.I), "finals_mvp"),
    (re.compile(r"^(?:NBA\s+|NHL\s+|MLB\s+|NFL\s+)?DPOY$", re.I), "dpoy"),
    (re.compile(r"^(?:NBA\s+|NHL\s+)?6MOY$", re.I), "6moy"),
    (re.compile(r"^(?:NBA\s+|NHL\s+)?6th Man of the Year$", re.I), "6moy"),
    (re.compile(r"^(?:NBA\s+|NHL\s+|MLB\s+|NFL\s+)?MIP$", re.I), "mip"),
    (re.compile(r"^(?:NBA\s+|NHL\s+|MLB\s+|NFL\s+)?ROY$", re.I), "roy"),
    (re.compile(r"^(?:NBA\s+)?Clutch Player$", re.I), "clutch_player"),
    (re.compile(r"^PPG Leader$", re.I), "ppg_leader"),
    (re.compile(r"^RPG Leader$", re.I), "rpg_leader"),
    (re.compile(r"^APG Leader$", re.I), "apg_leader"),
    (re.compile(r"^SPG Leader$", re.I), "spg_leader"),
    (re.compile(r"^BPG Leader$", re.I), "bpg_leader"),
    (re.compile(r"^3PM Leader$", re.I), "3pm_leader"),
    (re.compile(r"^Best Record$", re.I), "best_record"),
    (re.compile(r"^Worst Record$", re.I), "worst_record"),
    (re.compile(r"Win Total$", re.I), "win_total"),
    (re.compile(r"(\w+) Division Winner", re.I), r"\1_division"),
    (re.compile(r"(Eastern|Western) Conference Finals Matchup", re.I),
     r"\1_conf_finals_matchup"),
    (re.compile(r"NBA Finals Matchup", re.I), "nba_finals_matchup"),
    (re.compile(r"(Eastern|Western) Conf Finals MVP", re.I), r"\1_conf_finals_mvp"),
    (re.compile(r"All-NBA (\d)", re.I), r"all_nba_\1"),
    (re.compile(r"All-Defensive (\d)", re.I), r"all_def_\1"),
    (re.compile(r"NBA Draft #?(\d+)\w*\s+Pick", re.I), r"nba_draft_\1"),

    # Trade destinations (per-player merge group)
    (re.compile(r"^(.+?)\s+Trade Destination$", re.I), r"\1_trade"),

    # NFL
    (re.compile(r"Super Bowl Champion", re.I), "nfl_champion"),
    (re.compile(r"(AFC|NFC) Champion", re.I), r"\1_champion"),
    (re.compile(r"Super Bowl Matchup", re.I), "super_bowl_matchup"),
    (re.compile(r"Make NFL Playoffs", re.I), "make_nfl_playoffs"),
    (re.compile(r"^NFL MVP$", re.I), "nfl_mvp"),

    # NHL
    (re.compile(r"Stanley Cup Champion", re.I), "stanley_cup_champion"),
    (re.compile(r"Stanley Cup Matchup", re.I), "stanley_cup_matchup"),
    (re.compile(r"Make NHL Playoffs", re.I), "make_nhl_playoffs"),
    (re.compile(r"^Hart Trophy$", re.I), "hart_trophy"),
    (re.compile(r"^Norris Trophy$", re.I), "norris_trophy"),
    (re.compile(r"^Vezina Trophy$", re.I), "vezina_trophy"),
    (re.compile(r"^Calder Trophy$", re.I), "calder_trophy"),
    (re.compile(r"^Art Ross Trophy$", re.I), "art_ross_trophy"),
    (re.compile(r"^Rocket Richard Trophy$", re.I), "rocket_richard_trophy"),
    (re.compile(r"^Selke Trophy$", re.I), "selke_trophy"),
    (re.compile(r"^Conn Smythe Trophy$", re.I), "conn_smythe_trophy"),
    (re.compile(r"^Presidents['\u2019]?\s+Trophy$", re.I), "presidents_trophy"),

    # MLB
    (re.compile(r"World Series Champion", re.I), "world_series_champion"),
    (re.compile(r"^AL Champion$", re.I), "al_champion"),
    (re.compile(r"^NL Champion$", re.I), "nl_champion"),
    (re.compile(r"Make MLB Playoffs", re.I), "make_mlb_playoffs"),
    (re.compile(r"World Series Matchup", re.I), "world_series_matchup"),
    (re.compile(r"^(AL|NL)\s+(East|West|Central)\s+Winner$", re.I), r"\1_\2"),

    # MLB awards (#4414). The award rules further up take an optional
    # FOUR-LETTER LEAGUE prefix (`NBA MVP`, `NFL MVP`), which cannot express a
    # race scoped by league WITHIN the sport, so `AL MVP` and `MLB: 2026 AL MVP`
    # both cleaned to "AL MVP", both returned None, and the event page rendered
    # the same race twice with two disagreeing numbers.
    #
    # The league word is CAPTURED, never consumed as a prefix: `al_mvp` and
    # `nl_mvp` are different races and merging them would be the strictly worse
    # bug — a duplicate is visibly odd, a wrong merge is invisibly wrong. The
    # award names are ENUMERATED rather than matched by grammar because `AL` is
    # also how several clubs arrive in uppercase ("AL Ahly SC (Egy) vs Club
    # Africain", "AL Suqoor vs Al-Fateh", "AL Wakrah SC vs. Al Rayyan SC"), and
    # a `^(AL|NL)\s+(.+)$` rule would mint a merge group for every one of them.
    (re.compile(r"^(AL|NL)\s+Hank Aaron(?: Award)?$", re.I), r"\1_hank_aaron"),
    (re.compile(r"^(AL|NL)\s+All-Star$", re.I), r"\1_all_star"),
    (re.compile(
        r"^(AL|NL)\s+(MVP|Cy Young|Rookie of the Year|Manager of the Year|"
        r"Reliever of the Year|Comeback Player of the Year)$", re.I,
    ), r"\1_\2"),

    # NCAA
    (re.compile(r"NCAA(?:B)? Champion", re.I), "ncaa_champion"),
    (re.compile(r"Make Final Four", re.I), "make_final_four"),
    (re.compile(r"Make Championship Game", re.I), "make_championship_game"),
    (re.compile(r"Make Sweet Sixteen", re.I), "make_sweet_sixteen"),
    (re.compile(r"^Most Outstanding Player$", re.I), "most_outstanding_player"),
    (re.compile(r"^Naismith Player of the Year$", re.I), "naismith_poty"),
    (re.compile(r"^Naismith DPOY$", re.I), "naismith_dpoy"),
]


def rewrite_venue_league_vocabulary(raw_name: str) -> str:
    """Rename a venue's league phrase to ours, and change nothing else (#7397).

    For surfaces that print a market's own title and cannot strip its league,
    because they are not scoped to one: search results, the typeahead dropdown.
    `Pro Football: 2027 Champion` → `NFL: 2027 Champion`.

    This is deliberately NOT `normalize_market_label`. That function is built for
    the Related Futures rail, where the page already says which league it is, so
    it goes on to delete the league prefix and the year — turning the same
    specimen into the bare `Champion`. Right on an event page, useless in a list
    of search results. See the note on `_VENUE_LEAGUE_REWRITES` for why the
    `All-Pro` rule is excluded here rather than shared.

    Whitespace is preserved exactly: a display-only rewrite must not also become
    a silent trim, or a caller comparing against the stored name sees a diff it
    did not ask for.
    """
    return _apply_venue_league_rewrites(raw_name, _VENUE_LEAGUE_REWRITES)


def _apply_venue_league_rewrites(
    raw_name: str, bare_rules: list[tuple[re.Pattern, str]]
) -> str:
    """Qualified phrases first, then the bare rules, which decline a qualifier.

    Shared by `rewrite_venue_league_vocabulary` and `normalize_market_label` so
    the two cannot drift: the WNBA defect existed in both, because the rail
    splats the same list.
    """
    label = raw_name
    for pat, repl in _QUALIFIED_VENUE_LEAGUE_REWRITES:
        label = pat.sub(repl, label)

    for pat, repl in bare_rules:
        # The phrase is matched together with any indefinite article in front of
        # it, so the two can be rewritten as one unit — see
        # `_VOWEL_SOUND_INITIALISMS`. The article is optional, so this still
        # matches everywhere the bare pattern did; `phrase` is a named group
        # because the qualifier test below needs the phrase's own start offset,
        # not the match's.
        composed = re.compile(
            r"(?:(?P<article>\ba)(?P<gap>\s+))?(?P<phrase>" + pat.pattern + r")",
            pat.flags,
        )

        # `re` has no variable-length lookbehind, so the qualifier test runs per
        # match against the text to its left. Read against `label`, not
        # `raw_name`: an earlier rule may already have rewritten that text, and
        # the question is what is in front of this match NOW.
        def _guarded(match: re.Match, _repl: str = repl) -> str:
            if _LEAGUE_CHANGING_QUALIFIER.search(match.string[: match.start("phrase")]):
                # Declining returns the WHOLE match, article included, so a
                # qualified phrase is left exactly as the venue wrote it.
                return match.group(0)

            article = match.group("article")
            if article is None:
                return _repl

            # A capital "A" that is not the first character of the name is a
            # Kalshi team abbreviation, not an article. This is not a
            # hypothetical: market 252 is `Los Angeles A pro baseball wins this
            # season?` — the LA Angels, written the same way as the `New York J`
            # and `New York G` rows the NFL page already serves. Treating it as
            # an article yields "Los Angeles An MLB wins this season?", which is
            # worse than the jargon we came to remove. A sentence-initial "A" is
            # a real article and is still corrected.
            is_team_abbreviation = article == "A" and match.start("article") != 0
            if is_team_abbreviation or _repl not in _VOWEL_SOUND_INITIALISMS:
                return f"{article}{match.group('gap')}{_repl}"

            return f"{'An' if article.isupper() else 'an'}{match.group('gap')}{_repl}"

        label = composed.sub(_guarded, label)
    return label


def normalize_market_label(raw_name: str) -> str:
    """Clean a raw market name into a human-readable label."""
    label = raw_name.strip()

    # Step 1: Rewrite "Pro Basketball/Football/etc." → league name. Through the
    # shared applier, so the rail gets the qualified phrases and the qualifier
    # guard too — it splats the same bare list and had the same WNBA defect.
    label = _apply_venue_league_rewrites(label, _PRO_SPORT_REWRITES)

    # Step 2: Strip league:year prefix ("MLB: 2026 ...", "NHL: ...")
    label = _LEAGUE_PREFIX_RE.sub("", label)

    # Step 3: Strip standalone year prefix ("2026 ...", "2025-2026 ...")
    label = _YEAR_PREFIX_RE.sub("", label)

    label = label.strip()

    # Step 4: Apply specific label rewrites (these handle suffixes internally)
    for pat, repl in _LABEL_REWRITES:
        m = pat.match(label)
        if m:
            label = m.expand(repl)
            return label.strip()

    # Step 5: Don't strip suffixes from game props (e.g., "Team vs Team: First Half Winner")
    if _GAME_STAT_PROP_RE.search(label):
        return label.strip()

    # Step 6: Only strip verbose suffixes if no specific rewrite matched
    for pat, repl in _VERBOSE_SUFFIXES:
        label = pat.sub(repl, label)

    label = label.strip()

    # Step 7: Truncate very long labels (novelty/misc) at a word boundary
    if len(label) > 60:
        truncated = label[:57]
        # Cut at last space to avoid breaking mid-word
        last_space = truncated.rfind(" ")
        if last_space > 30:
            truncated = truncated[:last_space]
        label = truncated.rstrip(".,;: ") + "…"

    return label


def classify_market_category(
    clean_label: str,
    raw_name: str = "",
    market_category: str = "",
) -> str:
    """Assign a structured category to a market based on its clean label."""
    # Check clean label first
    for pat, cat in _CATEGORY_RULES:
        if pat.search(clean_label):
            return cat

    # Check raw name as fallback
    if raw_name and raw_name != clean_label:
        for pat, cat in _CATEGORY_RULES:
            if pat.search(raw_name):
                return cat

    # Use existing category from DB if available
    if market_category in ("game_prop", "championship", "award"):
        return market_category

    logger.debug("Unclassified market (category=other): clean=%r raw=%r", clean_label, raw_name)
    return "other"


def get_merge_group(clean_label: str) -> Optional[str]:
    """Get the merge group key for a clean label.

    Markets with the same merge group represent the same thing across
    different sources and should be aggregated into a single display item.
    """
    for pat, repl in _MERGE_RULES:
        m = pat.search(clean_label)
        if m:
            result = m.expand(repl)
            return result.lower().replace(" ", "_")
    return None


def is_wrong_sport_leak(
    raw_name: str,
    outcome_name: str,
    event_sport_key: str,
) -> bool:
    """Detect if a market leaked in from a different sport."""
    if not event_sport_key:
        return False

    sport_prefix = event_sport_key.split("_")[0]

    # ── NCAA bracket rounds in non-NCAA games ────────────────────────────
    if sport_prefix != "basketball" or "_ncaa" not in event_sport_key:
        if _NCAA_ROUND_RE.search(raw_name):
            return True
        if re.search(r"College Basketball Champion", raw_name, re.I):
            return True
        if re.search(r"NCAAB Championship", raw_name, re.I):
            return True
        if re.search(r"NCAA Tournament", raw_name, re.I):
            return True
        if re.search(r"Naismith", raw_name, re.I):
            return True

    # ── NHL teams leaking into NBA/NCAA via conference markets ───────────
    if sport_prefix == "basketball":
        _NHL_TEAMS = {
            "bruins", "rangers", "maple leafs", "canadiens", "penguins",
            "capitals", "flyers", "devils", "islanders", "hurricanes",
            "panthers", "lightning", "red wings", "senators", "sabres",
            "blue jackets", "blackhawks", "blues", "predators", "stars",
            "wild", "avalanche", "jets", "flames", "oilers", "canucks",
            "kraken", "coyotes", "sharks", "golden knights", "ducks",
            "utah hockey club",
        }
        outcome_lower = outcome_name.lower()
        for team in _NHL_TEAMS:
            if team in outcome_lower:
                return True

    # ── AHL / College Hockey leaking into NHL games ──────────────────────
    if "icehockey" in event_sport_key and "_nhl" in event_sport_key:
        if re.search(r"\bAHL\b|College Hockey", raw_name, re.I):
            return True

    # ── College Baseball leaking into MLB games ──────────────────────────
    if "baseball" in event_sport_key and "_mlb" in event_sport_key:
        if re.search(r"College Baseball", raw_name, re.I):
            return True

    # ── CFL leaking into US football (NFL / NCAAF / FCS) ─────────────────
    # #7851, reported by a reader watching Stanford–Duke on 2026-09-19:
    # `/api/events/15311565/related-futures` served "2026 CFL Grey Cup
    # Champion || Winnipeg Blue Bombers 0.125" as the SECOND card of Duke Blue
    # Devils' championship path. `_team_name_patterns("Duke Blue Devils")`
    # emits the bare token "Blue", and "Blue" occupies whole tokens of
    # "Winnipeg Blue Bombers", so the #6806 boundary rule cannot refuse it.
    # Measured the same day on the FCS page 15313355: "British Columbia Lions"
    # reached Columbia Lions by the same route, so this is a class, not a
    # specimen.
    #
    # The refusal is on the LEAGUE, not the token, because the token rule has
    # no way to know Winnipeg is not Duke. Scoped to leave a real CFL page
    # alone: event 15312374 (Hamilton Tiger-Cats vs Montreal Alouettes) serves
    # the Grey Cup correctly to both sides and must keep doing so.
    if sport_prefix == "americanfootball" and "_cfl" not in event_sport_key:
        if _CFL_MARKET_RE.search(raw_name):
            return True

    # ── NBA conference markets leaking into NCAA games ───────────────────
    if "_ncaa" in event_sport_key:
        if re.search(r"(Eastern|Western) Conference Finals Winner", raw_name, re.I):
            return True

    return False


# ── Playoff stage classification ─────────────────────────────────────────
# Single source of truth for playoff stage names and ordering.
# Frontends should use these pre-computed values instead of re-deriving.
# Priority order matters: conference MUST be checked before championship
# to prevent "Eastern Conference Champion" matching "champion" first.

_PLAYOFF_STAGE_RULES: list[tuple[re.Pattern, str, int]] = [
    # Priority 1: Conference (checked FIRST — "Eastern Conference Champion" is conference, not championship)
    # Includes "\bAL\b" and "\bNL\b" for MLB pennant (American/National League Champion)
    (re.compile(r"conference|eastern|western|afc|nfc|american\s+league|national\s+league|\bAL\b\s+champ|\bNL\b\s+champ", re.I),
     "conference", 4),
    # Priority 2: Championship
    (re.compile(r"championship|champion|title|finals|world\s+series|super\s+bowl|stanley\s+cup", re.I),
     "championship", 5),
    # Priority 3: Division
    (re.compile(r"division", re.I), "division", 3),
    # Priority 4: Play-In
    (re.compile(r"play[- ]?in", re.I), "play_in", 2),
    # Priority 5: Make Playoffs
    (re.compile(r"make\s+playoffs|playoff\s+berth|playoff\s+qualifiers|playoffs$", re.I),
     "playoffs", 1),
    # Priority 6: #1 Seed / Best Record
    (re.compile(r"#1\s+seed|top\s+seed|first\s+seed|best\s+record", re.I),
     "top_seed", 6),
]

# Extract specific conference/division name for display
_CONF_NAME_RE = re.compile(r"(eastern|western|afc|nfc|american|national|\bAL\b|\bNL\b)", re.I)
_DIV_NAME_RE = re.compile(r"([\w]+)\s+division", re.I)


def compute_playoff_stage(
    clean_label: str,
    raw_name: str = "",
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Compute playoff stage classification for a market.

    Returns (stage_type, stage_display_name, stage_order) or (None, None, None)
    if not a playoff-path market.

    stage_type: machine-readable key ("conference", "championship", "division", etc.)
    stage_display_name: human-readable label ("Eastern Champ", "Championship", "Atlantic Div")
    stage_order: sort order (1=Playoffs, 2=Play-In, 3=Division, 4=Conference, 5=Championship, 6=#1 Seed)
    """
    text = (clean_label or raw_name or "").lower()
    if not text:
        return None, None, None

    for pattern, stage_type, order in _PLAYOFF_STAGE_RULES:
        if pattern.search(text):
            # Compute display name based on stage type
            if stage_type == "conference":
                m = _CONF_NAME_RE.search(text)
                if m:
                    raw = m.group(1)
                    # Keep abbreviations uppercase (AL, NL, AFC, NFC)
                    if raw.upper() in ("AL", "NL", "AFC", "NFC"):
                        display = raw.upper() + " Champ"
                    else:
                        display = raw[0].upper() + raw[1:] + " Champ"
                else:
                    display = "Conference"
            elif stage_type == "championship":
                display = "Championship"
            elif stage_type == "division":
                m = _DIV_NAME_RE.search(text)
                if m and m.group(1).lower() not in ("the", "a", "win"):
                    display = m.group(1)[0].upper() + m.group(1)[1:] + " Div"
                else:
                    display = "Division"
            elif stage_type == "play_in":
                display = "Play-In"
            elif stage_type == "playoffs":
                display = "Playoffs"
            elif stage_type == "top_seed":
                display = "#1 Seed"
            else:
                display = clean_label or raw_name

            return stage_type, display, order

    return None, None, None


# ── Relevance filtering ──────────────────────────────────────────────────

CATEGORY_RELEVANCE_ORDER = [
    "playoff_path",
    "conference",
    "award",
    "season_stat",
    "game_prop",
    "trade",
    "novelty",
    "ncaa",
    "other",
]

CATEGORY_LIMITS = {
    "playoff_path": 8,
    "conference": 4,
    "award": 6,
    "season_stat": 4,
    "game_prop": 6,
    "trade": 3,
    "novelty": 2,
    "ncaa": 0,
    "other": 2,
}


# ── Market tier assignment ───────────────────────────────────────────────
# Moved from team_linking.py to co-locate all market classification logic.
# Tier = display priority/importance (1-5), orthogonal to category.

# Tier 1: Championship / title winner
_TIER_1_PATTERNS = [
    re.compile(r"\b(championship|champion|super.bowl|world.series|stanley.cup|nba.finals|title)\b", re.I),
    re.compile(r"\bwinner\b", re.I),
]

# Tier 2: Conference winner
_TIER_2_PATTERNS = [
    re.compile(r"\b(conference|eastern|western|afc|nfc|american.league|national.league)\b", re.I),
    re.compile(r"\badvance.to.+finals\b", re.I),
]

# Tier 3: Awards / MVP / individual honors
_TIER_3_PATTERNS = [
    re.compile(r"\b(mvp|rookie|defensive.player|sixth.man|most.improved|cy.young|heisman)\b", re.I),
    re.compile(r"\b(hart.trophy|vezina|calder|norris.trophy|selke|conn.smythe|ballon.d.or)\b", re.I),
    re.compile(r"\b(award|trophy|player.of.the.year|golden.boot|golden.glove)\b", re.I),
]

# Tier 4: Division winner
_TIER_4_PATTERNS = [
    re.compile(r"\b(division|atlantic|pacific|central|southeast|northwest|southwest)\b", re.I),
    re.compile(r"\b(al.east|al.west|al.central|nl.east|nl.west|nl.central)\b", re.I),
    re.compile(r"\b(afc.east|afc.west|afc.north|afc.south|nfc.east|nfc.west|nfc.north|nfc.south)\b", re.I),
    re.compile(r"\b(metropolitan|atlantic.division|pacific.division|central.division)\b", re.I),
    re.compile(r"\bplayoff.qualif", re.I),
    re.compile(r"\bmake.+(?:playoffs|postseason)", re.I),
    re.compile(r"\b(?:playoff|postseason).berth", re.I),
]

# Tier 5 patterns: game-level, series-level, and prop markets
_TIER_5_PATTERNS = [
    re.compile(r"\b(first|second|1st|2nd).half\b", re.I),
    re.compile(r"\btotal.games\b", re.I),
    re.compile(r"\b(o/u|over.under)\b", re.I),
    re.compile(r"\bnext.team\b", re.I),
    re.compile(r"\bwin.series\b", re.I),
    re.compile(r"\bseries.winner\b", re.I),
    re.compile(r"\bwho.will.win.series\b", re.I),
    re.compile(r"\bwin.by\b", re.I),
]

_NON_SPORT_CATEGORIES = {
    "politics", "crypto", "economics", "entertainment", "tech",
    "weather", "geopolitics", "culture",
}


def game_prop_category(
    market_name: str,
    category: Optional[str] = None,
    sport_category: Optional[str] = None,
) -> Optional[str]:
    """``"game_prop"`` when this market's own NAME describes one contest, else ``None``.

    This is the exact question :func:`compute_market_tier` asks immediately below
    before it returns 5 — lifted out so the `category` column can ask it too and
    the two answers cannot drift. #6471 fixed the tier for this population and
    #5516 is the half it could not reach: the search card's chip is
    ``marketCategoryLabel(market.category)`` (`components/FuturesCard.tsx`), which
    names neither `market_tier` nor `market_type_label`, so 120 open Polymarket
    inning props kept printing **Championship** in the same purple pill as
    "MLB World Series Champion 2026" while their tier already read 5.

    Returning the VALUE rather than a bool, and ``None`` rather than ``False``, so
    a caller can write ``category = game_prop_category(...) or category`` and
    never has to restate the target string. One literal, one place.

    The non-sport exemption is the same one and for the same reason: "OpenAI vs.
    Anthropic: First to another Millennium Prize?" is an "A vs B: C" string but a
    top-level question, and those carry no tier hierarchy.
    """
    if (sport_category or category or "").lower() in _NON_SPORT_CATEGORIES:
        return None
    if is_game_prop(market_name or ""):
        return "game_prop"
    return None


def compute_market_tier(market_name: str, category: Optional[str] = None,
                        sport_category: Optional[str] = None) -> int:
    """
    Assign a tier (1-5) to a futures market based on its name and category.

    Tiers:
        1 = Championship / title winner (highest relevance)
        2 = Conference winner / non-sports top-level
        3 = Awards / MVP / individual honors
        4 = Division winner
        5 = Props / other (lowest relevance)

    Non-sports markets (politics, crypto, entertainment, etc.) default to
    tier 2 since they have no championship/conference hierarchy — they're
    all top-level questions that should rank alongside major sports futures.

    Returns:
        Integer 1-5
    """
    name_lower = (market_name or "").lower()
    cat_lower = (category or "").lower()

    # Name patterns are more reliable than category (Polymarket uses "championship"
    # for everything; Kalshi uses "game_prop" for some season markets).
    # Check most-specific patterns first, then fall back to category.

    # A market that names one fixture is that fixture's prop, whatever the
    # name ends with. "Athletics vs. Cleveland Guardians - 4th Inning Winner"
    # reaches _TIER_1_PATTERNS' bare \bwinner\b otherwise and prints
    # "Championship" on the search card (#6471). Kalshi's poller has forced
    # this since it was written; asking the shared predicate here means the
    # other four callers agree — in particular the re-tier sweep in
    # _backfill_team_links, which re-reads every tier-5 row and used to
    # promote these straight back to tier 1.
    #
    # Non-sport questions are exempt: "OpenAI vs. Anthropic: First to another
    # Millennium Prize?" is an "A vs B: C" string but it is a top-level
    # question, and those carry no tier hierarchy (see _NON_SPORT_CATEGORIES
    # at the foot of this function).
    #
    # Asked through `game_prop_category` rather than restated here, so the tier
    # and the `category` column are the SAME sentence evaluated once (#5516).
    if game_prop_category(market_name, category, sport_category) is not None:
        return 5

    # Tier 5 first — game-level and series-level markets are never championships
    for pattern in _TIER_5_PATTERNS:
        if pattern.search(name_lower):
            return 5

    # Division check before championship — "Division Winner" also contains "winner"
    for pattern in _TIER_4_PATTERNS:
        if pattern.search(name_lower):
            return 4

    # Conference check before championship
    for pattern in _TIER_2_PATTERNS:
        if pattern.search(name_lower):
            return 2

    # Awards check before championship — "MVP Award" might match "winner"
    for pattern in _TIER_3_PATTERNS:
        if pattern.search(name_lower):
            return 3

    if cat_lower == "mvp":
        return 3

    # Championship / title — only if name actually matches championship patterns
    for pattern in _TIER_1_PATTERNS:
        if pattern.search(name_lower):
            return 1

    # Game props that didn't match any higher pattern
    if cat_lower == "game_prop":
        return 5

    # Non-sports markets default to tier 2 (no hierarchy — all top-level)
    effective_category = (sport_category or category or "").lower()
    if effective_category in _NON_SPORT_CATEGORIES:
        return 2

    # category == "championship" but name didn't match any tier 1 pattern
    # (common with Polymarket — they label everything as championship)
    # Default to tier 5 instead of trusting the category blindly
    logger.debug("Unclassified market (tier=5): name=%r category=%r", market_name, category)
    return 5


# The three tiers whose name is a rung of a SPORTS hierarchy, taken from
# :func:`compute_market_tier`'s own docstring: "Championship / title winner",
# "Conference winner", "Division winner". Tier 3 ("Awards / MVP / individual
# honors") and tier 5 ("Props / other") are deliberately absent — those nouns
# stay true off the field, so an Oscar reading "Award" is not a defect and is
# left exactly as it is.
_SPORTS_HIERARCHY_TIERS = frozenset({1, 2, 4})


def non_sport_topic_label(
    market_tier: Optional[int],
    category: Optional[str] = None,
    sport_category: Optional[str] = None,
) -> Optional[str]:
    """The topic word for a non-sport row whose tier label would lie, else ``None``.

    #7369. Tier 2 is TWO populations, and :func:`compute_market_tier` says so in
    its own docstring — "Conference winner / **non-sports top-level**", because
    non-sport markets "have no championship/conference hierarchy". Both search
    serializers then print one word for the whole rung, so on production
    `typeahead?q=trump` answered **Conference** on "Will Trump acquire Greenland
    before 2027?", and `q=fed` answered **Conference** on "What will Levi's say
    during their next earnings call?" — an earnings *call* badged a *conference*.
    Measured 2026-09-20: 13,542 open rows on tiers 1/2/4 carry a non-sport
    category (11,766 "Conference", 1,745 "Championship", 31 "Division").

    THE PREDICATE IS THE CATEGORY, NOT THE FK. `routes/events.py` already had the
    right replacement written (`llm_sport_category or category`, title-cased) but
    gated it on ``market.sport_id is None``, and those two disagree on **1,224**
    open rows of this population — rows with no sport FK but a real sport
    category, such as `SearchProdFixture.swift`'s "Will Jasmine Paolini advance to
    the Quarterfinals … 2026 US Open?" (`llm_sport_category: tennis`, `sport:
    null`). Keying on the FK would have relabelled those 1,224 tennis and soccer
    rows "Tennis"/"Soccer". So this asks the EXACT question that assigned the tier
    — ``(sport_category or category) in _NON_SPORT_CATEGORIES``, the same
    `effective_category` expression `compute_market_tier` uses two functions up —
    and the label can only undo the arm that created it.

    Returns ``None`` — not a label — for every other row, so each call site keeps
    its own existing fallback chain byte-for-byte (the typeahead's NULL-tier
    `sport_id` arm included). One literal, one place; same shape as
    :func:`game_prop_category`.
    """
    if market_tier not in _SPORTS_HIERARCHY_TIERS:
        return None
    raw = sport_category or category or ""
    if raw.lower() not in _NON_SPORT_CATEGORIES:
        return None
    # Never return "" — a blank second line is a worse row than the wrong word,
    # and the caller's `or` chain must be able to fall through.
    return raw.replace("_", " ").title() or None
