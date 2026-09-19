"""The three properties tennis's whole "no key join" argument rests on. #3258.

`utils/authority_tennis_agreement`'s module docstring builds the case against a
key join on one sentence: the identity relation "is reflexive and symmetric and
**not** transitive, and a non-transitive relation has no keys". Every downstream
choice — `pair_tennis_sides` calling `resolve_tennis_name` instead of grouping,
AMBIGUOUS being published rather than dropped — is downstream of that sentence
being true.

**Nothing pinned it.** #3258 was filed because a careful reader measured
`tennis_names_agree` and found it neither symmetric nor reflexive, and read that
as the docstring being wrong in two of its three clauses. Measured on
2026-09-18 the issue's premise does not hold, for two separate reasons, and both
are worth a test rather than a comment:

1. **The docstring's subject is `keys_agree`, not `tennis_names_agree`.** Read
   in place, the sentence is about the key-level relation. That relation is
   reflexive, symmetric and non-transitive exactly as claimed — asserted below,
   including a witness for the non-transitivity, which is the clause with no
   natural example in the corpus and so the one a sweep silently misses.
2. **`tennis_names_agree`'s asymmetry is the call, not the relation.** It takes
   `(ours, theirs)` and parses the two sides with two different functions. It
   was never claimed to be symmetric, and making it symmetric would mean
   normalising both sides through one parser — the surname-only join
   `authority_tennis_names` exists to refuse (contested 38.3% of the time).

The issue's third claim — `("Garcia Garcia", "Garcia Garcia")` being False, i.e.
not reflexive — no longer reproduces; it is reflexive now. That regression is
worth a guard on its own, so it is asserted here too.

None of this is a behaviour change. These tests pin what the code already does,
so that the next reader who measures `tennis_names_agree` in both directions
finds an assertion explaining what they are looking at instead of re-filing it.
"""

import itertools

import pytest

from app.utils.authority_tennis_names import (
    keys_agree,
    our_tennis_keys,
    statpal_tennis_key,
    tennis_names_agree,
)

#: Keys spanning every vocabulary the module documents: our four shapes (bare
#: surname, two-token, three-token, doubles handled separately) and StatPal's
#: one. Built from real name forms rather than hand-written tuples so a change
#: to either parser moves this population instead of leaving it fossilised.
_CORPUS_NAMES = (
    "Carlos Alcaraz",
    "Alcaraz",
    "C. Alcaraz",
    "A. Alcaraz",
    "Garcia Garcia",
    "Garcia",
    "G. Garcia",
    "A. Garcia",
    "Wu Yibing",
    "Y. Wu",
    "Wu",
    "Alejandro Davidovich Fokina",
    "D. Merida Aguilar",
    "Merida Aguilar",
    "T. M. Etcheverry",
    "Etcheverry",
    "B. Van De Zandschulp",
    "Van De Zandschulp",
    "Damm Jr",
    "Damm",
    "Hrazdil",
    "Gaston",
    "Bu",
    "Ha",
)


def _corpus_keys():
    """Every key either parser produces for `_CORPUS_NAMES`, deduped."""
    keys = set()
    for name in _CORPUS_NAMES:
        keys.update(our_tennis_keys(name) or ())
        theirs = statpal_tennis_key(name)
        if theirs is not None:
            keys.add(theirs)
    # Sort with a total order: the initial half is Optional[str].
    return sorted(keys, key=lambda k: (k[0], k[1] or ""))


class TestKeysAgreeIsReflexiveAndSymmetric:
    """The two clauses #3258 read as false. Both hold, at the key level."""

    def test_the_corpus_is_big_enough_to_be_worth_sweeping(self):
        """A sweep over three keys proves nothing; say the size out loud.

        If a parser change collapses this, the sweeps below go vacuous while
        still passing, which is the failure mode these assertions exist to
        avoid.
        """
        keys = _corpus_keys()
        assert len(keys) >= 25, f"corpus collapsed to {len(keys)} keys: {keys}"
        # Both shapes must be present or the None-handling is never exercised.
        assert any(k[1] is None for k in keys), "no initial-less key in corpus"
        assert any(k[1] is not None for k in keys), "no initialled key in corpus"

    def test_every_key_agrees_with_itself(self):
        """Reflexive. A player is the same player."""
        offenders = [k for k in _corpus_keys() if not keys_agree(k, k)]
        assert not offenders, f"non-reflexive keys: {offenders}"

    def test_agreement_does_not_depend_on_argument_order(self):
        """Symmetric — the clause the docstring is judged on."""
        keys = _corpus_keys()
        offenders = [
            (a, b)
            for a, b in itertools.permutations(keys, 2)
            if keys_agree(a, b) != keys_agree(b, a)
        ]
        assert not offenders, f"asymmetric key pairs: {offenders[:5]}"


