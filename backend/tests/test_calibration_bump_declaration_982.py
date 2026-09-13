"""CAL-P982 (#1978): a version bump DECLARES the shrink it expects.

``evaluate_publish`` used to return the moment it saw a bumped
``population_version``::

    if verdict.version_bumped:
        return verdict

That is an UNBOUNDED escape. Every comparative rule — population drift,
per-category collapse, liquidity ordering — was waived by one string changing,
so a bump that meant to remove 21.7% and a bump that removed 97% were the same
artifact to this gate. The q269 batch is a *deliberate* shrink and genuinely
needs the escape; what it does not need is an escape with no ceiling.

This queue replaces it with a DECLARED bound: a bump that uses the escape states
the population move it expects, and a move materially past that statement is
refused BY NAME. The bump keeps its power to authorise a methodology change; it
loses its power to authorise an arbitrary one.

Both arms are asserted here on purpose. A guard that only proves "past the bound
is refused" passes on an implementation that refuses everything, which would
leave the page permanently dark on the very batch this exists to ship. Every
rule below is therefore paired: refuses OUTSIDE, admits INSIDE.

The ``_control_*`` tests are green in both arms — they encode behaviour this
queue must not disturb, and they are the tripwire for over-refusing.

New symbols are imported INSIDE each test: before the implementation lands, a
module-level import would turn the whole file (controls included) into a
collection error instead of a run of honest failures.
"""

from __future__ import annotations

import pytest

from app.utils.calibration_publish_gate import evaluate_publish
from tests.test_calibration_publish_gate_297 import payload

# The measured q269 batch, from the completed 128-unit rebuild of 2026-09-01
# (CAL-P211): 930,149 -> 728,641 outcomes, i.e. a 21.66% shrink, of which crypto
# 4,625 -> 0 (D12) and economics 43,270 -> 10,501 (RULE E).
#
# These three stay as they are. Most of this file exercises the GATE against a
# locally-built ``declared()``, and a real, well-understood transition is the
# best fixture for that — re-pointing every case at the current ship would cost
# the twenty cases their worked example and buy nothing. Only the one test that
# asserts the SHIPPED declaration end to end has to follow the ship; its numbers
# are below.
Q268_POPULATION = 930_149
Q269_POPULATION = 728_641
Q269_DROP_PCT = 21.66

# The SHIPPED transition (CAL-P1137, 2026-09-12): q269 -> q270, the one recount.
# ``Q269_PUBLISHED`` is what /api/calibration was actually serving when the
# declaration was written (read 22:44:48Z, ``generated_at`` 22:16:25Z);
# ``Q270_CANDIDATE`` is that total less the rows the two new predicates remove,
# measured event-atomically by ``scripts/calibration_population_move_5401.py``
# (receipts in ``artifacts/cal-p1137/``).
Q269_PUBLISHED = 798_292
Q270_REMOVED = 95_832
Q270_CANDIDATE = Q269_PUBLISHED - Q270_REMOVED
# CAL-P1138: q271 (D112) WIDENS — the first bump in this file's history that
# does. It admits the lone-claim pair, measured at 3,046 rows (an upper bound:
# they must still clear every other q271 filter), so the q269 -> q271 move is
# q270's shrink LESS that widening. This is the candidate the shipped q269 arm
# has to admit.
Q271_ADMITTED = 3_046
Q271_CANDIDATE = Q270_CANDIDATE + Q271_ADMITTED


def declared(
    *,
    from_version: str | None = "q268",
    expected_drop_pct: float = Q269_DROP_PCT,
    tolerance_pct: float = 3.0,
) -> dict:
    """The declaration a bumped candidate carries."""
    body: dict = {
        "expected_drop_pct": expected_drop_pct,
        "tolerance_pct": tolerance_pct,
    }
    if from_version is not None:
        body["from_version"] = from_version
    return body


