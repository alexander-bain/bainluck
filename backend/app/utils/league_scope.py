"""Keep a sibling league's season markets off its sibling's event pages (#5798).

WHAT A READER SAW.

`bainluck.com/events/15315931` is a college game, Kentucky Wildcats @ **South
Alabama Jaguars**. Measured on production 2026-09-21 22:54Z, ten of the forty-nine
season-long markets served for South Alabama were the **Jacksonville Jaguars**:

    Pro Football: AFC Team to advance to Divisional Round   Jacksonville Jaguars  0.26
    Will the Jacksonville Jaguars make the 2027 NFL Playoffs?              Yes    0.60
    Pro Football: 2027 AFC Champion                         Jacksonville Jaguars  0.075
    NFL Super Bowl Winner                                   Jacksonville Jaguars  0.033
    ... 6 more

It runs the other way too: the LA Rams page carried `NCAAF Championship Winner —
Colorado State Rams`. `_team_name_patterns` is doing its job in both cases; the
mascot really is shared. The defect is that an NFL market was in a college game's
candidate pool at all.

WHY THE OBVIOUS FIXES DO NOT WORK — measured before this was written, so nobody
re-derives them (the full numbers are on #5798).

`_get_related_futures` ORs five sport arms. Two of them (`ext_id_patterns`,
`compatible_sport_ids`) are already correctly narrowed to the exact league by
`is_mens_specific`, and they therefore constrain **nothing**, because two wider
arms re-admit the same rows:

  * **Stoplisting the tokens** (`Jaguars`, `Carolina`) is the wrong instrument.
    #7858 could stoplist `united`/`city`/`town` because those name a club TYPE
    and no wanted outcome is ever labelled with one alone. `Jaguars` and
    `Carolina` fail that test in the other direction — both are somebody's real,
    wanted label (Jacksonville Jaguars; Kalshi writes the Carolina Panthers as
    "Carolina"). Stoplisting either buys the college page at the NFL page's cost.

  * **Dropping the `llm_sport_category` arm** is refused by the population.
    `americanfootball_nfl` and `americanfootball_ncaaf` both map to `football`
    (`sport_keys.py`), so the arm cannot discriminate — but **242 of the 392**
    season markets are reachable ONLY through it (all with NULL `sport_id` and an
    `external_id` matching neither Kalshi root nor either Odds-API prefix).
    Dropping it blanks 62% of the pool on **both** leagues' pages.

  * **Narrowing `_SPORT_TO_KALSHI_ROOTS["americanfootball"]`** to the event's own
    league is ~88% inert: of 82 season `KXNFL%` markets, **72** also carry
    `llm_sport_category='football'` and re-enter through the wide arm regardless.
    It is the small, obvious, safe-looking diff and it would have measured as no
    change at all.

So the only load-bearing edit is to constrain the wide arm, and the only signal
that survives on all 392 rows is the market's own NAME plus its `external_id`.

WHY THIS IS A REFUSAL AND NOT AN ADMISSION, which is the whole safety argument.

A positive rule ("a market reaches the college page only if it looks collegiate")
would blank every market it fails to recognise. This is the negative form: a
market is refused from a page only when it carries the SIBLING league's mark and
**not** its own. An unrecognised market is untouched — it keeps exactly the reach
it has today. The rule therefore cannot subtract a row that is correct today
unless that row's own name says it belongs to the other league.

The second clause is load-bearing and is not decoration. Polymarket lists

    Will a team from Texas win the 2027 Pro Football Championship
                            or the 2027 College Football National Championship?

which carries both marks and is genuinely relevant to both pages. Under a
one-clause rule ("refuse anything marked pro") it would vanish from both. It is
the single row in the census that exercises the clause, and
`test_league_scope_5798.py` pins it by name.

MEASURED OVER THE WHOLE POPULATION, 2026-09-21 (392 season markets, tiers 1-4,
`status open OR NULL`, `llm_sport_category='football'` — a complete population,
not a sample: the query limit is 1000):

    pro-marked only      166   refused from ncaaf pages, kept on nfl
    college-marked only  219   refused from nfl pages,   kept on ncaaf
    both marks             1   kept on both (the Texas row above)
    neither                6   kept on both — UNCHANGED reach

Every one of the 385 single-marked rows was read by hand and is genuinely the
league its mark names.

⚠️ THE UNMARKED ROWS ARE A DIFFERENT BUG AND ARE DELIBERATELY NOT TOUCHED HERE.
They carry no league mark, so this module cannot see them; they are an upstream
CLASSIFICATION defect and teaching this module to guess at them would hide it.
Filed as #5798's third finding, which became #7900.

🔴 THE LIST THIS PARAGRAPH USED TO CARRY WAS MOSTLY WRONG, and it is corrected
here rather than deleted because it was the next reader's map for three days.
It named six rows and asserted they "reach both football pages today and still
will". #7900 put all of them to Kalshi's own `/series/{ticker}` (notice 26) and
to the shipped `_categorize_kalshi_market`, and calibration/2723 measured reach
across all 74 upcoming NFL+NCAAF pages. Both instruments agree the real count is
TWO, and the sentence was false at serve time even when it was written:

  * `2026 CFL Grey Cup Champion` — the VENUE tags it `Football`, and Canadian
    football is football. Never a sport defect. If it should not sit beside
    NCAAF that is a league question, and it is already answered elsewhere:
    `_CFL_MARKET_RE` in `is_wrong_sport_leak` (#7851, `27f1f1e48`) refuses it at
    serve time. Measured reach: zero.
  * `Notre Dame Football to Join a Conference` — venue tags it `Football` too,
    so the "admitted control" is confirmed by the venue rather than by our
    judgement. It keeps its reach.
  * `Titled Tuesday` ×2 (chess) — DID NOT REPRODUCE. Those rows are stored
    `llm_sport_category='chess'`, not `football`. One has zero outcome rows and
    the other's chess-player outcomes match no team pattern on any page. The
    claim appears to have been read off a name, not off the column.
  * `Big Ten Regular Season Champion` (`KXNCAAMBBIGTENREG-27`) — REAL, and
    REPAIRED 2026-09-21. The venue tags it `Basketball`; the badge was a stale
    write frozen by #1888's `coalesce(nullif(existing, 'other'), new)`, which
    never overwrites a real tag, so no classifier change could ever have moved
    it. `repair_kalshi_series_tag_category` moved it and its three tier-5
    siblings to `basketball` (changed=4, drifted=0).
  * `2027 Steel Bridge National Champion` (`KXSTEELBRIDGE-27`, a student
    engineering contest) — REAL and STILL LIVE. This is the only row for which
    the original sentence is still true. Kalshi tags the series literally
    `Other`, so the shipped cascade returns `other`, and every repair rail in
    that family declines to write `other` (`no_usable_tag`) because their gate
    is "the venue names a DIFFERENT sport". Here the venue names NO sport. That
    gap is #7900's residual and owes a census before it is closed.

The lesson worth keeping: a row's stored badge is not the reason it reaches a
page, and a DB-side claim is not a serve-time claim. Three of the six were
already refused, already right, or not in this column at all.

THE SECOND HALF OF THE SHIP, which is the larger reader win and is easy to miss.

The season query is `.limit(400)` with a **per-tier cap of 100**, ordered
`market_tier, id`. Tier 1 holds 107 rows and tier 4 holds 131, so **38 markets are
silently cut today** — and because the order is by id, the cut is the NEWEST tail.
Thirty-four of those 38 are college:

    Will Alabama / Oregon / Florida / Iowa / Utah / Virginia / Pittsburgh /
    Illinois / BYU / TCU / Baylor / Vanderbilt / Kentucky / Arkansas ...
    ... Make the 2026-27 CFB Playoffs?

An Alabama fan's event page cannot show "Will Alabama Make the CFB Playoffs?"
today because seventy NFL markets sit ahead of it inside tier 4's cap. Because
this filter runs in SQL — **before** the cap, not as a post-filter after it —
no tier exceeds 100 on either page afterwards and those rows become reachable.
Verified on the specimen: `Will Kentucky Make the 2026-27 CFB Playoffs?` (id
61373627) is absent from Kentucky's side of 15315931 before this lands.

So the after-check is two-sided and falsifiable in both directions: the ten
Jacksonville rows disappear from South Alabama, AND Kentucky's CFB-playoff row
appears. A change that only subtracts has not delivered this.

SCOPE, NAMED SO IT IS A DECISION.

`SIBLING_LEAGUES` carries the americanfootball pair ONLY. The identical collision
exists for `basketball_nba` / `basketball_ncaab` (both map to `basketball`, both
are already in the route's `is_mens_specific` list), and adding it is a data edit
to the two tables below — but it needs **its own recall census** over its own
population first, exactly as this one did, and it does not get one for free
because this one passed. Nothing here is basketball-aware.

Only the SEASON pass is filtered. Tier-5 game props are selected by
`event_id == event_id` and are already correctly scoped; the series pass requires
both team names in the market name and is left alone.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from sqlalchemy import Column, func, not_, or_
from sqlalchemy.sql.elements import ColumnElement


class LeagueMark(NamedTuple):
    """How to recognise that a market belongs to one specific league.

    `name_pattern` is written in **Postgres** regex syntax, because Postgres is
    where it runs; `\\y` is Postgres's word boundary and Python's `re` spells the
    same thing `\\b`. `python_pattern` does that one substitution so the pure
    classifier below and the SQL agree, and `test_league_scope_5798.py` asserts they
    agree on every row of the recorded population rather than trusting it.
    """

    name_pattern: str
    external_id_prefixes: tuple[str, ...]

    @property
    def python_pattern(self) -> str:
        return self.name_pattern.replace(r"\y", r"\b")


#: The conference-championship phrases are deliberately anchored on the words
#: "Championship Game" rather than on the bare conference name: `MAC`, `ACC` and
#: `SEC` alone are three-letter tokens that would fire on unrelated text, and
#: `Big Ten Regular Season Champion` is a basketball market that must NOT be
#: claimed as college football (see the six-row warning in the module docstring).
_COLLEGE_CONFERENCES = (
    "acc",
    "sec",
    "big 12",
    "big ten",
    "mac",
    "sun belt",
    "conference usa",
    "mountain west",
    "pac-12",
    "american conference",
)

_COLLEGE_NAME_ALTERNATIVES = (
    r"\yncaa\y",
    r"\yncaaf\y",
    r"\ycollege football\y",
    r"\ycfb\y",
    r"\yheisman\y",
) + tuple(rf"\y{c} championship game\y" for c in _COLLEGE_CONFERENCES)

#: `super bowl` earns its place because Kalshi euphemises the game as "Pro
#: Football Championship" but the Odds API does not; both spellings occur in the
#: measured population.
_PRO_NAME_ALTERNATIVES = (
    r"\ypro football\y",
    r"\ynfl\y",
    r"\yafc\y",
    r"\ynfc\y",
    r"\ysuper bowl\y",
)

LEAGUE_MARKS: dict[str, LeagueMark] = {
    "americanfootball_nfl": LeagueMark(
        name_pattern="(" + "|".join(_PRO_NAME_ALTERNATIVES) + ")",
        external_id_prefixes=("KXNFL", "americanfootball_nfl"),
    ),
    "americanfootball_ncaaf": LeagueMark(
        name_pattern="(" + "|".join(_COLLEGE_NAME_ALTERNATIVES) + ")",
        external_id_prefixes=("KXNCAAF", "americanfootball_ncaaf"),
    ),
}

#: Leagues that share one `llm_sport_category` and so leak into each other's
#: candidate pool. Symmetric by construction — see the SCOPE note in the docstring
#: before adding the basketball pair.
SIBLING_LEAGUES: dict[str, str] = {
    "americanfootball_nfl": "americanfootball_ncaaf",
    "americanfootball_ncaaf": "americanfootball_nfl",
}


def is_marked(sport_key: str, name: Optional[str], external_id: Optional[str]) -> bool:
    """Does this market carry `sport_key`'s own league mark?

    Pure, so the census that justified this module can be replayed in a test
    against the same inputs production sees.
    """
    mark = LEAGUE_MARKS.get(sport_key)
    if mark is None:
        return False
    if re.search(mark.python_pattern, name or "", re.IGNORECASE):
        return True
    ext = (external_id or "").lower()
    return any(ext.startswith(p.lower()) for p in mark.external_id_prefixes)


def is_refused(sport_key: str, name: Optional[str], external_id: Optional[str]) -> bool:
    """Should this market be kept OFF `sport_key`'s event pages?

    The two clauses of the rule, in the order the docstring argues them: the
    market carries the sibling's mark, AND it does not carry this league's own.
    """
    sibling = SIBLING_LEAGUES.get(sport_key)
    if sibling is None:
        return False
    return is_marked(sibling, name, external_id) and not is_marked(
        sport_key, name, external_id
    )


def exclusion_condition(
    sport_key: Optional[str],
    name_col: Column,
    external_id_col: Column,
) -> Optional[ColumnElement[bool]]:
    """The SQL half of `is_refused`, or None when this sport has no sibling.

    Returning None rather than a tautology is deliberate: every sport outside
    `SIBLING_LEAGUES` must get a byte-identical query to the one it gets today,
    so this change cannot cost another sport a row or a millisecond.
    """
    sibling = SIBLING_LEAGUES.get(sport_key or "")
    if sibling is None:
        return None

    sibling_mark = LEAGUE_MARKS[sibling]
    own_mark = LEAGUE_MARKS[sport_key or ""]

    # ⚠️ Both columns are COALESCEd, and that is load-bearing rather than tidy.
    # `NULL ~* 'x'` is NULL, `false OR NULL` is NULL, and `NOT NULL` is NULL — so
    # without this a market with a NULL name or external_id would make the whole
    # predicate NULL and `WHERE` would drop it. A refusal rule that fails CLOSED
    # on missing data is the opposite of what this module argues for. Measured
    # 2026-09-21: zero of the 15,373 tier-1-4 open markets have either column
    # NULL, so this buys nothing today and costs nothing — it is here so the rule
    # stays a refusal if that ever stops being true.
    def _marked(mark: LeagueMark) -> ColumnElement[bool]:
        name = func.coalesce(name_col, "")
        ext = func.coalesce(external_id_col, "")
        clauses: list[ColumnElement[bool]] = [name.op("~*")(mark.name_pattern)]
        clauses.extend(ext.ilike(f"{prefix}%") for prefix in mark.external_id_prefixes)
        return or_(*clauses)

    # De Morgan of `NOT (sibling_marked AND NOT own_marked)`, written in the
    # positive form Postgres plans more readably.
    return or_(not_(_marked(sibling_mark)), _marked(own_mark))
