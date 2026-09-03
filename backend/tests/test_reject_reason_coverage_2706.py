"""#2706 — a retrieved row is not a candidate, and the top reject reason knew it.

WHAT THIS FILE GUARDS, and why it exists at all.

Receipts (#2705) shipped so that "why is this market unattached" would have an
answer without a person diagnosing it. The first look at production receipts
(``RECEIPTS-FIRST-LOOK-2026-09-02.md``) got an answer and the answer was wrong.

``name_mismatch`` was the #1 reason: **234 of 333** rejected receipts on open
unlinked markets, 70% of the population. It is documented as "candidates came
back, but none passed the team-name gate" — our fuzzy gate being too strict,
i.e. OUR bug, and an actionable one. Some of that population really is a
retrieval coincidence dressed as a gate failure.

THE FIRST ATTEMPT AT THIS FIX MEASURED COVERAGE WITH ``_fuzzy_team_match`` AND
CERT-783 BLOCKED IT. Asking the refusing gate whether the row it refused was the
right game has one possible answer, so **0 of 234** came back covered and the
patch would have relabelled the whole bucket ``no_candidate``. Market 60075060,
"CLE Browns vs JAC Jaguars: 1st Half Spread", carries event 14780144
("Jacksonville Jaguars" vs "Cleveland Browns") INSIDE its candidate window and
in its candidate list — a genuine, fixable name-gate failure that the patch
would have filed as an upstream absence, where nobody would ever look for it.

So coverage is measured by ``match_receipts.row_coverage`` — anchor tokens,
3-character floor, both sides on DIFFERENT team slots, read from the parsed
matchup AND from the market's own name — and never by the predicate under
diagnosis. Re-measured over production's 222 ``name_mismatch`` receipts
(2026-09-03): **109 stay** ``name_mismatch`` and 113 defer to the probe. The
109 are real gate failures with nameable causes, all of them ours:

* the gate cannot match a name of three characters or fewer AT ALL — the
  containment branch needs 4+, the word-subset branch needs 2+ words — so
  "LSU", "SMU", "BYU", "VMI", "USC" never match their own events;
* Kalshi's abbreviated fronts ("CLE Browns", "JAC Jaguars") are 2-word names
  whose first token is not a subset of the event's;
* leading articles ("The Citadel" / "Citadel Bulldogs"), parentheticals
  ("Miami (FL)" / "Miami Hurricanes"), renames ("Houston Christian" / "Houston
  Baptist Huskies").

Those are lane1's to fix under D35 (#2693); this file's job is that the receipt
NAMES them instead of hiding them.

The 113 that defer are the real coincidences. The mechanism is the retrieval
ILIKE, which fires on ONE token:

* "Morehouse Maroon Tigers vs Arkansas-Pine Bluff" retrieved *Detroit Tigers @
  Minnesota Twins* (MLB) and *Hanshin Tigers @ Tokyo Yakult Swallows* (NPB).
* "Merrimack vs Maine" retrieved *Merrimack Warriors @ Delaware* and *Maine
  Black Bears @ Appalachian State* — two different games, one side each.
* "St. Francis (IL) Fighting Saints vs Illinois St." retrieved *St Kilda Saints*
  (AFLW) and *New Orleans Saints* (NFL).

None of those games are in ``events``. Every one was filed as a name-gate
refusal, pointing the next reader at a name normalizer that is working fine.
Meanwhile ``no_candidate`` — documented as "the honest 'upstream has it, we do
not' bucket" — fired **1 time in 333**, because a one-token coincidence always
pre-empted it. The our-bug/upstream-gap distinction CLAUDE.md asks every
matching fix to make was not merely wrong, it was unreachable.

THE FIX IS TO THE REASON, NOT TO THE MATCH. Nothing here changes which market
links to which event; ``test_the_link_decision_is_untouched_by_the_reclassify``
holds that line. What changes is what the receipt SAYS about a refusal.

BOTH ARMS, ALWAYS. Every reclassification test below has a twin asserting the
documented ``name_mismatch`` still fires when both sides really are present and
the gate really did refuse them. A change that reclassified everything to
``no_candidate`` would satisfy half this file and fail the other half — which is
the point, because that change would be the same lie pointing the other way.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as mr
from app.utils.match_receipts import CandidateTrace, MatchReceipt

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)


# =============================================================================
# Doubles. Deliberately the same shapes as test_match_receipts_2705.py so the
# two files cannot drift into describing different matchers.
# =============================================================================


class _Sport:
    def __init__(self, key):
        self.key = key


class _Event:
    def __init__(self, id, home, away, commence, status="scheduled",
                 sport_key="americanfootball_ncaaf", external_id="odds-api-1"):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.status = status
        self.sport = _Sport(sport_key) if sport_key else None
        self.sport_id = 7
        self.external_id = external_id


def _Matchup(team_a, team_b, format_type="bare_matchup"):
    """The REAL MatchupInfo — a stand-in would drift from what the scorer reads."""
    from app.utils.prediction_market_matching import MatchupInfo

    return MatchupInfo(team_a, team_b, yes_team=team_a, format_type=format_type)


class _Market:
    def __init__(self, external_id=None, source="kalshi",
                 llm_sport_category=None, name="Merrimack vs Maine"):
        self.id = 1
        self.source = source
        self.external_id = external_id
        self.name = name
        self.llm_sport_category = llm_sport_category
        self.commence_time = NOW


def _receipt(**kw) -> MatchReceipt:
    base = dict(
        market_id=1, source="kalshi", external_id="kxncaafgame-26sep12-mrmk",
        market_name="Merrimack vs Maine", phase=mr.PHASE_PASS1_TICKER,
        attempted_at=NOW,
    )
    base.update(kw)
    return MatchReceipt(**base)


# =============================================================================
# Part 1 — the production shape. Verbatim rows from the receipts that motivated
# this fix, so the test dies if the real case stops being handled.
# =============================================================================


def test_two_one_sided_coincidences_are_not_a_name_mismatch():
    """The Merrimack–Maine receipt, verbatim from production.

    Two candidates came back. Each carries ONE of the two named sides, and they
    are different games. Filing this as ``name_mismatch`` claims our gate
    refused the right event; there is no right event here to refuse.
    """
    matchup = _Matchup("Merrimack", "Maine")
    candidates = [
        _Event(15181886, "Delaware Blue Hens", "Merrimack Warriors",
               NOW + timedelta(days=1)),
        _Event(15181917, "Appalachian State Mountaineers", "Maine Black Bears",
               NOW + timedelta(days=3)),
    ]
    receipt = _receipt()

    assert pmm._score_candidates(
        candidates, matchup, _Market(), NOW, NOW, receipt=receipt
    ) is None

    # Every candidate was traced, and each is recorded as covering ONE of two.
    assert len(receipt.candidates) == 2
    assert [c.sides_matched for c in receipt.candidates] == [1, 1]
    assert [c.sides_named for c in receipt.candidates] == [2, 2]
    assert not any(c.covers_matchup for c in receipt.candidates)

    # And so the aggregate reason defers to the probe instead of blaming names.
    assert pmm._reason_from_traces(receipt.candidates) is None


def test_a_cross_sport_mascot_collision_is_not_a_name_mismatch():
    """"Morehouse Maroon Tigers vs Arkansas-Pine Bluff" → Detroit Tigers (MLB).

    Retrieved on the single token "Tigers", from a different sport entirely.
    Note this lands BEFORE the sport gate: the market carries no ticker prefix
    and no llm_sport_category, so ``wrong_sport`` cannot catch it and the name
    gate is the only thing standing between this row and a reason.
    """
    matchup = _Matchup("Morehouse Maroon Tigers", "Arkansas-Pine Bluff")
    candidates = [
        _Event(15300441, "Minnesota Twins", "Detroit Tigers", NOW,
               status="live", sport_key="baseball_mlb"),
        _Event(15301084, "Tokyo Yakult Swallows", "Hanshin Tigers",
               NOW + timedelta(hours=13), sport_key="baseball_npb"),
    ]
    receipt = _receipt(market_name="Morehouse Maroon Tigers vs Arkansas-Pine Bluff")

    assert pmm._score_candidates(
        candidates, matchup, _Market(llm_sport_category=None), NOW, NOW,
        receipt=receipt,
    ) is None
    assert all(c.verdict == mr.REJECT_NAME_MISMATCH for c in receipt.candidates)
    assert pmm._reason_from_traces(receipt.candidates) is None


def test_a_candidate_covering_neither_side_is_not_a_name_mismatch():
    """The 21 of 234 that matched on neither side — retrieval noise, nothing more."""
    matchup = _Matchup("Merrimack", "Maine")
    candidates = [_Event(1, "Detroit Lions", "New Orleans Saints", NOW)]
    receipt = _receipt()

    pmm._score_candidates(candidates, matchup, _Market(), NOW, NOW, receipt=receipt)

    assert receipt.candidates[0].sides_matched == 0
    assert pmm._reason_from_traces(receipt.candidates) is None


# =============================================================================
# Part 2 — THE OTHER ARM. The documented name_mismatch must still fire.
# Without these, "reclassify everything" would pass Part 1.
# =============================================================================


def test_both_sides_present_and_refused_is_still_a_name_mismatch():
    """The bucket's documented meaning, and the one case that IS our bug.

    ``match_teams_to_event`` is the gate here: both named sides are carried by
    this single event, so a refusal is a real orientation/name failure and the
    next reader SHOULD be sent to the name logic.
    """
    matchup = _Matchup("Ann Li", "Donna Vekic")
    # One event carrying BOTH sides, refused downstream of the coverage gate.
    candidates = [_Event(1, "Ann Li", "Donna Vekic", NOW, sport_key="tennis_atp")]
    receipt = _receipt()

    pmm._score_candidates(
        candidates, matchup, _Market(llm_sport_category="tennis"), NOW, NOW,
        receipt=receipt,
    )

    trace = receipt.candidates[0]
    assert trace.sides_matched == 2 and trace.sides_named == 2
    assert trace.covers_matchup


def test_one_covering_candidate_among_coincidences_still_reads_as_name_mismatch():
    """Coverage is ANY, not ALL.

    A single genuine candidate that the gate refused is the finding; the noise
    beside it must not bury it. This is the direction that would break if the
    fix had been written as "all candidates must cover".
    """
    traces = [
        CandidateTrace(event_id=1, verdict=mr.REJECT_NAME_MISMATCH,
                       sides_matched=1, sides_named=2),
        CandidateTrace(event_id=2, verdict=mr.REJECT_NAME_MISMATCH,
                       sides_matched=2, sides_named=2),
    ]
    assert pmm._reason_from_traces(traces) == mr.REJECT_NAME_MISMATCH


def test_the_more_specific_reasons_still_outrank_coverage():
    """A candidate that reached the sport gate or a score had full coverage
    already; coverage must not demote those to a probe."""
    assert pmm._reason_from_traces([
        CandidateTrace(event_id=1, verdict=mr.REJECT_NAME_MISMATCH,
                       sides_matched=0, sides_named=2),
        CandidateTrace(event_id=2, verdict=mr.REJECT_WRONG_SPORT,
                       sides_matched=2, sides_named=2),
    ]) == mr.REJECT_WRONG_SPORT

    assert pmm._reason_from_traces([
        CandidateTrace(event_id=1, verdict=mr.REJECT_NAME_MISMATCH,
                       sides_matched=0, sides_named=2),
        CandidateTrace(event_id=2, verdict=mr.REJECT_NAME_SCORE_BELOW,
                       sides_matched=2, sides_named=2),
    ]) == mr.REJECT_NAME_SCORE_BELOW


def test_traces_that_never_measured_coverage_keep_the_old_reason():
    """Backward compatibility is load-bearing, not politeness.

    Receipts already on production were written without coverage. If an
    unmeasured trace silently became ``no_candidate``, the reconciliation job
    would read a reclassification as a drift event on its next cycle.
    """
    traces = [CandidateTrace(event_id=1, verdict=mr.REJECT_NAME_MISMATCH)]
    assert pmm._reason_from_traces(traces) == mr.REJECT_NAME_MISMATCH


# =============================================================================
# Part 3 — the probe. It re-uses the SAME one-token ILIKE, so it inherits the
# same defect: without coverage it moves the lie into `outside_time_window`.
# =============================================================================


class _Row:
    def __init__(self, id, home, away, commence, status="scheduled"):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.status = status


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


async def _probe(rows, matchup, *, window=(NOW - timedelta(hours=6),
                                           NOW + timedelta(hours=6))):
    receipt = _receipt()
    await pmm._record_no_match_reason(
        _FakeSession(rows), receipt, [], NOW, window[0], window[1],
        matchup=matchup, probe_allowed=True,
    )
    return receipt


@pytest.mark.asyncio
async def test_probe_hits_that_cover_nothing_are_an_upstream_gap():
    """Rows came back; not one is this game. That is ``no_candidate``.

    Before coverage, the mere existence of these rows proved "the game IS in
    our table" and the receipt blamed the time window — a matcher bug that does
    not exist, filed against a market whose event we simply do not carry.
    """
    receipt = await _probe(
        [
            _Row(15181886, "Delaware Blue Hens", "Merrimack Warriors",
                 NOW + timedelta(days=1)),
            _Row(15181917, "Appalachian State Mountaineers", "Maine Black Bears",
                 NOW + timedelta(days=3)),
        ],
        _Matchup("Merrimack", "Maine"),
    )

    assert receipt.reject_reason == mr.REJECT_NO_CANDIDATE
    assert receipt.detail["candidate_probe"]["hits"] == 2
    assert receipt.detail["candidate_probe"]["covering_hits"] == 0
    # The rows are still traced — the forensic survives the reclassification.
    assert [c.verdict for c in receipt.candidates] == [mr.REJECT_NO_CANDIDATE] * 2


@pytest.mark.asyncio
async def test_a_covering_probe_hit_outside_the_window_is_still_a_window_bug():
    """The other arm: the game IS ours, the window excluded it. Real matcher bug."""
    receipt = await _probe(
        [_Row(99, "Merrimack Warriors", "Maine Black Bears", NOW + timedelta(days=9))],
        _Matchup("Merrimack", "Maine"),
    )
    assert receipt.reject_reason == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert receipt.detail["candidate_probe"]["covering_hits"] == 1


@pytest.mark.asyncio
async def test_a_covering_probe_hit_inside_the_window_is_still_a_state_bug():
    """And the status arm: inside the searched window ⇒ only status excluded it."""
    receipt = await _probe(
        [_Row(99, "Merrimack Warriors", "Maine Black Bears", NOW,
              status="completed")],
        _Matchup("Merrimack", "Maine"),
    )
    assert receipt.reject_reason == mr.REJECT_STATE_DISAGREES
    assert receipt.detail["candidate_probe"]["covering_hits"] == 1


@pytest.mark.asyncio
async def test_a_covering_hit_is_not_masked_by_coincidences_beside_it():
    """One real hit among noise still decides the reason — ANY, not ALL."""
    receipt = await _probe(
        [
            _Row(1, "Detroit Tigers", "Minnesota Twins", NOW),
            _Row(99, "Merrimack Warriors", "Maine Black Bears",
                 NOW + timedelta(days=9)),
        ],
        _Matchup("Merrimack", "Maine"),
    )
    assert receipt.reject_reason == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert receipt.detail["candidate_probe"]["covering_hits"] == 1


@pytest.mark.asyncio
async def test_an_empty_probe_is_still_an_upstream_gap():
    """The pre-existing zero-row path is untouched."""
    receipt = await _probe([], _Matchup("Merrimack", "Maine"))
    assert receipt.reject_reason == mr.REJECT_NO_CANDIDATE


@pytest.mark.asyncio
async def test_a_single_sided_market_needs_only_its_one_side_covered():
    """``will_win`` names ONE side, so covering one IS full coverage.

    Holding ``sides_named`` per trace rather than assuming 2 is what keeps this
    shape out of the upstream-gap bucket.
    """
    receipt = await _probe(
        [_Row(99, "Merrimack Warriors", "Delaware Blue Hens",
              NOW + timedelta(days=9))],
        _Matchup("Merrimack", None, format_type="will_win"),
    )
    assert receipt.reject_reason == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert receipt.candidates[0].sides_named == 1
    assert receipt.candidates[0].covers_matchup


# =============================================================================
# Part 4 — the line this fix must not cross.
# =============================================================================


def test_the_link_decision_is_untouched_by_the_reclassify():
    """Coverage changes what a refusal is CALLED, never what gets linked.

    Run the real scorer over a candidate set holding one genuine match and two
    one-token coincidences, with and without a receipt attached, and require the
    same event out of both. D35 keeps matching decisions in lane1's hands; this
    ship is a diagnosis fix and has to prove it stayed one.
    """
    matchup = _Matchup("Merrimack", "Maine")
    market = _Market()

    def _candidates():
        return [
            _Event(15181886, "Delaware Blue Hens", "Merrimack Warriors",
                   NOW + timedelta(days=1)),
            _Event(777, "Merrimack Warriors", "Maine Black Bears", NOW),
            _Event(15181917, "Appalachian State Mountaineers", "Maine Black Bears",
                   NOW + timedelta(days=3)),
        ]

    without = pmm._score_candidates(_candidates(), matchup, market, NOW, NOW)
    with_receipt = pmm._score_candidates(
        _candidates(), matchup, market, NOW, NOW, receipt=_receipt()
    )

    assert without == with_receipt
    assert without is not None and without["event_id"] == 777


def test_coverage_is_serialized_so_the_bus_can_group_on_it():
    """A field the export drops is a field the next first-look cannot use."""
    d = CandidateTrace(
        event_id=1, verdict=mr.REJECT_NAME_MISMATCH,
        sides_matched=1, sides_named=2,
    ).to_dict()
    assert d["sides_matched"] == 1
    assert d["sides_named"] == 2


# =============================================================================
# Part 5 — CERT-783. The oracle must not be the predicate under diagnosis.
#
# Every test above is SYMMETRIC: the name gate and any coverage measure agree
# on all of them, so the whole file stayed green while coverage was computed
# from ``_fuzzy_team_match`` — the exact function whose refusal it is supposed
# to second-guess. Only a case where the GATE SAYS NO AND THE ROW IS STILL THE
# GAME can observe the difference. These are those cases, taken verbatim from
# the production rows CERT-783 cited.
# =============================================================================


#: Market 60075060 and its three siblings, and event 14780144. Both real, both
#: read off production 2026-09-03; the event's commence_time (09-13 17:00Z) sits
#: inside the receipt's recorded candidate window (09-12 18:00Z → 09-14 06:00Z),
#: and the receipt's own candidate list holds it.
_BROWNS_MARKET = "CLE Browns vs JAC Jaguars: 1st Half Spread"
_BROWNS_A, _BROWNS_B = "CLE Browns", "JAC Jaguars"
_BROWNS_HOME, _BROWNS_AWAY = "Jacksonville Jaguars", "Cleveland Browns"


def test_the_gate_that_refused_browns_jaguars_really_does_refuse_it():
    """The premise. Without this, the tests below could pass vacuously.

    If ``_fuzzy_team_match`` ever learns these abbreviations, the case stops
    being an asymmetric one and stops guarding anything — and this test says so
    out loud rather than letting the rest of Part 5 quietly go symmetric.
    """
    from app.utils.prediction_market_matching import _fuzzy_team_match

    assert not _fuzzy_team_match(_BROWNS_A, _BROWNS_AWAY)
    assert not _fuzzy_team_match(_BROWNS_B, _BROWNS_HOME)
    # And the reason why: the gate cannot match a name of <=3 characters at all.
    assert not _fuzzy_team_match("LSU", "LSU Tigers")


def test_browns_jaguars_is_a_name_mismatch_end_to_end():
    """The blocked ship, pinned end to end: scorer in, reject reason out.

    CERT-783: "carried event 14780144 is already inside the Browns-Jaguars
    narrow candidate window ... the final reason becomes ``no_candidate``. This
    sends a real name/abbreviation-gate failure to the upstream-absence
    subsystem, so the diagnosis ship is false."
    """
    matchup = _Matchup(_BROWNS_A, _BROWNS_B)
    market = _Market(external_id="KXNFL1HSPREAD-26SEP13CLEJAC", name=_BROWNS_MARKET)
    receipt = _receipt(market_name=_BROWNS_MARKET)
    candidates = [
        _Event(14780144, _BROWNS_HOME, _BROWNS_AWAY, NOW,
               sport_key="americanfootball_nfl"),
        # The other row the ILIKE returned on the "Jaguars" token — one side.
        _Event(15181941, "South Alabama Jaguars", "Southeastern Louisiana Lions",
               NOW, sport_key="americanfootball_ncaaf"),
    ]

    assert pmm._score_candidates(
        candidates, matchup, market, NOW, NOW, receipt=receipt,
    ) is None

    carried = next(t for t in receipt.candidates if t.event_id == 14780144)
    assert carried.sides_matched == 2, "the carried game covers both sides"
    coincidence = next(t for t in receipt.candidates if t.event_id == 15181941)
    assert coincidence.sides_matched == 1, "the NCAAF Jaguars cover one"

    assert pmm._reason_from_traces(receipt.candidates) == mr.REJECT_NAME_MISMATCH


def test_coverage_survives_a_gate_that_refuses_everything():
    """The structural guard, and the one that kills the blocked implementation.

    Coverage is measured with the gate stubbed to refuse every pair — which is
    what the gate DID on this row. An implementation that derives coverage from
    ``_fuzzy_team_match`` scores 0 here and defers to the probe; the shipped one
    is unmoved, because it never asks.
    """
    matchup = _Matchup(_BROWNS_A, _BROWNS_B)
    market = _Market(external_id="KXNFL1HSPREAD-26SEP13CLEJAC", name=_BROWNS_MARKET)
    receipt = _receipt(market_name=_BROWNS_MARKET)

    import app.utils.prediction_market_matching as upmm
    real = upmm._fuzzy_team_match
    pmm._fuzzy_team_match = lambda *a, **k: False
    upmm._fuzzy_team_match = lambda *a, **k: False
    try:
        pmm._score_candidates(
            [_Event(14780144, _BROWNS_HOME, _BROWNS_AWAY, NOW,
                    sport_key="americanfootball_nfl")],
            matchup, market, NOW, NOW, receipt=receipt,
        )
    finally:
        pmm._fuzzy_team_match = real
        upmm._fuzzy_team_match = real

    assert receipt.candidates[0].sides_matched == 2
    assert pmm._reason_from_traces(receipt.candidates) == mr.REJECT_NAME_MISMATCH


def test_a_three_letter_school_covers_its_own_event():
    """The largest single cause among the 109, and invisible to the gate.

    ``_fuzzy_team_match`` skips its containment branch below 4 characters and
    its word-subset branch below 2 words, so "LSU" cannot match "LSU Tigers".
    Nine of the sampled production rows are this exact shape.
    """
    assert mr.row_coverage(
        "Clemson vs LSU", "Clemson", "LSU", "LSU Tigers", "Clemson Tigers",
    ) == (2, 2)
    assert mr.row_coverage(
        "VMI vs Virginia Tech", "VMI", "Virginia Tech",
        "Virginia Tech Hokies", "VMI Keydets",
    ) == (2, 2)


def test_an_invented_matchup_is_still_measured_against_the_market_name():
    """65 of the 222 had a matchup the extractor made up.

    "Denver vs Kansas City" parsed to ``Nuggets``/``Chiefs`` — the NBA teams for
    those cities, on an NFL market. The retrieved row IS the game the name
    describes, so reading coverage only off the parsed sides would file a
    fixable extraction bug as an upstream absence. Filed for lane1 under #2693;
    what this pins is that the receipt does not lie about it.
    """
    assert mr.row_coverage(
        "Denver vs Kansas City", "Nuggets", "Chiefs",
        "Kansas City Chiefs", "Denver Broncos",
    ) == (2, 2)
    # ...but a name that names a DIFFERENT game still does not cover it.
    assert mr.row_coverage(
        "Denver vs Kansas City", "Nuggets", "Chiefs",
        "Detroit Lions", "New Orleans Saints",
    ) == (0, 2)


def test_the_vs_split_wins_over_the_at_split():
    """"University at Albany vs Buffalo" contains both separators.

    Splitting on "at" first yields three parts, the name reading is abandoned,
    and a covering row ("Buffalo Bulls" vs "Albany") reads as a coincidence.
    """
    assert mr.sides_from_market_name("University at Albany vs Buffalo") == (
        "University at Albany", "Buffalo",
    )
    assert mr.sides_from_market_name("Merrimack at Maine") == ("Merrimack", "Maine")
    assert mr.sides_from_market_name("Browns vs. Jaguars - Player Props") == (
        "Browns", "Jaguars - Player Props",
    )
    # A container row with no matchup in its name yields nothing, and coverage
    # falls back to the parsed sides alone.
    assert mr.sides_from_market_name("NFL Championship 2026") == (None, None)


def test_an_apostrophe_is_deleted_not_split_on():
    """Splitting on punctuation manufactures the one-letter token that lane1
    Q503 measured as a wildcard; "Hawai'i" must stay one anchor."""
    assert mr.coverage_anchors("Hawai'i") == {"hawaii"}
    assert mr.row_coverage(
        "UNLV vs Hawai'i", "UNLV", "Hawai'i",
        "Hawaii Rainbow Warriors", "UNLV Rebels",
    ) == (2, 2)


def test_a_short_shared_token_is_not_an_anchor():
    """Below the floor, "St"/"FC"/"LA" would make half the college feed cover
    the other half."""
    assert mr.coverage_anchors("Ohio St.") == {"ohio"}
    assert mr.row_coverage(
        "Ohio St. vs FC Dallas", "Ohio St.", "FC Dallas",
        "Ball State Cardinals", "FC Cincinnati",
    ) == (0, 2)


def test_both_sides_must_land_on_different_teams():
    """The whole distinction, and it needs an asymmetric case to be visible.

    Only a row where BOTH sides touch the SAME slot and NEITHER touches the
    other can tell "each side matched something" from "the two sides matched
    the two teams". Same-city pairs are that shape and are already a known
    hazard here — ``match_teams_to_event`` carries the "New York matching both
    Knicks and Nets" case in its own docstring.
    """
    assert mr.sides_covered(
        "New York Knicks", "New York Nets", "New York Giants", "Dallas Cowboys",
    ) == 1, "both sides anchor on the city, on ONE slot"
    assert mr.row_coverage(
        "New York Knicks vs New York Nets", "New York Knicks", "New York Nets",
        "New York Giants", "Dallas Cowboys",
    ) == (1, 2)
    # The same two sides against the row that really is both of them.
    assert mr.sides_covered(
        "New York Knicks", "New York Nets", "New York Nets", "New York Knicks",
    ) == 2

    assert mr.sides_covered(
        "Morehouse Maroon Tigers", "Arkansas-Pine Bluff",
        "LSU Tigers", "Clemson Tigers",
    ) == 1
    assert mr.sides_covered("Maine", "Merrimack", "Merrimack Warriors", "Delaware") == 1
    assert mr.sides_covered("Maine", "Merrimack", "Merrimack Warriors", "Maine Black Bears") == 2


def test_the_probe_reads_coverage_the_same_way_as_the_candidate_path():
    """Two code paths, one oracle. A probe with its own answer would move the
    lie from ``name_mismatch`` into ``outside_time_window`` instead of ending
    it — and a probe that is STRICTER than the candidate path re-opens
    CERT-783 one function further down."""
    matchup = _Matchup(_BROWNS_A, _BROWNS_B)
    assert pmm._row_coverage(
        _BROWNS_MARKET, matchup, _BROWNS_HOME, _BROWNS_AWAY,
    ) == (2, 2)
    assert pmm._row_coverage(
        _BROWNS_MARKET, matchup, "South Alabama Jaguars",
        "Southeastern Louisiana Lions",
    ) == (1, 2)
