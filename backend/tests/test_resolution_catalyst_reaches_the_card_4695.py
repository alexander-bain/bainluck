"""#4695 / #4150 — a resolution catalyst has to reach the reader.

Ship D1 (#4066): page one says why each card is here this morning.

THE DEFECT. `compute_futures_highlight` stopped emitting `resolving_soon_7d` and
`resolving_soon_30d` in 812ca09a (#141/Item 2). That commit's stated purpose was
to delete a double-counted +8/+4, and its sibling in the same hunk (`multi_source`)
did exactly that — kept the reason, dropped the score. The resolution-proximity
branch dropped BOTH, and collapsed the `<= 7` arm away entirely.

The two codes are the display input for ten consumer sites across the four copy
generators in `feed_reasons.py`, and they are rungs 5 and 6 of
`PRIMARY_REASON_LABELS`. With no producer, every one of those ten was unreachable
and no Discover card could say "resolving this week" however close it was.

Measured on production `bbf068c2` (`GET /api/feed?limit=100`): 34 of 100 served
cards resolve inside 30 days, 6 inside 7, and three of them carried no text of any
kind — the specimen below among them.

The tests are built FROM THE SPECIMEN, not from a convenient neighbour: the
numbers in `KYIV_*` are the ones the trace endpoint returned for market 60627568.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import feed_reasons as fr
from app.utils.futures_highlights import (
    PRIMARY_REASON_LABELS,
    compute_futures_highlight,
)

NOW = datetime(2026, 9, 10, 7, 12, tzinfo=timezone.utc)

# ── The specimen ────────────────────────────────────────────────────────────
# `/api/admin/discover-quality/trace/60627568`, production `bbf068c2`. Served at
# position 45, score 65, with reason, headline, hook_description and
# card_sum_reason ALL empty. Resolution 2026-09-17T20:59Z — seven days out.
KYIV_NAME = "Will Russia target Kyiv by September 17, 2026?"
KYIV_RESOLUTION = datetime(2026, 9, 17, 20, 59, tzinfo=timezone.utc)
KYIV_TIER = 2
KYIV_CATEGORY = "geopolitics"
KYIV_PROBABILITY = 0.925
KYIV_RENDERED_PERCENT = 93
# The stored highlight reasons at the blocked commit, verbatim from the trace.
KYIV_REASONS_BEFORE = ["category_base_geopolitics", "tier_2", "secondary_league"]


def _highlight(resolution_date, **overrides):
    kwargs = dict(
        market_tier=KYIV_TIER,
        sport_category=KYIV_CATEGORY,
        resolution_date=resolution_date,
        outcomes=[{"name": "Yes", "probability": KYIV_PROBABILITY, "rank": 1}],
        source_count=1,
        now=NOW,
        market_name=KYIV_NAME,
    )
    kwargs.update(overrides)
    return compute_futures_highlight(**kwargs)


def _resolution_codes(result):
    return [r for r in result.reasons if r.startswith("resolving_soon_")]


# ── 1. The producer emits the code, at both edges of every interval ─────────


@pytest.mark.parametrize(
    "days_until,expected",
    [
        # `micro_bet` owns today/tomorrow — a daily settle is suppressed, not
        # announced, and that behaviour is unchanged by this fix.
        (0, []),
        (1, []),
        # 7d interval: both edges.
        (2, ["resolving_soon_7d"]),
        (6, ["resolving_soon_7d"]),
        # …and the `hours=1` padding below is why 7 sits HERE and not above.
        # #4805 / CERT-2513: the codes are classified off the real duration, not
        # off `timedelta.days`, which floors. `days=7, hours=1` is 7d01h — eight
        # days by any honest reading — and it used to floor to 7 and print
        # "resolves within a week". The padding was added to dodge an exact
        # boundary and it was landing a full hour into the wrong rung.
        (7, ["resolving_soon_30d"]),
        # 30d interval: both edges, including the day after the 7d boundary.
        (8, ["resolving_soon_30d"]),
        (29, ["resolving_soon_30d"]),
        # Same story at the far edge: 30d01h is past thirty days and claims
        # nothing, where the floored test called it "within a month".
        (30, []),
        # Beyond the horizon nothing is claimed. A card with no time-bound
        # signal must NOT be handed a manufactured one (#4080 clause (d) is the
        # answer for those cards, and it is a ranking change, not a copy one).
        (31, []),
        (112, []),
    ],
)
def test_resolution_proximity_emits_its_display_code(days_until, expected):
    result = _highlight(NOW + timedelta(days=days_until, hours=1))
    assert _resolution_codes(result) == expected


def test_the_specimens_own_resolution_date_emits_a_resolution_code():
    """The real row, at the real horizon, not a synthetic offset.

    #4695's ship is that the card gets a resolution sentence at all — it was
    served with reason, headline, hook_description and card_sum_reason ALL empty.
    That still holds.

    Which RUNG it gets moved with #4805 / CERT-2513, and this specimen is why the
    BLOCK was right: Kyiv resolves 2026-09-17T20:59Z against a `NOW` of
    2026-09-10T07:12Z — **7 days 13 hours 47 minutes**. `timedelta.days` floored
    that to 7 and the card told a reader it was "resolving this week". It is the
    month rung, and the month rung is true.
    """
    result = _highlight(KYIV_RESOLUTION)
    assert "resolving_soon_30d" in result.reasons
    assert "resolving_soon_7d" not in result.reasons
    assert result.primary_reason == "Resolving within a month"


# ── 2. Restored WITHOUT the score — #141 was right about that half ──────────


def test_emitting_the_code_moves_no_score():
    """The double-count #141 deleted stays deleted.

    A market seven days from resolution and one 112 days out differ by this
    reason code and by nothing in the score. If a future edit reattaches an
    additive term to this branch, this fails.
    """
    near = _highlight(NOW + timedelta(days=6, hours=1))
    far = _highlight(NOW + timedelta(days=112, hours=1))

    assert "resolving_soon_7d" in near.reasons
    assert _resolution_codes(far) == []
    assert near.score == far.score
    assert near.raw_score == far.raw_score
    # And the value itself is the one production reported for this row.
    assert near.score == 59.0


# ── 3. The class guard: no display label may be unreachable ─────────────────


def test_every_primary_reason_label_is_reachable_from_the_producer():
    """THE GUARD FOR THIS DEFECT CLASS.

    `PRIMARY_REASON_LABELS` is a consumer vocabulary. This bug existed because a
    producer stopped emitting two of its codes while all ten consumer sites went
    on reading them — the two halves agreed on a vocabulary that nothing
    connected, so no test on either side failed.

    This drives `compute_futures_highlight` with inputs chosen to trigger each
    label and asserts the code actually comes out. It is deliberately
    BEHAVIOURAL rather than a source scan: the restored emission is a
    conditional expression inside one `append`, so `grep` for
    `append("resolving_soon_7d")` finds nothing and a source-scan guard would
    report a false negative on the very line it is meant to protect.
    """
    triggers = {
        "leader_change": dict(
            resolution_date=NOW + timedelta(days=200),
            outcomes=[
                {"name": "Alpha", "probability": 0.6, "rank": 1, "rank_change_24h": 1},
                {"name": "Beta", "probability": 0.4, "rank": 2, "rank_change_24h": -1},
            ],
        ),
        "major_movement_24h": dict(
            resolution_date=NOW + timedelta(days=200),
            outcomes=[
                {
                    "name": "Alpha",
                    "probability": 0.6,
                    "rank": 1,
                    "probability_change_24h": 0.30,
                }
            ],
        ),
        "moderate_movement_24h": dict(
            resolution_date=NOW + timedelta(days=200),
            outcomes=[
                {
                    "name": "Alpha",
                    "probability": 0.6,
                    "rank": 1,
                    "probability_change_24h": 0.03,
                }
            ],
        ),
        "volume_spike": dict(
            resolution_date=NOW + timedelta(days=200),
            volume_24h=100_000,
            volume_7d_avg=1_000.0,
        ),
        "resolving_soon_7d": dict(resolution_date=NOW + timedelta(days=5)),
        "resolving_soon_30d": dict(resolution_date=NOW + timedelta(days=20)),
    }

    labelled_codes = [code for code, _label in PRIMARY_REASON_LABELS]
    assert set(triggers) == set(labelled_codes), (
        "PRIMARY_REASON_LABELS changed — give every new code a trigger here, or "
        "it can go unreachable the way resolving_soon_* did."
    )

    unreachable = [
        code
        for code in labelled_codes
        if code not in _highlight(**triggers[code]).reasons
    ]
    assert unreachable == [], (
        f"display labels no producer can emit: {unreachable}. Every string in "
        "PRIMARY_REASON_LABELS is one a reader can end up looking at; a code "
        "nothing emits silently disables its copy in feed_reasons.py."
    )


# ── 4. The code reaches the READER, through the real copy generators ────────


def test_the_silent_specimen_gains_a_true_sentence():
    """End to end on the specimen: producer output feeds the copy generator.

    The reasons list is taken from `compute_futures_highlight` rather than
    hand-written, so a fixture that drifts from what the producer actually emits
    cannot make this pass.
    """
    result = _highlight(KYIV_RESOLUTION)

    copy = fr.compose_binary_card_copy(
        market_name=KYIV_NAME,
        highlight_reasons=result.reasons,
        affirmative_probability=KYIV_PROBABILITY,
        rendered_affirmative_percent=KYIV_RENDERED_PERCENT,
        now=NOW,
    )

    assert copy.reason.strip()
    assert copy.headline.strip()
    # #4805 / CERT-2513: the month rung, because the specimen is 7d13h out. See
    # `test_the_specimens_own_resolution_date_emits_a_resolution_code`. #4695's
    # ship — that this card says ANYTHING — is what the two asserts above pin.
    assert "resolves within a month" in copy.context_summary.lower()
    # The catalyst is the news; the bare probability alone was #4056's defect.
    assert copy.context_summary != f"{KYIV_RENDERED_PERCENT}% chance"


def test_the_same_specimen_is_silent_without_the_code():
    """The control — and it uses the specimen's OWN pre-fix reasons.

    These are the three codes the trace reported for market 60627568 at the
    blocked commit. If this ever stops being silent, the fix above has stopped
    being the thing under test.
    """
    copy = fr.compose_binary_card_copy(
        market_name=KYIV_NAME,
        highlight_reasons=KYIV_REASONS_BEFORE,
        affirmative_probability=KYIV_PROBABILITY,
        rendered_affirmative_percent=KYIV_RENDERED_PERCENT,
        now=NOW,
    )
    assert copy.reason == ""
    assert copy.headline == ""
    assert copy.context_summary == ""


@pytest.mark.parametrize("code", ["resolving_soon_7d", "resolving_soon_30d"])
def test_each_copy_generator_speaks_on_the_code(code):
    """All four generators, so a fix that reaches one door is not mistaken for
    a fix that reaches the reader (#4610's lesson: a rule that lands in one
    component is not landed)."""
    reasons = [*KYIV_REASONS_BEFORE, code]
    common = dict(
        leader_name="Yes",
        leader_probability=KYIV_PROBABILITY,
        rendered_leader_percent=KYIV_RENDERED_PERCENT,
        now=NOW,
    )

    assert fr.generate_futures_reason(
        market_name=KYIV_NAME, highlight_reasons=reasons, **common
    ).strip()

    headline = fr.generate_futures_headline(
        highlight_reasons=reasons, market_name=KYIV_NAME, **common
    )
    assert headline.strip()

    assert fr.generate_futures_context_summary(
        headline=headline,
        highlight_reasons=reasons,
        market_name=KYIV_NAME,
        **common,
    ).strip()

    binary = fr.compose_binary_card_copy(
        market_name=KYIV_NAME,
        highlight_reasons=reasons,
        affirmative_probability=KYIV_PROBABILITY,
        rendered_affirmative_percent=KYIV_RENDERED_PERCENT,
        now=NOW,
    )
    assert binary.reason.strip() and binary.headline.strip()


# ── 5. The other direction — nothing is manufactured ────────────────────────


def test_a_far_horizon_card_is_still_allowed_to_say_nothing():
    """#4080 clause (d), not a sentence.

    `Will China invade Taiwan by end of 2026?` (market 112921, served at
    position 16, score 85) resolves 112 days out with no movement and no leader
    change. It has no time-bound signal, and the fix must not invent one for it
    — a card with nothing true to say yields its slot; it does not get filler.
    """
    result = _highlight(
        NOW + timedelta(days=112),
        market_name="Will China invade Taiwan by end of 2026?",
        sport_category="politics",
    )
    assert _resolution_codes(result) == []

    copy = fr.compose_binary_card_copy(
        market_name="Will China invade Taiwan by end of 2026?",
        highlight_reasons=result.reasons,
        affirmative_probability=0.0385,
        rendered_affirmative_percent=4,
        now=NOW,
    )
    assert copy.reason == ""


def test_a_card_that_already_speaks_keeps_its_own_sentence():
    """Both directions (#4695 acceptance 3).

    A market that moved today AND resolves this month leads with the move: the
    editorial order in `compose_binary_card_copy` puts what changed ahead of
    what is scheduled, and restoring the resolution code must not displace it.
    """
    reasons = [*KYIV_REASONS_BEFORE, "major_movement_24h", "resolving_soon_30d"]
    copy = fr.compose_binary_card_copy(
        market_name=KYIV_NAME,
        highlight_reasons=reasons,
        affirmative_probability=KYIV_PROBABILITY,
        rendered_affirmative_percent=KYIV_RENDERED_PERCENT,
        top_mover_change=0.12,
        now=NOW,
    )
    assert "today" in copy.headline.lower()
    assert "resolving" not in copy.headline.lower()
