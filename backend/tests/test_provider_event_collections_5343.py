"""#5343 — one provider event, one collection: the pure rules.

SHIP: a politics, economics, technology or entertainment event on Polymarket
becomes one complete collection on its own, and a new provider event uses the same
code with no member list. Pillars: MATCHING / DISCOVER / TRUTH.

The events here are real Gamma payloads (``tests/fixtures/…/PROVENANCE.md``)
turned into the rows ingestion stores. The roster key on the parent is the
PROPOSED ingestion field, supplied by the test. Nothing here is served proof.
The transaction and lock half lives in
``tests/integration/test_provider_event_collections_5343_pg.py``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils import provider_event_collections as pec
from app.utils.container_presentation import edition_for_slug
from app.utils.provider_event_collections import (
    ADMITTED_ROSTER_MEMBER,
    ADMITTED_ROW_IDENTITY,
    CARRIED_DOMAIN_UNSUPPORTED,
    CARRIED_ROW_ABSENT,
    EXCLUDED_GROUP_ANCHOR,
    EXCLUDED_IDENTITY_CONFLICT,
    EXCLUDED_IDENTITY_MOVED,
    EXCLUDED_NOT_IN_ROSTER,
    EXCLUDED_UNSUPPORTED_DOMAIN,
    EXCLUDED_WITHDRAWN,
    PriorDecision,
    ProviderEventIdentity,
    assemble_event,
    header_changes,
    identity_from_group_id,
    parse_collection_slug,
    parse_roster,
    plan_event_pass,
    provider_row,
    publication_eligibility,
)
from tests.provider_event_fixtures_5343 import ingested_rows, load_gamma, roster_payload

OBSERVED = datetime(2026, 10, 12, 0, 49, 13, tzinfo=timezone.utc)
NOW = OBSERVED + timedelta(hours=1)


def _identity(event_id: str) -> ProviderEventIdentity:
    identity = identity_from_group_id(f"polymarket:{event_id}")
    assert identity is not None
    return identity


def _rows(
    event_id: str, domain: str, *, roster: bool = True, first_id: int = 1000, **kw
):
    event = load_gamma(event_id)
    raw = ingested_rows(
        event, domain, first_id=first_id, roster_at=OBSERVED if roster else None, **kw
    )
    return event, [provider_row(r) for r in raw]


def _by_reason(assembly) -> dict:
    out: dict = {}
    for d in assembly.decisions:
        out.setdefault(d.reason, []).append(d.child_id)
    return out


def _prior_from(assembly) -> dict:
    """What the writer would read back as decision rows after this pass."""
    return {
        d.child_id: PriorDecision(
            d.child_id,
            d.reason,
            d.evidence.get("external_id"),
            (
                datetime.fromisoformat(d.evidence["applied_roster_at"])
                if d.evidence.get("applied_roster_at")
                else None
            ),
        )
        for d in assembly.decisions
    }


# ---------------------------------------------------------------------------
# Identity and destination
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_group_id_slug_round_trip(self):
        identity = _identity("1038648")
        assert identity.group_id == "polymarket:1038648"
        assert identity.slug == "polymarket-event-1038648"
        assert parse_collection_slug(identity.slug) == identity

    @pytest.mark.parametrize(
        "group_id",
        [
            None,
            "",
            "polymarket:",
            "polymarket:01",
            "polymarket:12:3",
            "polymarket:abc",
            " polymarket:12",
            "polymarket: 12",
            "kalshi:12",
            "polymarket:1234567890123456789",
            12,
            "POLYMARKET:12",
        ],
    )
    def test_malformed_or_foreign_groups_have_no_identity(self, group_id):
        assert identity_from_group_id(group_id) is None

    @pytest.mark.parametrize(
        "slug",
        [
            "polymarket-event-01",
            "polymarket-event-1-x",
            "Polymarket-event-1",
            "polymarket-event-",
            "polymarket-1038648",
            "nfl-2026-week-4",
            None,
        ],
    )
    def test_only_the_builders_own_slug_parses(self, slug):
        assert parse_collection_slug(slug) is None

    @pytest.mark.parametrize("event_id", ["1038648", "2026", "86832", "1"])
    def test_a_provider_slug_is_never_an_nfl_mlb_or_theme_edition(self, event_id):
        """So the route serves it through the simple published envelope. A
        four-digit id has the theme slug's SHAPE (``subject-YYYY``) and is still
        refused, because the theme parser answers only for its own registry."""
        assert edition_for_slug(_identity(event_id).slug) is None


# ---------------------------------------------------------------------------
# The roster contract
# ---------------------------------------------------------------------------


class TestRoster:
    def test_the_proposed_shape_parses(self):
        event = load_gamma("1038648")
        roster, reason = parse_roster(roster_payload(event, OBSERVED))
        assert reason is None
        assert len(roster.members) == 6
        assert roster.observed_at == OBSERVED
        assert roster.event_closed is False
        closed = {m.external_id for m in roster.members if m.closed}
        assert closed == {event["markets"][0]["conditionId"]}

    def _good(self):
        return roster_payload(load_gamma("1038648"), OBSERVED)

    def test_absent(self):
        assert parse_roster(None) == (None, pec.ROSTER_ABSENT)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda r: r.pop("complete"),
            lambda r: r.update(complete=False),
            lambda r: r.update(complete="true"),
            lambda r: r.update(observed_at="2026-10-12T00:49:13"),  # naive
            lambda r: r.update(observed_at="yesterday"),
            lambda r: r.update(markets=[]),
            lambda r: r.update(markets="0xabc"),
            lambda r: r["markets"].append(dict(r["markets"][0])),  # duplicate id
            lambda r: r["markets"][0].update(id="0x1234"),
            lambda r: r["markets"][0].update(closed="no"),
            lambda r: r.update(event_closed="false"),
        ],
    )
    def test_any_doubt_is_malformed(self, mutate):
        raw = self._good()
        mutate(raw)
        assert parse_roster(raw) == (None, pec.ROSTER_MALFORMED)

    def test_not_a_mapping(self):
        assert parse_roster(["0x"])[1] == pec.ROSTER_MALFORMED


# ---------------------------------------------------------------------------
# Real events, contrasting domains
# ---------------------------------------------------------------------------


class TestRealEvents:
    def test_a_politics_event_with_its_roster_is_a_complete_eligible_collection(self):
        event, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        reasons = _by_reason(a)
        assert reasons[EXCLUDED_GROUP_ANCHOR] == [1000]
        assert len(reasons[ADMITTED_ROSTER_MEMBER]) == 6
        assert a.complete and a.roster_unstored == ()
        assert a.header.name == "US-Iran ceasefire continues through...?"
        assert a.header.category == "geopolitics"
        assert a.header.status == "scheduled"
        assert a.header.window_end == datetime(
            2026, 10, 31, 23, 59, tzinfo=timezone.utc
        )
        e = publication_eligibility(a, now=NOW)
        assert e.eligible, e.reasons
        assert e.shown_members == 6

    def test_a_closed_member_stays_a_member_with_its_provider_state(self):
        """Settled means settled: the Sep 20 leg closed and is still listed."""
        event, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        closed_id = event["markets"][0]["conditionId"]
        d = next(d for d in a.decisions if d.evidence.get("external_id") == closed_id)
        assert d.reason == ADMITTED_ROSTER_MEMBER
        assert d.evidence["provider_closed"] is True
        assert d.evidence["row_status"] == "resolved"

    def test_an_economics_event_is_incomplete_while_its_zero_priced_legs_are_unstored(
        self,
    ):
        """106884: six closed rungs carry a Yes price of 0. Ingestion skips them,
        so the provider lists 13 markets and we hold 7. The collection assembles
        and is NOT eligible — the gap is named, not guessed past."""
        event, rows = _rows("106884", "economics")
        a = assemble_event(_identity("106884"), rows)
        assert len(a.admitted) == 7
        assert len(a.roster_unstored) == 6
        assert not a.complete
        e = publication_eligibility(a, now=NOW)
        assert not e.eligible
        assert e.reasons == (pec.INELIGIBLE_ROSTER_UNSTORED,)

    def test_every_member_names_its_provider_event_and_reference(self):
        event, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        conditions = {m["conditionId"] for m in event["markets"]}
        for d in a.decisions:
            assert d.evidence["provider"] == "polymarket"
            assert d.evidence["provider_event_id"] == "1038648"
            assert d.evidence["group_id"] == "polymarket:1038648"
            assert d.evidence["rule_version"] == pec.RULE_VERSION
            assert d.evidence["roster_observed_at"] == OBSERVED.isoformat()
        members = [d for d in a.decisions if d.reason == ADMITTED_ROSTER_MEMBER]
        assert {d.evidence["external_id"] for d in members} == conditions
        assert all(
            d.evidence["identity_signals"] == ["group_id", "metadata_event_id"]
            for d in members
        )

    def test_nothing_is_averaged_and_nothing_is_priced(self):
        _, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        blob = repr([d.evidence for d in a.decisions]) + repr(
            publication_eligibility(a, now=NOW).as_dict()
        )
        assert "probab" not in blob and "price" not in blob


class TestHeldOutEvent:
    """86832 is named by no source file. It assembles with the code unchanged."""

    def test_a_held_out_tech_event_needs_no_source_edit(self):
        event, rows = _rows("86832", "tech", first_id=5000)
        a = assemble_event(_identity("86832"), rows)
        assert len(a.admitted) == len(event["markets"]) == 19
        assert a.complete
        assert publication_eligibility(a, now=NOW).eligible

    def test_no_source_file_names_an_event_or_market(self):
        root = Path(__file__).resolve().parents[1] / "app"
        sources = [
            root / "utils" / "provider_event_collections.py",
            root / "tasks" / "provider_event_collection_assembly.py",
        ]
        events = ("86832", "1038648", "106884")
        ids = set(events)
        for event_id in events:
            ids |= {m["conditionId"] for m in load_gamma(event_id)["markets"]}
        for path in sources:
            text = path.read_text()
            assert not any(i in text for i in ids), path
            assert not re.search(r"0x[0-9a-fA-F]{8,}", text), path
            assert not re.search(r"\b\d{5,}\b", text), path


# ---------------------------------------------------------------------------
# Completeness needs the roster
# ---------------------------------------------------------------------------


class TestCompleteness:
    def test_without_a_roster_members_assemble_but_the_collection_is_never_complete(
        self,
    ):
        """Today's stored reality: ``market_count`` is on the parent and equals
        the children we hold (6 = 6), and that is still not a roster."""
        event, rows = _rows("1038648", "geopolitics", roster=False)
        a = assemble_event(_identity("1038648"), rows)
        parent = next(r for r in rows if r.external_id == "1038648")
        assert len([r for r in rows if r is not parent]) == len(event["markets"])
        assert len(_by_reason(a)[ADMITTED_ROW_IDENTITY]) == 6
        assert not a.complete
        e = publication_eligibility(a, now=NOW)
        assert e.reasons == (pec.ROSTER_ABSENT,)

    def test_a_roster_listing_a_market_we_do_not_hold_is_incomplete(self):
        event = load_gamma("1038648")
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        raw[0]["market_metadata"]["polymarket_event_roster"] = roster_payload(
            event, OBSERVED, extra=("0x" + "ab" * 32,)
        )
        a = assemble_event(_identity("1038648"), [provider_row(r) for r in raw])
        assert a.roster_unstored == ("0x" + "ab" * 32,)
        assert (
            pec.INELIGIBLE_ROSTER_UNSTORED
            in publication_eligibility(a, now=NOW).reasons
        )

    def test_a_row_the_roster_does_not_list_is_not_linked(self):
        event = load_gamma("1038648")
        dropped = event["markets"][3]["conditionId"]
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        raw[0]["market_metadata"]["polymarket_event_roster"] = roster_payload(
            event, OBSERVED, drop=(dropped,)
        )
        a = assemble_event(_identity("1038648"), [provider_row(r) for r in raw])
        excluded = [d for d in a.decisions if d.reason == EXCLUDED_NOT_IN_ROSTER]
        assert [d.evidence["external_id"] for d in excluded] == [dropped]
        assert not excluded[0].keep_edge
        assert a.complete  # the roster's own list is fully held

    def test_an_expired_roster_still_decides_but_cannot_make_it_eligible(self):
        _, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        late = OBSERVED + pec.ROSTER_MAX_AGE + timedelta(seconds=1)
        assert publication_eligibility(a, now=late).reasons == (
            pec.INELIGIBLE_ROSTER_EXPIRED,
        )
        assert publication_eligibility(a, now=OBSERVED + pec.ROSTER_MAX_AGE).eligible

    def test_a_single_market_event_is_not_a_collection(self):
        event = load_gamma("1038648")
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)[:2]
        raw[0]["market_metadata"]["polymarket_event_roster"] = roster_payload(
            {**event, "markets": event["markets"][:1]}, OBSERVED
        )
        a = assemble_event(_identity("1038648"), [provider_row(r) for r in raw])
        assert len(a.admitted) == 1
        assert publication_eligibility(a, now=NOW).reasons == (
            pec.INELIGIBLE_TOO_FEW_MEMBERS,
        )


# ---------------------------------------------------------------------------
# Negatives: duplicates, other events, wrong edition, unsupported
# ---------------------------------------------------------------------------


class TestNegatives:
    def test_a_duplicate_row_is_one_member(self):
        _, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows + rows[2:4])
        assert len(a.admitted) == 6
        assert len({d.child_id for d in a.decisions}) == len(a.decisions)

    def test_same_title_different_event_is_a_different_collection(self):
        """Another edition with the very same title. Titles never decide."""
        _, rows = _rows("1038648", "geopolitics")
        twin = load_gamma("1038648")
        twin = {**twin, "id": "1038649", "slug": twin["slug"] + "-2"}
        other = [
            provider_row(r)
            for r in ingested_rows(
                twin, "geopolitics", first_id=2000, roster_at=OBSERVED
            )
        ]
        a = assemble_event(_identity("1038648"), rows + other)
        assert {d.child_id for d in a.decisions} == {r.id for r in rows}
        assert _identity("1038649").slug != _identity("1038648").slug

    def test_a_row_naming_another_event_in_its_metadata_is_never_linked(self):
        """Wrong edition: ``group_id`` says this event, the stamped event id says
        another. Two signals disagree, so neither is trusted."""
        event = load_gamma("1038648")
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        raw[2]["market_metadata"]["polymarket_event_id"] = "999"
        a = assemble_event(_identity("1038648"), [provider_row(r) for r in raw])
        assert _by_reason(a)[EXCLUDED_IDENTITY_CONFLICT] == [1002]
        assert 1002 not in a.kept
        e = publication_eligibility(a, now=NOW)
        assert pec.INELIGIBLE_IDENTITY_CONFLICTS in e.reasons
        assert pec.INELIGIBLE_ROSTER_UNSTORED in e.reasons

    def test_metadata_absent_falls_back_to_the_group_alone(self):
        event = load_gamma("1038648")
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        del raw[2]["market_metadata"]["polymarket_event_id"]
        a = assemble_event(_identity("1038648"), [provider_row(r) for r in raw])
        d = next(d for d in a.decisions if d.child_id == 1002)
        assert d.reason == ADMITTED_ROSTER_MEMBER
        assert d.evidence["identity_signals"] == ["group_id"]

    def test_another_providers_market_with_the_same_question_is_not_a_member(self):
        _, rows = _rows("1038648", "geopolitics")
        kalshi = provider_row(
            {
                **vars(rows[1]),
                "id": 9001,
                "source": "kalshi",
                "external_id": "KXIRAN-26SEP25",
                "group_id": None,
                "market_metadata": None,
                "llm_sport_category": "geopolitics",
            }
        )
        a = assemble_event(_identity("1038648"), rows + [kalshi])
        assert 9001 not in {d.child_id for d in a.decisions}

    @pytest.mark.parametrize("domain", ["basketball", "crypto", "weather", None])
    def test_an_unsupported_domain_links_nothing(self, domain):
        _, rows = _rows("1038648", domain)
        a = assemble_event(_identity("1038648"), rows)
        assert a.admitted == ()
        assert set(_by_reason(a)) == {
            EXCLUDED_GROUP_ANCHOR,
            EXCLUDED_UNSUPPORTED_DOMAIN,
        }
        assert not publication_eligibility(a, now=NOW).eligible

    def test_a_mixed_domain_event_is_ambiguous_and_links_nothing(self):
        event = load_gamma("1038648")
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        raw[3]["llm_sport_category"] = "politics"
        a = assemble_event(_identity("1038648"), [provider_row(r) for r in raw])
        assert a.domain_state == pec.DOMAIN_AMBIGUOUS
        assert a.admitted == ()

    def test_a_domain_change_carries_existing_members_rather_than_retiring_them(self):
        _, rows = _rows("1038648", "basketball")
        a = assemble_event(_identity("1038648"), rows, edged=[1001, 1002])
        assert set(a.kept) == {1001, 1002}
        assert _by_reason(a)[CARRIED_DOMAIN_UNSUPPORTED] == [1001, 1002]


# ---------------------------------------------------------------------------
# Stability, retirement, corrections, outages — the plan
# ---------------------------------------------------------------------------


class TestStability:
    def test_title_change_keeps_the_slug_and_the_members_and_moves_only_the_label(self):
        _, before = _rows("1038648", "geopolitics")
        _, after = _rows(
            "1038648", "geopolitics", title="US x Iran: ceasefire holds through...?"
        )
        a1 = assemble_event(_identity("1038648"), before)
        a2 = assemble_event(
            _identity("1038648"), after, edged=a1.kept, prior=_prior_from(a1)
        )
        assert a1.identity.slug == a2.identity.slug
        assert plan_event_pass(a2, a1.kept).membership_changed is False
        assert header_changes(a2.header, {"name": a1.header.name}) == {
            "name": "US x Iran: ceasefire holds through...?",
            "category": "geopolitics",
            "status": "scheduled",
            "window_start": a2.header.window_start,
            "window_end": a2.header.window_end,
        }

    def test_member_arrival_adds_one_edge(self):
        event = load_gamma("1038648")
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        first = assemble_event(
            _identity("1038648"), [provider_row(r) for r in raw[:-1]]
        )
        later = assemble_event(
            _identity("1038648"),
            [provider_row(r) for r in raw],
            edged=first.kept,
            prior=_prior_from(first),
        )
        plan = plan_event_pass(later, first.kept)
        assert plan.upserts == (raw[-1]["id"],) and plan.deletes == ()

    def test_a_pass_over_the_same_evidence_changes_nothing(self):
        _, rows = _rows("1038648", "geopolitics")
        a1 = assemble_event(_identity("1038648"), rows)
        a2 = assemble_event(
            _identity("1038648"), rows, edged=a1.kept, prior=_prior_from(a1)
        )
        assert plan_event_pass(a2, a1.kept).membership_changed is False
        assert [d.evidence for d in a1.decisions] == [d.evidence for d in a2.decisions]


class TestRetirement:
    def _closed(self, event_id="1038648"):
        event = load_gamma(event_id)
        event = {
            **event,
            "closed": True,
            "markets": [{**m, "closed": True} for m in event["markets"]],
        }
        raw = ingested_rows(event, "geopolitics", first_id=1000, roster_at=OBSERVED)
        return event, assemble_event(
            _identity(event_id), [provider_row(r) for r in raw]
        )

    def test_the_providers_closed_flag_makes_the_collection_final(self):
        _, a = self._closed()
        assert a.header.status == "final"

    def test_retirement_is_fourteen_days_after_the_providers_window_on_a_fixed_clock(
        self,
    ):
        _, a = self._closed()
        end = a.header.window_end
        before = publication_eligibility(
            a, now=end + pec.RETIRE_AFTER - timedelta(seconds=1)
        )
        after = publication_eligibility(a, now=end + pec.RETIRE_AFTER)
        assert pec.INELIGIBLE_RETIRED not in before.reasons
        assert pec.INELIGIBLE_RETIRED in after.reasons
        assert after.retire_at == end + pec.RETIRE_AFTER
        # Retirement never subtracts a member: the page keeps its results.
        assert len(a.kept) == 6

    def test_an_open_event_past_its_window_does_not_retire(self):
        _, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        far = a.header.window_end + timedelta(days=60)
        assert pec.INELIGIBLE_RETIRED not in publication_eligibility(a, now=far).reasons

    def test_no_provider_flag_leaves_the_status_alone(self):
        _, rows = _rows("1038648", "geopolitics", roster=False)
        a = assemble_event(_identity("1038648"), rows, current_status="final")
        assert a.header.status == "final"


class TestCorrectionsAndOutages:
    def _applied(self):
        _, rows = _rows("1038648", "geopolitics")
        a = assemble_event(_identity("1038648"), rows)
        return rows, a

    def test_a_withdrawn_member_stays_out_on_every_later_pass(self):
        rows, a = self._applied()
        for _ in range(3):
            a = assemble_event(
                _identity("1038648"),
                rows,
                edged=a.kept,
                withdrawn=[1003],
                prior=_prior_from(a),
            )
            assert 1003 not in a.kept
            assert _by_reason(a)[EXCLUDED_WITHDRAWN] == [1003]

    def test_a_withdrawn_publication_is_never_re_offered(self):
        rows, a = self._applied()
        e = publication_eligibility(a, now=NOW, publication_state="withdrawn")
        assert e.reasons == (pec.INELIGIBLE_PUBLICATION_WITHDRAWN,)

    def test_an_outage_carries_last_good_membership(self):
        """No roster, no rows: every edge is carried, nothing retires."""
        rows, a = self._applied()
        outage = assemble_event(
            _identity("1038648"), [], edged=a.kept, prior=_prior_from(a)
        )
        assert set(outage.kept) == set(a.kept)
        assert set(_by_reason(outage)) == {CARRIED_ROW_ABSENT, pec.EXCLUDED_ROW_ABSENT}
        assert plan_event_pass(outage, a.kept).deletes == ()

    def test_a_lost_roster_retires_nothing(self):
        rows, a = self._applied()
        _, bare = _rows("1038648", "geopolitics", roster=False)
        b = assemble_event(
            _identity("1038648"), bare, edged=a.kept, prior=_prior_from(a)
        )
        assert set(b.kept) == set(a.kept)

    def test_a_newer_roster_that_drops_a_member_retires_it(self):
        rows, a = self._applied()
        event = load_gamma("1038648")
        dropped = event["markets"][4]["conditionId"]
        raw = ingested_rows(event, "geopolitics", first_id=1000)
        raw[0]["market_metadata"]["polymarket_event_roster"] = roster_payload(
            event, OBSERVED + timedelta(hours=1), drop=(dropped,)
        )
        b = assemble_event(
            _identity("1038648"),
            [provider_row(r) for r in raw],
            edged=a.kept,
            prior=_prior_from(a),
            now=OBSERVED + timedelta(hours=2),  # fresh: a confirmed removal
        )
        plan = plan_event_pass(b, a.kept)
        assert len(plan.deletes) == 1
        gone = next(d for d in b.decisions if d.child_id == plan.deletes[0])
        assert gone.evidence["external_id"] == dropped

    def test_an_older_roster_never_resurrects_what_a_newer_one_removed(self):
        """Out of order: R2 (newer) dropped a member; then the stored roster
        regresses to R1 (older, still listing it). The member stays out until a
        roster NEWER than R2 lists it again."""
        rows, a = self._applied()
        event = load_gamma("1038648")
        dropped = event["markets"][4]["conditionId"]
        r2 = OBSERVED + timedelta(hours=2)

        def at(observed, drop=()):
            raw = ingested_rows(event, "geopolitics", first_id=1000)
            raw[0]["market_metadata"]["polymarket_event_roster"] = roster_payload(
                event, observed, drop=drop
            )
            return [provider_row(r) for r in raw]

        b = assemble_event(
            _identity("1038648"),
            at(r2, (dropped,)),
            edged=a.kept,
            prior=_prior_from(a),
            now=r2,
        )
        member = next(
            d.child_id for d in b.decisions if d.evidence.get("external_id") == dropped
        )
        assert member not in b.kept

        c = b
        for _ in range(3):  # a stale pass must not erase the epoch for the next one
            c = assemble_event(
                _identity("1038648"),
                at(OBSERVED + timedelta(hours=1)),
                edged=c.kept,
                prior=_prior_from(c),
            )
            assert c.roster_state == pec.ROSTER_OLDER_THAN_APPLIED
            assert member not in c.kept
            assert set(c.kept) == set(b.kept)
            assert all(
                x.evidence["applied_roster_at"] == r2.isoformat() for x in c.decisions
            )
            assert not publication_eligibility(c, now=r2).eligible

        d = assemble_event(
            _identity("1038648"),
            at(r2 + timedelta(hours=1)),
            edged=c.kept,
            prior=_prior_from(c),
        )
        assert member in d.kept

    def test_a_vanished_row_the_roster_still_lists_is_carried(self):
        rows, a = self._applied()
        b = assemble_event(
            _identity("1038648"),
            [r for r in rows if r.id != 1004],
            edged=a.kept,
            prior=_prior_from(a),
        )
        assert 1004 in b.kept
        assert (
            next(d for d in b.decisions if d.child_id == 1004).reason
            == CARRIED_ROW_ABSENT
        )
        assert not b.complete

    def test_a_vanished_row_the_roster_dropped_is_retired(self):
        rows, a = self._applied()
        event = load_gamma("1038648")
        gone = next(r for r in rows if r.id == 1004).external_id
        raw = ingested_rows(event, "geopolitics", first_id=1000)
        raw[0]["market_metadata"]["polymarket_event_roster"] = roster_payload(
            event, OBSERVED + timedelta(hours=1), drop=(gone,)
        )
        b = assemble_event(
            _identity("1038648"),
            [provider_row(r) for r in raw if r["id"] != 1004],
            edged=a.kept,
            prior=_prior_from(a),
            now=OBSERVED + timedelta(hours=2),
        )
        assert 1004 not in b.kept
        assert b.complete

    def test_a_member_whose_row_moved_to_another_event_leaves(self):
        rows, a = self._applied()
        moved = provider_row(
            {
                **vars(rows[2]),
                "group_id": "polymarket:7",
                "market_metadata": {"polymarket_event_id": "7"},
            }
        )
        b = assemble_event(
            _identity("1038648"),
            [r for r in rows if r.id != moved.id] + [moved],
            edged=a.kept,
            prior=_prior_from(a),
        )
        assert moved.id not in b.kept
        assert (
            next(d for d in b.decisions if d.child_id == moved.id).reason
            == EXCLUDED_IDENTITY_MOVED
        )

    def test_a_slot_another_source_holds_is_neither_taken_nor_counted(self):
        rows, a = self._applied()
        plan = plan_event_pass(a, {}, foreign_held=[1001])
        assert 1001 not in plan.upserts
        assert len(plan.upserts) == 5