def candidate(*, outcomes: int, version: str = "q269", declaration=..., **kw) -> dict:
    """A bumped candidate, optionally carrying a declaration."""
    from app.utils.calibration_publish_gate import DECLARATION_FIELD

    body = payload(outcomes=outcomes, version=version, **kw)
    if declaration is not ...:
        body[DECLARATION_FIELD] = declaration
    return body


def published(*, outcomes: int = Q268_POPULATION, version: str = "q268", **kw) -> dict:
    return payload(outcomes=outcomes, version=version, **kw)


# ---------------------------------------------------------------------------
# Arm 1 — a declared bump is REFUSED when the move lands materially past it
# ---------------------------------------------------------------------------


def test_declared_bump_refuses_a_shrink_materially_past_its_declaration():
    """The whole point: 21.7% was declared, 46% arrived, and it is refused."""
    verdict = evaluate_publish(
        candidate(outcomes=500_000, declaration=declared()),  # -46.2%
        published(),
    )

    assert not verdict.ok, "a bump past its own declaration must not publish"
    assert "version_bump_exceeds_declaration" in verdict.codes
    detail = verdict.summary()
    # Refused BY NAME: the reader must not have to re-derive either number.
    assert "21.66" in detail and "46." in detail, detail


def test_declared_bump_refuses_a_move_that_overshoots_in_the_GROWTH_direction():
    """A declaration bounds the move, not merely its downside.

    A bump that declared a shrink and delivered growth did not do what it said,
    and 'it went the nicer way' is not evidence that the predicate is right.
    """
    verdict = evaluate_publish(
        candidate(outcomes=1_400_000, declaration=declared()),  # +50%, not -21.7%
        published(),
    )

    assert not verdict.ok
    assert "version_bump_exceeds_declaration" in verdict.codes


def test_undeclared_bump_that_uses_the_escape_is_refused():
    """The unbounded escape itself — this is the line the queue removes."""
    verdict = evaluate_publish(
        candidate(outcomes=Q269_POPULATION, declaration=...),  # no declaration
        published(),
    )

    assert not verdict.ok, "an undeclared bump must no longer waive Rule 2"
    assert "version_bump_undeclared" in verdict.codes


def test_declaration_measured_against_a_DIFFERENT_baseline_is_refused():
    """CAL-P213's actual failure mode, as a gate rule.

    calibration-022 chained two population numbers measured on two different
    builds in two different failure states and read the difference as one
    continuous move. A declaration that names a baseline it was not measured
    against is that same mistake, pre-registered.
    """
    verdict = evaluate_publish(
        candidate(
            outcomes=Q269_POPULATION,
            declaration=declared(from_version="q267"),  # published is q268
        ),
        published(version="q268"),
    )

    assert not verdict.ok
    assert "version_declaration_stale" in verdict.codes
    assert "q267" in verdict.summary() and "q268" in verdict.summary()


@pytest.mark.parametrize(
    "bad, why",
    [
        ("21.7%", "not a mapping"),
        ({"tolerance_pct": 3.0}, "no expected_drop_pct"),
        ({"expected_drop_pct": 21.66}, "no tolerance_pct"),
        ({"expected_drop_pct": float("nan"), "tolerance_pct": 3.0}, "non-finite"),
        ({"expected_drop_pct": 21.66, "tolerance_pct": 0}, "zero tolerance"),
        ({"expected_drop_pct": 21.66, "tolerance_pct": -3.0}, "negative tolerance"),
    ],
)
def test_a_malformed_declaration_is_refused_rather_than_ignored(bad, why):
    """An unreadable declaration must not silently restore the old escape."""
    verdict = evaluate_publish(
        candidate(outcomes=Q269_POPULATION, declaration=bad), published()
    )

    assert not verdict.ok, f"{why}: a declaration that cannot be read must refuse"
    assert "version_declaration_malformed" in verdict.codes


