"""#6734, the PARENT half — a settled event stops being re-opened every hour.

`submarket_is_open` fixed the decomposed CHILD rows. The parent row written by
`_process_event_batch` — `external_id=event.id` — kept reading `event.active`
alone, and `_process_event_batch` is fed by a `closed=True` tag sweep as well as
by the open poll. Gamma keeps `active=true` on a CLOSED event, so every hour
that sweep re-stamped settled parents `open`, nulled `settled_at` on the same
statement, and dropped the resolver's `resolution_gate` stamp (written into
`market_metadata`, which this upsert REPLACEs). The children kept their
`api_settlement` grades, because the poll does not touch them.

The result was not a backlog but an oscillation: the settlement sweep resolved
the parent, the next poll re-opened it, and the sweep's outcome UPDATE was a
permanent no-op afterwards (`COALESCE(fo.resolution_source,'') !=
'api_settlement'`). That is why every measurement of the RESOLVER — reach, the
write predicate, the CERT-751 mixed-children guard, the leg arrays, the row
shape — came back clean. None of them were the broken half.

Measured on production 2026-09-18, the specimen and the class:

  * Gamma event 14366 "Next Republican House Conference Chair?" answers
    `active=true, closed=true, archived=false, endDate=2025-06-30`, six legs
    `closed` and terminal. Market 55254705 held `status='open'`,
    `settled_at=NULL`, no `resolution_gate`, and all six outcomes graded
    `is_winner` / `resolution_source='api_settlement'`.
  * 842 Polymarket markets sat `open` with EVERY outcome already graded
    `api_settlement`. Twenty were sampled at random and put to Gamma directly:
    19 answered `closed=true`, and all 19 of those still carried `active=true`.
    The 20th is genuinely open with one settled leg, and the predicate leaves it
    open — the control, not a miss.

Counting note, recorded because the obvious query overstates the class: markets
with ANY graded outcome number 1,257, but 415 of those are live questions with
one leg settled. And `settled_at IS NULL` holds for every `open` row by
construction of the writer, so it is a tautology here rather than a fingerprint.
The fully-graded count is the honest one.

As in the child fix, the fixtures are driven through the REAL parser: the claim
that `closed`/`archived` reach the DTO from a venue-shaped payload is
load-bearing, and a hand-built DTO would pass just as happily if the parser
dropped either field — the one way this fix could silently do nothing.
"""

import re

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly


def _event(*, active: bool, closed: bool, archived: bool = False) -> dict:
    """The specimen's own shape: a settled multi-leg field event."""
    return {
        "id": "14366",
        "title": "Next Republican House Conference Chair?",
        "slug": "next-republican-house-conference-chair",
        "active": active,
        "closed": closed,
        "archived": archived,
        "endDate": "2025-06-30T12:00:00Z",
        "markets": [
            {
                "id": "552547",
                "conditionId": "0x464154fdbd7e25fc",
                "question": "Will Lisa McClain be the next Chair?",
                "slug": "mcclain-chair",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["1", "0"]',
                "clobTokenIds": '["111", "222"]',
                "closed": closed,
            }
        ],
    }


def _parsed(*, active: bool, closed: bool, archived: bool = False):
    svc = PolymarketAPIService()
    event = svc._parse_event(_event(active=active, closed=closed, archived=archived))
    assert event is not None, "the parser refused a venue-shaped payload"
    assert event.markets, "the parser dropped the nested market"
    return event


class TestTheFieldsSurviveTheRealParser:
    """If `closed`/`archived` do not arrive, every other test here is vacuous."""

    def test_the_event_carries_the_venues_closed_flag(self):
        assert _parsed(active=True, closed=True).closed is True

    def test_and_it_is_not_simply_always_true(self):
        assert _parsed(active=True, closed=False).closed is False

    def test_archived_arrives_too(self):
        assert _parsed(active=True, closed=False, archived=True).archived is True

    def test_the_specimens_exact_contradiction_round_trips(self):
        """`active=true` AND `closed=true` on one event — the whole defect."""
        event = _parsed(active=True, closed=True)
        assert (event.active, event.closed) == (True, True)


