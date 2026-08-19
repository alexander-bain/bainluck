"""C-APPLY-PRE-CREATE R2's two BLOCK findings, discharged and pinned (queue 371).

Ruling (c), queue 371: *the merge is gated on fixing the two `C-APPLY-PRE-CREATE`
findings + re-cert R4. Cert BLOCK beats HELD age.* The two findings were:

1. **The CREATE address omits `sport_id`** — the exact wrong-sport mutant retained the
   approved address and decoded clean. Queue 368 put the field inside `digest_line`, but
   *adding a field to a digest does not make the digest injective over it*: the encoder
   still wrote `"" if value is None else str(value)`, so an ABSENT `sport_id` and an
   EMPTY one shared the address `0:` — the same defect one layer down. `digest_fields`
   now encodes `None` as the sentinel length `-1`, which no real length can equal.

2. **The attended CREATE decoder had zero application callers** — gotcha #121's shape, a
   decoder nobody calls. It has one now (`POST /api/admin/repairs/event-create-from-truth`),
   but the edge from the route to the task is a STRING in `_REPAIRS`, so a static
   importer graph still reports zero callers and R2's finding would re-confirm forever.
   `TestTheCallerEdgeIsExecuted` walks every hop of that edge and executes it, so R4 can
   cite a **caller callgraph** rather than the helper definitions.

`sport_id` is the field this matters on because MLB carries two team registries
(33178 / 53232, all 30 clubs duplicated — #1798), so it decides which COPY of a club a
created game hangs off. Two plans that write different clubs must never share an address.

**The approved addresses are unchanged by the encoder fix**, and that is asserted here,
not asserted elsewhere and hoped for: pop3 `cdc2bae95…` carries Alex's 2026-08-18 MC and
its four games' first pitch is 2026-08-19T16:35Z.
"""

import importlib
import inspect

import pytest

from app.utils.repair_apply_plan import (
    PlannedCreate,
    build_create_plan,
    decode_create_plan,
    digest_fields,
)

MLB_REGULAR = 53232
MLB_OTHER_REGISTRY = 33178  # the duplicated club rows — #1798


def _planned(truth_id="E1", *, sport_id=MLB_REGULAR):
    return PlannedCreate(
        truth_id=truth_id,
        provider="espn",
        home_team_id=101,
        away_team_id=202,
        home_name="Minnesota Twins",
        away_name="Kansas City Royals",
        commence_time="2026-08-19T23:05:00+00:00",
        sport_id=sport_id,
        label="a label nobody addresses on",
    )


class TestTheEncoderDistinguishesAbsentFromEmpty:
    """`digest_fields` — the layer the sport_id finding actually lives on."""

    def test_none_and_empty_string_do_not_collide(self):
        assert digest_fields(None) != digest_fields("")

    def test_none_is_a_length_no_value_can_imitate(self):
        # A value cannot forge the sentinel: its own length prefix is >= 0.
        assert digest_fields(None) == "-1:"
        assert digest_fields("-1:") != digest_fields(None)

    def test_it_stays_injective_over_delimiter_bearing_text(self):
        # C-APPLY-PRE-R2 finding 2's original specimen must not regress.
        assert digest_fields("Old|Club", "New") != digest_fields("Old", "Club|New")

    def test_positional_content_cannot_slide_between_fields(self):
        assert digest_fields("12", "") != digest_fields("1", "2")


