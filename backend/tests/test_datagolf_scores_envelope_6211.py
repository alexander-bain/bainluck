"""#6211 / CERT-2930 — a 200 we cannot parse may never become an absent tournament.

WHAT THE CERT FOUND
-------------------
#6211's own fix narrowed ``get_historical_results`` so that only an evidenced
absence returns ``[]`` and everything else raises. It left the *parser* alone,
and the parser was the same defect one layer down::

    raw_rows = data if isinstance(data, list) else data.get("data", data.get("rounds", []))

The live endpoint answers under neither key. Measured against the production
provider key on 2026-09-15 (``tour=pga&event_id=100&year=2023``): HTTP 200,
208,858 bytes, **156 player rows under a top-level ``scores``** key. So a real,
completed, fully-populated tournament parsed to zero rows, and the caller reads
zero rows as "DataGolf's historical index has no such event" and writes the
permanent ``datagolf_recovery_residual`` flag that removes the market from the
published curve. The 36 winner-only rows would have stayed exactly where they
were, with the fix reporting success.

The envelope in ``tests/fixtures/datagolf_historical_rounds_pga_100_2023.json``
is that live response, verbatim, with ``scores`` trimmed to three real players
(the winner, a tied finisher, a missed cut) and nothing else edited.

TWO SHAPES, AND WHY THE SHAPE DECIDES
-------------------------------------
``scores`` is one row per PLAYER with the rounds nested inside it. The shape the
old aggregation was written for is one row per player-ROUND. Feeding the second
algorithm the first data returns a plausible, wrong leaderboard rather than an
error, so the choice is made on the rows themselves, never on which key they
arrived under.

ALSO MEASURED, SAME SESSION: the provider signals a genuinely absent event with
**HTTP 400 and a prose body**, not a 404 and not an empty 200::

    event_id=999999 -> 400 "event number 999999 is not available in the 2023 pga
                       calendar year, please input a valid event number."
    year=1899       -> 400 "we don't have any historical raw data for 1899 -
                       please choose from the following: 1983, 1984, ..."

Only the first is evidence about the event; the second is our own request being
out of range, as is a 400 from a bad tour code (#994). Without the first, the
terminal-absence channel is unreachable in production and every genuinely absent
event burns its whole retry budget instead — so these tests pin both directions.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.services.datagolf_api import (
    DataGolfUnknownEnvelope,
    DataGolfAPIService,
    _is_evidenced_absent_400,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "datagolf_historical_rounds_pga_100_2023.json"
)


def _live_envelope() -> dict:
    envelope = json.loads(FIXTURE.read_text())
    envelope.pop("_capture", None)  # capture provenance, not part of the shape
    return envelope


def _error(status: int, body: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://feeds.datagolf.com/x")
    response = httpx.Response(status, request=request, text=body)
    return httpx.HTTPStatusError(body or str(status), request=request, response=response)


@pytest.fixture
def service(monkeypatch):
    svc = DataGolfAPIService()
    monkeypatch.setattr(svc, "api_key", "test-key", raising=False)
    return svc


def _answer(service, monkeypatch, payload):
    async def _get(endpoint, params=None):
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(service, "_get", _get)


class TestTheLiveScoresEnvelopeIsRead:
    """The specimen the cert blocked on, driven through the real call path."""

    async def test_the_live_envelope_yields_its_players_not_an_absence(
        self, service, monkeypatch
    ):
        _answer(service, monkeypatch, _live_envelope())
        results = await service.get_historical_results(
            tour="pga", event_id="100", year=2023
        )

        assert results, (
            "the live 200 parsed to zero rows — the caller reads that as an "
            "evidenced absence and permanently withholds the market"
        )
        assert len(results) == len(_live_envelope()["scores"])

    async def test_every_player_carries_the_dg_id_the_recovery_path_matches_on(
        self, service, monkeypatch
    ):
        """``_recover_datagolf_participation`` re-grades on ``dg_id`` alone.

        A parse that returned rows but dropped the ids would clear the
        withholding while recovering no losers at all.
        """
        _answer(service, monkeypatch, _live_envelope())
        results = await service.get_historical_results(tour="pga", event_id="100")

        assert {8825, 9771, 22085} == {p["dg_id"] for p in results}

    async def test_position_and_to_par_come_from_the_nested_rounds(
        self, service, monkeypatch
    ):
        """Brian Harman won The Open 2023 at -13 over four rounds.

        `scores` carries no total, so the figure is summed over the rounds the
        player completed. The missed cut has two rounds and must not be scored
        as though it had four.
        """
        _answer(service, monkeypatch, _live_envelope())
        by_id = {p["dg_id"]: p for p in await service.get_historical_results(
            tour="pga", event_id="100"
        )}

        assert by_id[8825]["position"] == "1"
        assert by_id[8825]["total_score"] == -13
        assert by_id[8825]["name"] == "Brian Harman"  # normalised off "Harman, Brian"

        assert by_id[9771]["position"] == "T2"
        assert by_id[9771]["total_score"] == -7

        assert by_id[22085]["position"] == "CUT"
        assert by_id[22085]["total_score"] == 4

    async def test_the_flat_per_round_shape_still_aggregates_to_the_last_round(
        self, service, monkeypatch
    ):
        """The other shape is not regressed: one row per player-ROUND, latest kept."""
        _answer(service, monkeypatch, {"data": [
            {"dg_id": 1, "player_name": "Alpha, Ann", "round_num": 1,
             "fin_text": "T40", "total_to_par": 2},
            {"dg_id": 1, "player_name": "Alpha, Ann", "round_num": 4,
             "fin_text": "T9", "total_to_par": -3},
        ]})
        results = await service.get_historical_results(tour="pga", event_id="1")

        assert len(results) == 1
        assert results[0]["position"] == "T9"
        assert results[0]["total_score"] == -3


class TestAnUnreadableTwoHundredIsNeverAnAbsence:
    """The fail-closed half. ``[]`` is a truth claim; only the provider may make it."""

    async def test_an_unknown_envelope_with_content_RAISES(self, service, monkeypatch):
        """The exact regression: rows present, under a key we do not know."""
        _answer(service, monkeypatch, {
            "event_name": "The Open Championship",
            "leaderboard": [{"dg_id": 8825, "fin_text": "1"}],
        })
        with pytest.raises(DataGolfUnknownEnvelope):
            await service.get_historical_results(tour="pga", event_id="100")

    async def test_a_dict_with_no_row_list_at_all_RAISES(self, service, monkeypatch):
        _answer(service, monkeypatch, {"message": "temporarily unavailable"})
        with pytest.raises(DataGolfUnknownEnvelope):
            await service.get_historical_results(tour="pga", event_id="100")

    async def test_a_scalar_body_RAISES(self, service, monkeypatch):
        _answer(service, monkeypatch, "service unavailable")
        with pytest.raises(DataGolfUnknownEnvelope):
            await service.get_historical_results(tour="pga", event_id="100")

    @pytest.mark.parametrize("key", ["scores", "data", "rounds"])
    async def test_a_recognised_key_holding_an_empty_list_IS_an_absence(
        self, service, monkeypatch, key
    ):
        """The provider's own empty row list is the only 200 we read as absence."""
        _answer(service, monkeypatch, {"event_id": 100, key: []})
        assert await service.get_historical_results(tour="pga", event_id="100") == []

    async def test_the_unknown_envelope_error_names_what_it_saw(
        self, service, monkeypatch
    ):
        """A retryable flag records `last_error`; an opaque one cannot be triaged."""
        _answer(service, monkeypatch, {"leaderboard": [], "event_name": "x"})
        with pytest.raises(DataGolfUnknownEnvelope) as caught:
            await service.get_historical_results(tour="pga", event_id="100")

        assert "leaderboard" in str(caught.value)


