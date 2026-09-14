"""#3813 follow-up — the club-synonym lookup cannot grow into a rule.

**SHIP: one club under two spellings keeps matching, and two clubs never
start.** (Pillar: MATCHING.) This guards the derivation that let
``KXLALIGAGAME-26AUG27BARATH``'s "Athletic Club" reach our "Athletic Bilbao"
when #3813 armed La Liga's game tickers.

WHY THIS FILE EXISTS, WHICH IS THE WHOLE POINT
═══════════════════════════════════════════════

``_build_club_synonym_pairs``'s docstring used to cite lane1b's 709-pair golden
replay as proof that the derivation fuses nothing. lane1b/255 measured that
claim and refused the credit for it, correctly: **a frozen corpus is a ratchet,
not a guard.** It re-runs the same 709 captured pairs, so it can say nothing
about the thirteenth entry someone adds to ``AUTHORITY_SYNONYMS`` tomorrow —
which is precisely when the assumption would break and nothing would notice.

lane1b bounded the live exposure before raising it, and that is why this is a
guard gap and not an alarm: 12 entries, 24 ordered pairs, **zero names with more
than one partner**, every pair genuinely one club under two spellings. No live
false match exists. int361 merged #3813 over the open finding on that reading
and recorded the three lines as owed; this is them.

THE ASSUMPTION BEING GUARDED
═════════════════════════════

``_fuzzy_team_match`` takes two strings and no sport key, so this lookup is
consulted ACROSS sports while ``AUTHORITY_SYNONYMS`` is keyed per sport. That is
sound only while each pair is two complete club names with a single partner
each. Two properties carry it, and a future table entry is what can break them:

* **Functional** — no normalized name maps to two different partners. A name
  with two partners is a fusion channel: A↔B and A↔C makes B and C reachable
  from one another through A, across sports, with nobody having said so.
* **Whole-name and equality-only** — a bare shared token ("Sporting",
  "Athletic") is never a key. The moment a sub-token is admitted the lookup has
  become the structural rule it exists to avoid, and would reach Ohio State from
  Texas State.

The authority lane's own suite pins the source table as directional and
sport-scoped (``test_authority_synonyms_2823.py``). This file pins what OUR
derivation does to it: drops the direction deliberately, drops the sport key
deliberately, and must not drop anything else.
"""

import pytest

from app.utils.prediction_market_matching import (
    _CLUB_SYNONYM_PAIRS,
    _fuzzy_team_match,
    _normalize_for_matching,
)


class TestTheDerivationIsNotVacuous:
    def test_the_table_actually_produced_pairs(self):
        """A guard over an empty set is a green light with no traffic."""
        assert len(_CLUB_SYNONYM_PAIRS) >= 20, (
            f"only {len(_CLUB_SYNONYM_PAIRS)} ordered pairs — AUTHORITY_SYNONYMS "
            "moved, was renamed, or stopped being imported, and every assertion "
            "below would pass on the wreckage"
        )

    def test_the_pair_that_made_3813_need_this(self):
        assert _fuzzy_team_match("Athletic Club", "Athletic Bilbao") is True
        assert _fuzzy_team_match("Athletic Bilbao", "Athletic Club") is True


class TestNoNameHasTwoPartners:
    """The fusion channel, asserted on the derivation rather than on a corpus."""

    def test_every_name_has_exactly_one_partner(self):
        partners: dict[str, set[str]] = {}
        for left, right in _CLUB_SYNONYM_PAIRS:
            partners.setdefault(left, set()).add(right)

        fused = {name: sorted(p) for name, p in partners.items() if len(p) > 1}
        assert not fused, (
            "a name reaching two different clubs — B and C are now matchable "
            "through A, across sports, and no one wrote that down. Split the "
            "AUTHORITY_SYNONYMS entries or thread the sport key through "
            f"_fuzzy_team_match:\n  {fused}"
        )

    def test_the_relation_is_symmetric(self):
        missing = [
            (left, right)
            for left, right in _CLUB_SYNONYM_PAIRS
            if (right, left) not in _CLUB_SYNONYM_PAIRS
        ]
        assert not missing, (
            "a one-way pair. The source table is directional because it asks "
            "what the AUTHORITY calls a club; ours is symmetric because which "
            f"side holds which spelling is an accident of the ticker: {missing}"
        )

    def test_no_pair_is_a_name_with_itself(self):
        assert not [p for p in _CLUB_SYNONYM_PAIRS if p[0] == p[1]]


class TestNothingShorterThanAWholeNameIsAKey:
    """Equality-only. A shared token must gain nothing at all."""

    @pytest.mark.parametrize("token", ["Sporting", "Athletic", "Real", "Inter"])
    def test_a_bare_shared_token_is_not_a_key(self, token):
        normalized = _normalize_for_matching(token)
        holders = sorted(
            {
                left
                for left, _ in _CLUB_SYNONYM_PAIRS
                if normalized and normalized in left.split()
            }
        )
        if not holders:
            pytest.skip(f"no pair currently contains the token {token!r}")

        assert (normalized, normalized) not in _CLUB_SYNONYM_PAIRS
        for holder in holders:
            assert (normalized, holder) not in _CLUB_SYNONYM_PAIRS, (
                f"{token!r} alone is a key into {holder!r} — the lookup has "
                "become a structural rule, and a structural rule that reaches "
                "Athletic Club from Athletic Bilbao also reaches Ohio State "
                "from Texas State"
            )

    def test_an_unlisted_club_gains_nothing_from_the_table(self):
        """Two clubs sharing a word are still two clubs.

        These pass today through the surrounding structural rules being
        conservative; the assertion here is that the SYNONYM table is not what
        would let them through.
        """
        for left, right in [
            ("Sporting Gijón", "Sporting Kansas City"),
            ("Athletic Club", "Club Brugge"),
            ("Real Sociedad", "Real Madrid"),
        ]:
            key = (_normalize_for_matching(left), _normalize_for_matching(right))
            assert key not in _CLUB_SYNONYM_PAIRS, key


class TestWhatTheDerivationDeliberatelyDrops:
    """Recorded so a later reader does not "fix" an intentional decision."""

    def test_the_sport_key_is_dropped_on_purpose(self):
        """`_fuzzy_team_match` has no sport argument, and that is the trade.

        Sound only while the two properties above hold, which is why they are
        asserted rather than assumed. If this ever has to change, the change is
        threading a sport key through every call site — not loosening the pairs.
        """
        import inspect

        assert "sport" not in inspect.signature(_fuzzy_team_match).parameters

    def test_direction_is_dropped_on_purpose(self):
        """The source table answers an asymmetric question; ours is symmetric.

        Pinned as a property of the DERIVATION so that if the authority lane's
        table ever stops being directional, this file still describes what we do
        with it.
        """
        assert all(
            (right, left) in _CLUB_SYNONYM_PAIRS
            for left, right in _CLUB_SYNONYM_PAIRS
        )