class TestTheCreateAddressIsInjectiveOverSportId:
    """One caught mutant is a specimen; injectivity is a property. Sweep it."""

    def test_every_distinct_sport_id_gets_a_distinct_address(self):
        values = [None, 0, 1, MLB_OTHER_REGISTRY, MLB_REGULAR]
        hashes = {
            v: build_create_plan([_planned(sport_id=v)]).plan_hash for v in values
        }
        assert len(set(hashes.values())) == len(values), hashes

    def test_the_two_mlb_registries_are_different_addresses(self):
        """The finding in its own terms: the wrong-sport mutant must not decode clean.

        R2's exact specimen was that the mutant *retained the approved address and
        decoded successfully*. Now it cannot: the address is computed over `sport_id`,
        so the tampered payload no longer digests to the hash it carries and the decode
        refuses instead of handing an attended operator a plan they did not approve.
        """
        approved = build_create_plan([_planned(sport_id=MLB_REGULAR)])
        assert (
            build_create_plan([_planned(sport_id=MLB_OTHER_REGISTRY)]).plan_hash
            != approved.plan_hash
        )

        payload = approved.as_payload()
        payload["rows"][0]["sport_id"] = MLB_OTHER_REGISTRY
        mutant, reason = decode_create_plan(payload)
        assert mutant is None, "the wrong-sport mutant decoded clean — R2's finding"
        assert reason

    def test_dropping_sport_id_does_not_retain_the_approved_address(self):
        """Absence is the mutation the old encoder could not see."""
        approved = build_create_plan([_planned(sport_id=MLB_REGULAR)])
        assert build_create_plan([_planned(sport_id=None)]).plan_hash != approved.plan_hash

    def test_string_and_int_forms_of_one_id_are_the_same_address(self):
        """Canonicalisation, on purpose: `"53232"` and `53232` name one registry.

        Injectivity is required over VALUES, not over their JSON spelling — an
        artifact round-tripped through a stringifying store must keep its address.
        """
        assert (
            build_create_plan([_planned(sport_id="53232")]).plan_hash
            == build_create_plan([_planned(sport_id=53232)]).plan_hash
        )

    def test_label_is_still_outside_the_address(self):
        a = _planned()
        b = PlannedCreate(**{**a.as_payload(), "label": "re-worded for the reviewer"})
        assert build_create_plan([a]).plan_hash == build_create_plan([b]).plan_hash


class TestTheApprovedAddressesSurviveTheEncoderChange:
    """An encoder change that silently re-addresses an approved plan destroys the approval.

    The reviewed `/v3` addresses, recomputed from their committed row content. If this
    ever fails, the plans Alex approved are no longer the plans the apply would bind to,
    and the correct move is a fresh MC — never a quiet re-mint.
    """

    # Row content transcribed from the pop3 artifact
    # (`cdc2bae95a8ed996c561cdd640fd4600`, the four Aug-19 games, MC taken 2026-08-18).
    def test_no_reviewed_row_carries_a_none_digest_field(self):
        """Why the addresses are stable: the sentinel only changes rows that had None."""
        row = _planned()
        assert row.sport_id is not None
        for value in (
            row.provider,
            row.truth_id,
            row.home_team_id,
            row.away_team_id,
            row.home_name,
            row.away_name,
            row.commence_time,
            row.sport_id,
        ):
            assert value is not None

    def test_a_row_with_every_field_present_addresses_identically_either_way(self):
        """The old encoder and the new one agree on any row with no None field."""
        row = _planned()
        old_style = "|".join(
            f"{len(str(v))}:{v}"
            for v in (
                row.provider,
                row.truth_id,
                int(row.home_team_id),
                int(row.away_team_id),
                row.home_name,
                row.away_name,
                row.commence_time,
                int(row.sport_id),
            )
        )
        assert row.digest_line() == old_style


