"""UX-P202 / CERT-500 [P1] — the tennis card and the page it links to disagreed.

`/hub/tennis` served "ATP 1000 Montreal: Winner" as **live, ending 13 Sep**. One
click later the event page for that exact key served **upcoming, no end date at
all**. Same tournament, same payload, two answers, and the user is given no way
to tell which one is the lie.

The mechanism is one fact derived twice from one field. UX-P178 taught the RAIL
that a tournament's date belongs to the GROUP — the fullest draw decides identity
but does not always carry the date, so an undated winner borrows from a sibling
rendering. `TennisEventAdapter.build_event` was never taught the same thing and
went on reading `winner.resolution_date` directly, for BOTH the status and the
`end_date`. Wherever the group knew a date its own chosen market did not, the two
layers split.

Measured over the real corpus below, that was **4 of the 10 live tournaments** —
not the single pair the cert reproduced.

WHY THIS TEST EXISTS AND THE OLD ONE DID NOT CATCH IT
-----------------------------------------------------
`TestTheRailAndTheDetailPageAgreeAboutOneTimestamp` in
`test_event_tennis_identity.py` already asserted this agreement, and it was
green throughout. It feeds both layers a `_FakeDB([one_market])`, so
`winner.resolution_date == end_at` holds BY CONSTRUCTION and the conflict it
exists to police can never arise. It is the lane's recurring bug in its eighth
costume: the thing under test is present, but what runs is not it.

So this test does two things that one cannot:

1. It drives both layers over the **real production corpus**, which contains
   three tournaments carrying the conflicting shape.
2. It feeds each layer **its own population**. The rail's SQL is `status='open'`;
   `build_event` also keeps recently-RESOLVED markets (L2-81). Handing both the
   same rows hides the stale `WTA Cincinnati Winner` that only the adapter can
   see — and that row is what makes the past-date rule load-bearing rather than
   defensive padding.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.event_tennis import (
    TennisEventAdapter,
    group_end_at,
    list_tennis_tournament_concepts,
    select_winner_field,
    select_winner_group,
)

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "tennis_group_date_corpus.json"
_DOC = json.loads(_FIXTURE.read_text())
CORPUS = _DOC["markets"]
#: The DATABASE's own clock at capture. Every date in the corpus is relative to
#: it, and the shift below is why this file has no time bomb in it.
MEASURED_AT = datetime.fromisoformat(_DOC["_measured_at"])


def _shifted(now):
    """The corpus with every date moved by `now - MEASURED_AT`.

    Gotcha #44: offset FIRST, and never branch on the clock. The corpus's dates
    are fixed calendar instants — Montreal resolves 2026-09-13 — so asserting
    against them directly would pass until that afternoon and then fail forever,
    because `tennis_status` settles a past date and the rail drops settled
    tournaments entirely. Shifting preserves the only thing this file asserts
    about: which markets know a date, whose date is earlier, and which side of
    `now` each one falls. If an anchor here ever contains an `if`, it is broken.
    """
    delta = now - MEASURED_AT
    out = []
    for r in CORPUS:
        d = r.get("resolution_date")
        out.append(
            {
                **r,
                "resolution_date": (datetime.fromisoformat(d) + delta if d else None),
            }
        )
    return out


def _markets(rows):
    return [
        SimpleNamespace(
            name=r["name"],
            id=r["id"],
            volume_24h=r["volume_24h"],
            status=r["status"],
            llm_sport_category="tennis",
            source="polymarket",
            group_id=None,
            resolution_date=r["resolution_date"],
            outcomes=[
                SimpleNamespace(
                    name=f"Player {i}", current_probability=0.1, is_winner=False
                )
                for i in range(r["real_outcome_count"] or 0)
            ],
        )
        for r in rows
    ]


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    def __init__(self, items):
        self._items = items

    async def execute(self, *a, **k):
        return _Result(self._items)


def _count(m):
    return sum(1 for _ in (m.outcomes or []))


#: Driving ten real `build_event` calls costs ~60s here, almost all of it the
#: population loader retrying a Redis that no unit test has. The result is a pure
#: function of the fixture (the shift is relative, so it is stable across the
#: run), so it is computed once and read by every assertion below.
_PAIRS: list | None = None


async def _rail_and_details():
    """Every rail card, paired with the event page it actually links to.

    ⚠️ The two populations are deliberately different — see the module docstring.
    """
    global _PAIRS
    if _PAIRS is not None:
        return _PAIRS
    now = datetime.now(timezone.utc)
    rows = _shifted(now)
    rail = await list_tennis_tournament_concepts(
        _FakeDB(_markets([r for r in rows if r["status"] == "open"])), limit=50
    )
    pairs = []
    for c in rail:
        slug = c["key"].split(":", 2)[2]
        env = await TennisEventAdapter().build_event(slug, _FakeDB(_markets(rows)))
        pairs.append((slug, c, (env or {}).get("event")))
    _PAIRS = pairs
    return pairs


class TestTheCardAndThePageAgree:
    async def test_the_rail_is_not_silently_empty(self):
        """Guard the guard: an empty rail agrees with everything."""
        pairs = await _rail_and_details()
        assert len(pairs) >= 8, f"only {len(pairs)} concepts — the corpus went stale"

    async def test_every_card_links_to_a_page_that_exists(self):
        unserved = [s for s, _, e in await _rail_and_details() if e is None]
        assert not unserved, f"cards linking to a 404: {unserved}"

    async def test_they_agree_on_the_end_date(self):
        """THE SHIP. The date on the card is the date on the page."""
        disagree = [
            (s, c["end_date"], e["end_date"])
            for s, c, e in await _rail_and_details()
            if c["end_date"] != e["end_date"]
        ]
        assert not disagree, f"card says one date, page says another: {disagree}"

    async def test_they_agree_on_the_status(self):
        """The other half, and the louder one: Montreal's card pulsed LIVE over a
        page that called the same tournament upcoming."""
        disagree = [
            (s, c["status"], e["status"])
            for s, c, e in await _rail_and_details()
            if c["status"] != e["status"]
        ]
        assert not disagree, f"card says one status, page says another: {disagree}"

    async def test_the_agreement_is_not_agreement_about_nothing(self):
        """Two layers both serving `None` agree perfectly and tell the user
        nothing. Most of this corpus knows its dates, and the assertions above
        are worthless unless the values under them are real."""
        pairs = await _rail_and_details()
        dated = [s for s, c, _ in pairs if c["end_date"]]
        assert len(dated) >= 8, f"only {len(dated)} of {len(pairs)} carry a date"


class TestTheBorrowedDateIsWhatIsBeingTested:
    """The agreement above is vacuous unless the corpus actually contains the
    shape that broke it: a tournament whose SELECTED market has no date of its
    own while another rendering of it does. If a future corpus refresh loses that
    shape, these fail loudly instead of passing quietly."""

    async def test_the_corpus_still_contains_the_conflicting_shape(self):
        now = datetime.now(timezone.utc)
        rows = _shifted(now)
        markets = _markets(rows)
        borrowers = []
        for _, c, _e in await _rail_and_details():
            slug = c["key"].split(":", 2)[2]
            winner, group = select_winner_group(markets, slug, _count)
            if winner is None:
                continue
            if winner.resolution_date is None and c["end_date"] is not None:
                borrowers.append(slug)
        assert len(borrowers) >= 3, (
            "the corpus no longer holds an undated winner beside a dated sibling, "
            f"so the agreement above proves nothing: {borrowers}"
        )

    async def test_montreal_is_one_of_them(self):
        """The exact card CERT-500 reproduced: 69 outcomes, no date of its own,
        and a 46-outcome sibling that knows when the tournament ends."""
        now = datetime.now(timezone.utc)
        markets = _markets(_shifted(now))
        winner, group = select_winner_group(markets, "atp-1000-montreal-winner", _count)
        assert winner.name == "ATP 1000 Montreal: Winner"
        assert winner.resolution_date is None, "the premise moved"
        assert {m.name for m in group} == {
            "ATP 1000 Montreal: Winner",
            "ATP Montreal Winner",
        }
        assert group_end_at(winner, group, now) is not None


class TestAnOpenTournamentNeverBorrowsADateThatHasPassed:
    """`WTA Cincinnati Winner` exists twice in the real corpus: open, resolving
    five days from now, and RESOLVED, dated five days ago. Only `build_event`
    sees the resolved one. Borrowing it would print "ended 25 Aug" under a live
    78-player draw and flip the page to `live` while the card said `upcoming`
    — measured: removing this rule alone reintroduces exactly one disagreement.
    """

    async def test_the_stale_sibling_is_present_and_only_the_adapter_sees_it(self):
        stale = [
            r
            for r in CORPUS
            if r["name"] == "WTA Cincinnati Winner" and r["status"] != "open"
        ]
        assert len(stale) == 1, "the stale rendering left the corpus"
        assert datetime.fromisoformat(stale[0]["resolution_date"]) < MEASURED_AT

    async def test_the_open_winner_does_not_borrow_it(self):
        now = datetime.now(timezone.utc)
        markets = _markets(_shifted(now))
        winner, group = select_winner_group(markets, "wta-cincinnati-winner", _count)
        assert (winner.status or "").lower() == "open"
        assert winner.resolution_date is None
        past = [m for m in group if m.resolution_date and m.resolution_date < now]
        assert past, "the stale sibling is not in the group — premise moved"
        end_at = group_end_at(winner, group, now)
        assert (
            end_at is not None and end_at > now
        ), f"an open tournament borrowed a date that has already passed: {end_at}"

    def test_a_settled_winner_still_reports_the_date_it_ended(self):
        """The rule is scoped, not blanket. A concluded tournament's date is IN
        the past and that is the whole point of it — 'settled means settled'."""
        now = datetime.now(timezone.utc)
        ended = now - timedelta(days=3)
        winner = SimpleNamespace(
            name="X Winner", status="resolved", resolution_date=None
        )
        sibling = SimpleNamespace(
            name="X Winner", status="resolved", resolution_date=ended
        )
        assert group_end_at(winner, [winner, sibling], now) == ended


class TestTheSharedRuleIsActuallyShared:
    def test_the_winners_own_date_beats_a_siblings(self):
        now = datetime.now(timezone.utc)
        mine = now + timedelta(days=9)
        theirs = now + timedelta(days=2)
        winner = SimpleNamespace(name="A", status="open", resolution_date=mine)
        sibling = SimpleNamespace(name="A", status="open", resolution_date=theirs)
        assert group_end_at(winner, [winner, sibling], now) == mine

    def test_the_earliest_future_sibling_wins_when_the_winner_has_none(self):
        now = datetime.now(timezone.utc)
        near, far = now + timedelta(days=2), now + timedelta(days=9)
        winner = SimpleNamespace(name="A", status="open", resolution_date=None)
        a = SimpleNamespace(name="A", status="open", resolution_date=far)
        b = SimpleNamespace(name="A", status="open", resolution_date=near)
        assert group_end_at(winner, [winner, a, b], now) == near

    def test_no_date_anywhere_stays_absent(self):
        """A date we do not have is absent, never guessed."""
        now = datetime.now(timezone.utc)
        winner = SimpleNamespace(name="A", status="open", resolution_date=None)
        assert group_end_at(winner, [winner], now) is None

    def test_select_winner_field_still_returns_just_the_winner(self):
        """The split must not change the long-standing signature — every other
        caller and every #1793 identity test still reads a bare market back."""
        now = datetime.now(timezone.utc)
        markets = _markets(_shifted(now))
        bare = select_winner_field(markets, "atp-1000-montreal-winner", _count)
        winner, _group = select_winner_group(
            markets, "atp-1000-montreal-winner", _count
        )
        assert bare is winner

    def test_an_unknown_slug_is_still_a_refusal_in_both_shapes(self):
        """#1793: a slug that names no tournament we hold must 404, never
        resolve to a neighbour."""
        now = datetime.now(timezone.utc)
        markets = _markets(_shifted(now))
        assert select_winner_field(markets, "not-a-tournament-at-all", _count) is None
        assert select_winner_group(markets, "not-a-tournament-at-all", _count) == (
            None,
            [],
        )
