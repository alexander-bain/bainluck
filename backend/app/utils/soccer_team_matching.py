"""Does this StatPal soccer team name and ours name the same club? #3366 / D50.

## Why soccer cannot inherit the NFL rule, measured rather than assumed

:mod:`app.utils.nfl_team_matching` is *equality after normalization* and says so
in its own docstring: StatPal and we spell all 32 franchises identically, so
there is nothing to bridge and a looser rule could only buy a wrong game.

**Soccer is the opposite case, and the gap is 50 games wide.** Measured
2026-09-07 over the whole two-day join population — our 90 production soccer
`events` in `[2026-09-07T20:00Z, 2026-09-10T06:00Z)` against the 621 distinct
fixtures StatPal's own `soccer/matches/daily?offset=1` and `offset=2` boards
serve, both pinned as `tests/fixtures/statpal_soccer_join_corpus_20260907.json`:

    equality after normalization (the NFL rule)   17 / 90   18.9%
    this module's rule                            67 / 90   74.4%

Neither number is a guess about the remaining 23: every one of them was read
against the boards by hand and is accounted for in `THE 23 MISSES` below.

The reason is one-sided and consistent: **StatPal writes the short name and we
write the long one.** `Wrexham` / `Wrexham AFC`, `Cardiff` / `Cardiff City`,
`Instituto` / `Instituto de Córdoba`, `Dortmund` / `Borussia Dortmund`,
`Nijmegen` / `NEC Nijmegen`. That is a *token* relationship, not a spelling
one, so the rule is stated over tokens.

## The rule

Both sides normalized (`normalize_team`, reused deliberately — see below), then
split into tokens, then, in order:

1. **Token subset, either direction**, after dropping club-form noise
   (:data:`CLUB_FORM_TOKENS`) — `fc`, `afc`, `sc`, `de` and friends. Equality is
   its degenerate case (each side a subset of the other) and gets no branch of
   its own; the 17/90 the NFL rule scores is how many of the 67 land there.
2. **Initialism.** One side is a single token that is the initials of the
   other's: `PSG` / `Paris Saint Germain`, `QPR` / `Queens Park Rangers`,
   `CRB` / `Clube de Regatas Brasil`. Exactly three games in the corpus, all
   three verified by hand, and it is the only tier that can match two strings
   sharing no token at all — so it is the narrowest one written here.

Tier 1 accounts for 64 of the 67 (17 by equality, 47 by a real subset) and
tier 2 for the remaining 3.

Before any of that, runs of two or more single-letter tokens are joined, so our
`D.C. United` and StatPal's `DC United` are the same two tokens rather than
three against two. One letter alone is left alone (`U. Espanola` keeps its `u`).

## The subset rule needs a guard, and the board proves why

A strict subset is the whole point of tier 1 — and it is also how `Everton`
matches `Everton U21`. This is not hypothetical: the same two boards carry
`Hartlepool v Everton U21`, `FC Halifax v Wolves U21`, `Atlanta United 2 v
Connecticut FC`, `Racing Club 2 v Argentinos Jrs 2`, `New York City II v New
York Red Bulls II` and `Liverpool U19 v Atl. Madrid U19` — the last of these
5 hours from the senior fixture it shadows. Reserve, youth and women's sides are
a large minority of a global soccer board, not an edge case.

So :data:`SQUAD_QUALIFIERS`: if the tokens the two names *disagree* about
include an age band, a reserve marker or a women's marker, the answer is `False`
whatever the subset says. `jr`/`jrs`/`juniors` are deliberately NOT in that set —
`Boca Juniors` and `Argentinos Juniors` are senior clubs whose names contain the
word, and a marker list that eats a club name is worse than no marker list.

**Known residual, stated rather than hidden: a reserve side with its own NAME
is not caught.** `Real Madrid` matches `Real Madrid Castilla`. No suffix rule
can catch a named B-team, and inventing a list of them from memory would be the
kind of unmeasured vocabulary this module exists to avoid. What stands behind
the gap is the caller's contract, not this function: the ±1h window, and the
requirement that a claim be refused unless exactly one fixture matches.

## THE 23 MISSES, read against the boards rather than assumed

A rate with an unexamined remainder is how "the venue doesn't list it" gets
written about a game the venue lists (standing notices 26 and 27). So:

  * **15 are on the board under a name this grammar cannot reach.** They are
    abbreviations (`Sheffield United`/`Sheffield Utd`, `West Bromwich Albion`/
    `West Brom`, `Atlético Madrid`/`Atl. Madrid`, `Atlanta United FC`/
    `Atlanta Utd`, `Estudiantes La Plata`/`Estudiantes L.P.`, `Go Ahead Eagles`/
    `G.A. Eagles`, `Atletico Goianiense`/`Atletico GO`, `Clube Atlético
    Mineiro`/`Atletico-MG`, `América Mineiro`/`America MG`), a plural
    (`Helsingborgs IF`/`Helsingborg`), alternative club names (`Sporting
    Lisbon`/`Sporting CP`, `Ulsan Hyundai FC`/`Ulsan HD`, `Sandvikens IF`/
    `Sandviken`), a spelling (`Al-Taawoun`/`Al Taawon`), and one real RENAME
    (`Sangju Sangmu FC`/`Gimcheon Sangmu`, where our side is the stale one).
    That is the next tier's evidence, and it is deliberately not guessed at
    here: `utd`→`united` and `atl`→`atletico` are a token-alias table, which is
    a vocabulary, which has to be measured over more than two days before it is
    written down.
  * **5 kick off after the last fixture the two boards carry** (board span
    `2026-09-07T23:00Z` → `2026-09-10T00:45Z`; all five are west-coast MLS at
    `02:30Z`). Not a name defect and not a coverage gap — a READ-WINDOW defect
    in whatever calls this. `offset=1` and `offset=2` do not reach the tail of
    their own second day.
  * **1 kicks off before the boards start**: a game already in progress today.
    `matches/daily` cannot see today at all (`offset=0` is byte-identical to
    `matches/live`), which is #3800.
  * **2 are genuinely absent from the board while StatPal carries the league.**
    `Oxford United v Reading` (our `soccer_england_league1`, 09-08 18:45Z) and
    `Everton v Wolverhampton Wanderers` (our `soccer_england_efl_cup`, 09-09
    18:45Z). Second method per notice 26, `GET /api/v2/soccer/leagues`: England
    League One is league `3039`, season 2026/2027, and EFL Cup is `3032`,
    01.08.2026–17.09.2026 — both in season, so "the venue doesn't carry it" is
    NOT the explanation. Which side is wrong is unsettled and filed rather than
    asserted: our Everton row has a twin at 09-16 18:45Z, also EFL Cup, also
    `odds_api`, and only one of the two can be the tie.

## The caller's contract, in three parts

1. **Dedupe the board by `fallback_id_3` before matching.** StatPal repeats 15
   of its 636 raw rows verbatim across the two boards' league lists, same id
   both times. Judged undeduped, three of the 67 above read as AMBIGUOUS — a
   fixture "matching two candidates" that are one fixture printed twice.
2. **Refuse anything but exactly one match.** This module answers about one pair
   of names; it cannot see that two fixtures matched. Zero and two are both
   receipts, never a link.
3. **Keep the ±1h window.** It is doing real work here, not decoration: the
   corpus carries `Liverpool U19 v Atl. Madrid U19` five hours before
   `Liverpool v Atl. Madrid`, and named reserve sides (see the residual above)
   have nothing else standing between them and a wrong claim.

## `soccer_pair_matches` keeps the orientation, like NFL's

Home to home, away to away. Two clubs meet twice a season and the reverse
fixture is a different game.

## Why `normalize_team` is imported rather than copied

The fold soccer needs — NFKC then NFKD, drop combining marks so `Grêmio` reads
as `gremio`, lowercase, strip everything that is not a letter/digit/space,
collapse runs — is character-for-character the fold NFL needed, and a third copy
of it in this repo would be a third place for `Atlético` to stop folding. The
coupling is real, so `test_soccer_team_matching_3366.py` pins the fold's
behaviour on *soccer* inputs directly: if a future NFL change moves it, a soccer
test fails and names soccer, rather than the corpus count drifting silently.
"""

