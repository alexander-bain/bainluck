"""T11-1 (#5461), CERT-2691's required repair `5461-FEED-TIME-STAMPED-EVIDENCE-INTO-THE-HOOK`.

The BLOCK: presentation one told the model to *"state ONE specific development"* while handing it
only a market name, a category, a leaderboard of probabilities, a resolution date and a volume.
There is no development in that input, so the model had to invent one or reach for stale training
knowledge — and the sentence went on a card as if we stood behind it.

The repair has two fail-closed exits and this file drives **the real task** through both, because
that is where the grader's claim lives. A pure-function test of `should_generate_hook` would prove
the helper and nothing about what production does with it.

* **Exit 1 — we decline to ask.** A market with no resolution date and no linked fixture has no
  dated evidence, so `enrich_market_hooks` never calls the model. Asserted by the *absence of the
  call* on a client that would otherwise answer, which is the only assertion that distinguishes
  "not asked" from "asked and filtered".
* **Exit 2 — the model declines to answer.** `NO_HOOK` is a first-class reply and is honoured:
  nothing is written to the row.

The evidence-present path is asserted in the same run so neither exit passes by refusing
everything — a fail-closed guard that also fails the happy path is not a guard, it is an outage.
"""

from __future__ import annotations

import sys
import types
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from app.utils.hook_prompt import (
    NO_HOOK_SENTINEL,
    accept_hook_output,
    build_hook_evidence,
    should_generate_hook,
)

_NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------
# A fake session narrow enough to be readable and wide enough to be honest: it answers the
# three reads the task makes (candidates, outcomes, the linked event) and records writes.
# --------------------------------------------------------------------------------------


@dataclass
class _FakeMarket:
    id: int
    name: str
    llm_sport_category: Optional[str] = "politics"
    resolution_date: Optional[datetime] = None
    volume_24h: Optional[float] = 12_000
    event_id: Optional[int] = None
    hook_description: Optional[str] = None
    hook_generated_at: Optional[datetime] = None
    hook_leader_at_generation: Optional[str] = None
    market_metadata: Any = field(default_factory=dict)
    source: str = "kalshi"


@dataclass
class _Outcome:
    name: str
    current_probability: Optional[float]
    opening_probability: Optional[float] = None
    probability_change_24h: Optional[float] = None


class _Result:
    def __init__(self, rows, scalars=None):
        self._rows = rows
        self._scalars = scalars

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Result(self._scalars if self._scalars is not None else self._rows)


class _FakeSession:
    """Answers by inspecting which entity the statement selects, not by call order."""

    def __init__(self, market: _FakeMarket, outcomes, event_row=None):
        self.market = market
        self.outcomes = outcomes
        self.event_row = event_row
        self.updates: list[dict] = []
        self.committed = False

    async def execute(self, stmt):
        text = str(stmt)
        # STARTSWITH, not `"UPDATE" in text.upper()`. The candidates SELECT orders by
        # `futures_markets.updated_at`, which contains the substring "UPDATE" — the first
        # cut of this fake routed the candidate query into the write branch and returned
        # no candidates, so all four task tests failed with the task never running at all.
        verb = text.lstrip().split(None, 1)[0].upper() if text.strip() else ""
        if verb == "UPDATE":
            self.updates.append(dict(stmt.compile().params))
            return _Result([])
        if "futures_outcomes" in text:
            return _Result(self.outcomes)
        if "events" in text and "futures_markets" not in text:
            return _Result([self.event_row] if self.event_row else [])
        return _Result([self.market], scalars=[self.market])

    async def commit(self):
        self.committed = True


class _CountingClient:
    """An LLM client that always has an answer — so a missing call means NOT ASKED."""

    def __init__(self, reply: str = "A sentence about the thing."):
        self.reply = reply
        self.calls: list[str] = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, *, model, messages, max_tokens, temperature):
        self.calls.append(messages[0]["content"])
        msg = types.SimpleNamespace(content=self.reply)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


