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
    this module's rule, as first written          67 / 90   74.4%
    with the alias tables (#5829)                 73 / 90   81.1%

Neither number is a guess about the remainder: every one of them was read
against the boards by hand and is accounted for in `THE MISSES` below.

The same rule was re-measured against a SECOND live population on 2026-09-13 —
148 of our production soccer rows against the 834 distinct fixtures on offsets
1, 2 and 3 — and moves 71 -> 78 there. Two populations six days apart, because
one afternoon is how a vocabulary gets written down wrong.

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

Tier 1 accounts for 64 of the first 67 (17 by equality, 47 by a real subset) and
tier 2 for the remaining 3.

Before any of that, two things happen to the tokens:

* **The alias tables** (:data:`CLUB_NAME_ALIASES`, then
  :data:`CLUB_TOKEN_ALIASES`) put both sides' spelling of a club on one word,
  so the two tiers above can do their work on `FC Cologne` as they always could
  on `FC Köln`. This is the tier the "THE MISSES" section below deferred in
  September until it had been measured twice; #5829 is that measurement.
* **Runs of two or more single-letter tokens are joined**, so our `D.C. United`
  and StatPal's `DC United` are the same two tokens rather than three against
  two. One letter alone is left alone (`U. Espanola` keeps its `u`), and a run
  made ENTIRELY of squad markers is left alone too — see
  :func:`_join_initialism_run`, which exists because `Barcelona B W` was
  reaching `Barcelona`.

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

## THE MISSES, read against the boards rather than assumed

A rate with an unexamined remainder is how "the venue doesn't list it" gets
written about a game the venue lists (standing notices 26 and 27). 23 when this
module was written, 17 after the alias tables:

  * **15 were on the board under a name this grammar could not reach, and 6 of
    them are now joined.** The tables took the abbreviations that appear on
    BOTH the 2026-09-07 corpus and the 2026-09-13 live boards — `Sheffield
    United`/`Sheffield Utd`, `West Bromwich Albion`/`West Brom`, `Atlético
    Madrid`/`Atl. Madrid`, `Atlanta United FC`/`Atlanta Utd`, `Clube Atlético
    Mineiro`/`Atletico-MG`, `América Mineiro`/`America MG` — which is the tier
    this paragraph deferred ("a vocabulary, which has to be measured over more
    than two days before it is written down"). The bar was met and the entries
    carry their evidence; see :data:`CLUB_TOKEN_ALIASES`.

    **The 9 still missing are the ones no measured pair supports**: an
    initialism of a PREFIX (`Go Ahead Eagles`/`G.A. Eagles`), an abbreviation
    whose expansion is ambiguous on the same board (`Atletico Goianiense`/
    `Atletico GO`, where `GO` is also the English word in `Go Ahead Eagles`),
    a genitive plural (`Helsingborgs IF`/`Helsingborg`, `Sandvikens IF`/
    `Sandviken`), alternative club names (`Sporting Lisbon`/`Sporting CP`,
    `Ulsan Hyundai FC`/`Ulsan HD`), a spelling (`Al-Taawoun`/`Al Taawon`), and
    one real RENAME (`Sangju Sangmu FC`/`Gimcheon Sangmu`, where our side is
    the stale one). Each is a different mechanism, so none of them is this
    table's next entry — they are their own tiers, and none has been measured.

    **A THIRD mechanism, found on 2026-09-13 and not fixed here:** the shared
    fold drops a Latin letter that NFKD does not decompose instead of folding
    it, and the drop SPLITS the token. `Bodø/Glimt` tokenizes to `bod glimt`,
    `Zagłębie Lubin` to `zag ebie lubin`, `Großaspach` to `gro aspach`. The
    board writes `Bodo/Glimt`, `Zaglebie` and `Grossaspach`, so all three miss
    — and the invented tokens are worse than a miss, because they can subset
    something else. That is `normalize_team`'s behaviour, shared with NFL, and
    it is filed rather than changed under a soccer ship.
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
        # `Calcio` is the Italian for football and carries exactly as much
        # identity as `FC` does. Ours writes it and StatPal does not: production
        # 2026-09-13 carries `Sassuolo Calcio`, `Parma Calcio` and `Frosinone
        # Calcio` against the boards' `Sassuolo`, `Parma`, `Frosinone`.
        "calcio",
    }
)

#: One WORD we and StatPal write differently for the same club, variant ->
#: canonical. Applied to both sides, so the direction of an entry is arbitrary
#: as long as every variant of a word lands on one canonical spelling.
#:
#: **Why a curated table and not a rule (#5829).** No transliteration takes
#: `Köln` to `Cologne`: it is an exonym, a different word for the same city in
#: another language, and English-language feeds use it while the venue does not.
#: The same is true of `Nuremberg`/`Nürnberg`. There is nothing to derive, so the
#: only honest mechanism is a list of measured pairs.
#:
#: **The bar for an entry, and it is the bar this module set for itself.** The
#: docstring above deferred `utd`->`united` in September with the reason "a
#: token-alias table is a vocabulary, which has to be measured over more than two
#: days before it is written down". Every entry below clears that: it appears in
#: the pinned 2026-09-07 corpus *and* on StatPal's live boards read 2026-09-13,
#: or it is a pair of our own production rows a reader is being shown twice
#: today. The evidence for each is named beside it.
#:
#: **What is deliberately NOT here.** `dep` is the board's abbreviation for both
#: `Deportivo` (`Dep. Riestra`) and `Deportes` (`Deportes Tolima` is ours, and
#: `Deportes Limache` is on the same board) — one variant, two expansions, so it
#: is not a word alias and guessing one would join the wrong club. `ath`, `est`
#: and `a` were each seen on one day only. An entry that cannot be written with
#: its evidence does not get written.
CLUB_TOKEN_ALIASES: dict[str, str] = {
    # Exonyms. Ours from ESPN, the canonical from StatPal's own board.
    #   `FC Cologne` (ours, 2026-09-12 + 2026-09-04) / `FC Koln` (board)
    "cologne": "koln",
    #   `Nuremberg` (ours) / `Nurnberg` (board, 2. Bundesliga)
    "nuremberg": "nurnberg",
    # A club name one writer shortens. `Hamburg SV` and `Hamburg` are both ours;
    # `Hamburger SV` is ours and the board's.
    "hamburg": "hamburger",
    # Abbreviations, each on both reads.
    #   `Sheffield Utd` (2026-09-07), `Manchester Utd` (2026-09-13),
    #   `Atlanta Utd` (2026-09-07)
    "utd": "united",
    #   `West Brom` (2026-09-07) / `West Bromwich Albion` (ours)
    "brom": "bromwich",
    #   `Wolves` (2026-09-13) / `Wolverhampton Wanderers` (ours)
    "wolves": "wolverhampton",
    #   `Atl. Madrid` (2026-09-07 and 2026-09-13), `Atl. San Luis` (2026-09-13)
    "atl": "atletico",
    #   `Atletico-MG` and `America MG` on both reads; `MG` is Minas Gerais and
    #   `Mineiro` is its adjective, which is how ours spells the same two clubs.
    "mg": "mineiro",
}