from __future__ import annotations

import re
from typing import Optional

from app.utils.nfl_team_matching import normalize_team

#: Club-form words that carry no identity: two clubs in one league are never
#: told apart by these alone. `united` and `city` are NOT here and never will be
#: — Manchester United and Manchester City are the reason the NFL module refuses
#: a city fallback, and soccer has the same pair in the same city.
CLUB_FORM_TOKENS: frozenset[str] = frozenset(
    {
        "fc",
        "afc",
        "cf",
        "sc",
        "ac",
        "if",
        "ik",
        "sk",
        "kv",
        "cd",
        "ca",
        "club",
        "de",
        "the",
    }
)

#: Tokens that mark a DIFFERENT SQUAD of the same club. Disagreement about any
#: of these refuses the match, in either direction. See the module docstring for
#: the six real examples on the pinned boards.
SQUAD_QUALIFIERS = re.compile(
    r"^(u\d{2}|ii|iii|iv|b|c|2|3|4|res|reserves|reserve|youth|"
    r"w|women|womens|ladies|fem|femenino|feminino|academy|dev)$"
)


#: A run of TWO OR MORE single characters, which is someone else's initialism
#: written with periods. `{1,}` and not `{0,}`: a lone letter is left alone,
#: because it is usually a real word in a name whose long form we have not seen
#: (`U. Espanola`), while `d c` is only ever `dc`.
_INITIALISM_RUN = re.compile(r"\b(?:[a-z0-9] ){1,}[a-z0-9]\b")