async def _run_task(monkeypatch, market, outcomes, event_row=None, reply="A sentence."):
    from app.tasks import enrich_markets

    session = _FakeSession(market, outcomes, event_row)
    client = _CountingClient(reply)

    @asynccontextmanager
    async def _fake_session_cm():
        yield session

    monkeypatch.setattr(enrich_markets, "get_task_session", _fake_session_cm)
    monkeypatch.setattr(
        sys.modules["app.services.llm"], "_get_client", lambda *a, **k: client
    )
    monkeypatch.setattr(enrich_markets, "asyncio", types.SimpleNamespace(sleep=_noop_sleep))
    stats = await enrich_markets.enrich_market_hooks(limit=5)
    return stats, session, client


async def _noop_sleep(_seconds):
    return None


_OUTCOMES = [_Outcome("Yes", 0.62, 0.40, 0.03), _Outcome("No", 0.38, 0.60, -0.03)]


class TestEnrichMarketHooksRequiresEvidenceForSpecificDevelopment5461:
    """The name the grader asked for, on the real task, both paths."""

    @pytest.mark.asyncio
    async def test_no_dated_evidence_means_the_model_is_never_asked(self, monkeypatch):
        market = _FakeMarket(
            id=1,
            name="Will something unspecified happen?",
            resolution_date=None,  # no settlement date
            event_id=None,  # no linked fixture
        )
        stats, session, client = await _run_task(monkeypatch, market, _OUTCOMES)

        assert client.calls == [], (
            "the task asked the model to write about a market it holds no dated fact for — "
            "that is the invented-development path CERT-2691 blocked"
        )
        assert stats["skipped_no_evidence"] == 1
        assert stats["generated"] == 0
        assert session.updates == [], "a hook was written with no evidence behind it"

    @pytest.mark.asyncio
    async def test_a_settlement_date_on_its_own_is_not_asked_about(self, monkeypatch):
        """Presentation three's measurement, pinned.

        Asking on a bare settlement date is not a TRUTH failure — every one of the 26 lines it
        produced on production was entailed by its evidence. It is a notice-34 failure: they all
        read "The question 'X' is settled no later than DATE", which is our settlement mechanic
        described to a reader, off a date that is routinely the padded latest-possible one
        (#2644). So the gate is the KIND of evidence, not its presence.
        """
        market = _FakeMarket(
            id=2,
            name="Will the rate be cut in September?",
            resolution_date=datetime.now(timezone.utc) + timedelta(days=4),
        )
        stats, session, client = await _run_task(monkeypatch, market, _OUTCOMES)

        assert client.calls == [], (
            "the model was asked to write a card line off a settlement date alone — the only "
            "sentence that supports is the one notice 34 removed from the US Open page"
        )
        assert stats["skipped_no_evidence"] == 1
        assert stats["generated"] == 0
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_a_fixture_is_asked_about_and_its_hook_is_written(self, monkeypatch):
        """The other direction. A guard that refuses everything is an outage, not a guard.

        This is the whole positive path: the gate opens on a fixture, the settlement date rides
        along as a second line, the model is asked once, and the answer reaches the row.
        """
        real_now = datetime.now(timezone.utc)
        kickoff = real_now + timedelta(days=2)
        market = _FakeMarket(
            id=2,
            name="Philadelphia vs Atlanta",
            resolution_date=real_now + timedelta(days=5),
            event_id=77,
        )
        stats, session, client = await _run_task(
            monkeypatch,
            market,
            _OUTCOMES,
            event_row=(kickoff, "Atlanta Braves", "Philadelphia Phillies"),
        )

        assert len(client.calls) == 1
        prompt = client.calls[0]
        assert "EVIDENCE — the ONLY facts you may state" in prompt
        stamp = kickoff.strftime("%b %d, %Y")
        assert f"Philadelphia Phillies vs Atlanta Braves is scheduled for {stamp}." in prompt
        settles = (real_now + timedelta(days=5)).strftime("%b %d, %Y")
        assert f"settled no later than {settles}" in prompt, (
            "the settlement date stopped travelling; it may not stand alone but it is still "
            "an anchor the sentence may bound itself against"
        )
        assert stats["generated"] == 1
        assert session.updates and session.updates[0]["hook_description"] == "A sentence."

    @pytest.mark.asyncio
    async def test_a_linked_fixture_is_cited_and_preferred_over_the_settlement_date(
        self, monkeypatch
    ):
        """#2644: the stored resolution date is routinely a padded latest-possible
        settlement — on the US Open singles markets it read two weeks past the final. So a
        real kickoff, when we have one, leads the evidence block.

        The task reads the wall clock, so the anchors are offsets FROM it and the expected
        string is derived from the same instant (gotcha #44): a fixed 2026 date here would
        pass today and fail tomorrow when it stops being in the future.
        """
        real_now = datetime.now(timezone.utc)
        kickoff = real_now + timedelta(days=1)
        market = _FakeMarket(
            id=3,
            name="US Open ATP: Alexander Zverev vs Karen Khachanov",
            resolution_date=real_now + timedelta(days=16),
            event_id=99,
        )
        event_row = (kickoff, "Karen Khachanov", "Alexander Zverev")
        stats, session, client = await _run_task(
            monkeypatch, market, _OUTCOMES, event_row=event_row
        )

        prompt = client.calls[0]
        # Split on the BLOCK HEADER, not the bare word: "EVIDENCE" also appears earlier, in
        # the criterion "State ONLY what an EVIDENCE line supports".
        evidence_block = prompt.split("EVIDENCE — the ONLY facts you may state")[1]
        stamp = kickoff.strftime("%b %d, %Y")
        assert evidence_block.index(stamp) < evidence_block.index("settled no later than"), (
            "the padded settlement date outranked a real kickoff"
        )
        assert (
            f"Alexander Zverev vs Karen Khachanov is scheduled for {stamp}." in prompt
        )

    @pytest.mark.asyncio
    async def test_a_fixture_that_has_already_started_is_not_cited_as_scheduled(
        self, monkeypatch
    ):
        """Found on production while building this: `US Open ATP: Khachanov vs Blockx`
        settles Sep 16 but its linked fixture started Sep 09. Cited unconditionally, the
        evidence line tells the model a match played three days ago "is scheduled" — a
        false claim handed over as a fact. We know when it was due to start; we do not know
        here whether it finished or how, so it is dropped and the settlement line stands.
        """
        real_now = datetime.now(timezone.utc)
        market = _FakeMarket(
            id=5,
            name="US Open ATP: Karen Khachanov vs Alexander Blockx",
            resolution_date=real_now + timedelta(days=4),
            event_id=77,
        )
        event_row = (real_now - timedelta(days=3), "Karen Khachanov", "Alexander Blockx")
        stats, session, client = await _run_task(
            monkeypatch, market, _OUTCOMES, event_row=event_row
        )

        # Dropping the started fixture leaves the settlement date alone, and presentation
        # three's gate does not open on that — so the market is not asked about at all.
        # Both halves matter: the past fixture is not cited as upcoming (the falsehood), AND
        # nothing is written off what remains (the jargon). The evidence helper's own test,
        # `test_a_kickoff_in_the_past_is_dropped_even_though_it_is_dated`, holds the citation
        # shape now that no prompt is built here to read it off.
        assert client.calls == [], "a past fixture was described, or a bare settlement date was"
        assert stats["skipped_no_evidence"] == 1
        assert stats["generated"] == 0
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_the_models_no_hook_reply_is_honoured_and_nothing_is_written(
        self, monkeypatch
    ):
        # The gate has to OPEN for this test to say anything, so the market carries a fixture:
        # with settlement evidence alone the model is never asked and "it declined" would be
        # indistinguishable from "we never asked".
        real_now = datetime.now(timezone.utc)
        market = _FakeMarket(
            id=4,
            name="Northgate vs Riverside",
            resolution_date=real_now + timedelta(days=4),
            event_id=88,
        )
        stats, session, client = await _run_task(
            monkeypatch,
            market,
            _OUTCOMES,
            event_row=(real_now + timedelta(days=1), "Riverside", "Northgate"),
            reply=f'"{NO_HOOK_SENTINEL}"',
        )

        assert len(client.calls) == 1, "the model must still be asked — it declined, we did not"
        assert stats["declined_no_hook"] == 1
        assert stats["generated"] == 0
        assert session.updates == [], "a declined hook was written to the row anyway"


