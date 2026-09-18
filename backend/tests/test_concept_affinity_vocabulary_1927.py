"""A concept card's sport vocabulary must reach the reader's stored one (#1927).

CERT-3059's required repair. The wide half of #1927 gave keyed cards — concepts
and tournaments — a sport-affinity RANK pass. Concept identity is the
``llm_sport_category`` the card's ``ConceptSource`` declares, and the F1 source
declares ``motorsports``; onboarding stores ``motorsport_formula1``. The scan in
``_match_sport_affinity`` asks whether the category is a SUBSTRING of the stored
key, and ``"motorsports" in "motorsport_formula1"`` is False — on the trailing
``s`` alone.

So a reader who had gone through onboarding and explicitly LOVED F1 read as a
reader who had never heard of it: the implicit-Nah clause ("a sport the reader
stored nothing for reads as 0.0") fired, and a score-60 F1 concept card served
at 24 carrying ``sport_nah:-0.60``. A positive signal inverted into a penalty —
which is the one thing #1927's wide half is not allowed to do, since it holds
every positive term IN while lifting the negatives out.

The repair reads ``LLM_CATEGORY_TO_SPORT_PREFIX`` from ``sport_keys.py`` — the
single source of truth for exactly this translation, which has held
``"motorsports": "motorsport"`` all along — as an ADDITIVE retry: reached only
when the direct scan matched nothing, so it can convert a miss and can never
restate a match.

The file grades the three behavioural arms the cert named (Love / "if it's
wild" / Nah), asserts NO ARM DELETES, and pins the blast radius: of the sixteen
entries in the canonical map, only ``motorsports`` can reach the retry at all.
"""

from __future__ import annotations

import pytest

from app.routes.feed import (
    _keyed_item_sport_identity,
    _rank_keyed_items_by_sport_affinity,
)
from app.utils.personalization import (
    LOW_AFFINITY_PENALTY,
    NAH_AFFINITY_PENALTY,
    PersonalizationContext,
    _match_sport_affinity,
    compute_sport_affinity_multiplier,
)
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX

#: What onboarding actually writes when a reader picks Formula 1
#: (`routes/user.py`: `"motorsport": ["motorsport_formula1"]`).
STORED_F1_KEY = "motorsport_formula1"

#: What the F1 concept card declares about itself.
CONCEPT_F1_CATEGORY = "motorsports"

BASE_SCORE = 60


def _f1_concept_card(score: int = BASE_SCORE) -> dict:
    return {
        "type": "concept",
        "score": score,
        "data": {"domain": "f1", "name": "Formula 1"},
    }


def _ctx(affinity: float | None) -> PersonalizationContext:
    """A signed-in reader. `None` = onboarded but stored nothing for F1."""
    stored = {"basketball_nba": 0.5}
    if affinity is not None:
        stored[STORED_F1_KEY] = affinity
    return PersonalizationContext(sport_affinities=stored)


# --- the identity the ship reads -------------------------------------------


def test_the_f1_concept_card_really_does_declare_the_plural_category():
    """The premise. If the concept tier ever renames its category this file is
    grading a card that no longer exists, and the arms below would pass for the
    wrong reason."""
    sport_key, sport_category = _keyed_item_sport_identity(_f1_concept_card())
    assert sport_key is None
    assert sport_category == CONCEPT_F1_CATEGORY


def test_the_two_vocabularies_really_do_disagree():
    """The defect's mechanism, stated so it cannot quietly stop being true: the
    substring scan the matcher is built on fails on these two strings."""
    assert CONCEPT_F1_CATEGORY not in STORED_F1_KEY
    assert LLM_CATEGORY_TO_SPORT_PREFIX[CONCEPT_F1_CATEGORY] in STORED_F1_KEY


def test_the_canonical_map_resolves_what_the_direct_scan_missed():
    assert _match_sport_affinity(CONCEPT_F1_CATEGORY, {STORED_F1_KEY: 1.0}) == 1.0


# --- the three behavioural arms the cert named ------------------------------