def test_a_blank_cheque_tolerance_is_refused():
    """A declaration wide enough to admit anything is not a declaration."""
    from app.utils.calibration_publish_gate import DECLARATION_MAX_TOLERANCE_PCT

    verdict = evaluate_publish(
        candidate(
            outcomes=Q269_POPULATION,
            declaration=declared(tolerance_pct=DECLARATION_MAX_TOLERANCE_PCT + 0.1),
        ),
        published(),
    )

    assert not verdict.ok
    assert "version_declaration_malformed" in verdict.codes
    assert str(DECLARATION_MAX_TOLERANCE_PCT) in verdict.summary()


# ---------------------------------------------------------------------------
# Arm 2 — a declared bump is ADMITTED when the move lands inside it
# ---------------------------------------------------------------------------


def test_declared_bump_admits_the_shrink_it_declared():
    """The q269 batch itself. If this reddens, the queue's ship cannot sail."""
    verdict = evaluate_publish(
        candidate(outcomes=Q269_POPULATION, declaration=declared()), published()
    )

    assert verdict.ok, verdict.summary()
    assert verdict.version_bumped
    assert verdict.rejections == []


def test_an_admitted_bump_records_what_it_admitted():
    """An accepted escape that says nothing is the uncheckable-read-as-clean shape.

    The module already refuses to let Rule 2 admit a +17.9% move silently
    (``population_growth_acknowledged``); the bump escape is the larger hole and
    was doing exactly that.
    """
    verdict = evaluate_publish(
        candidate(outcomes=Q269_POPULATION, declaration=declared()), published()
    )

    assert verdict.ok, verdict.summary()
    assert "version_bump_within_declaration" in verdict.observation_codes
    detail = " ".join(o["detail"] for o in verdict.observations)
    assert "21.66" in detail, detail


@pytest.mark.parametrize("drop_pct", [21.66, 19.0, 24.3])
def test_declared_bump_admits_anything_inside_the_declared_band(drop_pct):
    """Declared 21.66 ±3.0 — the whole band publishes, not just the midpoint."""
    outcomes = round(Q268_POPULATION * (1 - drop_pct / 100))

    verdict = evaluate_publish(
        candidate(outcomes=outcomes, declaration=declared()), published()
    )

    assert verdict.ok, f"{drop_pct}% is inside 21.66 ±3.0: {verdict.summary()}"


def test_a_bump_that_does_not_use_the_escape_needs_no_declaration():
    """Declaring is the price of the ESCAPE, not a tax on renaming a version.

    A bump whose population move is inside the ordinary no-bump band waived
    nothing, so there is nothing for it to declare.
    """
    verdict = evaluate_publish(
        candidate(outcomes=int(Q268_POPULATION * 0.99), declaration=...), published()
    )

    assert verdict.ok, verdict.summary()
    assert verdict.version_bumped
    assert "version_bump_undeclared" not in verdict.codes


def test_a_declared_bump_still_waives_per_category_collapse():
    """Crypto goes 4,625 -> 0 by D12 and that is the RULING, not a defect.

    Rule 3 must stay waived under a declared bump — a methodology change
    reshapes cells by definition — otherwise the q269 batch collects ten
    ``category_collapse`` codes and can never publish. The per-category detail
    is RECORDED instead (see the ledger arm below).
    """
    verdict = evaluate_publish(
        candidate(
            outcomes=Q269_POPULATION,
            declaration=declared(),
            categories={"politics": 400_000, "sports": 324_016, "crypto": 4_625},
        ),
        published(
            categories={"politics": 400_000, "sports": 350_000, "crypto": 180_149}
        ),
    )

    assert verdict.ok, verdict.summary()
    assert "category_collapse" not in verdict.codes


# ---------------------------------------------------------------------------
# Arm 3 (the rider) — the ledger records WHAT fell, not just THAT it fell
# ---------------------------------------------------------------------------


