"""#7867 — a name token that is PART of another known club's name is not ours.

THE DEFECT. `_build_related_futures` classifies an outcome by name when neither
its ticker, its exact alias nor its stored ``team_id`` decides it, and the name
test is whole-token (#6806) over the sub-tokens `_team_name_patterns` emits so
short venue labels can match: ``Duke Blue Devils`` → ``Duke``, ``Devils``,
``Blue``. A token that genuinely IS a whole token of another entity's name
passes that test, and the other entity's row lands on this team's card:

    Duke Blue Devils          claims  Arizona State Sun Devils     (`Devils`)
    Miami Hurricanes          claims  Ball St. vs Miami (OH)       (`Miami`)
    Coastal Carolina          claims  Alabama vs South Carolina    (`Carolina`)
    Columbia Lions            claims  Penn State Nittany Lions     (`Lions`)
    San Francisco Giants      claims  Yomiuri Giants (NPB)         (`Giants`)
    New York Islanders        claims  Bridgeport Islanders (AHL)   (`Islanders`)
    Minnesota Lynx            claims  Minnesota Timberwolves (NBA) (`Minnesota`)

Production specimens, ids and dates: issue #7867 and its three comments.

THE RULE THAT WAS MEASURED AND REJECTED (#7867, PR #7866): *a label is claimed
only when the team's own names cover all of its tokens* — 841 claimed rows, 190
lost, among them ``Miami (FL)`` for the Hurricanes and ``NE Patriots D/ST: 1+``
for New England. It cannot tell ``Miami (FL)`` from ``Miami (OH)`` because it
asks whether a token is PRESENT. The discriminating question is whether the
token is PART OF A DIFFERENT KNOWN CLUB'S NAME, and that is what this module
asks — against the canonical ``teams`` rows the route already reads, never
against a nickname list or a score.

THE RULE. For a label the route is about to admit by name, take every
whole-token occurrence of every one of this team's patterns in the label. The
label names another club when EVERY such occurrence sits strictly inside a
longer whole-token span that is the name, location or listed alias of a team
in this sport family that is not one of ours. One occurrence that is not so
covered — the team's full name, its own alias, a bare venue label, a prop
label with an unknown suffix — admits the row exactly as it does today.

    Miami Hurricanes | Ball St. vs Miami (OH)    `Miami` ⊂ `Miami (OH)` → RedHawks   REFUSED
    Miami Hurricanes | Miami (FL) vs Stanford    `Miami` ⊂ `Miami (FL)` → Hurricanes  admitted (ours)
    Miami Hurricanes | Miami (FL)                same                                   admitted
    New England      | NE Patriots D/ST: 1+      `Patriots` covered by nothing          admitted (unknown)
    Coastal Carolina | Coastal Carolina vs Troy  `Carolina` ⊂ `Coastal Carolina` → ours admitted
    Coastal Carolina | Alabama vs South Carolina `Carolina` ⊂ `South Carolina` → SC     REFUSED
    Duke Blue Devils | Duke Tobin                `Duke` covered by nothing              admitted (unknown)

The last line is the named limitation, kept on purpose: a person is not in
``teams``, so a person's identity cannot be established here, and an
unestablished identity is never refused. Known-contradictory is refused;
unknown is untouched.

WHY STRICTLY LONGER. An occurrence that IS a club's alias on its own — the
bare ``Miami`` on a label reading exactly ``Miami``, ``Carolina`` for the
Panthers — is the short venue label the sub-token patterns exist to reach. If
a sibling league happened to list that bare word as ITS alias and ours did not,
an equal-span rule would refuse the venue's own label for our club. The equal
span therefore never refuses; only a longer name does, because a longer name
is positive evidence that the token was borrowed.

WHY THE FAMILY, NOT THE LEAGUE. The route's candidate pool is every market in
the sport FAMILY (`basketball%`, `baseball%`) — that is how an NPB title, an
AHL title and an NBA title reach an MLB, NHL and WNBA page — so the identity
that refuses them has to be read at the same width. ``teams`` carries Yomiuri
Giants (12494, baseball_npb), Bridgeport Islanders (1347, icehockey_ahl) and
Minnesota Timberwolves (106, basketball_nba); read only at the event's league
they are unknown, and unknown is admitted.

WHY "OURS" IS WIDER THAN TWO IDS. Production ``teams`` carries twin rows for
one club in one league — ``New York I`` (6181), ``New Jersey`` (12716) and
``New York Islanders`` (54) all carry abbreviation ``NYI`` in icehockey_nhl;
``New York R`` (8293) beside ``New York Rangers`` (57). A twin's truncated name
strictly covers our own bare city token (``New York`` ⊂ ``New York R``), so a
twin read as foreign would refuse the Rangers' own Stanley Cup legs on the
Rangers' page. A row is therefore OURS when it is one of the event's resolved
ids, carries the same normalized name as one of the event's teams anywhere in
the family (the same school in men's and women's basketball), or shares an
abbreviation with a resolved team IN THE SAME LEAGUE. Cross-league siblings
sharing an abbreviation (Lynx / Timberwolves, both ``MIN``) stay foreign.

WHAT THIS NEVER DOES. No nickname denylist, no score, no LLM, no query of its
own — the roster rows are the ones the route already holds — and no refusal of
a row whose only evidence is absence. An ambiguous alias (claimed by several
foreign clubs) still refuses, because "which of them" does not matter when
"none of them is ours" is known; an alias that ANY of ours claims never does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from app.utils.team_pattern_match import pattern_token_spans

__all__ = [
    "LabelIdentity",
    "build_label_identity",
    "label_is_another_club",
    "label_names_another_club",
]


_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def _norm(value: Optional[str]) -> str:
    """Lowercase, strip punctuation, collapse whitespace — the same reading of
    "the same string" `team_identity_resolution._norm` takes."""
    return _WS.sub(" ", _PUNCT.sub(" ", (value or "").lower())).strip()


def _escape_like(s: str) -> str:
    """`routes.events._escape_like`, so a raw alias reads back through
    `pattern_token_spans` exactly as the route's own patterns do."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class LabelIdentity:
    """Every alias string in the family → the ids of the clubs that claim it,
    plus the set of ids that count as THIS event's own.

    `claims` keys are the raw alias text lower-cased (not `_norm`ed): labels
    carry the same punctuation the alias does (``Miami (OH)``, ``North Carolina
    St.``), and the whole-token match runs on raw text.
    """

    claims: Mapping[str, frozenset]
    own: frozenset
    # Per-token memo of the foreign aliases that could cover it: the alias
    # scan is over the whole family (thousands of strings on a soccer page)
    # and the same handful of tokens recur on every row of one request.
    _covering: dict = field(default_factory=dict, compare=False, repr=False)

    def is_armed(self) -> bool:
        return bool(self.claims) and bool(self.own)

    def foreign_aliases_containing(self, needle: str) -> list:
        """Every alias strictly longer than ``needle`` that contains it and
        is claimed by no club of ours, ILIKE-escaped for the span test."""
        cached = self._covering.get(needle)
        if cached is None:
            cached = [
                _escape_like(alias)
                for alias, ids in self.claims.items()
                if len(alias) > len(needle) and needle in alias and not (ids & self.own)
            ]
            self._covering[needle] = cached
        return cached


