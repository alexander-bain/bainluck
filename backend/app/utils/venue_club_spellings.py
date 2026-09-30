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
}


def venue_spellings_of(stored_name: object) -> frozenset[str]:
    """The lower-cased venue spellings of a club stored as ``stored_name``.

    For the exact-name resolvers, which compare ``lower()`` strings. Empty when
    the table names no spelling for it.
    """
    if not isinstance(stored_name, str) or not stored_name.strip():
        return frozenset()
    ours = stored_name.strip().lower()
    return frozenset(
        venue.lower()
        for venue, stored in VENUE_CLUB_SPELLINGS.items()
        if stored.lower() == ours
    )
