"""#2060 — the labeling card trio, from Alex's own 08-20 gold session.

THE REPORT, in his words: *"Labeling card: 93% + 8% = 101% (complement
inconsistency), no commence time, truncated team names."* The card was
`Los Angeles D vs Colorado`, baseball/kalshi, and he correctly voted it Bad.

THE FIXTURE. ``labeling_card_trio_20260821.json`` is the LIVE output of
``GET /api/admin/ranking-judgments/candidates?limit=100`` captured against
production ``ec636bae`` **before** the fix. It reproduces the report exactly:
**14 of its 17 two-outcome cards** render a sum other than 100, and market
**59183794** — the card named in the issue — is among them at 93 + 8.

THE CAUSE, which is not "someone rounded carelessly". Every value here is
produced by ``rendered_percent``, which is correct, contract-pinned across three
runtimes, and was never the bug. The bug is applying it TWICE to one question.
Kalshi quotes a complement pair on a HALF-CENT grid — 0.925/0.075, 0.915/0.085,
0.705/0.305 — so ``p * 100`` lands on ``.5`` for **both sides at once** and
half-up rounds both up. Measured on production 2026-08-21: 10,198 of 21,524 open
two-outcome markets render a sum other than 100, and 8,982 of those are 101
against only 318 at 99. A 28:1 skew is one systematic cause, not scatter.

WHY THE TESTS BELOW ASSERT THE LEAVE-ALONE DIRECTION AS HARD AS THE FIXED ONE.
Two outcomes are not automatically two sides of one question: measured
two-outcome field sums run from 0.001 to 2.0, and forcing a 0.001 field to 100
would invent a probability rather than round one. A guard whose tests only prove
it fires is how a diversity cap emptied the Sports tab (gotcha #43), so the
untouched cases are pinned here by name.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.admin_judgments import _serialize_labeling_candidate
from app.utils.graded_card import (
    COMPLEMENT_MAX,
    COMPLEMENT_MIN,
    is_complement_pair,
    rendered_card_percents,
    rendered_percent,
)
from app.utils.kalshi_display_names import (
    apply_name_repairs,
    repair_truncated_names,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "labeling_card_trio_20260821.json"
)

#: The card Alex named in the issue.
EXEMPLAR_ID = 59183794


@pytest.fixture(scope="module")
def doc():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def rows(doc):
    return doc["items"]


def _market(
    *,
    market_id=1,
    name="Los Angeles D vs Colorado",
    external_id="KXMLBGAME-26AUG182040LADCOL",
    probabilities=(0.925, 0.075),
    outcome_names=("Los Angeles D", "Colorado"),
    commence_time=datetime(2026, 8, 18, 0, 40, tzinfo=timezone.utc),
):
    """A stand-in carrying only what the serializer reads.

    Deliberately not an ORM object: the serializer is pure over its inputs, and a
    test that needs a database to prove a rounding rule is a test that will be
    skipped the first time the database is slow.
    """
    outcomes = [
        SimpleNamespace(
            id=100 + i,
            name=outcome_names[i],
            current_probability=probabilities[i],
            probability_change_24h=0.0,
            rank=i + 1,
        )
        for i in range(len(probabilities))
    ]
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        outcomes=outcomes,
        description=None,
        hook_description=None,
        image_url=None,
        group_id=None,
        source="kalshi",
        status="open",
        llm_sport_category="baseball",
        sport=None,
        market_tier=1,
        commence_time=commence_time,
        resolution_date=datetime(2026, 8, 22, 0, 40, tzinfo=timezone.utc),
        created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )


# ── 1. THE FIXTURE REALLY DOES CONTAIN THE DEFECT ────────────────────────────
#
# If this stops holding, the fixture was re-captured after the fix and every
# assertion below it is proving nothing.


def test_the_captured_pool_reproduces_the_report(rows):
    two = [r for r in rows if len(r["top_outcomes"]) == 2]
    assert len(two) == 17

    broken = []
    for row in two:
        percents = [rendered_percent(o["probability"]) for o in row["top_outcomes"]]
        if None not in percents and sum(percents) != 100:
            broken.append((row["id"], percents))

    assert len(broken) == 14, (
        "the fixture must still show the pre-fix behaviour; got "
        f"{len(broken)} broken rows instead of 14"
    )
    assert EXEMPLAR_ID in {row_id for row_id, _ in broken}


def test_the_exemplar_card_is_the_one_alex_named(rows):
    card = next(r for r in rows if r["id"] == EXEMPLAR_ID)
    assert card["name"] == "Los Angeles D vs Colorado"
    assert [o["probability"] for o in card["top_outcomes"]] == [0.925, 0.075]
    # 93 + 8 = 101, exactly as reported.
    assert [rendered_percent(o["probability"]) for o in card["top_outcomes"]] == [93, 8]


# ── 2. THE DISPLAY-LAYER INVARIANT (#2060 item 1) ────────────────────────────


def test_every_complement_pair_in_the_live_pool_now_sums_to_exactly_100(rows):
    """THE invariant the issue asked for, run over real captured cards."""
    checked = 0
    for row in rows:
        probs = [o["probability"] for o in row["top_outcomes"]]
        if not is_complement_pair(probs):
            continue
        percents = rendered_card_percents(probs)
        checked += 1
        assert sum(percents) == 100, (
            f"card {row['id']} ({row['name']}) renders {percents}, "
            f"which sums to {sum(percents)}"
        )
    # A vacuous pass is the failure mode this whole file exists to prevent: if
    # the predicate ever stops matching anything, the loop above is green and
    # proves nothing (gotcha #53 — an empty result is a response shape).
    assert checked >= 14, f"only {checked} complement pairs found in the pool"


def test_non_complement_cards_are_left_exactly_as_they_were(rows):
    """The other direction, and it is not a formality.

    Four cards in this pool are two-outcome fields that are NOT complement pairs.
    Their rendered sums are 97, 99 and 102 and they must STAY that way — a
    two-outcome book summing to 0.97 has a real three-point spread, and flattening
    it to 100 would claim precision the market does not have.
    """
    untouched = 0
    for row in rows:
        probs = [o["probability"] for o in row["top_outcomes"]]
        if is_complement_pair(probs):
            continue
        assert rendered_card_percents(probs) == [rendered_percent(p) for p in probs], (
            f"card {row['id']} ({row['name']}) is not a complement pair but the "
            f"card rule changed its rendering"
        )
        untouched += 1
    assert untouched >= 12


def test_the_exemplar_now_renders_93_and_7(rows):
    card = next(r for r in rows if r["id"] == EXEMPLAR_ID)
    probs = [o["probability"] for o in card["top_outcomes"]]
    assert rendered_card_percents(probs) == [93, 7]


# ── 3. THE SERIALIZER — the actual display layer, not just the helper ────────


def test_the_served_card_carries_rendered_percents_that_sum_to_100():
    row = _serialize_labeling_candidate(_market(), rank=1, stratum="top_feed_like")
    percents = [o["rendered_percent"] for o in row["top_outcomes"]]
    assert percents == [93, 7]
    assert sum(percents) == 100


def test_the_served_card_carries_a_commence_time():
    """#2060 item 2 — a probability is ungradeable without a when.

    `resolution_date` was the only temporal field on the card, and on a Kalshi
    game market that is the CLOSE time, not the start (gotcha #14). So the one
    date Alex could see was the wrong one.
    """
    row = _serialize_labeling_candidate(_market(), rank=1, stratum="top_feed_like")
    assert row["commence_time"] == "2026-08-18T00:40:00+00:00"
    assert row["resolution_date"] == "2026-08-22T00:40:00+00:00"
    assert row["commence_time"] != row["resolution_date"]


def test_a_partially_hydrated_row_renders_instead_of_500ing_the_queue():
    """The new fields are OPTIONAL DISPLAY inputs, and absence is a fine card.

    Reading `market.external_id` / `market.commence_time` directly turned any row
    that lacked them into an `AttributeError` **inside a route handler** — which
    is not a missing name on one card, it is the entire labeling queue returning
    500. Eighteen existing tests caught it, and the production shape it protects
    against is a `load_only` query rather than a test double.
    """
    bare = SimpleNamespace(
        id=7,
        name="Some market",
        outcomes=[
            SimpleNamespace(
                id=1, name="Yes", current_probability=0.6,
                probability_change_24h=None, rank=1,
            )
        ],
        description=None, hook_description=None, image_url=None, group_id=None,
        source="kalshi", status="open", llm_sport_category="politics", sport=None,
        market_tier=1, resolution_date=None, created_at=None, updated_at=None,
    )
    row = _serialize_labeling_candidate(bare, rank=1, stratum="s")
    assert row["commence_time"] is None
    assert row["name"] == "Some market"
    assert row["name_at_source"] == "Some market"
    assert row["card_fingerprint"]


def test_a_market_with_no_commence_time_serves_null_not_a_guess():
    row = _serialize_labeling_candidate(
        _market(commence_time=None), rank=1, stratum="top_feed_like"
    )
    assert row["commence_time"] is None


def test_the_served_card_untruncates_the_team_name():
    """#2060 item 3."""
    row = _serialize_labeling_candidate(_market(), rank=1, stratum="top_feed_like")
    assert row["name"] == "Los Angeles Dodgers vs Colorado"
    # The source text is kept, not overwritten — a repair with no audit trail is
    # indistinguishable from a corruption.
    assert row["name_at_source"] == "Los Angeles D vs Colorado"
    assert row["top_outcomes"][0]["name"] == "Los Angeles Dodgers"
    assert row["top_outcomes"][0]["name_at_source"] == "Los Angeles D"
    # `Colorado` was never truncated, so it is not rewritten.
    assert row["top_outcomes"][1]["name"] == "Colorado"


def test_the_fingerprint_is_taken_over_the_rendered_card():
    """The load-bearing wiring.

    `graded_card`'s promise is that "the fingerprint changes exactly when the
    picture changes". If the digest were still taken per-outcome, the server would
    expect 93/8 while every client showed 93/7, and EVERY verdict on a Kalshi
    binary would be refused for a drift nobody could see — a gate that refuses
    everything being exactly as useless as one that refuses nothing.
    """
    a = _serialize_labeling_candidate(_market(), rank=1, stratum="s")
    # Same card, different rank/stratum: unchanged, as before.
    b = _serialize_labeling_candidate(_market(), rank=9, stratum="other")
    assert a["card_fingerprint"] == b["card_fingerprint"]

    # A move too small to change the PICTURE must not change the digest…
    same_picture = _serialize_labeling_candidate(
        _market(probabilities=(0.9251, 0.0749)), rank=1, stratum="s"
    )
    assert same_picture["card_fingerprint"] == a["card_fingerprint"]

    # …and one that does change it must.
    moved = _serialize_labeling_candidate(
        _market(probabilities=(0.88, 0.12)), rank=1, stratum="s"
    )
    assert moved["card_fingerprint"] != a["card_fingerprint"]


@pytest.mark.parametrize("external_id", ["KXMLBGAME-26AUG182040LADCOL", None])
def test_the_digest_is_recomputable_from_the_SERVED_card(external_id):
    """The strongest form of "fingerprint what is rendered": recompute it.

    Rebuilding the digest out of the fields the response actually carries — the
    served title, the served outcome names, the served percents — and demanding it
    match proves the server hashed the card it sent, not some neighbouring value.

    An earlier version of this test compared a repaired card against an
    unrepairable one and asserted the digests differed. It passed while the title
    was still being fingerprinted from the SOURCE text, because the outcome names
    differed too and carried the inequality on their own. A mutation that swapped
    `display_name` back to `market.name` survived it. Asserting a difference is
    weak; asserting the exact value is not.
    """
    market = _market(external_id=external_id)
    row = _serialize_labeling_candidate(market, rank=1, stratum="s")

    from app.utils.graded_card import NATIVE_SERVED_OUTCOMES, card_fingerprint

    recomputed = card_fingerprint(
        title=row["name"],
        # Not served — native does not print status — but deliberately in the
        # digest; see the serializer for why the sampler's strata make it part of
        # what put the card on screen.
        status=market.status,
        resolution_date=row["resolution_date"],
        field_coherent=row["field_coherent"],
        outcomes=row["top_outcomes"],
        served_outcomes=NATIVE_SERVED_OUTCOMES,
    )
    assert recomputed == row["card_fingerprint"]


# ── 4. THE BAND ──────────────────────────────────────────────────────────────


def test_the_complement_band_is_closed_at_both_ends():
    assert is_complement_pair([0.705, 0.305])  # 1.01 exactly
    assert is_complement_pair([0.59, 0.4])  # 0.99 exactly
    assert not is_complement_pair([0.706, 0.305])  # 1.011
    assert not is_complement_pair([0.589, 0.4])  # 0.989


def test_the_band_mirrors_the_existing_true_binary_threshold():
    """1.01 is not a new number invented for this fix.

    `card_integrity.display_scale` already treats 1.01 as the two-outcome "true
    binary" cutoff. The band here is that constant made SYMMETRIC, and the missing
    lower half was itself part of the defect: a pair summing to 0.99 rendered 99
    and nothing in the system considered that wrong.
    """
    from app.utils import card_integrity

    assert COMPLEMENT_MAX == 1.01
    assert round(COMPLEMENT_MIN + COMPLEMENT_MAX, 6) == 2.0, (
        "the band must stay symmetric about 1.0"
    )
    # Read the threshold out of `display_scale` itself rather than restating it:
    # if that function ever stops treating 1.01 as the two-outcome cutoff, the
    # claim in this module's docstring is false and this must go red.
    assert 1.01 in card_integrity.display_scale.__code__.co_consts, (
        "display_scale no longer carries 1.01 as its two-outcome threshold — "
        "COMPLEMENT_MAX is documented as mirroring it and no longer does"
    )


def test_a_pair_is_exactly_two_priced_outcomes():
    assert not is_complement_pair([0.5, 0.3, 0.2])
    assert not is_complement_pair([1.0])
    assert not is_complement_pair([0.6, None])
    assert not is_complement_pair([])
    assert not is_complement_pair(None)


# ── 5. NAME REPAIR NEVER INVENTS ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "ticker,outcomes,title,expected",
    [
        (
            "KXMLBGAME-26AUG182040LADCOL",
            ["Los Angeles D", "Colorado"],
            "Los Angeles D vs Colorado",
            "Los Angeles Dodgers vs Colorado",
        ),
        (
            "KXMLBGAME-26AUG182005CWSCHC",
            ["Chicago C", "Chicago WS"],
            "Chicago WS vs Chicago C",
            "Chicago White Sox vs Chicago Cubs",
        ),
        (
            # `A` is consistent with BOTH "Angels" and "Astros"; only the ticker
            # CODES separate them. This is the case that forced
            # `extract_team_codes_from_ticker` to exist.
            "KXMLBGAME-26AUG182010LAAHOU",
            ["Los Angeles A", "Houston"],
            "Los Angeles A vs Houston",
            "Los Angeles Angels vs Houston",
        ),
        (
            "KXNBAGAME-26FEB21LALLAC",
            ["Los Angeles L", "Los Angeles C"],
            "Los Angeles L vs Los Angeles C",
            "Los Angeles Lakers vs Los Angeles Clippers",
        ),
        (
            # Suffixed series titles keep their suffix.
            "KXMLBGAME-26AUG182040LADCOL",
            ["Los Angeles D", "Colorado"],
            "Los Angeles D vs Colorado: Spread",
            "Los Angeles Dodgers vs Colorado: Spread",
        ),
    ],
)
def test_truncated_names_are_repaired_from_the_ticker(
    ticker, outcomes, title, expected
):
    repairs = repair_truncated_names(ticker, outcomes)
    assert apply_name_repairs(title, repairs) == expected


@pytest.mark.parametrize(
    "ticker,outcomes,title",
    [
        # Nothing truncated — correct data is not rewritten.
        ("KXMLBGAME-26AUG181940SEAMIL", ["Milwaukee", "Seattle"], "Seattle vs Milwaukee"),
        # Tennis: the abbreviation map is pro-league only, so nothing resolves.
        ("KXATPMATCH-26AUG18YANVAS", ["Yang", "Vasileva"], "Yang vs Vasileva"),
        # No ticker at all (Polymarket).
        (None, ["Los Angeles D", "Colorado"], "Los Angeles D vs Colorado"),
        # A ticker that parses to nothing recognisable.
        ("KXWEIRD-26AUG18ZZZQQQ", ["Los Angeles D", "Colorado"], "Los Angeles D vs Colorado"),
    ],
)
def test_unresolvable_names_ship_exactly_as_the_source_sent_them(
    ticker, outcomes, title
):
    """A short name is visibly short. A WRONG name is not.

    So the fallback is always "change nothing" — never a best guess.
    """
    repairs = repair_truncated_names(ticker, outcomes)
    assert repairs == {}
    assert apply_name_repairs(title, repairs) == title