def soccer_tokens(name: Optional[str]) -> list[str]:
    """Normalized tokens, with runs of single characters joined into one.

    `"D.C. United"` -> `["dc", "united"]`; `"U. Espanola"` -> `["u", "espanola"]`.
    """
    normalized = normalize_team(name)
    joined = _INITIALISM_RUN.sub(lambda m: m.group(0).replace(" ", ""), normalized)
    return joined.split()


def _initials_match(short: list[str], long: list[str]) -> bool:
    """Is `short` a one-token initialism of `long`?

    Both spellings of the initials are accepted — with the club-form tokens and
    without — because `CRB` is `Clube de Regatas Brasil` only if `de` counts and
    `Clube Regatas Brasil` only if it does not, and the provider does not say
    which it meant.

    The two-character floor is not decoration. Stripping club-form tokens can
    leave a ONE-letter initialism — `FC Porto` reduces to `p` — and `P` is not
    evidence of Porto.
    """
    if len(short) != 1 or len(long) < 2 or len(short[0]) < 2:
        return False
    with_form = "".join(t[0] for t in long)
    without_form = "".join(t[0] for t in long if t not in CLUB_FORM_TOKENS)
    return short[0] in (with_form, without_form)


def soccer_team_matches(statpal_name: Optional[str], our_name: Optional[str]) -> bool:
    """Same club, same squad? See the module docstring for the two tiers.

    Empty on either side is `False`, never a match — absence has never been
    evidence, and two blank names pairing would link two broken rows and call it
    a game. That falls out of the empty-core refusal below rather than getting
    its own guard: a name with no tokens has no core either.
    """
    a = soccer_tokens(statpal_name)
    b = soccer_tokens(our_name)
    set_a, set_b = set(a), set(b)
    core_a = set_a - CLUB_FORM_TOKENS
    core_b = set_b - CLUB_FORM_TOKENS
    if not core_a or not core_b:
        # A name that is nothing but club-form words identifies no club, and
        # this is checked FIRST so that `FC` against `FC` is refused rather than
        # sailing through on equality.
        return False

    # A squad marker on one side and not the other is a different team, and it
    # is checked before the subset tier BECAUSE the subset tier is what would
    # otherwise accept it.
    if any(SQUAD_QUALIFIERS.match(t) for t in set_a ^ set_b):
        return False

    if core_a <= core_b or core_b <= core_a:
        return True

    return _initials_match(a, b) or _initials_match(b, a)


def soccer_pair_matches(
    statpal_pair: tuple[Optional[str], Optional[str]],
    our_pair: tuple[Optional[str], Optional[str]],
) -> bool:
    """Both sides of the fixture, in the SAME orientation.

    Home matches home and away matches away. Orientation is not a detail to be
    relaxed about in soccer of all sports: every league in the corpus plays its
    fixtures home and away, so accepting the swap would pair a game with its own
    reverse fixture later in the season.
    """
    return soccer_team_matches(statpal_pair[0], our_pair[0]) and soccer_team_matches(
        statpal_pair[1], our_pair[1]
    )
