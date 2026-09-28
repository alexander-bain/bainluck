"""#9348 — a "Completed Match" novelty may not speak as the match winner.

THE DEFECT, as a reader saw it. WTA qualifying, Hunter vs Zhang (event
15320043), Sep 28: the live chart spiked to ~54% at the start of play. The
stored Polymarket readings were 0.085 · 0.98 · 0.98 · 0.98 · 0.09 — three polls
(06:10:36Z, 06:14:36Z, 06:16:36Z) reading Zhang at 98% while Kalshi held 0.095.

THE MECHANISM, read off the three snapshots' own `game_state`: not the match
market's book at all. The speaker was market 62862881, `China Open,
Qualification: Completed Match: Ruien Zhang vs Storm Hunter` — "will the match
be completed?", outcomes Yes/No, Yes at 0.98. The title recognizer splits at the
LAST colon, reads `Completed Match` as a competition prefix and finds a bare
matchup behind it, so it answers `moneyline`; `find_moneyline_outcome` orients
the generic "Yes" onto the first-named player. It only got the floor because the
real moneyline (62842519) was briefly inadmissible — no post-kickoff
observation past the #4854 grace — so the blend fell through to the next
admissible row.

THE FIX reads the venue's own label, already stored on the row
(`content_understanding_v1.venue_type = tennis_completed_match`). Measured
2026-09-28 over every Polymarket market linked to an event within ±7 days: 495
such markets, 3 speaking right now, and 0 of the 651 speaking `moneyline` legs
touched.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone

from app.tasks import prediction_market_matching as pmm
from app.utils import live_blend
from app.utils.content_understanding import venue_label_refutes_full_contest_winner
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_as_blend_speaker,
    compute_source_home_probability,
    count_admissible_speakers,
)

HOME = "Zhang"
AWAY = "Hunter"

# The rows' own `content_understanding_v1`, verbatim from production.
_CU_COMPLETED = {
    "v": 1,
    "rule": "content_understanding@5273",
    "agreement": "contradicted",
    "venue_type": "tennis_completed_match",
    "semantic_type": "moneyline",
}
_CU_MONEYLINE = {
    "v": 1,
    "rule": "content_understanding@5273",
    "agreement": "corroborated",
    "venue_type": "moneyline",
    "semantic_type": "moneyline",
}


class _Market:
    def __init__(self, mid, name, *, metadata=None, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id
        self.status = "open"
        self.market_metadata = metadata


class _Outcome:
    current_yes_bid = current_yes_ask = None
    is_winner = None

    def __init__(self, rank, name, probability, last_updated=None):
        self.rank = rank
        self.name = name
        self.current_probability = probability
        self.last_updated = last_updated


def _completed_match(metadata, observed=None):
    return _Market(
        62862881,
        "China Open, Qualification: Completed Match: Ruien Zhang vs Storm Hunter",
        metadata=metadata,
    ), [
        _Outcome(1, "Yes", 0.98, observed),
        _Outcome(2, "No", 0.02, observed),
    ]


def _moneyline(metadata, observed=None):
    return _Market(
        62842519,
        "China Open, Qualification: Ruien Zhang vs Storm Hunter",
        metadata=metadata,
    ), [
        _Outcome(2, "Ruien Zhang", 0.085, observed),
        _Outcome(1, "Storm Hunter", 0.915, observed),
    ]


def _entry(pair, commence=None):
    market, outcomes = pair
    return MarketOutcomes(
        market=market,
        outcomes=outcomes,
        event_commence_time=commence,
        event_has_result=False,
    )


# The specimen's clock, offset from NOW first (gotcha #44): play began ten
# minutes ago, past the 7-minute kickoff grace; the moneyline was last observed
# before the whistle, the novelty half a minute ago.
_NOW = datetime.now(timezone.utc)
_KICKOFF = _NOW - timedelta(minutes=10)
_PRE_KICKOFF = _KICKOFF - timedelta(minutes=15)
_JUST_NOW = _NOW - timedelta(seconds=30)


class TestTheSpecimen:
    def test_the_novelty_no_longer_takes_the_floor_when_the_moneyline_is_silent(self):
        group = [
            _entry(_moneyline({"content_understanding_v1": _CU_MONEYLINE}, _PRE_KICKOFF), _KICKOFF),
            _entry(_completed_match({"content_understanding_v1": _CU_COMPLETED}, _JUST_NOW), _KICKOFF),
        ]
        assert compute_source_home_probability(group, HOME, AWAY) is None
        # And the retirement path agrees there is nobody left to speak, so the
        # stored leg is cleared rather than frozen at its last value.
        assert count_admissible_speakers(group) == 0

    def test_strawman_without_the_label_the_novelty_publishes_098(self):
        """The same rows with the label stripped reproduce production exactly.

        This is what makes the test above non-vacuous: the title recognizer
        DOES admit the novelty and "Yes" DOES orient onto Zhang.
        """
        group = [
            _entry(_moneyline(None, _PRE_KICKOFF), _KICKOFF),
            _entry(_completed_match(None, _JUST_NOW), _KICKOFF),
        ]
        reading = compute_source_home_probability(group, HOME, AWAY)
        assert reading is not None
        assert reading.market.id == 62862881
        assert reading.outcome.name == "Yes"
        assert reading.home_probability == 0.98

    def test_both_fresh_the_moneyline_speaks_alone_and_is_not_averaged_with_the_novelty(self):
        group = [
            _entry(_moneyline({"content_understanding_v1": _CU_MONEYLINE}, _JUST_NOW), _KICKOFF),
            _entry(_completed_match({"content_understanding_v1": _CU_COMPLETED}, _JUST_NOW), _KICKOFF),
        ]
        reading = compute_source_home_probability(group, HOME, AWAY)
        assert reading is not None
        assert reading.market.id == 62842519
        assert reading.home_probability == 0.085
        assert [o.name for o in reading.contributing_outcomes] == ["Ruien Zhang"]
        assert not reading.devigged


class TestTheGateReadsOnlyAPresentLabel:
    def test_a_moneyline_label_is_admitted(self):
        market, outcomes = _moneyline({"content_understanding_v1": _CU_MONEYLINE})
        assert admissible_as_blend_speaker(market, is_primary=True, outcomes=outcomes)

    def test_an_absent_label_is_not_a_refutation(self):
        unconfirmed = {k: v for k, v in _CU_MONEYLINE.items() if k != "venue_type"}
        unconfirmed["agreement"] = "unconfirmed"
        for metadata in (None, {}, {"content_understanding_v1": unconfirmed}):
            market, outcomes = _moneyline(metadata)
            assert not venue_label_refutes_full_contest_winner(market)
            assert admissible_as_blend_speaker(market, is_primary=True, outcomes=outcomes)

    def test_a_future_version_reads_as_absent(self):
        market, outcomes = _completed_match({"content_understanding_v1": {**_CU_COMPLETED, "v": 99}})
        assert not venue_label_refutes_full_contest_winner(market)

    def test_the_novelty_is_refused_as_primary_and_as_fallback(self):
        market, outcomes = _completed_match({"content_understanding_v1": _CU_COMPLETED})
        for is_primary in (True, False):
            assert not admissible_as_blend_speaker(
                market, is_primary=is_primary, outcomes=outcomes
            )

    def test_a_kalshi_primary_is_untouched_whatever_its_metadata(self):
        market = _Market(
            1, "Zhang vs Hunter", source="kalshi", external_id="KXWTAMATCH-26SEP28ZHAHUN-ZHA",
            metadata={"content_understanding_v1": _CU_COMPLETED},
        )
        assert admissible_as_blend_speaker(market, is_primary=True, outcomes=[])


class TestTheMatcherSeesTheLabelToo:
    """The 15-minute matcher hands the blend `_LinkedMarketRef` scalar copies.

    Without the metadata on them the gate abstains on that path, and the
    matcher would re-admit every 15 minutes what the live poll refuses — the
    two writers alternating on the page.
    """

    def test_the_ref_carries_metadata_and_stays_hashable(self):
        ref = pmm._LinkedMarketRef(
            market_id=62862881,
            source="polymarket",
            external_id="0x540d",
            name="China Open, Qualification: Completed Match: Ruien Zhang vs Storm Hunter",
            event_id=15320043,
            event_commence_time=None,
            home_team_name=HOME,
            away_team_name=AWAY,
            market_metadata={"content_understanding_v1": _CU_COMPLETED},
        )
        hash(ref)
        assert not admissible_as_blend_speaker(ref, is_primary=True, outcomes=[])

    def test_every_construction_site_passes_market_metadata(self):
        tree = ast.parse(inspect.getsource(pmm))
        sites = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "_LinkedMarketRef"
        ]
        # Pinned so a new site cannot be added without being read here.
        assert len(sites) == 4
        for node in sites:
            assert "market_metadata" in {k.arg for k in node.keywords}, node.lineno


def test_the_gate_is_the_shared_one_not_a_copy():
    """The live poll, the WS lane and the matcher all reach this through
    `admissible_as_blend_speaker`; the predicate must be imported, not restated."""
    assert (
        live_blend.venue_label_refutes_full_contest_winner
        is venue_label_refutes_full_contest_winner
    )