def test_the_verdict_carries_the_per_category_diff_it_already_computes():
    """CAL-P213 sat legible in a Sentry message for four days.

    ``runner.outcome`` recorded ``gate = refuse`` and nothing about which cells
    moved. The gate computes that diff for the issue body and then throws it
    away; this makes it a first-class field.
    """
    verdict = evaluate_publish(
        candidate(
            outcomes=Q269_POPULATION,
            declaration=declared(),
            categories={"politics": 400_000, "sports": 324_016, "crypto": 4_625},
        ),
        published(
            categories={"politics": 400_000, "sports": 350_000, "crypto": 180_149}
        ),
    )

    by_name = {row["category"]: row for row in verdict.category_diff}

    assert by_name["crypto"]["previous"] == 180_149
    assert by_name["crypto"]["candidate"] == 4_625
    assert by_name["crypto"]["delta"] == 4_625 - 180_149
    assert by_name["crypto"]["drop_pct"] == pytest.approx(97.43, abs=0.01)
    # Biggest absolute mover first: a truncated read still sees what mattered.
    assert verdict.category_diff[0]["category"] == "crypto"


def test_a_category_that_APPEARS_is_in_the_diff_too():
    """A cell arriving is a methodology change as much as a cell leaving."""
    verdict = evaluate_publish(
        candidate(
            outcomes=Q269_POPULATION,
            declaration=declared(),
            categories={"politics": 400_000, "esports": 328_641},
        ),
        published(categories={"politics": 930_149}),
    )

    by_name = {row["category"]: row for row in verdict.category_diff}
    assert by_name["esports"]["previous"] == 0
    assert by_name["esports"]["candidate"] == 328_641


def test_the_ledger_record_names_the_cells_and_never_drops_them_silently():
    """Bounded, but never silently — an omitted tail states its own size."""
    from app.utils.calibration_publish_gate import (
        LEDGER_CATEGORY_DIFF_LIMIT,
        gate_ledger_record,
    )

    n = LEDGER_CATEGORY_DIFF_LIMIT + 5
    prev_cats = {f"cat{i:03d}": 1_000 * (n - i) for i in range(n)}
    cand_cats = {f"cat{i:03d}": 1 for i in range(n)}

    verdict = evaluate_publish(
        candidate(
            outcomes=sum(cand_cats.values()),
            declaration=declared(expected_drop_pct=99.99, tolerance_pct=0.5),
            categories=cand_cats,
        ),
        published(outcomes=sum(prev_cats.values()), categories=prev_cats),
    )
    record = gate_ledger_record(verdict)

    assert len(record["category_diff"]) == LEDGER_CATEGORY_DIFF_LIMIT
    assert record["category_diff_omitted"] == 5
    # The tail is summarised, not vanished.
    assert record["category_diff_omitted_outcomes"] > 0


def test_the_ledger_record_survives_json_round_trip():
    """It is persisted into ``calibration:main:phase_ledger``; it must serialise."""
    import json

    from app.utils.calibration_publish_gate import gate_ledger_record

    verdict = evaluate_publish(
        candidate(outcomes=500_000, declaration=declared()), published()
    )
    record = gate_ledger_record(verdict)

    assert json.loads(json.dumps(record)) == record
    assert record["codes"] == verdict.codes


def test_the_producer_persists_the_gate_diff_onto_the_run_outcome():
    """The diff has to reach the ledger, not merely exist on the verdict.

    ``save_phase_ledger`` persists ``runner.outcome``; a field the producer
    never copies there is a field no later reader can query.
    """
    import inspect

    import app.tasks.precompute_calibration as pc

    source = inspect.getsource(pc._run_calibration_main_build)

    assert "gate_ledger_record" in source, (
        "the producer must copy the gate's ledger record onto runner.outcome — "
        "otherwise the per-category diff dies with the process"
    )