def build_label_identity(
    rows: Iterable[Mapping[str, Any]],
    *,
    own_team_ids: Iterable[int],
    own_team_names: Iterable[Optional[str]],
) -> LabelIdentity:
    """Build from the family's ``teams`` rows.

    Each row: ``id``, ``sport_id``, ``name``, ``location``, ``abbreviation``,
    ``alternate_names``. ``own_team_ids`` are the ids the route resolved for
    this event's two sides (league-scoped, exact name); ``own_team_names`` the
    event's two names. See the module docstring for how "ours" widens.
    """
    rows = list(rows)
    own: set = {tid for tid in own_team_ids if tid is not None}
    if not own:
        # Nothing resolved ⇒ nothing is ours ⇒ nothing can be foreign. The
        # name and abbreviation folds below WIDEN a resolved identity; they
        # never conjure one, or an event whose teams the route could not find
        # would start refusing rows on the strength of a name fold alone.
        return LabelIdentity(claims={}, own=frozenset())
    own_names = {_norm(n) for n in own_team_names if n}
    own_names.discard("")

    # Pass 1 — the same club under the same name anywhere in the family.
    for row in rows:
        if row.get("id") is None:
            continue
        if _norm(row.get("name")) in own_names:
            own.add(row["id"])

    # Pass 2 — abbreviation twins, same league only.
    own_abbrevs: dict = {}
    for row in rows:
        if row.get("id") in own:
            abbr = (row.get("abbreviation") or "").strip().upper()
            if abbr:
                own_abbrevs.setdefault(row.get("sport_id"), set()).add(abbr)
    if own_abbrevs:
        for row in rows:
            abbr = (row.get("abbreviation") or "").strip().upper()
            if abbr and abbr in own_abbrevs.get(row.get("sport_id"), ()):
                own.add(row["id"])

    claims: dict = {}
    for row in rows:
        tid = row.get("id")
        if tid is None:
            continue
        texts = [row.get("name"), row.get("location")]
        alts = row.get("alternate_names") or []
        if isinstance(alts, (list, tuple)):
            texts.extend(a for a in alts if isinstance(a, str))
        for t in texts:
            key = (t or "").strip().lower()
            if key:
                claims.setdefault(key, set()).add(tid)

    return LabelIdentity(
        claims={k: frozenset(v) for k, v in claims.items()},
        own=frozenset(own),
    )


