"""#5821 / #5905 — the fixture the venue published as PERIODS AND PROPS ONLY.

**SHIP: the Atlético–Real Madrid derby stops being two pages. A reader who
searches "Atletico Madrid" and a reader who searches "Real Madrid" land on the
same page, and that page carries all nine legs instead of one of them carrying
nine and the other one.**  (Pillar: MATCHING.)

🔴 **THE SWEEP REPORTED ITSELF DRAINED WHILE THIS WAS LIVE, AND THAT IS THE
POINT OF THIS FILE.** `polymarket_container_twin_sweep`'s 14:29:04Z pass on
2026-09-18 banked `split_keys_examined: 253, pairs_found: 159, to_tag: 0,
terminal: complete`, reason *"every split family in the window is already
tagged — the healthy end state for a drained backlog"*. It was true of the
families its key could FORM. The key was `(container-stripped title, venue
kickoff)` and the container stripper knows two suffixes, so a fixture the venue
split into `- 1st Half Exact Score` / `- Player Props` events formed no family
at all: each derivative was its own key naming one row, counted in
`keys_examined` and never in `split_keys_examined`. A census taken through the
guarded branch cannot see the unguarded one.

Measured on production 2026-09-18 over the sweep's own ±45d window, every sport,
reader-reachable rows only (untagged, not `merged`/`voided`):

    families the WIDER key forms                                12
    …no base-title holder, label names two sides  (now tag)      5
    …exactly one base-title holder                (now tag)      3
    …two base-title holders            (ambiguous, refused)      4

and all five of the zero-holder families are genuine:

    CA Osasuna vs. Rayo Vallecano de Madrid   15312046 / 15307694   65 legs / 39
    Club Atlético de Madrid vs. Real Madrid   15312071 / 15307707    1 leg  /  9
    Shelbourne FC vs. Drogheda United FC      15310537 / 15310808
    Haiti vs. Trinidad and Tobago             15310361 / 15311039
    Cayman Islands vs. Dominica               15310362 / 15311042

All ten rows answered HTTP 200 serving their own id — none folded, none 410.

TWO HALVES, AND NEITHER SHIPS ALONE
════════════════════════════════════

Measured both ways before either was written, which is the only reason the
shape is this one:

* widening the key ALONE pays 1 of the 5, and that one ("Canada vs. Chile") is
  two pages serving **0 legs each** — a fix that moves no reader;
* relaxing the base-title rule ALONE pays 0 of the 5, because without the wider
  key those families never form to be judged.

WHAT IS DELIBERATELY STILL REFUSED
═══════════════════════════════════

`REFUSE_AMBIGUOUS` (two base holders) is not collateral — it is the guard that
holds back the generic-label false pair, and the widening is only safe because
it stays. `'Games Total: O/U 2.5' @ 2026-09-15T14:00` is `Phantom v G2 Ares`
AND `ASTRAL v Rune Eaters`: two different esports matches whose markets carry a
market label where a fixture title belongs. Three such families are live right
now and every one of them carries two base holders, because a generic label has
no derivative suffix to strip and both rows therefore hold it unchanged.

The reader-visible half of the tag — `folded_event_ids` serving the duplicate's
markets on the canonical inside `_build_game_markets` — is unchanged by this
diff and is proven end to end on real rows by Part C of
`test_existing_split_container_family_5821`. This file grades the judgement that
now reaches the family; it does not re-prove the rail underneath it.
"""

from __future__ import annotations

import pytest

from app.utils.polymarket_container_twins import (
    REFUSE_AMBIGUOUS,
    REFUSE_ANCHORED,
    REFUSE_GENERIC_LABEL,
    REFUSE_NO_ELECTION,
    ContainerMarket,
    ContainerRow,
    family_key,
    fixture_label,
    holds_base_title,
    names_two_sides,
    plan_container_tags,
)

# ── the production specimen, 2026-09-18 ──────────────────────────────────────

KALSHI_MINTED = 15307707  # reachable by searching "Atletico Madrid"; 9 legs
ESPN_CANONICAL = 15312071  # reachable by searching "Real Madrid";    1 leg
KICKOFF = "2026-09-20T14:15:00+00:00"
DERBY = "Club Atlético de Madrid vs. Real Madrid CF"


def _m(event_id: int, name: str, vgs: str = KICKOFF) -> ContainerMarket:
    return ContainerMarket(event_id=event_id, name=name, venue_game_start=vgs)