def test_the_producer_declares_the_bump_it_is_currently_shipping():
    """A bound with no way to declare is a trap, not a guard.

    If ``CALIBRATION_POPULATION_VERSION`` is bumped but the producer emits no
    declaration, every rebuild is refused ``version_bump_undeclared`` forever —
    the same forever-refusal shape q269 exists to escape, just with a new code.
    So: whenever the shipped version is one the gate will treat as a bump, the
    producer must state its expected move.
    """
    import app.tasks.precompute_calibration as pc

    # CAL-P1138: the producer now ships an ARM PER BASELINE (q271 was written
    # while its own predecessor q270 had merged but not yet published, so which
    # artifact it replaces is not knowable at edit time). The bound this test
    # defends is unchanged — it just has to hold for the arm that will actually
    # be stamped. The one that matters is the LAST PUBLISHED version: if that
    # transition declares nothing while moving past the ordinary band, every
    # rebuild is refused forever, which is the trap this test exists for.
    declaration = pc._declaration_for_baseline(
        pc.PREVIOUS_PUBLISHED_POPULATION_VERSION
    )
    assert declaration is not None, (
        "the shipped build bumps the population version away from the artifact "
        "that is actually published, so it must declare the move it expects"
    )
    # It has to be a declaration the GATE accepts, not merely a dict.
    from app.utils.calibration_publish_gate import _read_declaration

    parsed, problem = _read_declaration(declaration)
    assert problem is None, problem
    # `from_version` names the artifact the shrink was MEASURED AGAINST — the
    # one being replaced. That is a different question from
    # COMPATIBLE_PREVIOUS_POPULATION_VERSIONS, which names artifacts still safe
    # to SERVE while the new build runs, and which is deliberately EMPTY under
    # q269 because q268 is exactly what q269 declares incomparable. Asserting
    # membership there would demand the declaration name a version the build
    # says it cannot compare with — the two lists must not be conflated.
    assert isinstance(parsed["from_version"], str) and parsed["from_version"]
    assert parsed["from_version"] != pc.CALIBRATION_POPULATION_VERSION, (
        "a bump cannot declare itself as its own baseline"
    )


def test_the_shipped_declaration_admits_the_measured_rebuild():
    """The ship itself, end to end: the real numbers must publish.

    This is the one test in the file that reads the SHIPPED constant rather than
    a locally-built declaration, so it is re-aimed at whatever transition is
    currently on the wire — today q269 -> q270, the one recount. If the shipped
    declaration cannot admit the move its own branch measured, the bump turns
    the publish from 'refused for not declaring' into 'refused for
    mis-declaring', which is not an improvement, and the refusal CLEARS THE
    CHECKPOINT so every later rebuild is binned too.
    """
    import app.tasks.precompute_calibration as pc

    verdict = evaluate_publish(
        candidate(
            outcomes=Q271_CANDIDATE,
            version=pc.CALIBRATION_POPULATION_VERSION,
            declaration=pc._declaration_for_baseline(
                pc.PREVIOUS_PUBLISHED_POPULATION_VERSION
            ),
        ),
        published(
            outcomes=Q269_PUBLISHED,
            version=pc.PREVIOUS_PUBLISHED_POPULATION_VERSION,
        ),
    )

    assert verdict.ok, verdict.summary()
    assert "version_bump_within_declaration" in verdict.observation_codes


def test_the_shipped_declaration_still_refuses_a_move_it_did_not_declare():
    """The re-aim above must not have widened the band into a blank cheque.

    Same shipped declaration, a candidate that removes twice what the branch
    measured. If this passes, the tolerance is doing nothing and the test above
    is asserting only that a number is a number.
    """
    import app.tasks.precompute_calibration as pc

    verdict = evaluate_publish(
        candidate(
            outcomes=Q269_PUBLISHED - (Q270_REMOVED * 2),
            version=pc.CALIBRATION_POPULATION_VERSION,
            declaration=pc._declaration_for_baseline(
                pc.PREVIOUS_PUBLISHED_POPULATION_VERSION
            ),
        ),
        published(
            outcomes=Q269_PUBLISHED,
            version=pc.PREVIOUS_PUBLISHED_POPULATION_VERSION,
        ),
    )

    assert not verdict.ok, verdict.summary()
    assert "version_bump_exceeds_declaration" in verdict.codes


