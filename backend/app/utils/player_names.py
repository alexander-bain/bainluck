"""Is this the same player? — the one comparator, shared by everything that asks.

Lifted verbatim out of ``tournament_slate`` (lane1/057 STEP 0), which is where
these grew and where they were still private.  Nothing about them is about
building a slate: they answer "are these two display names the same person" and
"does our pairing name the same two people the authority does", and the tennis
ESPN **anchor** needs exactly those two answers before it may stamp an
``espn_id`` on an event.

Two callers, one rule.  The alternative — a second name comparator inside the
anchor — is how the slate would come to withhold a fixture the anchor had just
linked, disagreeing about a person while both cited "the authority".

``tournament_slate`` keeps its private aliases and its behaviour is unchanged;
the sweep that justified ``SUBSTANTIAL_TOKEN_CHARS`` (378 registered players,
one false pair) is recorded on that constant below and still holds.
"""

from __future__ import annotations

import unicodedata
from typing import Any


def name_tokens(name: Any) -> frozenset[str]:
    """A display name as its set of alphanumeric tokens, accent-folded."""
    if not isinstance(name, str):
        return frozenset()
    folded = unicodedata.normalize("NFD", name).lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in folded)
    return frozenset(token for token in cleaned.split() if token)


#: Shortest token that may serve as the shared anchor between two names. Two
#: characters is enough to exclude the initials that make the prefix rule a
#: wildcard, and short enough to keep every real surname in the draw.
SUBSTANTIAL_TOKEN_CHARS = 3


def token_covered(token: str, others: frozenset[str] | set[str]) -> bool:
    """Is ``token`` the same name-part as something in ``others``?

    Prefix either way, so an initial matches the name it abbreviates:
    ``j`` covers ``jj``, and ``J.J. Wolf`` is ``JJ Wolf``.
    """
    return any(
        token == other or token.startswith(other) or other.startswith(token)
        for other in others
    )


def names_agree(a: Any, b: Any) -> bool:
    """Are these two display names the same person?

    Token SETS, where one side's tokens must all be covered by the other's.
    Deliberately looser than ``espn_tennis.normalize_name``, which concatenates
    and would therefore call ``Bu Yunchaokete`` and ``Yunchaokete Bu`` two
    different people — ESPN and the register genuinely disagree on the leading
    token for several names, and **a false disagreement here DELETES A REAL
    MATCH from the card**, which is a worse defect than the one this exists to
    catch.  One-way coverage handles the other two benign cases: a middle name
    one side drops (``Juan Manuel Cerundolo`` / ``Juan Cerundolo``) and an
    initialism (``J.J. Wolf`` / ``JJ Wolf``).

    It stays strict where it has to be.  Two players who share a surname do not
    agree — ``Francisco Cerundolo`` and ``Juan Manuel Cerundolo`` are both in
    this draw and neither given name covers the other.

    An empty name agrees with anything: it is an absent read, not a claim.
    """
    tokens_a, tokens_b = name_tokens(a), name_tokens(b)
    if not tokens_a or not tokens_b:
        return True

    covered = all(token_covered(t, tokens_b) for t in tokens_a) or all(
        token_covered(t, tokens_a) for t in tokens_b
    )
    if not covered:
        return False

    # AND ONE SUBSTANTIAL TOKEN IN COMMON — the surname anchor.
    #
    # Coverage alone is not enough, because a ONE-LETTER TOKEN IS A WILDCARD
    # under the prefix rule: it covers every token beginning with that letter.
    # Swept over all 378 registered players, that made exactly one pair of
    # genuinely different people agree — `Christopher O'Connell` and
    # `Oleksandra Oliynykova`, where the `o` of `O'Connell` covers both
    # `Oleksandra` and `Oliynykova`.  (The sweep's only other two hits are one
    # person listed twice under both word orders, `Shang Juncheng` and `Wang
    # Xiyu` — the case the tolerance exists for.)
    #
    # A false AGREEMENT only fails us silent, so it was the safe direction to be
    # wrong in, but it is still a hole.  Requiring one shared token of real
    # length closes it and costs none of the benign cases: every one of them
    # shares a full surname.
    return any(
        len(token) >= SUBSTANTIAL_TOKEN_CHARS
        and any(
            len(other) >= SUBSTANTIAL_TOKEN_CHARS and token_covered(token, {other})
            for other in tokens_b
        )
        for token in tokens_a
    )


def shares_substantial_token(a: Any, b: Any) -> bool:
    """Do these two names share one whole name-part of real length?

    EXACT token equality, not the prefix rule :func:`token_covered` uses — this
    is the weaker half of a two-name pairing test (see
    ``espn_tennis_anchor.pairing_anchors``) and the prefix tolerance that is
    safe when BOTH names must agree becomes a wildcard when only one does.

    ``Caty McNally`` and ``Catherine McNally`` share ``mcnally``; ``Marin
    Cilic`` and ``Andrey Rublev`` share nothing.
    """
    tokens_a, tokens_b = name_tokens(a), name_tokens(b)
    return any(
        len(token) >= SUBSTANTIAL_TOKEN_CHARS and token in tokens_b
        for token in tokens_a
    )


def pairing_agrees(ours: Any, theirs: Any) -> bool:
    """Does our pairing name the same two people the authority does?

    ``theirs`` is ESPN's competitor list for the competition this fixture is
    anchored to.  Anything that is not a pair of names on EITHER side returns
    ``True`` — silence and half-reads are facts about the read, never about the
    match, which is the same posture ``order_of_play_complete`` is held to
    (CERT-532/548, gotcha #53).  Only a full, unambiguous contradiction counts.

    Matched without regard to side order, because ESPN's competitor order is
    ingest order and the register's is the matchup key's.

    **Not a matcher.**  Its permissive reading of silence is right for "does the
    authority contradict this fixture" and wrong for "which competition is
    this" — a matcher built on it would anchor an event to the first
    competition with a missing name.  The anchor uses
    :func:`espn_tennis_anchor.pairing_matches`, which demands two real names on
    both sides.
    """
    if not isinstance(ours, list) or not isinstance(theirs, list):
        return True
    if len(ours) != 2 or len(theirs) != 2:
        return True
    straight = names_agree(ours[0], theirs[0]) and names_agree(ours[1], theirs[1])
    crossed = names_agree(ours[0], theirs[1]) and names_agree(ours[1], theirs[0])
    return straight or crossed
