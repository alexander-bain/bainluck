"""#2088 — a two-outcome card that does not total 100 says why, on the payload.

THE FILING, from INT-104's post-deploy verification of UX-P113: the queue's own
stated deploy check — *"every two-outcome card's ``rendered_percent`` sums to
100"* — measured **17 of 18** in production, not 18 of 18. The miss was not a
rounding failure. ``is_complement_pair`` correctly refused market 59194098
(``Bilardo vs Gschwendtner``, 0.57 + 0.40 = 0.97) because normalizing it would
invent three points of probability, and the code was behaving exactly as
designed.

The defect is what the reader was left with: a card printing ``57 / 40`` and
nothing saying why. That is indistinguishable from the ``93 / 8`` bug #2060 had
just fixed. In the issue's own words — **an unexplained non-100 is the defect; a
labelled one is a fact.**

RE-MEASURED 2026-08-29 against the same endpoint the issue used: 100 cards, 18
two-outcome, 17 summing to 100, one at 99 (``Diane Parry vs Ann Li: Set 2
Winner``, served ``[51, 48]``). A different market from the filed row and the
same shape, so the class is a population rather than an anecdote.

WHAT THIS FILE PROVES THAT THE CONTRACT SUITE CANNOT. ``test_graded_card_contract``
drives ``card_sum_reason`` through the shared table and would stay green if
neither serializer ever put the field on the wire. These tests run the REAL
serializers over the REAL captured pool and assert the thing the acceptance
criterion actually asks for: **the count of unexplained non-100 cards is zero,
and it is assertable from the served payload.**
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.admin_judgments import _serialize_labeling_candidate
from app.routes.admin_label_pass import _live_features
from app.utils.graded_card import (
    LABEL_PASS_SERVED_OUTCOMES,
    NATIVE_SERVED_OUTCOMES,
    SUM_INDEPENDENT_PRICES,
    SUM_UNPRICED_OUTCOME,
    card_fingerprint,
    card_sum,
    card_sum_reason,
    rendered_card_percents,
)

FIXTURE = Path(__file__).parent / "fixtures" / "labeling_card_trio_20260821.json"

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)

#: The card #2088 names. It is in the captured pool, which is what lets this file
#: assert the acceptance criterion over a real population rather than a stub.
FILED_EXEMPLAR_ID = 59194098
FILED_EXEMPLAR_PROBABILITIES = [0.57, 0.40]


@pytest.fixture(scope="module")
def rows():
    return json.loads(FIXTURE.read_text())["items"]


# ── 1. THE ACCEPTANCE CRITERION, OVER THE REAL CAPTURED POOL ─────────────────


def test_no_two_outcome_card_in_the_live_pool_misses_100_UNEXPLAINED(rows):
    """Acceptance criterion 2, stated as the issue states it.

    Every two-outcome card whose printed percents do not total 100 must carry a
    machine-readable reason, so the count of UNEXPLAINED non-100 cards is zero.
    """
    unexplained = []
    for row in rows:
        probabilities = [o["probability"] for o in row["top_outcomes"]]
        if len(probabilities) != 2:
            continue
        if card_sum(probabilities) == 100:
            continue
        if card_sum_reason(probabilities) is None:
            unexplained.append((row["id"], row["name"], rendered_card_percents(probabilities)))

    assert unexplained == [], (
        f"{len(unexplained)} two-outcome cards miss 100 with no reason: {unexplained}"
    )


def test_the_pool_actually_contains_the_card_the_issue_names(rows):
    """Gotcha #53: a zero is a response shape until you prove the instrument was
    pointed at something.

    The test above is satisfied perfectly by a pool containing no non-100 cards at
    all. MEASURED over this fixture: of its 17 two-outcome cards, exactly ONE
    misses 100 — and it is **59194098, `Bilardo vs Gschwendtner`, the card #2088
    was filed about**, rendering 57 + 40 = 97.

    (The neighbouring #2060 file's prose says "four cards … 97, 99 and 102"; that
    count is over non-complement cards of every arity, not two-outcome ones. Cross
    -checked by measuring rather than inherited.)
    """
    reasoned = {
        row["id"]: card_sum([o["probability"] for o in row["top_outcomes"]])
        for row in rows
        if len(row["top_outcomes"]) == 2
        and card_sum_reason([o["probability"] for o in row["top_outcomes"]]) is not None
    }
    assert reasoned, "no explained cards in the pool — the zero above proves nothing"
    assert FILED_EXEMPLAR_ID in reasoned, (
        f"the card #2088 names is gone from the fixture; explained ids: {list(reasoned)}"
    )
    assert reasoned[FILED_EXEMPLAR_ID] == 97
    exemplar = next(r for r in rows if r["id"] == FILED_EXEMPLAR_ID)
    probabilities = [o["probability"] for o in exemplar["top_outcomes"]]
    assert rendered_card_percents(probabilities) == [57, 40]
    assert card_sum_reason(probabilities) == SUM_INDEPENDENT_PRICES


def test_complement_pairs_in_the_live_pool_stay_silent(rows):
    """The other direction (gotcha #43), and here it is the more dangerous one.

    #2060 normalizes these to exactly 100. A reason on one of them would be an
    apology for a card that is already correct, printed on the surface where Alex
    grades — worse than the unexplained card this feature removes.
    """
    checked = 0
    for row in rows:
        probabilities = [o["probability"] for o in row["top_outcomes"]]
        if len(probabilities) != 2 or card_sum(probabilities) != 100:
            continue
        checked += 1
        assert card_sum_reason(probabilities) is None, (
            f"card {row['id']} ({row['name']}) totals 100 and still earned a reason"
        )
    assert checked >= 12, f"only {checked} totalling-100 cards found in the pool"


# ── 2. THE SERIALIZERS ACTUALLY PUT IT ON THE WIRE ───────────────────────────


def _native_market(*, probabilities=(0.57, 0.40), names=("Bilardo", "Gschwendtner")):
    """The filed exemplar, shaped for `_serialize_labeling_candidate`.

    Deliberately not an ORM object, for the same reason the #2060 file gives: a
    test that needs a database to prove a display rule is a test that gets
    skipped the first time the database is slow.
    """
    outcomes = [
        SimpleNamespace(
            id=100 + i,
            name=names[i],
            current_probability=probabilities[i],
            probability_change_24h=0.0,
            rank=i + 1,
        )
        for i in range(len(probabilities))
    ]
    return SimpleNamespace(
        id=59194098,
        name="Bilardo vs Gschwendtner",
        external_id="KXTENNIS-26AUG21BILGSC",
        outcomes=outcomes,
        description=None,
        hook_description=None,
        image_url=None,
        group_id=None,
        source="kalshi",
        status="open",
        llm_sport_category="tennis",
        sport=None,
        market_tier=2,
        commence_time=datetime(2026, 8, 21, 0, 40, tzinfo=timezone.utc),
        resolution_date=datetime(2026, 8, 22, 0, 40, tzinfo=timezone.utc),
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )


def _proposal():
    return SimpleNamespace(
        id=1,
        item_type="futures",
        item_id="59194098",
        item_name="Bilardo vs Gschwendtner",
        category="tennis",
        archetype=None,
        decision="llm_proposed_promote",
        admin_notes=None,
        features={"generation": "g1", "evidence_generation": "g1"},
        created_at=NOW,
    )


def _label_pass_market():
    return SimpleNamespace(
        id=59194098,
        name="Bilardo vs Gschwendtner",
        status="open",
        resolution_date=FUTURE,
        volume_24h=1200,
        llm_sport_category="tennis",
        market_tier=2,
        external_id="KXTENNIS-26AUG21BILGSC",
        commence_time=datetime(2026, 8, 21, 0, 40, tzinfo=timezone.utc),
    )


def _label_pass_outcomes(*pairs):
    return [
        SimpleNamespace(id=i, market_id=59194098, name=n, current_probability=p)
        for i, (n, p) in enumerate(pairs, start=1)
    ]


def test_the_native_serializer_serves_the_reason_and_the_total():
    row = _serialize_labeling_candidate(_native_market(), rank=1, stratum="top_feed_like")
    assert [o["rendered_percent"] for o in row["top_outcomes"]] == [57, 40]
    assert row["rendered_sum"] == 97
    assert row["card_sum_reason"] == SUM_INDEPENDENT_PRICES


def test_the_native_serializer_stays_silent_on_a_complement_pair():
    row = _serialize_labeling_candidate(
        _native_market(probabilities=(0.925, 0.075), names=("Dodgers", "Colorado")),
        rank=1,
        stratum="top_feed_like",
    )
    assert [o["rendered_percent"] for o in row["top_outcomes"]] == [93, 7]
    assert row["rendered_sum"] == 100
    assert row["card_sum_reason"] is None


def test_the_label_pass_serializer_serves_the_reason_and_the_total():
    features = _live_features(
        _proposal(),
        _label_pass_market(),
        _label_pass_outcomes(("Bilardo", 0.57), ("Gschwendtner", 0.40)),
    )
    assert [o["rendered_percent"] for o in features["outcomes"]] == [57, 40]
    assert features["rendered_sum"] == 97
    assert features["card_sum_reason"] == SUM_INDEPENDENT_PRICES


def test_the_label_pass_serializer_stays_silent_on_a_complement_pair():
    features = _live_features(
        _proposal(),
        _label_pass_market(),
        _label_pass_outcomes(("Dodgers", 0.925), ("Colorado", 0.075)),
    )
    assert features["rendered_sum"] == 100
    assert features["card_sum_reason"] is None


def test_both_serializers_agree_about_the_same_card():
    """Ruling 021 — what is shared is the DECISION.

    #1933's whole finding was that a card fix landing in one route handler is a
    card fix the other surface never gets. Two surfaces, one card, one answer.
    """
    native = _serialize_labeling_candidate(
        _native_market(), rank=1, stratum="top_feed_like"
    )
    web = _live_features(
        _proposal(),
        _label_pass_market(),
        _label_pass_outcomes(("Bilardo", 0.57), ("Gschwendtner", 0.40)),
    )
    assert native["card_sum_reason"] == web["card_sum_reason"]
    assert native["rendered_sum"] == web["rendered_sum"]


# ── 3. THE FIELD MUST NOT MOVE THE DRIFT FINGERPRINT ─────────────────────────


def test_serving_the_reason_does_not_change_the_card_fingerprint():
    """Adding a field to the served card must not refuse anybody's verdict.

    `card_fingerprint` gates every write on the label pass. If a new served field
    entered the digest, the deploy would refuse every in-flight verdict — Alex's
    open tab would start rejecting labels for a drift nobody could see, which is
    precisely the failure `graded_card` exists to prevent.

    It cannot, and the reason is structural rather than lucky: `card_sum_reason`
    is a pure function of the rendered percents, which are ALREADY inside the
    digest. So there is no state it can observe that the fingerprint does not.
    """
    outcomes = [
        {"name": "Bilardo", "probability": 0.57},
        {"name": "Gschwendtner", "probability": 0.40},
    ]
    digest = card_fingerprint(
        title="Bilardo vs Gschwendtner",
        status="open",
        resolution_date=None,
        field_coherent=True,
        outcomes=outcomes,
        served_outcomes=LABEL_PASS_SERVED_OUTCOMES,
    )
    # The exact digest the PRE-#2088 code produced for this card, computed by
    # loading `graded_card.py` at git HEAD~ and calling it. Pinned as a literal on
    # purpose: recomputing it with the current function on both sides of the
    # comparison would agree with itself no matter what the function did.
    assert digest == "352764e92ed1c5ed"

    # And the two surfaces' slices still differ, as they are meant to.
    assert LABEL_PASS_SERVED_OUTCOMES != NATIVE_SERVED_OUTCOMES


# ── 4. THE TWO REASONS NAME DIFFERENT FACTS ──────────────────────────────────


def test_an_unpriced_side_is_not_a_disagreement():
    """Ruling 086: a store that folds absence and disagreement together cannot
    report either. Telling a reader "these two do not add up" about a card
    carrying ONE number would be exactly that."""
    features = _live_features(
        _proposal(),
        _label_pass_market(),
        _label_pass_outcomes(("Bilardo", 0.57), ("Gschwendtner", None)),
    )
    assert features["card_sum_reason"] == SUM_UNPRICED_OUTCOME
    assert features["rendered_sum"] == 57


def test_a_withheld_field_carries_no_total_and_no_reason():
    """When the field is incoherent the card draws nothing, so there is nothing to
    total. `field_withheld_reason` already says why the field is absent; this
    must not add a second, contradictory explanation."""
    features = _live_features(
        _proposal(),
        _label_pass_market(),
        # Three outcomes each at 100% — incoherent, so the field is withheld.
        _label_pass_outcomes(("A", 1.0), ("B", 1.0), ("C", 1.0)),
    )
    assert features["outcomes"] is None
    assert features["field_withheld_reason"]
    assert features["rendered_sum"] is None
    assert features["card_sum_reason"] is None