def test_the_declaration_is_stamped_before_the_payload_is_serialised():
    """It must be in the BYTES that publish, not only in what the gate saw.

    ``payload_json = json.dumps(response)`` runs before the gate; a declaration
    stamped after it would be judged and then not published, so the artifact on
    the page would not carry the statement it was admitted on.
    """
    import inspect

    import app.tasks.precompute_calibration as pc

    source = inspect.getsource(pc._run_calibration_main_build)
    # CAL-P1138: the stamp is now the call that SELECTS the arm. It moved down,
    # to just after `baseline_read` (the arm depends on which artifact is being
    # replaced, which the build does not know until it has read one) — but it
    # still has to land before serialisation, which is the whole of this test.
    stamp = source.index("_declaration_for_baseline")
    serialise = source.index("payload_json = json.dumps(response)")

    assert stamp < serialise, (
        "the declaration is stamped after serialisation — the gate would see it "
        "but the published bytes would not carry it"
    )


def test_the_ledger_rider_did_not_move_the_build_input_fingerprint():
    """The bank must survive this queue.

    ``_main_input_fingerprint`` hashes the SOURCE of four build functions plus a
    named constant list. The producer edit this queue makes is in
    ``_run_calibration_main_build``, which is none of them — so the 128-unit
    staged-futures bank is NOT discarded. Asserted rather than assumed, because
    getting it wrong costs a ~2.5h rebuild.
    """
    import inspect

    import app.tasks.precompute_calibration as pc

    hashed = (
        inspect.getsource(pc.compute_calibration_payload)
        + inspect.getsource(pc._calibration_population_ctes)
        + inspect.getsource(pc._virtual_market_ctes)
        + inspect.getsource(pc._main_futures_sql)
    )

    for symbol in ("gate_ledger_record", "CALIBRATION_POPULATION_DECLARATION"):
        assert symbol not in hashed, (
            f"{symbol} landed inside a fingerprinted function — that resets the "
            "checkpoint cursor and bins the staged-futures bank"
        )

    # And the constant must not be hashed BY VALUE either: it is publish-time
    # metadata about a version transition, not something that shapes which rows
    # qualify, so listing it would spend a ~2.5h rebuild on a comment-level edit.
    assert "CALIBRATION_POPULATION_DECLARATION" not in inspect.getsource(
        pc._main_input_fingerprint
    )


# ---------------------------------------------------------------------------
# Controls — green in BOTH arms. These are the over-refusal tripwire.
# ---------------------------------------------------------------------------


def test_control_a_healthy_unbumped_build_still_publishes():
    assert evaluate_publish(payload(outcomes=1_010_000), payload()).ok


def test_control_an_unbumped_shrink_is_still_refused_by_rule_2():
    verdict = evaluate_publish(payload(outcomes=600_000), payload())

    assert not verdict.ok
    assert "population_shrink" in verdict.codes


def test_control_a_bump_still_does_not_excuse_an_incomplete_build():
    verdict = evaluate_publish(
        payload(
            outcomes=Q269_POPULATION, version="q269", drop_sections=("by_category",)
        ),
        payload(outcomes=Q268_POPULATION, version="q268"),
    )

    assert not verdict.ok
    assert "incomplete_sections" in verdict.codes


def test_control_a_first_publish_is_still_granted_on_a_proved_cold_start():
    """The page must never be left dark by this queue."""
    from app.utils.calibration_durable_baseline import COLD_START, BaselineProbe

    verdict = evaluate_publish(
        payload(version="q269"),
        None,
        durable_probe=lambda: BaselineProbe(COLD_START, detail="no durable row"),
    )

    assert verdict.ok, verdict.summary()
    assert verdict.first_publish


