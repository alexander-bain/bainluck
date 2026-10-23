"""#698 — a settled Polymarket row whose stored price never reached 0 or 1 is
served as "result unknown", not as a loss.

WHAT A READER SAW
-----------------

``/futures/62134744`` (*Marchi vs. Lokoli: Match O/U 21.5*, resolved) stores
both legs as ``0.500000 / is_winner false / clob_authoritative``. The detail
payload carried those three values faithfully, and every client turned them
into two rows reading **Lost · 0% · Settled** — a result nobody stored and a
0% the row never held. Whether the venue voided that match is UNKNOWN (the one
venue read stopped on a 403 and was not retried), so the honest render is
"Result unknown · Last recorded 50%", and the server is the only place that
can say so for every client at once.

This file pins the additive ``settlement_display`` contract: the rules on
labelled synthetic rows, and the serializer on the four exact specimens built
from their STORED rows (``tests/fixtures/settled_display_698.json``, taken
verbatim from the read-only specimen receipt and the banked served responses).
Every route test also asserts the served values the reader already received —
id, name, probability, grade, source, opening — are byte-equivalent to the
banked response: the contract is additive and changes nothing else.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from app.utils import settlement_display as sd
from app.utils.resolution_authority import KNOWN_SOURCES

FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "settled_display_698.json").read_text()
)
SPECIMENS = FIXTURE["specimens"]

#: The served keys a reader already receives; each must equal the banked value.
BANKED_KEYS = (
    "id",
    "name",
    "probability",
    "is_winner",
    "resolution_source",
    "opening_probability",
)


def _verdict(**kw):
    return sd.settlement_display(**kw)


# ── the rules, on labelled SYNTHETIC rows ───────────────────────────────────


class TestTheRulesOnSyntheticRows:
    """Synthetic by construction: no row here is a production specimen."""

    @pytest.mark.parametrize("winner", [False, True])
    @pytest.mark.parametrize(
        "price", [Decimal("0.5"), Decimal("0.001"), Decimal("0.999"), 0.05, 0.95]
    )
    def test_a_midrange_stored_price_is_never_a_result(self, price, winner):
        """Midrange — including near-terminal .001/.999 and a midrange TRUE — is
        unknown regardless of an authoritative-looking source. No threshold."""
        got = _verdict(
            is_winner=winner,
            resolution_source="clob_authoritative",
            stored_probability=price,
        )
        assert got == {"verdict": "unknown", "basis": "nonterminal_stored_price"}

    def test_terminal_agreement_is_a_result_and_says_what_it_rests_on(self):
        won = _verdict(
            is_winner=True, resolution_source="api_settlement", stored_probability=Decimal("1.000000")
        )
        lost = _verdict(
            is_winner=False, resolution_source="api_settlement", stored_probability=Decimal("0.000000")
        )
        assert won == {"verdict": "won", "basis": "stored_terminal_agreement"}
        assert lost == {"verdict": "lost", "basis": "stored_terminal_agreement"}

    @pytest.mark.parametrize(
        "winner, price", [(True, Decimal("0")), (False, Decimal("1"))]
    )
    def test_a_grade_that_disagrees_with_its_terminal_price_is_not_repaired(self, winner, price):
        got = _verdict(is_winner=winner, resolution_source="api_settlement", stored_probability=price)
        assert got == {"verdict": "unknown", "basis": "conflicting_stored_evidence"}

    @pytest.mark.parametrize("winner", [True, False, None])
    def test_a_retraction_is_refused_first(self, winner):
        got = _verdict(
            is_winner=winner, resolution_source="ungradeable_result", stored_probability=Decimal("0")
        )
        assert got == {"verdict": "unknown", "basis": "retracted_grade"}

    @pytest.mark.parametrize("source", [None, ""])
    def test_a_missing_source_is_not_a_grade(self, source):
        got = _verdict(is_winner=False, resolution_source=source, stored_probability=Decimal("0"))
        assert got == {"verdict": "unknown", "basis": "missing_grade_source"}

    def test_an_unrecognised_source_is_not_a_grade(self):
        assert "made_up_source" not in KNOWN_SOURCES
        got = _verdict(
            is_winner=False, resolution_source="made_up_source", stored_probability=Decimal("0")
        )
        assert got == {"verdict": "unknown", "basis": "unrecognized_grade_source"}

    def test_a_null_grade_is_not_a_loss(self):
        got = _verdict(is_winner=None, resolution_source="api_settlement", stored_probability=Decimal("0"))
        assert got == {"verdict": "unknown", "basis": "missing_grade"}

    def test_a_null_price_is_not_zero(self):
        got = _verdict(is_winner=False, resolution_source="api_settlement", stored_probability=None)
        assert got == {"verdict": "unknown", "basis": "missing_stored_price"}

    @pytest.mark.parametrize("price", [float("nan"), float("inf"), Decimal("1.5"), -0.1, "x", True])
    def test_an_invalid_price_is_not_a_result(self, price):
        got = _verdict(is_winner=False, resolution_source="api_settlement", stored_probability=price)
        assert got == {"verdict": "unknown", "basis": "invalid_stored_price"}

    def test_an_explicit_independent_field_of_terminal_losses_stays_all_lost(self):
        """SYNTHETIC explicit independence (not the real bridesmaids venue): a
        field may settle with no affirmative winner. Every row is judged on its
        own; nothing invents a winner, an Other, or a void."""
        rows = [
            _verdict(is_winner=False, resolution_source="api_settlement", stored_probability=Decimal("0"))
            for _ in range(5)
        ]
        assert {r["verdict"] for r in rows} == {"lost"}

    def test_scope_is_resolved_polymarket_only(self):
        assert sd.applies_to_market(SimpleNamespace(source="polymarket", status="resolved"))
        for source, status in [
            ("polymarket", "open"),
            ("polymarket", "withdrawn"),
            ("kalshi", "resolved"),
            ("odds_api", "resolved"),
        ]:
            assert not sd.applies_to_market(SimpleNamespace(source=source, status=status))


# ── the serializer, on the four exact specimens ─────────────────────────────


def _parse(ts):
    if ts is None:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _specimen_market(sid: str):
    spec = SPECIMENS[sid]
    served = spec["served"]
    m = spec["market"]
    openings = {o["id"]: o for o in served["outcomes"]}
    outcomes = []
    # The relation's own order is not in the receipt; ties (ten 0.0 candidates)
    # keep input order through the serializer's stable sort, so the rows are fed
    # in the banked served order, unserved aliases last.
    position = {o["id"]: i for i, o in enumerate(served["outcomes"])}
    stored = sorted(
        spec["stored_outcomes"],
        key=lambda r: position.get(r["outcome_id"], len(position)),
    )
    for row in stored:
        banked = openings.get(row["outcome_id"], {})
        outcomes.append(
            SimpleNamespace(
                id=row["outcome_id"],
                name=row["outcome_name"],
                external_id=row["outcome_external_id"],
                current_probability=(
                    Decimal(row["current_probability"])
                    if row["current_probability"] is not None
                    else None
                ),
                current_american_odds=row["current_american_odds"],
                rank=banked.get("rank"),
                rank_change_24h=None,
                probability_change_24h=None,
                opening_probability=(
                    Decimal(str(banked["opening_probability"]))
                    if banked.get("opening_probability") is not None
                    else None
                ),
                opening_american_odds=banked.get("opening_american_odds"),
                is_winner=row["is_winner"],
                resolution_source=row["resolution_source"],
                last_updated=_parse(row["last_updated"]),
                price_changed_at=_parse(row["price_changed_at"]),
                team_id=None,
                team=None,
                current_yes_bid=None,
                current_yes_ask=None,
            )
        )
    return SimpleNamespace(
        id=m["found_market_id"],
        name=m["market_name"],
        description=served.get("description"),
        category=served.get("category"),
        source=m["source"],
        external_id=m["external_id"],
        status=m["status"],
        sport=SimpleNamespace(key=served["sport"], name=served["sport_name"]),
        sport_id=None,
        event_id=None,
        market_type=m["market_type"],
        market_tier=None,
        llm_sport_category=served.get("llm_sport_category"),
        mutually_exclusive=m["mutually_exclusive"],
        commence_time=_parse(served.get("commence_time")),
        resolution_date=_parse(served.get("resolution_date")),
        created_at=_parse(served.get("created_at")),
        updated_at=_parse(served.get("updated_at")),
        group_id=m["group_id"],
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


#: The banked responses were fetched 2026-10-16 ~21:18Z; pin the clock there.
SERVED_AT = datetime.fromisoformat("2026-10-16T21:18:00+00:00")


def _serve(sid: str):
    import app.routes.futures as futures_routes

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return SERVED_AT if tz else SERVED_AT.replace(tzinfo=None)

    with mock.patch.object(futures_routes, "datetime", _Clock):
        return futures_routes._format_market_detail(
            _specimen_market(sid), None, set(), fleet_newest_observation=SERVED_AT
        )


def _assert_banked_values_unchanged(sid: str, detail: dict):
    banked = SPECIMENS[sid]["served"]["outcomes"]
    got = detail["outcomes"]
    assert [o["id"] for o in got] == [o["id"] for o in banked], (
        "the served row set/order moved; this contract must not drop, add or reorder rows"
    )
    for g, b in zip(got, banked):
        for key in BANKED_KEYS:
            assert g[key] == b[key], (sid, g["id"], key, g[key], b[key])


class TestTheTennisCoinFlip62134744:
    def test_both_legs_are_served_as_unknown_on_a_nonterminal_price(self):
        detail = _serve("62134744")
        rows = {o["name"]: o for o in detail["outcomes"]}
        assert set(rows) == {"Over", "Under"}
        for row in rows.values():
            assert row["settlement_display"] == {
                "verdict": "unknown",
                "basis": "nonterminal_stored_price",
            }

    def test_the_served_values_are_byte_equivalent_to_the_banked_response(self):
        """0.5 stays 0.5, `false` stays `false`, the source stays the source:
        nothing is nulled on the wire to simulate uncertainty."""
        _assert_banked_values_unchanged("62134744", _serve("62134744"))


class TestTheTerminalControl13798072:
    def test_no_won_and_yes_lost_on_stored_terminal_agreement(self):
        detail = _serve("13798072")
        rows = {o["name"]: o["settlement_display"] for o in detail["outcomes"]}
        assert rows == {
            "No": {"verdict": "won", "basis": "stored_terminal_agreement"},
            "Yes": {"verdict": "lost", "basis": "stored_terminal_agreement"},
        }
        _assert_banked_values_unchanged("13798072", detail)


class TestTheField12194657:
    def test_ten_candidates_served_each_lost_aliases_still_filtered(self):
        detail = _serve("12194657")
        served_ids = [o["id"] for o in detail["outcomes"]]
        stored_ids = [r["outcome_id"] for r in SPECIMENS["12194657"]["stored_outcomes"]]
        assert len(stored_ids) == 12 and len(served_ids) == 10
        aliases = {
            r["outcome_id"]
            for r in SPECIMENS["12194657"]["stored_outcomes"]
            if r["outcome_name"] in ("Yes", "No")
        }
        assert len(aliases) == 2 and not aliases & set(served_ids)
        assert {o["settlement_display"]["verdict"] for o in detail["outcomes"]} == {"lost"}
        _assert_banked_values_unchanged("12194657", detail)


class TestTheOpenParent113360:
    def test_an_open_parent_carries_no_settlement_contract(self):
        detail = _serve("113360")
        assert detail["status"] == "open"
        assert not any("settlement_display" in o for o in detail["outcomes"])
        assert [o["id"] for o in detail["outcomes"]] == [
            o["id"] for o in SPECIMENS["113360"]["served"]["outcomes"]
        ]


class TestNonTargetedSourcesAreUntouched:
    def test_a_resolved_kalshi_board_carries_no_settlement_contract(self):
        """#10066 / #10964's graded-priceless contracts live on other sources;
        this change does not reach them."""
        import app.routes.futures as futures_routes

        market = _specimen_market("13798072")
        market.source = "kalshi"
        detail = futures_routes._format_market_detail(market, None, set())
        assert not any("settlement_display" in o for o in detail["outcomes"])


class TestTheFrontendFixtureCarriesWhatThisServerServes:
    """`frontend/__tests__/fixtures/settledDisplay698.json` drives the web
    renderer guard with the contract this serializer emits. If the rules move,
    this fails here rather than leaving the web guard testing a stale answer."""

    def test_every_specimen_contract_matches_the_serializer(self):
        web = json.loads(
            (
                pathlib.Path(__file__).resolve().parents[2]
                / "frontend"
                / "__tests__"
                / "fixtures"
                / "settledDisplay698.json"
            ).read_text()
        )["specimens"]
        assert set(web) == set(SPECIMENS)
        for sid in SPECIMENS:
            assert web[sid]["served"] == SPECIMENS[sid]["served"], sid
            assert web[sid]["served_sha256"] == SPECIMENS[sid]["served_sha256"], sid
            served = {
                str(o["id"]): o["settlement_display"]
                for o in _serve(sid)["outcomes"]
                if "settlement_display" in o
            }
            assert web[sid]["contract"] == served, sid