class TestTheParentPredicate:
    """`sunk_event_is_open` is reused, not restated. These pin what it must say."""

    def test_the_specimen_is_not_open(self):
        """Event 14366: settled fifteen months ago, still flagged active."""
        assert poly.sunk_event_is_open(_parsed(active=True, closed=True)) is False

    def test_an_archived_event_is_not_open(self):
        assert (
            poly.sunk_event_is_open(_parsed(active=True, closed=False, archived=True))
            is False
        )

    def test_a_genuinely_trading_event_is_open(self):
        """Non-vacuity: a predicate that always refused would pass the rest."""
        assert poly.sunk_event_is_open(_parsed(active=True, closed=False)) is True

    def test_it_never_un_resolves_a_row(self):
        """STRICTLY TIGHTENING — the same bound the child fix carries.

        `status` gates `/api/futures/{categories,faceted,grouped-feed,movers}`.
        A predicate that turned `resolved` back into `open` would push settled
        markets onto the feed and into Biggest Movers. `active=false` must stay
        `resolved` whatever the other two flags say, so this fix can only ever
        REMOVE rows from those surfaces.
        """
        for closed in (True, False):
            for archived in (True, False):
                assert (
                    poly.sunk_event_is_open(
                        _parsed(active=False, closed=closed, archived=archived)
                    )
                    is False
                )

    def test_it_is_pure(self):
        event = _parsed(active=True, closed=True)
        before = (event.active, event.closed, event.archived)
        poly.sunk_event_is_open(event)
        assert (event.active, event.closed, event.archived) == before


class TestTheWriterActuallyAsksIt:
    """Source-level, because the alternative is standing up the whole writer.

    Comments are stripped first: a blunt substring test over source text cannot
    tell code from prose, and this fix ships a long explanatory comment that
    names `event.active` — which would otherwise satisfy, or break, these
    assertions for entirely the wrong reason.
    """

    @staticmethod
    def _code() -> str:
        import inspect

        src = inspect.getsource(poly._process_event_batch)
        return "\n".join(line.split("#")[0] for line in src.splitlines())

    def test_the_parent_sites_ask_the_venue_predicate(self):
        code = self._code()
        assert "_venue_open = sunk_event_is_open(event)" in code
        assert len(re.findall(r'"open" if _venue_open else "resolved"', code)) == 2, (
            "the update set and the insert values must agree, or an upsert "
            "disagrees with itself about whether the venue still trades this"
        )

    def test_settled_at_stays_coupled_to_the_same_value(self):
        """LINKLOSS-02: the stamp moves in the SAME statement as the status.

        This is what produced the class's 1257/1257 `settled_at IS NULL`
        signature, so it is also the line that stops producing it.
        """
        assert len(re.findall(r"None if _venue_open", self._code())) == 1

    def test_no_status_site_reads_the_raw_flag_any_more(self):
        """Neither half. A reappearance on either is the defect coming back."""
        code = self._code()
        assert 'if event.active else "resolved"' not in code
        assert "None if event.active" not in code


@pytest.mark.parametrize(
    "active,closed,archived,expected",
    [
        (True, False, False, "open"),
        (True, True, False, "resolved"),  # the specimen
        (True, False, True, "resolved"),
        (True, True, True, "resolved"),
        (False, False, False, "resolved"),
        (False, True, False, "resolved"),
        (False, False, True, "resolved"),
        (False, True, True, "resolved"),
    ],
)
def test_the_whole_truth_table(active, closed, archived, expected):
    """All eight combinations, so the shape is pinned rather than sampled."""
    event = _parsed(active=active, closed=closed, archived=archived)
    status = "open" if poly.sunk_event_is_open(event) else "resolved"
    assert status == expected


def test_exactly_one_combination_is_open():
    """The counting form of the table above.

    A tightening fix's failure mode is tightening too far — refusing everything
    and reading green. Exactly one of the eight inputs may survive as `open`.
    """
    survivors = [
        (a, c, r)
        for a in (True, False)
        for c in (True, False)
        for r in (True, False)
        if poly.sunk_event_is_open(_parsed(active=a, closed=c, archived=r))
    ]
    assert survivors == [(True, False, False)]