@pytest.mark.parametrize(
    "affinity,expect_reason,expect_nah",
    [
        (1.0, "sport_boost", False),   # Love
        (0.1, "sport_suppress", False),  # "only if it's wild"
        (0.0, "sport_nah", True),      # Nah
    ],
)
def test_the_stored_preference_decides_the_arm(affinity, expect_reason, expect_nah):
    r = compute_sport_affinity_multiplier(
        _ctx(affinity), sport_key=None, sport_category=CONCEPT_F1_CATEGORY
    )
    assert any(x.startswith(expect_reason) for x in r.reasons), (affinity, r.reasons)
    assert r.sport_nah is expect_nah


def test_loving_f1_raises_the_card_instead_of_burying_it():
    """THE REGRESSION. Before the repair this served at 24 with
    `sport_nah:-0.60`; the reader had explicitly asked for more F1."""
    [item] = _rank_keyed_items_by_sport_affinity(
        [_f1_concept_card()], ctx=_ctx(1.0), my_teams_only=False
    )
    assert item["score"] >= BASE_SCORE, item
    assert not any(
        r.startswith("sport_nah") for r in item.get("personalization_reasons", [])
    ), item


def test_the_nah_reader_still_ranks_f1_down():
    """The control that keeps the preference real — a repair that simply made
    the dial inert would pass every arm above and fail here."""
    [item] = _rank_keyed_items_by_sport_affinity(
        [_f1_concept_card()], ctx=_ctx(0.0), my_teams_only=False
    )
    assert item["score"] < BASE_SCORE, item
    assert any(r.startswith("sport_nah") for r in item["personalization_reasons"])


@pytest.mark.parametrize("affinity", [1.0, 0.1, 0.0, None])
def test_no_arm_deletes_the_card(affinity):
    """#1927's whole ruling, on this card type: "a ranking signal, not a death
    certificate". Every arm — including the reader who never picked F1 — serves
    exactly one card."""
    items = _rank_keyed_items_by_sport_affinity(
        [_f1_concept_card()], ctx=_ctx(affinity), my_teams_only=False
    )
    assert len(items) == 1, (affinity, items)
    assert items[0]["score"] >= 1


def test_a_reader_who_never_picked_f1_is_unchanged_by_the_repair():
    """The retry must not invent a preference. Someone who onboarded and did not
    pick F1 still reads as the implicit Nah — that behaviour is #1927's, and the
    repair is about readers who DID choose, not about softening the dial."""
    r = compute_sport_affinity_multiplier(
        _ctx(None), sport_key=None, sport_category=CONCEPT_F1_CATEGORY
    )
    assert r.sport_nah is True
    assert any(x.startswith("sport_nah") for x in r.reasons)


# --- blast radius -----------------------------------------------------------


def test_the_retry_moves_only_motorsports():
    """WHO NEWLY MATCHES. The retry is additive, but "additive" bounds the
    direction, not the population. Every category in the canonical map is asked
    whether the direct scan already answers it for a reader who stored the
    matching key; only `motorsports` may reach the retry, so only F1 moves.

    If a future entry lands here, this fails and names it rather than letting it
    change ranking silently.
    """
    reaches_the_retry = []
    for category, prefix in LLM_CATEGORY_TO_SPORT_PREFIX.items():
        if prefix == category:
            continue  # maps to itself: the retry is a no-op by construction
        stored = {f"{prefix}_league": 1.0}
        direct_hit = any(category.lower() in k.lower() for k in stored)
        if not direct_hit:
            reaches_the_retry.append(category)
    assert reaches_the_retry == [CONCEPT_F1_CATEGORY], reaches_the_retry


def test_the_retry_does_not_match_an_unrelated_sport():
    """It resolves a vocabulary, it does not relax the matcher: an F1 lover's
    stored key must not answer for someone else's sport."""
    assert _match_sport_affinity("esports", {STORED_F1_KEY: 1.0}) is None
    assert _match_sport_affinity("mma", {STORED_F1_KEY: 1.0}) is None
    assert _match_sport_affinity(CONCEPT_F1_CATEGORY, {"basketball_nba": 1.0}) is None


def test_the_penalty_constants_are_the_existing_ones():
    """No new dial was minted for this repair."""
    assert NAH_AFFINITY_PENALTY == -0.6
    assert LOW_AFFINITY_PENALTY == -0.3