# ---------------------------------------------------------------------------
# CAL-P1138: LATE-BOUND DECLARATIONS — an arm per baseline, chosen by the gate.
# ---------------------------------------------------------------------------


class TestTheDeclarationArmMatchesTheBaselineBeingReplaced:
    """q271 was written while its own predecessor had not published.

    q270 merged and went live on the web at 04:48Z 2026-09-13, but the producer
    is a HEAVY_TASK and `bainluck-heavy` had not taken the sha, so /calibration
    was still dark and the last PUBLISHED artifact was still q269. Whether q271
    replaces q269 or q270 is therefore a fact about an attended redeploy on
    another app, decided after this code was written.

    The two transitions are ~12pp apart (q271 GROWS ~0.76% over q270; it is
    q270's ~12% shrink less that widening over q269), so no single declaration
    covers both: one band spanning them needs +/-6.0, past
    DECLARATION_MAX_TOLERANCE_PCT. And guessing is the expensive way to be
    wrong — a mis-declaration is refused, and a refusal CLEARS THE CHECKPOINT,
    binning every later rebuild until another deploy.
    """

    def test_replacing_the_version_that_is_actually_published_is_admitted(self):
        import app.tasks.precompute_calibration as pc

        verdict = evaluate_publish(
            candidate(
                outcomes=Q271_CANDIDATE,
                version=pc.CALIBRATION_POPULATION_VERSION,
                declaration=None,
            ),
            published(outcomes=Q269_PUBLISHED, version="q269"),
            declaration_for_baseline=pc._declaration_for_baseline,
        )

        assert verdict.ok, verdict.summary()
        assert "version_bump_within_declaration" in verdict.observation_codes

    def test_replacing_q270_needs_no_declaration_and_is_still_admitted(self):
        """The widening is inside the gate's ordinary band, so it waives nothing.

        This is the arm that is deliberately ``None``. Declaring is the price of
        the escape, not a tax on renaming a version — and stating a number here
        would invite the size test on a move that never needed it.
        """
        import app.tasks.precompute_calibration as pc

        q270_published = Q270_CANDIDATE
        verdict = evaluate_publish(
            candidate(
                outcomes=q270_published + Q271_ADMITTED,
                version=pc.CALIBRATION_POPULATION_VERSION,
                declaration=None,
            ),
            published(outcomes=q270_published, version="q270"),
            declaration_for_baseline=pc._declaration_for_baseline,
        )

        assert verdict.ok, verdict.summary()
        assert "version_bump_used_no_escape" in verdict.observation_codes

    def test_the_wrong_arm_would_have_been_refused(self):
        """The pairing that makes the two tests above mean something.

        If either arm could publish against the other's baseline, the whole
        mechanism is decoration — one constant would have done. Here the q269
        arm is applied to a q270 baseline explicitly, which is what a single
        hard-coded declaration would have done on the day q270 published.
        """
        import app.tasks.precompute_calibration as pc

        q269_arm = pc._declaration_for_baseline("q269")
        assert q269_arm is not None

        q270_published = Q270_CANDIDATE
        verdict = evaluate_publish(
            candidate(
                outcomes=q270_published + Q271_ADMITTED,
                version=pc.CALIBRATION_POPULATION_VERSION,
                declaration=q269_arm,
            ),
            published(outcomes=q270_published, version="q270"),
        )

        assert not verdict.ok, verdict.summary()
        assert "version_declaration_stale" in verdict.codes

    def test_an_unforeseen_baseline_gets_the_strict_rule_not_a_borrowed_number(self):
        """Fail to the strict side.

        A baseline this bump never reasoned about must not inherit whichever arm
        happens to be lying around — that is the "shrink measured on one build
        applied to another" failure the gate names. With no arm the ordinary
        +/-5% band applies, so a large move is refused BY NAME rather than waved
        through on someone else's measurement.
        """
        import app.tasks.precompute_calibration as pc

        assert pc._declaration_for_baseline("q999") is None
        assert pc._declaration_for_baseline(None) is None

        verdict = evaluate_publish(
            candidate(
                outcomes=Q271_CANDIDATE,
                version=pc.CALIBRATION_POPULATION_VERSION,
                declaration=None,
            ),
            published(outcomes=Q269_PUBLISHED, version="q999"),
            declaration_for_baseline=pc._declaration_for_baseline,
        )

        assert not verdict.ok, verdict.summary()
        assert "version_bump_undeclared" in verdict.codes

    def test_a_pre_stamped_declaration_is_never_overridden(self):
        """Every existing single-declaration build behaves exactly as before.

        The resolver is consulted ONLY when the candidate carries no declaration
        of its own. A caller that knows its own transition keeps deciding it.
        """
        import app.tasks.precompute_calibration as pc

        sentinel_calls = []

        def _resolver(version):
            sentinel_calls.append(version)
            return {"from_version": version, "expected_drop_pct": 0.0, "tolerance_pct": 1.0}

        evaluate_publish(
            candidate(
                outcomes=Q271_CANDIDATE,
                version=pc.CALIBRATION_POPULATION_VERSION,
                declaration=pc._declaration_for_baseline("q269"),
            ),
            published(outcomes=Q269_PUBLISHED, version="q269"),
            declaration_for_baseline=_resolver,
        )

        assert sentinel_calls == [], (
            "the resolver was consulted on a candidate that already declared its "
            "own move — a pre-stamped declaration must win"
        )

    def test_the_chosen_arm_lands_in_the_payload_that_publishes(self):
        """A declaration judged but not published is a number with no warrant.

        The gate writes the arm it used back into the candidate payload, and the
        producer serialises AFTER the gate for exactly this reason. Without it
        the page would carry a version bump whose stated expectation exists
        nowhere in the artifact.
        """
        import app.tasks.precompute_calibration as pc
        from app.utils.calibration_publish_gate import DECLARATION_FIELD

        payload = candidate(
            outcomes=Q271_CANDIDATE,
            version=pc.CALIBRATION_POPULATION_VERSION,
            declaration=None,
        )
        assert payload.get(DECLARATION_FIELD) is None

        evaluate_publish(
            payload,
            published(outcomes=Q269_PUBLISHED, version="q269"),
            declaration_for_baseline=pc._declaration_for_baseline,
        )

        assert payload[DECLARATION_FIELD] == pc._declaration_for_baseline("q269")

    def test_the_resolver_returns_a_copy_so_the_constant_cannot_be_mutated(self):
        """The arms are module constants shared by every beat in the process."""
        import app.tasks.precompute_calibration as pc

        first = pc._declaration_for_baseline("q269")
        first["expected_drop_pct"] = 99.0
        assert pc._declaration_for_baseline("q269")["expected_drop_pct"] != 99.0

    def test_a_raising_resolver_costs_a_publish_and_never_buys_one(self):
        """Best-effort must mean strict, not permissive."""
        import app.tasks.precompute_calibration as pc

        def _boom(_version):
            raise RuntimeError("durable store unreadable")

        verdict = evaluate_publish(
            candidate(
                outcomes=Q271_CANDIDATE,
                version=pc.CALIBRATION_POPULATION_VERSION,
                declaration=None,
            ),
            published(outcomes=Q269_PUBLISHED, version="q269"),
            declaration_for_baseline=_boom,
        )

        assert not verdict.ok
        assert "version_bump_undeclared" in verdict.codes
        # And it is NAMED, not swallowed: "the resolver broke" and "this bump
        # had nothing to declare" reach the same verdict and are different
        # findings, so the run evidence has to tell them apart.
        assert "version_declaration_resolver_failed" in verdict.observation_codes