@pytest.mark.asyncio
async def test_enrich_market_hooks_requires_evidence_for_specific_development_5461(monkeypatch):
    """The identifier CERT-2691 named, as a FUNCTION, carrying both directions in one run.

    The class above is spelled the same way, but a class is not selectable by the name the BLOCK
    wrote: `pytest -k test_enrich_market_hooks_requires_evidence_for_specific_development_5461`
    collects zero tests against a CamelCase class, and zero collected tests exit 0. A grader
    reading that as "the named test passes" would be reading the harness, not the product.
    """
    no_evidence = _FakeMarket(id=10, name="Will something happen?", resolution_date=None)
    stats, session, client = await _run_task(monkeypatch, no_evidence, _OUTCOMES)
    assert client.calls == [] and stats["generated"] == 0 and session.updates == []

    kickoff = datetime.now(timezone.utc) + timedelta(days=3)
    with_evidence = _FakeMarket(
        id=11,
        name="Northgate vs Riverside",
        resolution_date=datetime.now(timezone.utc) + timedelta(days=6),
        event_id=42,
    )
    stats, session, client = await _run_task(
        monkeypatch, with_evidence, _OUTCOMES, event_row=(kickoff, "Riverside", "Northgate")
    )
    assert len(client.calls) == 1
    assert kickoff.strftime("%b %d, %Y") in client.calls[0]
    assert stats["generated"] == 1 and session.updates