#: Exactly what production holds: three period markets on the Kalshi-minted row,
#: one prop container on the ESPN-anchored row, and NO base-titled market on
#: either. The venue never published the plain fixture as its own Gamma event.
DERBY_FAMILY = [
    _m(KALSHI_MINTED, f"{DERBY} - 1st Half Exact Score"),
    _m(KALSHI_MINTED, f"{DERBY} - 1st Half First Team to Score"),
    _m(KALSHI_MINTED, f"{DERBY} - 2nd Half First Team to Score"),
    _m(ESPN_CANONICAL, f"{DERBY} - Player Props"),
]


def _rows(winner: int, loser: int, **overrides) -> dict[int, ContainerRow]:
    """A family whose fold election `winner` wins. Ranks are opaque tuples.

    Same discipline as the sibling file: the judgement only COMPARES ranks, so
    reproducing `twin_identity_rank` here would assert our own copy of the
    election instead of that the real one is deferred to.
    """
    rows = {
        winner: ContainerRow(winner, identity_rank=(2,)),
        loser: ContainerRow(loser, identity_rank=(1,)),
    }
    for event_id, row in overrides.items():
        rows[int(event_id)] = row
    return rows


#: The ESPN-anchored row wins its own election — `twin_identity_rank` ranks an
#: ESPN id first, and on this specimen only `15312071` carries one.
ESPN_WINS = _rows(ESPN_CANONICAL, KALSHI_MINTED)


class TestTheDerbyIsOneFixture:
    def test_the_kalshi_row_is_a_duplicate_of_the_espn_row(self):
        """The whole ship: two reader-reachable pages become one."""
        plan = plan_container_tags(DERBY_FAMILY, ESPN_WINS)

        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (KALSHI_MINTED, ESPN_CANONICAL)
        ]
        assert plan.refusals == []

    def test_the_family_forms_at_all(self):
        """The defect was upstream of the verdict: the key never grouped them.

        Pinned separately from the tag because these are two different failures
        and only this one explains a `split_keys_examined` that never counted
        the family and a `to_tag: 0` that read healthy.
        """
        assert len({family_key(m) for m in DERBY_FAMILY}) == 1
        assert family_key(DERBY_FAMILY[0]) == (DERBY, KICKOFF)

    def test_no_row_holds_the_base_title(self):
        """The precondition that used to be a refusal. If this ever goes false
        the specimen has changed and the test above is passing for a new
        reason — a one-holder family, which the shipped rule already tagged."""
        assert [m for m in DERBY_FAMILY if holds_base_title(m)] == []

    def test_the_direction_follows_the_election_and_not_the_market_count(self):
        """🔴 The zero-holder path must not pick its own winner either.

        The Kalshi row holds THREE markets and the ESPN row one, so any
        implementation that broke the tie on market count — the tempting proxy
        when no base title is there to confirm anything — elects the Kalshi row
        and tags the ESPN-anchored one. `not_a_proven_duplicate` runs BEFORE
        the fold, so that would suppress the anchored row and send the reader
        to the worse of the two. Pinned from both sides.
        """
        espn_wins = plan_container_tags(DERBY_FAMILY, ESPN_WINS)
        assert espn_wins.tags[0].canonical_id == ESPN_CANONICAL

        kalshi_wins = plan_container_tags(
            DERBY_FAMILY, _rows(winner=KALSHI_MINTED, loser=ESPN_CANONICAL)
        )
        assert kalshi_wins.tags[0].canonical_id == KALSHI_MINTED
        assert kalshi_wins.tags[0].duplicate_id == ESPN_CANONICAL

    def test_a_zero_holder_family_still_needs_an_election(self):
        """Fail closed. The new path inherits every guard the old one had."""
        plan = plan_container_tags(
            DERBY_FAMILY,
            {
                ESPN_CANONICAL: ContainerRow(ESPN_CANONICAL, identity_rank=(2,)),
                KALSHI_MINTED: ContainerRow(KALSHI_MINTED),
            },
        )
        assert plan.tags == []
        assert any(REFUSE_NO_ELECTION in r for r in plan.refusals)

    def test_a_zero_holder_family_still_refuses_to_tag_an_anchored_row(self):
        """Ruling 048 from the other side: an id-anchored row is never called a
        copy of an id-less one, whatever the venue's titles say."""
        plan = plan_container_tags(
            DERBY_FAMILY,
            _rows(winner=KALSHI_MINTED, loser=ESPN_CANONICAL)
            | {
                ESPN_CANONICAL: ContainerRow(
                    ESPN_CANONICAL, identity_rank=(1,), espn_id="401882865"
                )
            },
        )
        assert plan.tags == []
        assert any(REFUSE_ANCHORED in r for r in plan.refusals)


