"""A reviewed order-alias has to state its evidence, and the row has to publish it.

#3287. `_ORDER_ALIASES_REVIEWED` used to be two bare token tuples in a frozenset
with a trailing comment each. The two entries are real, but **nothing in the
repo distinguished them from an invented third**: appending
``("carlos", "alcaraz")`` to the set and one line to the module header passed
every test the module had, including the anti-padding guard — because that guard
checks the header MENTIONS the class, and prose is not evidence.

What this file pins, in the order the ship makes the claims:

1. the reviewed set is DERIVED from the records, so the two cannot drift;
2. a record has to state both orderings, a reviewer, a date and a basis, and
   the orderings have to be genuine permutations of each other;
3. the corpus discriminator — a reviewed entry exists *because* the field spells
   only one of its orders, so the stated `corpus_order` must really be in the
   corpus and the stated `claimed_order` must really be absent;
4. the allowance is published on the agreement row, beside `excluded` and never
   inside it, with every receipt field an operator needs;
5. `Join` refuses a name that is both an allowance and a refusal.

**What this file deliberately does NOT claim.** None of it makes an attestation
TRUE. #3287's option 1 measured that question dead: 272 distinct strings / 451
occurrences carrying `juncheng` or `qinwen` across `events.home_team_name`,
`away_team_name` and `futures_outcomes.name`, **zero** in family-name-first
order, so no sweep can promote these two; and citing an id-anchored StatPal
spelling cannot discriminate either, because StatPal abbreviates (`G. Monfils`)
and so can only attest which token is the surname — which a fabricated
`Carlos Alcaraz` entry passes too. A fully-populated fabricated record still
constructs, and `test_a_complete_fabrication_still_constructs` says so out loud
rather than leaving a reader to assume otherwise. The ship is disclosure: the
claim becomes attributable, dated, falsifiable and PUBLISHED, and it carries
`ratified_by_alex: false` until a person with authority over the product reads it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import partial
from pathlib import Path

import pytest

from app.utils.authority_agreement import DEFAULT_EXCLUDED_KEYS, Join
from app.utils.authority_tennis_agreement import ORDER_ALIAS_ALLOWANCE
from app.utils.authority_tennis_names import (
    ORDER_ALIASES,
    REVIEWED_ALIASES,
    ReviewedAlias,
    _ORDER_ALIASES_MEASURED,
    _ORDER_ALIASES_REVIEWED,
    _ORDER_ALIASES_SLOT_PROVEN,
    _tokens,
    is_doubles_name,
    looks_like_a_player,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def corpus() -> list[str]:
    doc = json.loads(
        (FIXTURES / "tennis_name_corpus_20260905.json").read_text(encoding="utf-8")
    )
    names = doc["names"]
    assert len(names) == doc["count"] == 7731
    return names


def _written_orders(corpus: list[str]) -> dict[tuple[str, ...], set[tuple[str, ...]]]:
    orders: dict[tuple[str, ...], set[tuple[str, ...]]] = defaultdict(set)
    for name in corpus:
        if is_doubles_name(name) or not looks_like_a_player(name):
            continue
        tokens = tuple(_tokens(name))
        if tokens:
            orders[tuple(sorted(tokens))].add(tokens)
    return orders


def _valid(**overrides) -> dict:
    """A well-formed record, so each test can break exactly one thing."""
    base = dict(
        corpus_order="Juncheng Shang",
        claimed_order="Shang Juncheng",
        reviewer="authority lane (agent)",
        reviewed_on="2026-09-05",
        attestation="family name leads in the claimed order",
    )
    base.update(overrides)
    return base


class TestTheSetIsDerivedFromTheRecords:
    """A second literal is a second thing to keep in step."""

    def test_the_reviewed_set_is_exactly_the_records_tokens(self):
        assert _ORDER_ALIASES_REVIEWED == frozenset(a.tokens for a in REVIEWED_ALIASES)

    def test_the_union_and_the_disjointness_still_hold(self):
        """D69 = A added a third source — classes the AUTHORITY RECORD proves
        (`test_tennis_order_aliases_are_proven_2907.py`). The union is now over
        three sets, and the reviewed pair is PARTLY absorbed by the proven one:
        Zheng yes, Shang not yet. CERT-2017 blocked the sweeping version of this
        claim, so the count below is exact rather than a containment."""
        assert ORDER_ALIASES == (
            _ORDER_ALIASES_MEASURED | _ORDER_ALIASES_REVIEWED | _ORDER_ALIASES_SLOT_PROVEN
        )
        assert not (_ORDER_ALIASES_MEASURED & _ORDER_ALIASES_REVIEWED)
        # ONE of the two reviewed classes is now independently proven (Zheng);
        # the other (Shang) is not, because StatPal served him only in doubles
        # and a team's surname proves a word rather than a person (CERT-2017).
        assert len(_ORDER_ALIASES_REVIEWED & _ORDER_ALIASES_SLOT_PROVEN) == 1

    def test_the_reviewed_records_still_number_two_and_carry_nothing_alone(self):
        """7 measured / 2 reviewed was the whole set before D69, and it still is
        the whole REVIEW layer. What changed is how much of it is load-bearing:
        one class of the two. A refactor that quietly added or dropped a REVIEWED
        class still shows here — the proven set is pinned by its own suite, not
        by this count."""
        assert (len(_ORDER_ALIASES_MEASURED), len(_ORDER_ALIASES_REVIEWED)) == (7, 2)
        assert len(_ORDER_ALIASES_MEASURED | _ORDER_ALIASES_REVIEWED) == 9
        # Drop the reviewed SOURCE and exactly one class goes with it — the one
        # the authority record does not yet prove. That single-element gap is
        # the honest measure of what still rests on an agent's reading, and it
        # closes itself the day the venue serves Shang in singles.
        assert (
            ORDER_ALIASES - (_ORDER_ALIASES_MEASURED | _ORDER_ALIASES_SLOT_PROVEN)
            == {("juncheng", "shang")}
        )

    def test_tokens_are_derived_from_the_orderings_not_declared_beside_them(self):
        """So a record cannot name one permutation class and admit another."""
        alias = ReviewedAlias(**_valid())
        assert alias.tokens == ("juncheng", "shang")
        # Folding is applied, so case and punctuation cannot smuggle a variant in.
        assert ReviewedAlias(**_valid(corpus_order="  JUNCHENG   Shang ")).tokens == (
            "juncheng",
            "shang",
        )


class TestARecordMustStateItsEvidence:
    """Every shape a bare tuple used to be allowed to be."""

    def test_the_two_shipped_records_are_well_formed(self):
        assert len(REVIEWED_ALIASES) == 2
        for alias in REVIEWED_ALIASES:
            assert alias.reviewer.strip()
            assert alias.attestation.strip()
            assert alias.reviewed_on == "2026-09-05"

    def test_a_record_claiming_no_second_ordering_is_refused(self):
        with pytest.raises(ValueError, match="no SECOND ordering"):
            ReviewedAlias(**_valid(claimed_order="Juncheng Shang"))

    def test_case_alone_is_not_a_second_ordering(self):
        """The two orderings are compared FOLDED, so `SHANG juncheng` does not
        count as the second spelling of `Shang Juncheng`."""
        with pytest.raises(ValueError, match="no SECOND ordering"):
            ReviewedAlias(
                **_valid(corpus_order="Juncheng Shang", claimed_order="JUNCHENG SHANG")
            )

    def test_a_record_whose_orderings_are_not_permutations_is_refused(self):
        """The failure that would admit a SUBSTITUTION rather than a re-ordering
        — the one harm this whole module is biased against."""
        with pytest.raises(ValueError, match="not a re-ordering"):
            ReviewedAlias(**_valid(claimed_order="Rafael Nadal"))

    @pytest.mark.parametrize(
        "override,expected",
        [
            ({"reviewer": "   "}, "names no reviewer"),
            ({"attestation": ""}, "states no basis"),
            ({"reviewed_on": "yesterday"}, "not an ISO date"),
            ({"reviewed_on": ""}, "not an ISO date"),
            ({"claimed_order": ""}, "both orderings spelled out"),
            ({"corpus_order": "   "}, "both orderings spelled out"),
            ({"corpus_order": 17}, "both orderings spelled out"),
        ],
    )
    def test_provenance_is_not_optional(self, override, expected):
        with pytest.raises(ValueError, match=expected):
            ReviewedAlias(**_valid(**override))

    def test_a_complete_fabrication_still_constructs(self):
        """Said out loud, because the honest limit of this ship is the thing a
        reader is most likely to assume away.

        No data we hold can tell a true attestation from a false one — that is
        #3287's measured finding, not an omission. What the record buys is that
        the lie must now be WRITTEN: a named reviewer, a date, a stated basis and
        two explicit spellings, published on the agreement row where someone
        reads it, instead of a two-token tuple nobody would look at twice.
        """
        fabricated = ReviewedAlias(
            corpus_order="Carlos Alcaraz",
            claimed_order="Alcaraz Carlos",
            reviewer="nobody",
            reviewed_on="2026-01-01",
            attestation="invented",
        )
        assert fabricated.tokens == ("alcaraz", "carlos")
        # …and it is NOT shipped, which is the part that is enforceable.
        assert fabricated.tokens not in _ORDER_ALIASES_REVIEWED


class TestTheCorpusDiscriminator:
    """A reviewed entry exists *because* the field spells only one of its orders.

    That premise is checkable even though the attestation is not, and checking it
    is what stops a reviewed entry being used as a general-purpose bypass: an
    entry for a class the corpus already spells both ways belongs in MEASURED,
    and an entry for a spelling the corpus does not hold at all is fiction.
    """

    def test_each_reviewed_record_names_a_spelling_the_corpus_actually_holds(
        self, corpus
    ):
        written = _written_orders(corpus)
        for alias in REVIEWED_ALIASES:
            orders = written.get(alias.tokens, set())
            assert orders, f"{alias.corpus_order!r} is not in the corpus at all"
            corpus_tokens = tuple(_tokens(alias.corpus_order))
            assert corpus_tokens in orders, (
                f"record says the register holds {alias.corpus_order!r}, "
                f"but the corpus holds {sorted(orders)}"
            )

    def test_each_reviewed_record_claims_an_ordering_the_corpus_does_NOT_hold(
        self, corpus
    ):
        """If the second spelling has arrived, the class is measurable and the
        entry must move to `_ORDER_ALIASES_MEASURED` rather than keep resting on
        review — otherwise a judgement call outlives the need for it."""
        written = _written_orders(corpus)
        for alias in REVIEWED_ALIASES:
            claimed_tokens = tuple(_tokens(alias.claimed_order))
            assert claimed_tokens not in written.get(alias.tokens, set()), (
                f"the corpus now holds {alias.claimed_order!r}; this class is "
                "measured, so move it to _ORDER_ALIASES_MEASURED"
            )

    def test_a_reviewed_class_is_never_one_the_sweep_already_found(self, corpus):
        written = _written_orders(corpus)
        both_ways = {m for m, orders in written.items() if len(orders) > 1}
        assert not (both_ways & _ORDER_ALIASES_REVIEWED)


def _join(**overrides) -> Join:
    """An empty join, so each test can vary only the vocabulary under test."""
    base = dict(
        fixtures=[],
        rows=[],
        paired=[],
        statpal_only=[],
        ours_only=[],
        unusable_fixtures=[],
        unusable_rows=[],
    )
    base.update(overrides)
    return Join(**base)


def _row_for(join: Join) -> dict:
    """The published row for a strategy that returns `join`."""
    from app.utils.authority_agreement import build_agreement_row

    return build_agreement_row(
        sport_key="tennis_singles",
        fixtures=[],
        rows=[],
        normalize=lambda v: (v or "").strip().lower(),
        pair_sides=lambda fixtures, rows, normalize: join,
    )


class TestTheRowPublishesTheAllowance:
    def test_an_allowance_is_published_beside_excluded_never_inside_it(self):
        """The sign error this guards: an allowance folded into `excluded` would
        read as rows taken OUT when in fact they were let IN."""
        receipt = {"tokens": ["juncheng", "shang"], "ratified_by_alex": False}
        row = _row_for(_join(allowances={ORDER_ALIAS_ALLOWANCE: [receipt]}))

        assert row["allowances"] == {
            ORDER_ALIAS_ALLOWANCE: {"count": 1, "receipts": [receipt]}
        }
        # The load-bearing half: it did NOT land in the exclusion census.
        assert ORDER_ALIAS_ALLOWANCE not in row["excluded"]
        assert set(row["excluded"]) == set(DEFAULT_EXCLUDED_KEYS)

    def test_the_real_tennis_strategy_publishes_both_shipped_allowances(self):
        """End to end through the shipped strategy, not a hand-built join — the
        two ends can agree while the wiring between them is dead."""
        from app.utils.authority_agreement import build_agreement_row
        from app.utils.authority_tennis_agreement import SINGLES, pair_tennis_sides

        row = build_agreement_row(
            sport_key=SINGLES,
            fixtures=[],
            rows=[],
            normalize=lambda v: (v or "").strip().lower(),
            pair_sides=partial(pair_tennis_sides, draw=SINGLES),
        )
        published = row["allowances"][ORDER_ALIAS_ALLOWANCE]
        assert published["count"] == 2
        assert [r["corpus_order"] for r in published["receipts"]] == [
            a.corpus_order for a in REVIEWED_ALIASES
        ]
        assert all(r["ratified_by_alex"] is False for r in published["receipts"])

    def test_an_unstated_draw_publishes_no_allowance(self):
        """Fail closed. A caller that has not said which draw it is building does
        not get a claim published on its behalf."""
        from app.utils.authority_tennis_agreement import pair_tennis_sides

        assert pair_tennis_sides([], []).allowances == {}


class TestTheDoublesRowClaimsNoOrderAllowance:
    """CERT-1948. The first cut published both singles-only order allowances on
    the separately banked `tennis_doubles` row as well.

    The doubles join keys on an UNORDERED pair of surnames, so a re-ordering
    tolerance cannot move a doubles number: measured over the pinned corpus,
    **0 of 1,674 doubles names have a token multiset in `ORDER_ALIASES`**. The
    doubles row was therefore asserting it had relied on a tolerance it never
    relied on — a row saying something untrue about its own pass, which is the
    exact failure this ship exists to stop, committed by the ship itself.
    """

    def test_no_doubles_name_in_the_field_can_reach_the_order_tolerance(self, corpus):
        """The premise, measured rather than asserted — this is what makes the
        doubles row's claim false rather than merely redundant."""
        doubles = [n for n in corpus if is_doubles_name(n)]
        assert len(doubles) == 1674
        reachable = [
            n for n in doubles if tuple(sorted(_tokens(n))) in ORDER_ALIASES
        ]
        assert reachable == []

    def test_both_rows_at_once_singles_discloses_and_doubles_does_not(self):
        """The end-to-end two-row assertion the block asked for. Built through
        `tennis_agreement_rows`, so the draw binding at the real call site is
        what is under test — not a partial this test constructed itself."""
        from app.utils.authority_tennis_agreement import (
            DOUBLES,
            SINGLES,
            build_tennis_agreements,
        )

        rows = build_tennis_agreements(fixtures=[], rows=[])

        singles_allowances = rows[SINGLES]["allowances"]
        assert singles_allowances[ORDER_ALIAS_ALLOWANCE]["count"] == 2

        # The load-bearing half: empty, and empty for the RIGHT reason — the key
        # is absent entirely rather than present at a lying zero.
        assert rows[DOUBLES]["allowances"] == {}
        assert ORDER_ALIAS_ALLOWANCE not in rows[DOUBLES]["allowances"]

        # …and the two rows are still separately banked with their own censuses,
        # so this scoping did not collapse them into one.
        assert rows[SINGLES]["sport_key"] == SINGLES
        assert rows[DOUBLES]["sport_key"] == DOUBLES

    def test_the_doubles_partner_order_control_still_folds(self):
        """The control the block asked for: scoping the ALLOWANCE away from
        doubles must not disturb the tolerance doubles genuinely does have —
        partner order, which `doubles_key` sorts and which has nothing to do with
        `ORDER_ALIASES`. `Golubic / Waltert` and `Waltert/Golubic` are one team.
        """
        from app.utils.authority_tennis_names import doubles_key

        assert doubles_key("Golubic / Waltert") == doubles_key("Waltert/Golubic")
        assert doubles_key("Rojer/ Winegar") == doubles_key("Winegar / Rojer")
        # And it is still a real relation, not everything-matches-everything.
        assert doubles_key("Golubic / Waltert") != doubles_key("Rojer/Winegar")

    def test_a_name_cannot_be_both_an_allowance_and_a_refusal(self):
        with pytest.raises(ValueError, match="BOTH an allowance and a refusal"):
            _join(
                refusal_names=("ambiguous_identity",),
                allowances={"ambiguous_identity": []},
            )

    def test_an_allowance_cannot_shadow_a_default_excluded_key(self):
        victim = sorted(DEFAULT_EXCLUDED_KEYS)[0]
        with pytest.raises(ValueError, match="collide with the default"):
            _join(allowances={victim: []})

    def test_a_strategy_that_allows_nothing_publishes_an_empty_block(self):
        """Empty, not absent — the #3275 distinction, applied to allowances."""
        assert _join().allowances == {}
        assert _row_for(_join())["allowances"] == {}

    def test_every_receipt_carries_the_fields_an_operator_needs(self):
        for alias in REVIEWED_ALIASES:
            receipt = alias.receipt()
            assert set(receipt) == {
                "tokens",
                "corpus_order",
                "claimed_order",
                "reviewer",
                "reviewed_on",
                "attestation",
                "ratified_by_alex",
            }
            # JSON-safe: this goes out over an admin endpoint.
            json.dumps(receipt)
            assert receipt["tokens"] == list(alias.tokens)

    def test_both_shipped_allowances_disclose_that_alex_has_not_ratified_them(self):
        """The residue #3287 exists to disclose. If this ever reads True it must
        be because Alex said so and a `YOUR-TURN`/`alex-inbox` entry records it —
        the flip is a deliberate, reviewable edit, not a default."""
        assert [a.ratified_by_alex for a in REVIEWED_ALIASES] == [False, False]
