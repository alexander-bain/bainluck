"""#2012 — the labeling sampler must serve the RENDERABLE population.

THE REPORT. Alex sat down to label and the first THREE cards had no
probabilities. Specimen: `SpaceX IPO closing market cap above ___ ?` — an
unfilled template blank in the title and nothing to judge.

THE FIXTURE. `labeling_sampler_candidates_20260819.json` is the LIVE output of
`GET /api/admin/ranking-judgments/candidates?limit=40` captured **before** the
fix. It reproduces the report exactly: **21 of 40 rows** came back with
`rendered_probability: null`, and ranks **1, 2 and 3** are among them.

THE DIAGNOSIS, which is not the one the report guessed. Only ONE of the 21 is a
group parent. All 21 share something else: `field_sum > 2.0`, which is precisely
the band the SERVED feed renders **raw** — those outcomes are cumulative
thresholds, each meaningful on its own. `Ballon d'Or Winner 2026` (sum 59.0) is
fifty-nine independent "will X win?" binaries and Discover shows it perfectly.

So the sampler and the feed held two DIFFERENT renderability rules. That is the
exact failure `app/utils/card_integrity.py`'s docstring was written to prevent —

    "A predicate that lives in one of them gets re-implemented, slightly
     differently, in the other two."

— reproduced inside the module written to prevent it.

THE FIX, therefore, is not a cull. Dropping every incoherent field would have
deleted `Presidential Election Winner 2028`, `Democratic Presidential Nominee
2028` and `Ballon d'Or Winner 2026` from the labeling pool — the most valuable
cards in it — and biased the training slice toward simple binaries. The sampler
now SCALES the way the page scales, and refuses only what carries no honest
number at all.
"""

import json
from pathlib import Path

import pytest

from app.utils.card_integrity import (
    INDEPENDENT_BINARY_MAX_SUM,
    card_defects,
    display_scale,
    field_coherence,
    has_unfilled_template,
    is_unlabelable,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "labeling_sampler_candidates_20260819.json"
)


@pytest.fixture(scope="module")
def doc():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def rows(doc):
    return doc["rows"]


def _probs(row):
    """Every outcome probability the sampler held when it returned the blank.

    Read from `outcomes`, NOT from `top_outcomes_at_capture` — the pre-fix
    endpoint emitted `top_outcomes: null` on exactly the cards it withheld, so
    the captured payload cannot carry the probabilities the defect is about.
    They are joined in from `futures_outcomes` (941 rows across the 40 markets).
    """
    return [o.get("probability") for o in (row.get("outcomes") or [])]


def _names(row):
    return [o.get("name") for o in (row.get("outcomes") or [])]


# ── The defect, banked ──────────────────────────────────────────────────


def test_the_fixture_still_reproduces_what_alex_hit(rows):
    assert len(rows) == 40
    blank = [r for r in rows if r["rendered_probability_at_capture"] is None]
    assert len(blank) == 21, "the fixture must carry the 21 blank cards"
    # The reported symptom, precisely: the first three cards are unjudgeable.
    assert all(
        rows[i]["rendered_probability_at_capture"] is None for i in range(3)
    ), "ranks 1-3 must be blank — that is the report"


def test_every_blank_card_sat_in_the_band_the_FEED_RENDERS_RAW(rows):
    """The diagnosis, asserted. Not group parents — a threshold disagreement."""
    blank = [r for r in rows if r["rendered_probability_at_capture"] is None]
    sums = [r["field_sum_at_capture"] for r in blank]
    assert all(s is not None and s > INDEPENDENT_BINARY_MAX_SUM for s in sums), sums
    # And the group-parent theory explains only one of the twenty-one.
    parents = [r for r in blank if has_unfilled_template(r["name"])]
    assert len(parents) == 1
    assert "SpaceX IPO closing market cap above" in parents[0]["name"]


# ── The specimen ────────────────────────────────────────────────────────


def test_the_spacex_group_parent_is_refused(rows):
    row = next(r for r in rows if has_unfilled_template(r["name"]))
    assert (
        is_unlabelable(
            outcome_names=_names(row),
            outcome_probabilities=_probs(row),
            market_name=row["name"],
        )
        == "unfilled_template"
    )
    assert "unfilled_template" in card_defects(
        outcome_names=[],
        outcome_probabilities=[0.5],
        market_name=row["name"],
    )