class TestWhatStaysRefused:
    #: Live on production 2026-09-18 and NOT one fixture: two esports matches
    #: whose Polymarket markets carry a market label instead of a title.
    PHANTOM = 15312741
    ASTRAL = 15312742
    GENERIC = "Games Total: O/U 2.5"

    def test_two_different_esports_matches_are_not_folded_together(self):
        """🔴 The guard the widening is only safe because it keeps.

        Folding these would hide a LIVE match behind an unrelated one.
        """
        family = [
            _m(self.PHANTOM, self.GENERIC, "2026-09-15T14:00:00+00:00"),
            _m(self.ASTRAL, self.GENERIC, "2026-09-15T14:00:00+00:00"),
        ]
        plan = plan_container_tags(family, _rows(self.PHANTOM, self.ASTRAL))

        assert plan.tags == []
        assert any(REFUSE_AMBIGUOUS in r for r in plan.refusals)

    def test_a_generic_label_with_no_base_holder_is_refused(self):
        """The zero-holder path's own floor, on a manufactured specimen.

        It reads zero on today's population — every live zero-holder family is
        a `"X vs. Y"` title — so there is no natural specimen and one is built.
        A generic label is exactly one unstripped derivative suffix away from
        arriving here with no base holder, and at that point nothing else in
        the module distinguishes it from a real fixture.
        """
        family = [
            _m(self.PHANTOM, f"{self.GENERIC} - Exact Score", "2026-09-15T14:00:00+00:00"),
            _m(self.ASTRAL, f"{self.GENERIC} - Player Props", "2026-09-15T14:00:00+00:00"),
        ]
        plan = plan_container_tags(family, _rows(self.PHANTOM, self.ASTRAL))

        assert plan.tags == []
        assert any(REFUSE_GENERIC_LABEL in r for r in plan.refusals)


class TestTheLabelStripper:
    @pytest.mark.parametrize(
        "name,expected",
        [
            (f"{DERBY} - 1st Half Exact Score", DERBY),
            (f"{DERBY} - Player Props", DERBY),
            (f"{DERBY} - More Markets", DERBY),
            (DERBY, DERBY),
            # A hyphen inside a club name is not a suffix.
            ("FC Thun vs. Lausanne-Sport", "FC Thun vs. Lausanne-Sport"),
        ],
    )
    def test_the_market_type_comes_off_and_nothing_else_does(self, name, expected):
        assert fixture_label(name) == expected

    def test_a_series_game_number_is_never_stripped(self):
        """🔴 The data-destroying merge this key must not make.

        `- Game 4` is a DISTINCT game in a series, not a market type. Stripping
        it would key Games 1-5 as one fixture and tag four real games as copies
        of the first. The exclusion lives in #2871's `_DERIVATIVE_SUFFIX_RE`,
        which this module reuses rather than re-spelling; this test is what
        fails if someone ever swaps in a fresh regex or a `split(' - ')`.
        """
        assert fixture_label("Mets vs. Dodgers - Game 4") == "Mets vs. Dodgers - Game 4"

        family = [
            _m(1, "Mets vs. Dodgers - Game 4"),
            _m(2, "Mets vs. Dodgers - Game 5"),
        ]
        assert len({family_key(m) for m in family}) == 2
        assert plan_container_tags(family, _rows(1, 2)).tags == []

    def test_widening_the_key_cannot_change_an_existing_familys_base_count(self):
        """The invariant that makes this safe for the 159 pairs already tagged.

        A row joining under the wider label holds no base-titled market — if it
        did, its own title WAS the narrow key and it was already in the family
        — so `base_holders` is unchanged wherever a family already formed, and
        a one-holder family cannot become ambiguous by gaining a derivative.
        """
        narrow = [_m(1, DERBY), _m(2, f"{DERBY} - More Markets")]
        widened = narrow + [_m(3, f"{DERBY} - 1st Half Exact Score")]

        assert [m.event_id for m in narrow if holds_base_title(m)] == [1]
        assert [m.event_id for m in widened if holds_base_title(m)] == [1]

        plan = plan_container_tags(
            widened,
            {
                1: ContainerRow(1, identity_rank=(3,)),
                2: ContainerRow(2, identity_rank=(2,)),
                3: ContainerRow(3, identity_rank=(1,)),
            },
        )
        assert sorted(t.duplicate_id for t in plan.tags) == [2, 3]
        assert {t.canonical_id for t in plan.tags} == {1}

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("CA Osasuna vs. Rayo Vallecano de Madrid", True),
            ("Club Atlético de Madrid vs. Real Madrid CF", True),
            ("Sao Paulo Open: Eva Lys vs Nadia Podoroska", True),
            ("Games Total: O/U 2.5", False),
            ("Map 2 Total Rounds: Over/Under 21.5", False),
            ("", False),
        ],
    )
    def test_names_two_sides_separates_a_title_from_a_market_label(
        self, label, expected
    ):
        assert names_two_sides(label) is expected