def label_names_another_club(
    label: Optional[str],
    patterns: Iterable[str],
    identity: Optional[LabelIdentity],
) -> bool:
    """True when every pattern occurrence in ``label`` is part of a foreign
    club's name. False on any uncertainty — see the module docstring.

    ``patterns`` arrive ILIKE-escaped, as `_team_name_patterns` emits them.
    """
    if not label or identity is None or not identity.is_armed():
        return False

    occurrences: list = []
    for p in patterns:
        for span in pattern_token_spans(label, p):
            occurrences.append(span)
    if not occurrences:
        return False

    hay = label.lower()
    covered_spans: list = []
    # Candidate covering aliases: strictly longer than the occurrence text and
    # containing it, claimed by no club of ours. Whole-token placement is then
    # checked on the label itself.
    for start, end in occurrences:
        needle = hay[start:end]
        covered = False
        for alias_pattern in identity.foreign_aliases_containing(needle):
            for a_start, a_end in pattern_token_spans(label, alias_pattern):
                if a_start <= start and end <= a_end and (a_end - a_start) > (end - start):
                    covered = True
                    break
            if covered:
                break
        if not covered:
            return False
        covered_spans.append((start, end))

    return bool(covered_spans)


def label_is_another_club(
    label: Optional[str],
    identities: Iterable[Optional[LabelIdentity]],
) -> bool:
    """True when ``label`` IS a known club that is neither side of this game.

    #8620 — the market-name fallback reads this over a market's ANSWERS. It
    admits every outcome of a market whose title carries one of our tokens, which
    is right for a game prop ("Boston at Golden State: Rebounds" → "Over 218.5")
    and wrong for a field of clubs: ``Portugal`` is a whole token of ``Liga
    Portugal Champion``, so all 18 Portuguese clubs landed on the national team's
    Championship Path. An answer that is itself another club says the market is a
    field of clubs, and a field's title is the competition's name, not a claim.

    Exact label only — the whole label (trimmed, lower-cased) is a name,
    location or listed alias of a family club — never a token inside it:
    ``Lamar Jackson: 50+`` must not read as Lamar or Jackson State. The club is
    foreign when NO claimant of that string is ours on EITHER side, so the
    opponent's own label (``Wales`` on a Portugal v Wales market) never counts.
    Disarmed with nothing resolved, as `label_names_another_club` is.
    """
    armed = [i for i in identities if i is not None and i.is_armed()]
    key = (label or "").strip().lower()
    if not key or not armed:
        return False
    # Every side's identity is built from the same family rows, so `claims`
    # is shared; only `own` differs per side.
    claimants = armed[0].claims.get(key)
    if not claimants:
        return False
    own = frozenset().union(*(i.own for i in armed))
    return not (claimants & own)
