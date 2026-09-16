"""Guard: `Lillestrom` and `Lillestroem` are one club, so one card (#5905).

THE PAGE THIS EXISTS FOR. `/sports/soccer_uefa_europa_league`, 390px,
2026-09-16. Europa League matchday 1 carried the same fixture twice:

    15298749  "Lillestrom"  v Torreense  19:00Z  scheduled  odds_api  anchored
    15307673  "Lillestroem" v Torreense  22:00Z  scheduled  kalshi    no anchor

#5905's recovery had ALREADY done its half: both rows serve 19:00Z, measured on
production the day this was built. So the clock is not what keeps them apart and
neither is the away club — `Torreense` is byte-identical on both rows. The only
thing left standing between the reader and one card is how the two providers
spell `ø`.

`strip_diacritics` folds `ø`, `ö`, `å` to a SINGLE letter (#5878 closed to make
it do that — before it, the letter was deleted outright). The Odds API agrees
and writes `Lillestrom`. Kalshi uses the other conventional ASCII spelling and
writes the DIGRAPH, `Lillestroem`. Neither is wrong. #5905's own comment called
this out — "the duplicate half is blocked on SPELLING, not on time ... the
remaining work is a soccer name arm on the fold" — and this is that arm.

WHAT EACH TEST HERE IS DEFENDING. Not "a helper returns a string". The ways a
transliteration fold reaches Alex having made things worse:

* it does not fire, because the retry never sees the pair the census promised
  (`test_the_europa_pair_folds_to_one_card`, and the vacuity pin below it);
* it fires and serves the row with no anchor and the wrong hour
  (`test_the_surviving_card_is_the_anchored_league_row`);
* it fires on two clubs that merely LOOK alike — `ss` was measured and refused
  for exactly this reason (`test_al_nasr_is_never_folded_into_al_nassr`);
* it chains three clubs into one card through a shared substring
  (`test_the_two_madrids_still_never_fold`);
* it silently costs a pair that folds today (`test_the_retry_is_additive`).

THE CENSUS THIS RESTS ON, so a later reader can re-run it rather than trust it.
Over every distinct soccer club name in the table — 9,471 — collapsing each
digraph and counting squashed forms that NEWLY collide: `oe` 5 groups (Bodø/
Glimt, Brøndby, Lillestrøm, SønderjyskE, Tromsø — every one a single club),
`aa` 1 group (Västerås SK), `ae` 0, `ue` 0, and `ss` 2 groups of which one is
Al Nasr against Al Nassr, two different clubs. That is why the rule is `oe` and
`aa` and nothing else.
"""

from datetime import datetime, timezone

from app.utils.event_twin_fold import (
    _collapse_transliteration,
    _pair_matches_after_transliteration,
    fold_twin_events,
)
from app.utils.soccer_team_matching import soccer_pair_matches