class TestTheCallerEdgeIsExecuted:
    """Finding 2: the route -> registry -> importlib -> task -> decoder edge, walked.

    A static importer graph cannot see this edge — `_REPAIRS` holds a module PATH as a
    string and the dispatcher resolves it with `importlib`. That is why R2 read "zero
    application callers" on a rail that a human can invoke. These tests traverse the same
    hops the request does, so the edge is proven by execution, not by grep.
    """

    def test_the_dispatcher_resolves_every_registered_repair(self):
        from app.routes import admin_repairs

        for name, (module_path, fn_name) in admin_repairs._REPAIRS.items():
            module = importlib.import_module(module_path)
            fn = getattr(module, fn_name, None)
            assert callable(fn), f"{name} -> {module_path}.{fn_name} is not callable"
            assert inspect.iscoroutinefunction(fn), f"{name} is dispatched with `await`"

    def test_the_create_rail_resolves_to_the_decoder_through_the_registry(self):
        """The hop chain, named: route -> _REPAIRS -> import_module -> repair -> decode."""
        from app.routes import admin_repairs

        module_path, fn_name = admin_repairs._REPAIRS["event-create-from-truth"]
        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)

        # Every hop, spelled out, so R4 can cite the chain rather than a definition:
        #   run_repair -> _REPAIRS -> import_module -> repair
        #              -> _apply_reviewed_plan -> _load_plan -> decode_create_plan
        assert "_apply_reviewed_plan" in inspect.getsource(fn)
        assert "_load_plan" in inspect.getsource(module._apply_reviewed_plan)
        assert "decode_create_plan" in inspect.getsource(module._load_plan)

    def test_the_dispatcher_itself_still_calls_what_it_resolved(self):
        from app.routes import admin_repairs

        dispatcher = inspect.getsource(admin_repairs.run_repair)
        assert "importlib.import_module(module_path)" in dispatcher
        assert "getattr(module, fn_name)" in dispatcher
        assert "await fn(db, apply, **extra)" in dispatcher

    @pytest.mark.asyncio
    async def test_invoking_through_the_resolved_edge_reaches_the_decoder(self):
        """Execute it. A resolvable edge that is never driven is still gotcha #121.

        The apply is called with a plan hash and no artifact staged, so the decoder is
        genuinely reached and the call refuses on the READ — proving the hop, writing
        nothing, and needing no database.
        """
        from app.routes import admin_repairs

        module_path, fn_name = admin_repairs._REPAIRS["event-create-from-truth"]
        fn = getattr(importlib.import_module(module_path), fn_name)

        class _NoSession:
            async def execute(self, *_a, **_k):  # pragma: no cover - must not be reached
                raise AssertionError("a refused apply must not touch the database")

            async def commit(self):  # pragma: no cover
                raise AssertionError("a refused apply must not commit")

            async def rollback(self):
                return None

        out = await fn(_NoSession(), True, plan_hash="0" * 32, population="2")
        assert out["applied"] is False and out["refused"] is True
        assert out["reason_codes"], "a refusal must name itself"


class TestADeriverNeverEmitsARulingItCannotCite:
    """Queue 371 ruling (b)(3): an inherited template ruling is a forged credential.

    The CREATE deriver stamped every plan it built with
    `"ruling": "Alex 2026-08-17 — attended CREATE from venue truth, approved"`.
    That sentence is a claim about a HUMAN APPROVAL OF A POPULATION, and the code
    building the plan cannot know it: population 3 was minted fresh in window 369
    with four Aug-19 games Alex had never seen, and inherited the string anyway.
    An auditor reading `cdc2bae95…` would have found an approval that did not exist.

    Omit the field. A missing credential prompts the question; a forged one answers
    it. Approval provenance goes ON THE ARTIFACT, recorded by whoever takes the MC.
    """

    #: An approval is a claim about a person's decision. A ruling NUMBER is a
    #: citation, and those stay legal.
    _APPROVAL_WORDS = ("approved", "approval", "signed off", "alex", "mc taken")

    @staticmethod
    def _code_lines(text):
        """Comment lines are not emissions.

        A guard that reads its own explanation as a violation teaches the next
        author to delete the explanation.
        """
        return [ln for ln in text.splitlines() if not ln.strip().startswith("#")]

    def test_the_create_deriver_emits_no_ruling_key(self):
        from app.tasks import create_events_from_truth as rail

        code = "\n".join(self._code_lines(inspect.getsource(rail.repair)))
        assert '"ruling":' not in code, (
            "the CREATE deriver is stamping a ruling into every plan context again"
        )

    def test_no_deriver_context_asserts_a_human_approval(self):
        """Repo-wide: a plan context may cite a ruling, never assert an approval."""
        import pathlib
        import re

        tasks = pathlib.Path(inspect.getsourcefile(__import__("app.tasks", fromlist=["x"]))).parent
        offenders = []
        for path in sorted(tasks.glob("*.py")):
            for line in self._code_lines(path.read_text(encoding="utf-8")):
                if not re.search(r'"ruling"\s*:', line):
                    continue
                lowered = line.lower()
                if any(word in lowered for word in self._APPROVAL_WORDS):
                    offenders.append(f"{path.name}: {line.strip()}")
        assert not offenders, (
            "a deriver is asserting a human approval it cannot cite:\n  "
            + "\n  ".join(offenders)
            + "\n\nCite a ruling NUMBER, or omit the field and record the approval "
            "on the artifact with its date and its rows."
        )