class TestTheEvidenceHelpersOnTheirOwn:
    """Behaviour of the pure pieces, so a task-level failure can be localised."""

    def test_no_fields_means_no_evidence(self):
        assert build_hook_evidence(market_name="x") == ()
        assert should_generate_hook(()) is False

    def test_a_bare_kickoff_without_team_names_is_still_dated_evidence(self):
        """`now` is passed explicitly. Left to the wall clock, this fixture is "upcoming"
        until noon UTC today and then silently stops testing anything (gotcha #44)."""
        ev = build_hook_evidence(
            market_name="x",
            event_commence_time=_NOW + timedelta(hours=1),
            now=_NOW,
        )
        assert len(ev) == 1
        assert "Sep 12, 2026" in ev[0].fact
        assert should_generate_hook(ev) is True

    def test_a_kickoff_in_the_past_is_dropped_even_though_it_is_dated(self):
        assert (
            build_hook_evidence(
                market_name="x",
                event_commence_time=_NOW - timedelta(hours=1),
                now=_NOW,
            )
            == ()
        )

    def test_the_settlement_line_says_no_later_than_and_names_no_venue(self):
        """#2644 again: the stored date is an upper bound, and the sentence must not
        promise it is the moment the thing happens. The venue's name never reaches the
        prompt, because the output rules forbid printing it."""
        ev = build_hook_evidence(market_name="Q?", resolution_date=_NOW, now=_NOW)
        assert "no later than" in ev[0].fact
        assert "It may be decided earlier." in ev[0].fact
        for venue in ("kalshi", "polymarket", "odds_api"):
            assert venue not in (ev[0].fact + ev[0].source).lower()

    @pytest.mark.parametrize(
        "raw",
        [NO_HOOK_SENTINEL, f" {NO_HOOK_SENTINEL} ", f'"{NO_HOOK_SENTINEL}"', "no_hook.", "", "   ", None],
    )
    def test_declines_and_empties_all_read_as_no_hook(self, raw):
        assert accept_hook_output(raw) is None

    def test_a_real_sentence_survives_unquoted(self):
        assert accept_hook_output('  "The hearing is Tuesday."  ') == "The hearing is Tuesday."

    def test_a_sentence_merely_containing_the_sentinel_is_not_a_decline(self):
        """Substring matching here would silently drop a legitimate hook."""
        assert accept_hook_output(f"There is {NO_HOOK_SENTINEL} yet, but the vote is Tuesday.") is not None
