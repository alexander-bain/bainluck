"""What SECTION a container member lands in. Computed once, at assembly.

#2927 Phase 3, spec §4. The class is computed from the member's own evidence
and **stored on the `contains` edge**, so the hub reads sections instead of
inferring them and ux never classifies (event-graph doctrine §C.4).

WHY STORED AND NOT DERIVED AT READ TIME. Three consumers would each have to
re-derive it — the hub, the API, and whatever renders a card's "part of…"
line — and three copies of a classifier is how the six named classes become
four in one place and eight in another. The edge is written once by a job that
can see the whole candidate; a reader sees one row.

THE RULE THAT OUTRANKS EVERY OTHER RULE HERE: **`unclassified` is a real answer
and is never a failure.** A member we cannot classify still gets an edge, still
gets a section (last, or a count), and stays visible. Returning `unclassified`
is this module working, not this module giving up — the alternative is guessing
a section, which puts a doubles fixture under Men's Singles and looks exactly
like a right answer.

THIS MODULE IS PURE. No database, no network, no clock. It takes a small
`MemberEvidence` record and returns a string. That is deliberate: classification
is the part of assembly most likely to be wrong, and it must be gradeable by a
table of examples rather than by standing up a tournament.

It imports only `container_graph` (which itself imports nothing from `app`) and
`market_shape`'s constant names, so it cannot participate in an import cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.utils.container_graph import (
    CLASS_UNCLASSIFIED,
    EDGE_CLASSES,
)

# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberEvidence:
    """Everything the classifier is allowed to look at.

    A frozen dataclass rather than a dict so a caller cannot pass a key this
    module silently ignores. Every field is optional because the whole point of
    the container is to take members from sources that know different things:
    an ESPN doubles competition has no market shape, a Kalshi prop has no draw.

    ``register_kind`` is the register's own word for what a row is
    (``matchup`` | ``reach`` | ``prop`` | ``player``), passed through rather
    than re-inferred, because the register already knows and re-deriving it
    from the title is how the register's four kinds become three.
    """

    #: ``container``/``event``/``market`` — what sort of node is being classed.
    node_type: str

    #: The member's display name or title, as the source gives it.
    name: Optional[str] = None

    #: ``app.utils.market_shape`` shape, when the member is a market.
    market_shape: Optional[str] = None

    #: The relation between the market's outcomes, when known.
    market_relation: Optional[str] = None

    #: Which register list this came from, when the source is the register.
    register_kind: Optional[str] = None

    #: The draw slug the member belongs to, e.g. ``mens-doubles``.
    draw: Optional[str] = None

    #: Provider ticker / slug / external id — read for FAMILY, never parsed for
    #: identity. See ``_looks_like_doubles``.
    external_id: Optional[str] = None

    #: How many participants a side holds, when the member is an event and the
    #: participants are known. ``2`` on either side means doubles, and this is
    #: the ONLY authoritative doubles signal — see below.
    max_side_size: Optional[int] = None


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

#: Draw slugs that ARE doubles. Matched whole, against the register's own slug
#: vocabulary — not by substring, because "mens-singles" and "mens-doubles"
#: differ by one token and a sloppy `in` test on "doubles" would be right here
#: only by luck.
_DOUBLES_DRAWS = frozenset(
    {"mens-doubles", "womens-doubles", "mixed-doubles", "wheelchair-doubles"}
)

#: A doubles NAME, as a fallback only. Two slash-joined pairs — "Bopanna/Ebden
#: vs Arevalo/Pavic" — is the shape ARTIFACT-M-20260903-I measured 79 of.
_SLASH_PAIR_RE = re.compile(r"[^/\s][^/]*/[^/]+\s+(?:vs\.?|v\.?|-)\s+[^/]+/[^/]+", re.I)

#: "reaches the R16", "to make the quarterfinals", "advances to…". Ladders.
_ADVANCEMENT_RE = re.compile(
    r"\b(?:reach(?:es|ing)?|advanc(?:e|es|ing)|make(?:s)?\s+(?:the\s+)?(?:cut|"
    r"final|semi|quarter)|to\s+(?:the\s+)?(?:r\d+|round\s+of\s+\d+|last\s+\d+|"
    r"quarterfinals?|semifinals?|finals?))\b",
    re.I,
)

#: "winner of the US Open", "to win the title", "champion", and — the shape
#: production actually uses — a BARE "Winner": `2026 Men's US Open Winner
#: (Tennis)`.
#:
#: The bare form was missing in the first cut and it cost the biggest market on
#: the page: measured against 60 real US Open market names on 2026-09-05, that
#: string was the one miss in ten, landing the outright in `unclassified`. It is
#: only safe because `prop` runs BEFORE `title` — "Set 1 Winner: Sinner vs
#: Shelton" is a prop and matches `_PROP_RE` first — so a bare `\bwinner\b`
#: here cannot swallow a set-winner or a match-winner leg. Moving the prop
#: branch below the title branch would break that silently, which is why the
#: ordering has its own tests.
_TITLE_RE = re.compile(
    r"\b(?:to\s+win(?:ner)?\b|\bwinner\b|\bchampion(?:ship)?\b|\btitle\b|"
    r"\boutright\b)",
    re.I,
)

#: "X vs Y" — one fixture.
_FIXTURE_RE = re.compile(r"\s+(?:vs\.?|v\.?)\s+", re.I)

#: "Will Sinner actually play?", "withdraws", "retires". Questions ABOUT the
#: tournament rather than results IN it.
_SIDE_QUESTION_RE = re.compile(
    r"\b(?:actually\s+play|withdraw(?:s|al)?|retire(?:s|ment)?|"
    r"be\s+(?:fit|ready)|compete\b|participat)",
    re.I,
)

#: Player/match props: totals, spreads, exact scores, set winners.
_PROP_RE = re.compile(
    r"\b(?:total\s+games|game\s+spread|exact\s+(?:match\s+)?score|set\s+\d+"
    r"\s+winner|aces|double\s+faults|tiebreak|straight\s+sets|"
    r"number\s+of\s+sets)\b",
    re.I,
)

# Register kinds, passed through rather than re-inferred.
_REGISTER_KIND_TO_CLASS = {
    "matchup": "match_winner",
    "reach": "advancement",
    "prop": "side_question",
}


def _looks_like_doubles(evidence: MemberEvidence) -> bool:
    """Is this member a doubles member?

    THE ORDER OF THESE THREE TESTS IS THE WHOLE POINT, and it is the ordering
    constraint spec §6 names: membership keys on ids and structure, never on
    names. A doubles fixture matched by name onto a singles row is a wrong
    answer that looks like a right one, and artifact I measured token-fallback
    producing 30+ of exactly those.

    1. **Participant count** — a side holding two entities. Structural, from
       `event_participants`, and the only signal that cannot be wrong. This is
       why doubles waits on the participants table rather than on an ingest
       patch: before that table existed, this test was unstatable.
    2. **Draw slug** — the authority's own word, matched WHOLE against a closed
       set. "mens-doubles" and "mens-singles" differ by one token.
    3. **Two slash-joined pairs in the name** — last, and only when the two
       above said nothing. A name is evidence, not proof.
    """
    if evidence.max_side_size is not None and evidence.max_side_size >= 2:
        return True
    if evidence.draw and evidence.draw.strip().lower() in _DOUBLES_DRAWS:
        return True
    if evidence.name and _SLASH_PAIR_RE.search(evidence.name):
        return True
    return False


def classify_member(evidence: MemberEvidence) -> str:
    """Return the class for a `contains` edge. Never raises, never returns None.

    A classifier that can throw is a classifier that drops a member, and a
    dropped member is the failure this program exists to end. Anything
    unrecognised returns ``unclassified``, which is a real class with a real
    section.

    THE ORDER OF THE BRANCHES IS THE POLICY. Read top to bottom:

    * **Doubles first.** It is a property of *what the member is*, not of how
      it is worded, and it outranks the fixture test — "Bopanna/Ebden vs
      Arevalo/Pavic" matches `X vs Y` too, and would otherwise be filed as an
      ordinary `match_winner` in a singles section.
    * **The register's own kind next**, where the source is the register.
      Passing it through beats re-deriving it from a title the register already
      parsed.
    * **Side questions before props**, because "Will Sinner actually play?" is
      a question about the tournament, not a stat line, and several of its
      phrasings would also match a prop pattern.
    * **Title before advancement**, because "to win the US Open" and "to reach
      the final" are both ladder-shaped and only the first is an outright.
    * **Fixtures last** among the named classes: `X vs Y` is the broadest
      pattern here and would swallow the narrower ones if it ran earlier.
    """
    # 1. Doubles — structural, and it outranks every naming test.
    if _looks_like_doubles(evidence):
        return "doubles"

    # 2. The register already knows what its own rows are.
    if evidence.register_kind:
        mapped = _REGISTER_KIND_TO_CLASS.get(evidence.register_kind.strip().lower())
        if mapped:
            return mapped

    name = (evidence.name or "").strip()

    # 3. Questions about the tournament, before stat lines.
    if name and _SIDE_QUESTION_RE.search(name):
        return "side_question"

    # 4. Player/match props.
    if name and _PROP_RE.search(name):
        return "prop"

    # 5. Outrights before ladders — both are ladder-shaped, one is a title.
    if name and _TITLE_RE.search(name):
        return "title"

    # 6. "Reaches R16" ladders.
    if name and _ADVANCEMENT_RE.search(name):
        return "advancement"

    # 7. One fixture's winner — the broadest name pattern, so it runs last.
    if name and _FIXTURE_RE.search(name):
        return "match_winner"

    # 8. An event with two known one-entity sides is a fixture even when its
    #    name does not say so — a card whose title is just "Sinner — Alcaraz".
    if evidence.node_type == "event" and evidence.max_side_size == 1:
        return "match_winner"

    # 9. We could not tell. This is a real answer, and the member stays visible.
    return CLASS_UNCLASSIFIED


def is_valid_class(value: str) -> bool:
    """Convenience for callers that hold a class from elsewhere."""
    return value in EDGE_CLASSES