@pytest.mark.parametrize(
    "name,blank",
    [
        ("SpaceX IPO closing market cap above ___ ?", True),
        ("SpaceX IPO closing market cap above $1.2T?", False),
        ("Who will be confirmed as Fed Chair?", False),
        ("Will the Fed cut rates?", False),
        # A single underscore is not a template blank — snake_case slugs and
        # stray punctuation must not be read as one.
        ("market_cap milestone reached?", False),
    ],
)
def test_unfilled_template_is_narrow(name, blank):
    assert has_unfilled_template(name) is blank


# ── The fix: scale, don't cull ──────────────────────────────────────────


def _verdict(row):
    return is_unlabelable(
        outcome_names=_names(row),
        outcome_probabilities=_probs(row),
        market_name=row["name"],
    )


def test_the_valuable_wide_fields_are_KEPT(rows):
    """The half that matters. These are the cards a cull would have deleted."""
    keep = [
        "Presidential Election Winner 2028",
        "Democratic Presidential Nominee 2028",
        "Ballon d'Or Winner 2026",
        "NBA: LeBron James Next Team",
        "Starmer out by...?",
    ]
    for name in keep:
        row = next(r for r in rows if r["name"] == name)
        # pre-fix: blank. The whole point.
        assert row["rendered_probability_at_capture"] is None
        # post-fix: served, because nothing about it is dishonest.
        assert _verdict(row) is None, f"{name} must stay in the labeling pool"


def test_the_full_recovery_census_over_the_production_rows(rows):
    """Total accounting: which of the 21 come back, and which stay refused.

    Pinned as an exact partition rather than a rate, because "most of them" is
    how a cull sneaks back in.
    """
    blank = [r for r in rows if r["rendered_probability_at_capture"] is None]
    served = [r for r in blank if _verdict(r) is None]
    refused = {r["name"]: _verdict(r) for r in blank if _verdict(r)}

    assert len(served) == 18, "18 of the 21 blank cards are recoverable"
    assert refused == {
        "SpaceX IPO closing market cap above ___ ?": "unfilled_template",
        "Who will be confirmed as Fed Chair?": "anonymized_outcomes",
        "Dublin-Central By-Election Winner": "anonymized_outcomes",
    }

    # And nothing that was already fine gets dropped.
    fine = [r for r in rows if r["rendered_probability_at_capture"] is not None]
    assert len(fine) == 19
    assert all(_verdict(r) is None for r in fine)


def test_the_fed_chair_card_is_refused_for_a_MEASURED_reason(rows):
    """It looks like a card a cull would wrongly delete. It is not.

    `Who will be confirmed as Fed Chair?` is a genuinely unreadable card that
    happens to have an interesting title. Measured on the production row:
    **25 of its 35 options are named `Person B` / `Person C` / `Person M`** —
    #1872, where Polymarket serves the anonymization itself and there is nothing
    on our side to un-collapse — and **26 of the 35 are priced at exactly 1.0**,
    which is #1874's shape. Refusing it is correct, and this test exists so a
    future reader does not "restore" it on the strength of the title.
    """
    row = next(r for r in rows if r["name"] == "Who will be confirmed as Fed Chair?")
    names, probs = _names(row), _probs(row)
    assert len(names) == 35
    assert sum(1 for n in names if n and n.startswith("Person ")) == 25
    # A MAJORITY placeholder field is what `is_anonymized_market` refuses, and
    # it is the right rule here: "Other" and a few real names among 25
    # placeholders is not a rankable set.
    assert sum(1 for p in probs if p == 1.0) == 26
    assert _verdict(row) == "anonymized_outcomes"


def test_a_wide_field_is_shown_RAW_exactly_as_the_feed_shows_it(rows):
    """sum > 2.0 -> scale 1.0. Each threshold probability is its own answer."""
    row = next(r for r in rows if r["name"] == "Ballon d'Or Winner 2026")
    assert row["field_sum_at_capture"] > INDEPENDENT_BINARY_MAX_SUM
    assert display_scale(_probs(row)) == 1.0


def test_the_scale_agrees_with_the_feeds_own_bands():
    """The anti-drift guard, band for band.

    `card_integrity.display_scale` and `feed._feed_display_scale` are two
    functions holding one policy. This pins the policy so a change to either
    without the other reds — which is the failure that produced #2012 in the
    first place.
    """
    # already sane -> raw
    assert display_scale([0.6, 0.3, 0.1]) == 1.0
    # true binary, stricter 1.01 threshold. [0.52, 0.51] is the case that
    # DISCRIMINATES: sum 1.03 normalizes under the binary threshold and would
    # be left raw under the 3-outcome one. Picked by measurement — [0.55, 0.55]
    # gives the same answer either way and passed a mutation that collapsed the
    # two thresholds into one.
    assert display_scale([0.52, 0.51]) == pytest.approx(1.03)
    assert display_scale([0.55, 0.55]) == pytest.approx(1.10)
    assert display_scale([0.5, 0.5]) == 1.0
    # ...and three outcomes summing to 1.03 stay RAW, which is the other side
    # of the same threshold.
    assert display_scale([0.4, 0.35, 0.28]) == 1.0
    # independent binaries in the normalizing band
    assert display_scale([0.7, 0.6, 0.4]) == pytest.approx(1.7)
    # cumulative thresholds above the cutoff -> raw, never flattened
    assert display_scale([0.9, 0.8, 0.7, 0.6]) == 1.0
    assert display_scale([]) == 1.0