KICKOFF = datetime(2026, 9, 17, 19, 0, tzinfo=timezone.utc)
VASTERAS_KICKOFF = datetime(2026, 9, 19, 13, 0, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `Event.sport` loaded.

    Deliberately not a MagicMock, for the reason #5918's file gives: an
    auto-attribute mock makes every `espn_id` truthy and every `sport.key` a
    soccer key by accident, so this whole file would pass with the pass deleted.
    """

    def __init__(
        self,
        row_id,
        home,
        away,
        commence_time=None,
        sport_id=2001,
        sport_key="soccer_uefa_europa_league",
        external_id=None,
        sources=None,
    ):
        self.id = row_id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time or KICKOFF
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.espn_id = None
        self.external_id = external_id
        self.home_score = None
        self.away_score = None
        self.win_probability_sources = sources
        self.status = "scheduled"


def _ids(result):
    return sorted(event.id for event in result.events)


def _europa_pair():
    """Production's two rows, at the minute #5905's recovery puts them both on."""
    return [
        _Row(
            15298749,
            "Lillestrom",
            "Torreense",
            external_id="01678a3de0b0537624fbc64304d90710",
        ),
        _Row(
            15307673,
            "Lillestroem",
            "Torreense",
            sources={"kalshi": {"probability": 0.5}},
        ),
    ]


# ── the ship ────────────────────────────────────────────────────────────────


def test_the_europa_pair_folds_to_one_card():
    """The defect itself: production's exact rows, production's exact spellings."""
    result = fold_twin_events(_europa_pair())

    assert _ids(result) == [15298749]
    assert result.folded_count == 1


def test_the_pair_is_genuinely_refused_without_the_retry():
    """The vacuity pin: this file must fail if the retry is deleted.

    Asserted against the predicate the fold used before this ship rather than by
    reverting the fold, so the guard names the one call that changed.
    """
    strict = soccer_pair_matches(
        ("Lillestrom", "Torreense"), ("Lillestroem", "Torreense")
    )
    assert strict is False

    assert (
        _pair_matches_after_transliteration(
            ("Lillestrom", "Torreense"), ("Lillestroem", "Torreense")
        )
        is True
    )


def test_the_surviving_card_is_the_anchored_league_row():
    """Folding the wrong way round would serve the 22:00Z row with no anchor."""
    survivor = fold_twin_events(_europa_pair()).events[0]

    assert survivor.id == 15298749
    assert survivor.external_id == "01678a3de0b0537624fbc64304d90710"
    assert survivor.home_team_name == "Lillestrom"


def test_the_vasteras_three_card_group_folds_across_the_catchall_key():
    """The `aa` half, on live rows, through the catch-all pass rather than the
    strict one.

    `/sports` carried this fixture THREE times on 2026-09-19 — one anchored
    Allsvenskan row and two `soccer_other` Polymarket rows — all three at the
    same minute, so no clock recovery is involved. `Västerås SK` squashes to
    `vasterassk` and `Vasteraas SK` to `vasteraassk`; nothing but the `å`
    spelling separated them.
    """
    rows = [
        _Row(
            15310907,
            "Västerås SK",
            "Malmo FF",
            commence_time=VASTERAS_KICKOFF,
            sport_id=3001,
            sport_key="soccer_sweden_allsvenskan",
            external_id="abc",
        ),
        _Row(
            15311530,
            "Vasteraas SK",
            "Malmo FF",
            commence_time=VASTERAS_KICKOFF,
            sport_id=3002,
            sport_key="soccer_other",
            sources={"polymarket": {"probability": 0.4}},
        ),
        _Row(
            15311559,
            "Vasteraas SK",
            "Malmo FF",
            commence_time=VASTERAS_KICKOFF,
            sport_id=3002,
            sport_key="soccer_other",
            sources={"polymarket": {"probability": 0.4}},
        ),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [15310907]
    assert result.folded_count == 2


# ── the refusals ────────────────────────────────────────────────────────────


def test_al_nasr_is_never_folded_into_al_nassr():
    """The measured reason `ss -> s` is NOT in the rule.

    Al Nasr and Al Nassr are two clubs. They were one of only two collisions the
    `ss` census found, and they are why the whole digraph family was not adopted
    wholesale. Pinned here so nobody adds `ss` back by symmetry with `oe`.
    """
    rows = [
        _Row(1, "Al Nasr", "Torreense", external_id="a"),
        _Row(2, "Al Nassr", "Torreense", sources={"kalshi": {}}),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2]
    assert result.folded_count == 0
    assert _collapse_transliteration("Al Nassr") == "Al Nassr"


def test_the_two_madrids_still_never_fold():
    """The chaining control #5918 was built around, re-asked after the retry.

    The retry widens what counts as one club, so the clique refusal is worth
    re-asserting rather than assumed to survive.
    """
    rows = [
        _Row(3, "Real Madrid", "Torreense", external_id="a"),
        _Row(4, "Atletico Madrid", "Torreense", sources={"kalshi": {}}),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [3, 4]
    assert result.folded_count == 0


def test_the_exonym_sub_class_is_not_claimed_by_this_ship():
    """Scope pin: `Ferencváros TC` / `Ferencvarosi` is still two cards.

    #5905 carries this pair as a clean control, and it is a DIFFERENT shape —
    the stems differ, not the transliteration of one letter. If a later widening
    folds it, that is a new licence with its own census, and this assertion is
    the thing it has to come and change on purpose.
    """
    rows = [
        _Row(5, "Celtic", "Ferencváros TC", external_id="a"),
        _Row(6, "Celtic", "Ferencvarosi", sources={"kalshi": {}}),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [5, 6]
    assert result.folded_count == 0


# ── the shape of the retry ──────────────────────────────────────────────────


def test_the_retry_is_additive():
    """A pair the strict predicate already matches is returned unchanged.

    `Sligo Rovers` / `Sligo Rovers FC` folds today. The club-suffix fold proposed
    on #6221 was rejected because it made `Sevilla v Valencia` ambiguous — it
    could LOSE a pair. A retry cannot: the strict answer is returned first.
    """
    assert soccer_pair_matches(
        ("Sligo Rovers", "Galway United"), ("Sligo Rovers FC", "Galway United FC")
    )
    assert _pair_matches_after_transliteration(
        ("Sligo Rovers", "Galway United"), ("Sligo Rovers FC", "Galway United FC")
    )


def test_the_collapse_preserves_case():
    """`soccer_team_matches` reads capitals when it falls back to initials, so
    the retry must not hand it a lowercased string."""
    assert _collapse_transliteration("Lillestroem") == "Lillestrom"
    assert _collapse_transliteration("LILLESTROEM") == "LILLESTROM"
    assert _collapse_transliteration("Vasteraas SK") == "Vasteras SK"


def test_the_collapse_mangles_non_nordic_words_and_that_is_safe():
    """`Phoenix` becomes `Phonix`, deliberately.

    The collapse is not a dictionary of Nordic clubs and does not try to be. It
    is only ever compared against another string put through the same function,
    so a mangling both sides share cannot separate two rows — and the 9,471-name
    census is what says it cannot join two clubs either.
    """
    assert _collapse_transliteration("Phoenix FC") == "Phonix FC"
    assert _collapse_transliteration("Phoenix FC") == _collapse_transliteration(
        "Phoenix FC"
    )
    assert not _pair_matches_after_transliteration(
        ("Phoenix FC", "Torreense"), ("Phonetic FC", "Torreense")
    )


def test_a_name_with_nothing_to_collapse_is_returned_untouched():
    """The early exit that keeps the retry off the hot path for most pairs."""
    assert _collapse_transliteration("Torreense") == "Torreense"
    assert _collapse_transliteration(None) is None
    assert _collapse_transliteration("") == ""