class TestTheFourHundredAbsenceChannel:
    """DataGolf says "no such event" with a 400 and a sentence, not a 404."""

    ABSENT = (
        "event number 999999 is not available in the 2023 pga calendar year, "
        "please input a valid event number."
    )
    OUT_OF_RANGE = (
        "we don't have any historical raw data for 1899 - please choose from "
        "the following: 1983, 1984, 1985"
    )

    async def test_the_event_number_400_is_an_evidenced_absence(
        self, service, monkeypatch
    ):
        _answer(service, monkeypatch, _error(400, self.ABSENT))
        assert await service.get_historical_results(
            tour="pga", event_id="999999", year=2023
        ) == []

    async def test_the_year_out_of_range_400_RAISES(self, service, monkeypatch):
        """That sentence is about our request, not about whether the event exists."""
        _answer(service, monkeypatch, _error(400, self.OUT_OF_RANGE))
        with pytest.raises(httpx.HTTPStatusError):
            await service.get_historical_results(tour="pga", event_id="100", year=1899)

    async def test_a_bare_400_RAISES(self, service, monkeypatch):
        """#994's bad-tour 400 stays retryable — it makes no claim about the event."""
        _answer(service, monkeypatch, _error(400, "bad request"))
        with pytest.raises(httpx.HTTPStatusError):
            await service.get_historical_results(tour="alt", event_id="100")

    def test_the_marker_predicate_is_not_a_blanket_400_match(self):
        assert _is_evidenced_absent_400(self.ABSENT) is True
        assert _is_evidenced_absent_400(self.OUT_OF_RANGE) is False
        assert _is_evidenced_absent_400("") is False
        assert _is_evidenced_absent_400("forbidden") is False


class TestTheFixtureIsTheLiveShape:
    """A fixture that has drifted from the venue guards nothing (notice 26)."""

    def test_the_capture_records_its_provenance(self):
        capture = json.loads(FIXTURE.read_text())["_capture"]

        assert capture["http_status"] == 200
        assert capture["rows_in_live_response"] == 156
        assert capture["params"]["event_id"] == "100"

    def test_the_fixture_carries_the_top_level_key_the_parser_missed(self):
        envelope = _live_envelope()

        assert "scores" in envelope
        assert "data" not in envelope and "rounds" not in envelope, (
            "if the live envelope ever grows a `data`/`rounds` key this test is "
            "the one that should notice, because the parser prefers `scores`"
        )

    def test_the_fixture_holds_no_credential(self):
        raw = FIXTURE.read_text().lower()

        assert "key=" not in raw and "api_key" not in raw