class TestKeysAgreeIsNotTransitive:
    """The clause that carries the argument, and the one with no free witness.

    A sweep of the corpus above finds NO transitivity violation — `("garcia",
    "a")` only enters the population if some name in it is spelled `A. Garcia`.
    That is exactly the reduced-fixture trap the module warns about elsewhere:
    the property that matters most is the one a sample is least likely to
    contain. So it is constructed rather than sampled.
    """

    def test_a_missing_initial_chains_two_players_who_are_not_one(self):
        with_g = ("garcia", "g")
        unknown = ("garcia", None)
        with_a = ("garcia", "a")

        # A missing initial is UNKNOWN, so it agrees with both...
        assert keys_agree(with_g, unknown)
        assert keys_agree(unknown, with_a)
        # ...but two initials that are both PRESENT and differ are a refusal.
        assert not keys_agree(with_g, with_a)

    def test_a_present_initial_is_never_a_wildcard(self):
        """The other half of the same rule, and the CERT-1890 guard.

        If `None` ever started meaning "matches anything" rather than "not
        known", the test above would still pass while the relation became an
        equivalence — and a key join would look legal again.
        """
        assert not keys_agree(("garcia", "g"), ("alcaraz", "g"))
        assert not keys_agree(("garcia", None), ("garcia garcia", None))


class TestTennisNamesAgreeIsDirectionalByConstruction:
    """`(ours, theirs)`. Swapping them asks a different question. #3258."""

    def test_our_doubled_surname_reaches_their_bare_one(self):
        """`our_tennis_keys` returns every reading; this is the one that hits."""
        assert ("garcia", "g") in our_tennis_keys("Garcia Garcia")
        assert tennis_names_agree("Garcia Garcia", "Garcia")

    def test_the_reverse_call_is_false_and_that_is_not_a_defect(self):
        """Their parser yields one key, and it is not our surname.

        Asserted so that a future change which makes this True has to come here
        and say why — the obvious route to symmetry is normalising both sides
        through one parser, which is the surname-only join this module refuses.
        """
        assert statpal_tennis_key("Garcia Garcia") == ("garcia garcia", None)
        assert not tennis_names_agree("Garcia", "Garcia Garcia")

    @pytest.mark.parametrize(
        "name",
        [
            "Garcia Garcia",
            "Carlos Alcaraz",
            "C. Alcaraz",
            "Alcaraz",
            "Wu Yibing",
            "Hrazdil",
        ],
    )
    def test_a_name_agrees_with_itself_in_both_vocabularies(self, name):
        """The regression #3258 actually caught, now fixed. Keep it fixed.

        `("Garcia Garcia", "Garcia Garcia") -> False` was the issue's least
        defensible finding: a name our side and StatPal spell identically not
        agreeing with itself. It reproduces no longer.
        """
        assert tennis_names_agree(name, name)

    def test_the_documented_join_direction_still_works(self):
        """The direction every production caller uses: ours, then theirs.

        `link_tennis_statpal_fixtures` and `authority_tennis_agreement` both
        call `(our_name, statpal_name)`. If that direction ever stopped
        working, tennis would silently stop joining at all.
        """
        assert tennis_names_agree("Carlos Alcaraz", "C. Alcaraz")
        assert tennis_names_agree("Alcaraz", "C. Alcaraz")
        assert tennis_names_agree("Jaume Munar", "J. Munar")
        # Surname-first, the reading that keeps Chinese players joinable.
        assert tennis_names_agree("Wu Yibing", "Y. Wu")
