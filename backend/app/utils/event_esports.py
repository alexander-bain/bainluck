"""Esports market classification for the hub's matches/props split.

UX-P180's second domain (#2167). The tennis half of this issue shipped the
`_PROP_CLASSIFIERS` route out of the "matches" section; esports was left in the
table that puts markets IN and absent from the table that takes them OUT, so it
kept the exact defect tennis was repaired for.

═══ WHAT A READER SAW ═══

`/hub/esports` printed **MATCHES · 104** and not one of the 104 was a match
(measured on production 2026-09-16 by authority/395, 390px frames in
`~/bainluck-dev/authority/artifacts-395/`). The whole section was partner-team
questions, roster moves, pentakill props, per-game totals, season outrights, and
seventeen consecutive "cover of MLB The Show 27" cards.

═══ THE HOLE, WHICH IS ONE LINE WIDE ═══

`league_futures._INDIVIDUAL_MATCH_SPORTS` = {tennis, mma, boxing, **esports**}
routes every individual sport's `game_prop` INTO "matches"
(`league_futures.py:1499`). `hub._PROP_CLASSIFIERS` = {ufc, boxing, **tennis**}
routes them back out. Esports is in the first table and was absent from the
second, and its `HubConfig` declared no `prop_classifier_domain`, so the split at
`hub.py` never ran for it.

Golf is deliberately unaffected: it is not in `_INDIVIDUAL_MATCH_SPORTS`, so it
never had this defect and must not be swept in.

═══ WHY THE MLB-THE-SHOW ROWS ARE NOT RETAGGED HERE ═══

Seventeen "Will <ballplayer> be on the cover of MLB The Show 27?" cards sit in
this category because `resolve_event_category` decided them on its `tag` arm, and
its corrective arms 3/4 are gated on `NON_SPORT` — so no corrector can see them.
That is a defensible tag for a video-game market, not a bad one, and under a
section that is not called "matches" they read fine. A retag would be the wrong
instrument for a sectioning defect, so this file simply classifies them as the
props they are.
"""

import re

#: Esports prop families, matched as PHRASES anywhere in the name.
#:
#: Every pattern below was written against the 104 rows the production hub
#: actually stranded under "MATCHES" on 2026-09-16, and every one of the 104 is
#: caught. Nothing here is speculative: a family we have not seen is not listed,
#: because a guessed pattern's failure mode is misfiling a REAL match, which is
#: strictly worse than leaving a prop where the next measurement will find it.
#:
#: Validated in both directions — see
#: `tests/test_esports_props_are_not_matches_2167.py`. The negative control is 40
#: genuine match rows read off production (`Counter-Strike: Nemiga vs Team Nemesis
#: (BO5) - CIS LAN Championship Playoffs`, `Dota 2: 1win vs Team Nemesis - Game 2
#: Winner`, `Map 3 Rounds Handicap: MEIA NOITE (-3.5) vs Los Niños (+3.5)`), and
#: none of them matches any pattern here. That control is the point of the file:
#: a classifier that is merely eager empties the matches rail instead of the props
#: out of it.
#:
#: Matched anywhere rather than after a colon for the reason
#: `_TENNIS_PROP_PATTERNS` documents: esports names carry a title PREFIX
#: ("Valorant: A vs B - Map 1 Winner") as often as a prop SUFFIX, so a positional
#: parse takes the wrong half.
_ESPORTS_PROP_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Will BBL Esports be a 2027 VCT EMEA partner team?" — league franchising,
    # 31 of the 104. Not anchored on VCT: the same question shape arrives for
    # every franchised circuit.
    (re.compile(r"\bpartner\s+team\b", re.IGNORECASE), "partner team"),
    # "Will FlyQuest make a roster change by December?" and the transfer form
    # "Will invy leave Paper Rex in 2026?" are one family to a reader.
    (re.compile(r"\bmake\s+a\s+roster\s+change\b", re.IGNORECASE), "roster move"),
    (re.compile(r"^Will\s+.+\s+leave\s+.+\s+in\s+\d{4}\b", re.IGNORECASE), "roster move"),
    # "Will Morgan Penta in LCS Split 3 2026?" — a pentakill prop. The trailing
    # " in" is load-bearing and not decoration: PENTA is also an esports ORG, so a
    # bare `\bPenta\b` would misfile a real fixture the day that org plays one.
    (re.compile(r"\bPenta\s+in\b", re.IGNORECASE), "player prop"),
    (re.compile(r"\breach\s+\w+\s+rank\b", re.IGNORECASE), "player prop"),
    # "Map 2 Total Rounds: Over/Under 20.5", "Game 3: Odd/Even Total Kills?",
    # "Game 4: Both Teams Slay Baron Nashor?", "Games Total: O/U 2.5".
    #
    # What keeps the `vs`-carrying handicap rows ("Map 3 Rounds Handicap: A (-3.5)
    # vs B (+3.5)", "Map Handicap: NEMI (-1.5) vs B (+1.5)") out is the REQUIRED
    # `Total|Odd/Even|Both Teams` token after the slot, NOT the `^`: those rows read
    # "Rounds Handicap" there and miss either way. Measured, not assumed — deleting
    # the anchor leaves all 35 guard tests green, so it currently has no witness and
    # is kept as the conservative reading of a corpus whose every member leads with
    # the slot. If a real fixture ever arrives carrying a map total as a SUFFIX
    # ("Valorant: A vs B - Map 2 Total Rounds O/U 20.5") the anchor is what would
    # strand it in "matches", and dropping it is then the fix.
    (
        re.compile(r"^(?:Map|Game)s?\s*\d*\s*:?\s*(?:Total|Odd/Even|Both\s+Teams)\b", re.IGNORECASE),
        "series prop",
    ),
    (re.compile(r"^Games\s+Total\b", re.IGNORECASE), "series prop"),
    # The MLB-The-Show cover cards described in the module docstring.
    (re.compile(r"\bon\s+the\s+cover\s+of\b", re.IGNORECASE), "cover"),
    # "Will LYON Qualify for Worlds 2026?" / "Will Cloud9 Make the LCS 2026 Summer
    # Grand Final?" — season outcomes, which belong beside the outrights.
    (re.compile(r"\bqualify\s+for\s+worlds\b", re.IGNORECASE), "season outcome"),
    (re.compile(r"\bmake\s+the\s+.+\s+grand\s+final\b", re.IGNORECASE), "season outcome"),
)


def classify_esports_prop(external_id: str | None, name: str | None) -> str | None:
    """Classify an esports market as a prop kind, or None if it is a real match.

    Signature matches `classify_tennis_prop` / `classify_ufc_prop` /
    `classify_boxing_prop` so the hub's `_PROP_CLASSIFIERS` table stays one
    uniform shape. `external_id` is accepted for that contract and deliberately
    unused, for the reason the tennis twin gives: esports prop tickers are not a
    stable family the way `KXUFCMOV` is, and guessing at one would misfile real
    matches — the names carry the signal.
    """
    n = name or ""
    for pattern, prop_type in _ESPORTS_PROP_PATTERNS:
        if pattern.search(n):
            return prop_type
    return None