def test_the_81_percent_leader_is_never_flattened_to_33():
    """The stated reason the >2.0 cutoff exists, asserted rather than trusted."""
    ladder = [0.81, 0.75, 0.7, 0.6]
    assert sum(ladder) > INDEPENDENT_BINARY_MAX_SUM
    scale = display_scale(ladder)
    assert scale == 1.0
    assert round(0.81 / scale, 4) == 0.81


# ── What is still refused ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "names,probs,expected",
    [
        ([], [], "no_priced_outcomes"),
        (["A", "B"], [None, None], "no_priced_outcomes"),
        (["A", "B"], [1.0, 1.0], "all_outcomes_certain"),
        (["Person B", "Person K"], [0.3, 0.2], "anonymized_outcomes"),
        # merely wide is NOT refused
        (["A", "B", "C"], [0.9, 0.8, 0.7], None),
        (["A", "B"], [0.6, 0.5], None),
    ],
)
def test_only_the_unshowable_is_refused(names, probs, expected):
    assert is_unlabelable(outcome_names=names, outcome_probabilities=probs) == expected


def test_field_coherence_still_reports_the_distribution_fact(rows):
    """`field_coherent` is not deleted — it is demoted from admission test to
    reported fact. A wide field is genuinely not a distribution, and the card
    should still say so; it just no longer decides whether Alex sees the card."""
    row = next(r for r in rows if r["name"] == "Ballon d'Or Winner 2026")
    verdict = field_coherence(_probs(row))
    assert verdict["coherent"] is False
    assert verdict["reason"] == "sum_exceeds_one"
    # ...and that same card is served.
    assert _verdict(row) is None


def test_card_defects_is_unchanged_for_callers_that_pass_no_name():
    """Additive: the optional `market_name` must not alter existing callers."""
    assert card_defects(
        outcome_names=["A", "B"], outcome_probabilities=[0.4, 0.4]
    ) == []
    assert card_defects(
        outcome_names=["Person B", "Person K"], outcome_probabilities=[0.4, 0.4]
    ) == ["anonymized_outcomes"]


# ── The second symptom: the pool is STALE, and updated_at hides it ──────


def test_the_labeling_pool_was_half_stale(rows):
    """Alex's standing "label cards run stale" complaint, quantified.

    Same root as the blanks — a raw-pool draw with no served-population
    constraint — which is why both symptoms arrive on the same 40 cards.
    """
    ages = [r["price_age_days_at_capture"] for r in rows]
    assert all(a is not None for a in ages), "every sampled market must have a price age"
    assert sum(1 for a in ages if a >= 7) == 19
    assert sum(1 for a in ages if a >= 30) == 14
    assert max(ages) >= 119


def test_both_cards_alex_marked_bad_were_months_stale(rows):
    """The two `bad` judgments recorded on 2026-08-19 (ranking_judgments 83, 84),
    at ranks 1 and 2 of his session."""
    for name, floor in (
        ("US x Iran permanent peace deal by...?", 60),
        ("Israel x Hezbollah Ceasefire extended by...?", 110),
    ):
        row = next(r for r in rows if r["name"] == name)
        assert row["price_age_days_at_capture"] >= floor
        # ...and both were ALSO blank. One draw, two symptoms.
        assert row["rendered_probability_at_capture"] is None


def test_market_updated_at_is_not_a_freshness_signal(doc):
    """The trap, banked so the floor is not "simplified" back onto updated_at.

    `FuturesMarket.updated_at` read ~5h old on markets whose prices had not
    moved in three months, and read IDENTICAL to the microsecond across
    unrelated markets — it is a bulk-write stamp. Several strata still ORDER BY
    it, which is how a stale card sorts to the top of a "recent" list.
    """
    note = doc["_provenance"]["price_age_note"]
    assert "BULK-WRITE" in note
    assert "futures_outcomes.last_updated" in note