#: A whole name that is this club under another name. Keyed on the FULL token
#: tuple, so an entry can never fire on a club that merely shares a word.
#:
#: Two entries, and both are the same Bundesliga club, because a one-word alias
#: cannot reach either of them:
#:
#: * `M´gladbach` is ours. It tokenizes to `m gladbach` — the apostrophe splits
#:   it — and `gladbach` alone is a real different club on the board
#:   (`Bergisch Gladbach`, Regionalliga West), so `gladbach`->`monchengladbach`
#:   would be a wrong join waiting for a cup draw.
#: * `B. Monchengladbach` is the BOARD's Bundesliga name, and it is refused
#:   today by :data:`SQUAD_QUALIFIERS`: the abbreviation `B.` tokenizes to `b`,
#:   which is the marker for a B-team. That is the guard working as written —
#:   `Racing Club B` really is a different squad — so the fix is to say what
#:   this particular name is before the guard reads it, not to weaken the guard.
#:   Until this entry, NO Gladbach fixture could be joined at all, in either
#:   direction, whatever else was written here.
CLUB_NAME_ALIASES: dict[tuple[str, ...], tuple[str, ...]] = {
    ("m", "gladbach"): ("borussia", "monchengladbach"),
    ("b", "monchengladbach"): ("borussia", "monchengladbach"),
}

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


def _join_initialism_run(match: re.Match[str]) -> str:
    """Join a run of single characters — unless the run is all squad markers.

    `b w` is not an initialism. It is a B-team marker next to a women's marker,
    and joining it into `bw` produces a token that is NEITHER, which is how
    StatPal's `Barcelona B W` reaches our senior `Barcelona` by plain subset
    today: :data:`SQUAD_QUALIFIERS` matches `b` and it matches `w`, and it
    cannot match the word this function invented out of the two of them.

    Twelve names on the boards read 2026-09-07 and 2026-09-13 are in this shape
    (`Real Madrid B W`, `Sparta Prague B W`, `Waregem 2 W`, `Termalica B-B.`),
    every one of them a reserve or women's side of a club whose senior team is
    on the same boards. The refusal they need already exists; this is only about
    letting it see them.

    The test is ALL and not ANY on purpose: `D.C. United` is the reason this join
    exists, and `c` alone is a squad marker, so an `any` here would refuse the
    one name the rule was written for.
    """
    parts = match.group(0).split()
    if all(SQUAD_QUALIFIERS.match(part) for part in parts):
        return match.group(0)
    return match.group(0).replace(" ", "")


def soccer_tokens(name: Optional[str]) -> list[str]:
    """Normalized tokens, with runs of single characters joined into one.

    `"D.C. United"` -> `["dc", "united"]`; `"U. Espanola"` -> `["u", "espanola"]`;
    `"Barcelona B W"` -> `["barcelona", "b", "w"]`, which two squad markers are
    what it says and `["barcelona", "bw"]` was not.
    """
    normalized = normalize_team(name)
    joined = _INITIALISM_RUN.sub(_join_initialism_run, normalized)
    return joined.split()


def club_alias_tokens(name: Optional[str]) -> list[str]:
    """`soccer_tokens` with the two alias tables applied, whole name first.

    `"FC Cologne"` -> `["fc", "koln"]`; `"B. Monchengladbach"` ->
    `["borussia", "monchengladbach"]`.

    The whole-name table is consulted before the word table, and its key is the
    complete tuple: an entry is a statement about one name, so it must not be
    reachable by a name that happens to end in the same words.
    """
    tokens = soccer_tokens(name)
    renamed = CLUB_NAME_ALIASES.get(tuple(tokens))
    if renamed is not None:
        return list(renamed)
    return [CLUB_TOKEN_ALIASES.get(t, t) for t in tokens]


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
    a = club_alias_tokens(statpal_name)
    b = club_alias_tokens(our_name)
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

    # `issubset` and not `<=`, which means the same thing and reads as a total
    # order: CodeQL's `py/redundant-comparison` flagged the second clause as
    # "always true, because of this condition", which is only sound for numbers.
    # Subset is a PARTIAL order and neither direction implies the other — the
    # mutant that drops the second clause is killed by the corpus, `Wrexham` ⊆
    # `Wrexham AFC` and `FC Porto` ⊇ `Porto` being real rows going opposite ways.
    if core_a.issubset(core_b) or core_b.issubset(core_a):
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
