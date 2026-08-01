"""Queue 297: the atomic publish gate + fail-honest serving contract for /api/calibration.

Two pure surfaces, no I/O, so both the publisher and the route can share exactly
one definition of "is this snapshot trustworthy":

* :func:`snapshot_verdict` — READ side. Is a cached payload shape-valid,
  version-compatible and age-bounded? The route uses it so a malformed, wrong-
  version or ancient ``last_good`` is never dressed up as the current curve.
* :func:`evaluate_publish` — WRITE side. Compare a freshly computed *candidate*
  against the currently *published* artifact and decide whether it may replace
  it. The publisher builds under a candidate key, validates, and only then does
  one atomic publication of ``main`` + ``last_good``.

Why this exists
---------------
Queue 272 already refused to publish an *empty* payload. It could not refuse a
payload that was complete-looking but wrong: a build that silently lost two
thirds of the population, or one whose well-traded/thin accuracy ordering
inverted, published cleanly and replaced the good copy. Alex found both by
reading the public page. This gate turns those into a rejected candidate, a
preserved last-good, and one deduped issue the same day.

Everything here is read-side/publish-side only. Nothing mutates data, re-grades
an outcome, or changes a threshold, filter or methodology (gotcha #21).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# --------------------------------------------------------------------------
# Contract constants
# --------------------------------------------------------------------------

#: Sections a complete main payload must carry. A candidate missing any of these
#: is an incomplete build (a phase died mid-compute), not a smaller population.
#: Deliberately the *structural* sections — adding a new filter block must not
#: retroactively reject every prior artifact, so this list is the floor, not the
#: full key set.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "buckets",
    "by_category",
    "by_source",
    "total_outcomes",
    "total_markets",
    "total_winners",
    "generated_at",
    "liquidity_filter",
    "mex_normalization",
    "truth_evidence",
)

#: Population may drift this much between builds without an explicit version
#: bump. Resolution genuinely adds outcomes hour over hour; ±5% is far above the
#: organic rate and far below the ~3x collapse that motivated this gate.
POPULATION_TOLERANCE = 0.05

#: A single category losing more than this share of its outcomes is a cohort
#: collapse (the cricket canary), even when the total looks fine.
CATEGORY_DROP_TOLERANCE = 0.20

#: A category must have at least this many outcomes in the PUBLISHED artifact
#: before its drop is judged. Below it, ordinary resolution churn swamps the
#: percentage and the check would be noise, not signal. Value fixed by the
#: contract corpus (``category_min_n``).
CATEGORY_MIN_N = 1000

#: A category whose ECE regresses by more than this many points is a cohort
#: quality collapse even when its sample size held. From the contract corpus
#: (``category_ece_regression_pp``).
CATEGORY_ECE_REGRESSION_PP = 5.0

#: Floor for the well-traded/thin ordering tolerance, from the contract corpus
#: (``tier_inversion_tolerance_pp``). The queue additionally requires the
#: tolerance be derived from real uncertainty rather than guessed, so the
#: effective tolerance is ``max(this floor, the cohorts' combined Wilson
#: half-width)`` — never looser than the contract, and wider when the sample is
#: genuinely too thin to support the claim.
TIER_INVERSION_TOLERANCE_FLOOR_PP = 0.5

#: The versioned contract this gate implements. Kept in lockstep with
#: ``backend/tests/evals/fixtures/calibration_publish_gate_contract.json``; the
#: corpus is the spec, this module is the production wiring against the real
#: payload shape (``by_category``/``by_source`` rather than the corpus's
#: synthetic ``categories``/``sources``).
CONTRACT_VERSION = "calibration-publish-gate/v1"

#: How old a ``last_good`` snapshot may be and still be served (with a dated
#: degraded banner). Matches the durable key's 7d TTL: past that the key is gone
#: anyway, so this bound is what makes the *process-local* copy honest too.
SERVE_MAX_AGE_S = 7 * 86400

#: Below this the well-traded/thin comparison is not asserted at all — the
#: rendered claim needs both cohorts to be real before an inversion means
#: anything.
COHORT_MIN_N = 1000


# --------------------------------------------------------------------------
# Read side — is a cached snapshot trustworthy?
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotVerdict:
    """Why a cached calibration snapshot may or may not be served."""

    status: str  # "ok" | "malformed" | "wrong_version" | "too_old"
    reason: str
    age_s: Optional[float] = None
    generated_at: Optional[str] = None
    population_version: Optional[str] = None

    @property
    def is_servable(self) -> bool:
        return self.status == "ok"


def _parse_generated_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    raw = value.strip()
    # ``datetime.fromisoformat`` on 3.11 handles offsets but not a trailing Z.
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def snapshot_verdict(
    payload: Any,
    *,
    expected_version: Optional[str],
    now: Optional[datetime] = None,
    max_age_s: float = SERVE_MAX_AGE_S,
) -> SnapshotVerdict:
    """Classify a cached snapshot before it is served to the public page.

    A snapshot is servable only when it is shape-valid (the structural sections
    are present and the curve is non-empty), carries the population version this
    build understands, and has a parseable ``generated_at`` inside ``max_age_s``.

    ``expected_version`` of ``None`` disables the version check — used by tests
    and by any consumer that deliberately accepts cross-version artifacts. A
    payload that carries NO version at all is accepted when a version is
    expected: historical artifacts predate the field, and rejecting them would
    blank the page for a reason that is not a data problem.
    """
    if not isinstance(payload, dict):
        return SnapshotVerdict("malformed", "payload is not an object")

    missing = [s for s in REQUIRED_SECTIONS if s not in payload]
    if missing:
        return SnapshotVerdict(
            "malformed", f"missing required sections: {', '.join(sorted(missing))}"
        )

    buckets = payload.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        return SnapshotVerdict("malformed", "buckets is empty or not a list")

    total = payload.get("total_outcomes")
    if not isinstance(total, (int, float)) or total <= 0:
        return SnapshotVerdict("malformed", "total_outcomes is missing or non-positive")

    version = payload.get("population_version")
    if (
        expected_version is not None
        and version is not None
        and version != expected_version
    ):
        return SnapshotVerdict(
            "wrong_version",
            f"snapshot population_version {version!r} != expected {expected_version!r}",
            population_version=version,
            generated_at=payload.get("generated_at"),
        )

    generated = _parse_generated_at(payload.get("generated_at"))
    if generated is None:
        return SnapshotVerdict(
            "malformed",
            "generated_at is missing or unparseable",
            population_version=version,
        )

    reference = now or datetime.now(timezone.utc)
    age_s = (reference - generated).total_seconds()
    # A small negative age is clock skew between the worker and the web dyno, not
    # a defect; a large one means the timestamp is not describing this build.
    if age_s < -3600:
        return SnapshotVerdict(
            "malformed",
            f"generated_at is {abs(round(age_s))}s in the future",
            age_s=age_s,
            generated_at=payload.get("generated_at"),
            population_version=version,
        )
    if age_s > max_age_s:
        return SnapshotVerdict(
            "too_old",
            f"snapshot is {round(age_s / 3600, 1)}h old (limit {round(max_age_s / 3600, 1)}h)",
            age_s=age_s,
            generated_at=payload.get("generated_at"),
            population_version=version,
        )

    return SnapshotVerdict(
        "ok",
        "shape-valid, version-compatible, within age bound",
        age_s=age_s,
        generated_at=payload.get("generated_at"),
        population_version=version,
    )


# --------------------------------------------------------------------------
# Census — the comparable fingerprint of one artifact
# --------------------------------------------------------------------------


def _wilson_half_width(winners: int, n: int, z: float = 1.96) -> float:
    """Half-width of the Wilson score interval, as a proportion.

    The same interval ``precompute_calibration._wilson_ci`` puts on every
    published bucket, re-derived here so this module stays import-free of the
    task layer. Sample-size aware by construction: a thin bucket gets a wide
    interval, so a thin cohort cannot trip the ordering check on noise.
    """
    if n <= 0:
        return 1.0
    p = winners / n
    denom = 1 + z * z / n
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return margin


def _cohort_stats(buckets: list[dict], *, well_traded: bool) -> dict:
    """Aggregate one trading-activity cohort exactly as the page renders it.

    ``frontend/app/calibration/page.tsx`` splits on ``price_moved``: the
    well-traded curve is ``price_moved !== false`` (real trades plus sportsbook
    consensus, which carries no flag) and the thin curve is
    ``price_moved === false``. The gate must judge the claim the reader sees, so
    it uses the same predicate rather than the payload's precomputed
    ``mce_closing_line`` / ``mce_opening_price`` pair, which splits strictly on
    ``True`` / ``False`` and drops the untagged rows.
    """
    agg: dict[Any, dict] = {}
    for b in buckets:
        if not isinstance(b, dict):
            continue
        moved = b.get("price_moved")
        in_cohort = (moved is not False) if well_traded else (moved is False)
        if not in_cohort:
            continue
        idx = b.get("bucket_idx")
        slot = agg.setdefault(idx, {"n": 0, "winners": 0, "sum_prob": 0.0})
        slot["n"] += b.get("n") or 0
        slot["winners"] += b.get("winners") or 0
        slot["sum_prob"] += float(b.get("sum_prob") or 0.0)

    populated = [v for v in agg.values() if v["n"] > 0]
    total_n = sum(v["n"] for v in populated)
    if not populated or total_n <= 0:
        return {"n": 0, "mce_pp": None, "tolerance_pp": None, "buckets": 0}

    abs_err = 0.0
    half_widths = 0.0
    for v in populated:
        avg_prob = v["sum_prob"] / v["n"]
        actual = v["winners"] / v["n"]
        abs_err += abs(actual - avg_prob)
        half_widths += _wilson_half_width(v["winners"], v["n"])

    k = len(populated)
    return {
        "n": total_n,
        "buckets": k,
        # Equal-per-bucket MCE, matching the published cohort metric.
        "mce_pp": round(abs_err / k * 100, 3),
        # Mean Wilson half-width over the cohort's buckets, in percentage points:
        # how much this cohort's MCE could move on sampling noise alone.
        "tolerance_pp": round(half_widths / k * 100, 3),
    }


def census(payload: Any) -> dict:
    """Reduce an artifact to the numbers the gate compares.

    Tolerant by design — a malformed payload yields a census with
    ``sections_missing`` populated rather than raising, so the caller reports a
    rejection instead of dying inside the publisher.
    """
    if not isinstance(payload, dict):
        return {
            "population": None,
            "markets": None,
            "winners": None,
            "population_version": None,
            "generated_at": None,
            "bucket_rows": 0,
            "categories": {},
            "category_ece": {},
            "duplicate_categories": [],
            "nonfinite_fields": [],
            "sections_missing": list(REQUIRED_SECTIONS),
            "cohorts": {},
        }

    buckets = payload.get("buckets") if isinstance(payload.get("buckets"), list) else []

    categories: dict[str, int] = {}
    category_ece: dict[str, float] = {}
    duplicate_categories: list[str] = []
    nonfinite_fields: list[str] = []
    by_category = payload.get("by_category")
    if isinstance(by_category, list):
        for row in by_category:
            if not isinstance(row, dict):
                continue
            name = row.get("category") or row.get("name")
            n = row.get("outcomes")
            if n is None:
                n = row.get("n")
            if not isinstance(name, str) or not isinstance(n, (int, float)):
                continue
            # A category appearing twice means the build double-counted it; the
            # totals then disagree with the rows and every ratio below is wrong.
            if name in categories:
                duplicate_categories.append(name)
            if isinstance(n, float) and not math.isfinite(n):
                nonfinite_fields.append(f"by_category[{name}].n")
                continue
            categories[name] = int(n)
            ece = row.get("ece")
            if isinstance(ece, (int, float)):
                if math.isfinite(ece):
                    category_ece[name] = float(ece)
                else:
                    nonfinite_fields.append(f"by_category[{name}].ece")

    for field_name in ("total_outcomes", "total_markets", "total_winners"):
        value = payload.get(field_name)
        if isinstance(value, float) and not math.isfinite(value):
            nonfinite_fields.append(field_name)

    well = _cohort_stats(buckets, well_traded=True)
    thin = _cohort_stats(buckets, well_traded=False)

    return {
        "population": payload.get("total_outcomes"),
        "markets": payload.get("total_markets"),
        "winners": payload.get("total_winners"),
        "population_version": payload.get("population_version"),
        "generated_at": payload.get("generated_at"),
        "bucket_rows": len(buckets),
        "categories": categories,
        "category_ece": category_ece,
        "duplicate_categories": sorted(set(duplicate_categories)),
        "nonfinite_fields": sorted(set(nonfinite_fields)),
        "sections_missing": [s for s in REQUIRED_SECTIONS if s not in payload],
        "cohorts": {"well_traded": well, "thin": thin},
    }


def _ordering(well: dict, thin: dict) -> Optional[str]:
    """Which cohort the artifact claims is better calibrated (lower MCE is better).

    ``None`` when the claim is not asserted: a missing cohort, a cohort below
    ``COHORT_MIN_N``, or a gap inside the combined sampling tolerance. Refusing
    to name an ordering is what keeps the check from firing on noise.
    """
    w_mce, t_mce = well.get("mce_pp"), thin.get("mce_pp")
    if w_mce is None or t_mce is None:
        return None
    if (well.get("n") or 0) < COHORT_MIN_N or (thin.get("n") or 0) < COHORT_MIN_N:
        return None
    # Independent cohorts: combine their sampling tolerances in quadrature, and
    # never go below the contract's fixed floor.
    w_tol = well.get("tolerance_pp") or 0.0
    t_tol = thin.get("tolerance_pp") or 0.0
    tolerance = max(TIER_INVERSION_TOLERANCE_FLOOR_PP, math.sqrt(w_tol**2 + t_tol**2))
    gap = t_mce - w_mce
    if abs(gap) <= tolerance:
        return None
    return "well_traded_better" if gap > 0 else "thin_better"


@dataclass
class PublishVerdict:
    """The decision, the evidence behind it, and a stable alert fingerprint."""

    ok: bool
    rejections: list[dict] = field(default_factory=list)
    candidate: dict = field(default_factory=dict)
    published: dict = field(default_factory=dict)
    version_bumped: bool = False
    first_publish: bool = False

    @property
    def codes(self) -> list[str]:
        return sorted({r["code"] for r in self.rejections})

    @property
    def fingerprint(self) -> str:
        """Stable across repeated builds of the SAME failure class.

        Keyed on the rejection codes plus the versions involved — deliberately
        NOT on the changing counts, so an hourly beat that keeps producing the
        same bad shape comments on one issue instead of filing a new one every
        hour.
        """
        basis = "|".join(
            [
                "calibration-publish-gate",
                ",".join(self.codes) or "ok",
                str(self.published.get("population_version")),
                str(self.candidate.get("population_version")),
            ]
        )
        return hashlib.sha256(basis.encode()).hexdigest()[:16]

    def summary(self) -> str:
        if self.ok:
            return "publish gate passed"
        return "; ".join(r["detail"] for r in self.rejections)


def evaluate_publish(candidate: Any, published: Any) -> PublishVerdict:
    """Decide whether ``candidate`` may replace ``published``.

    Rejects when:

    1. the candidate is structurally incomplete (missing sections, empty curve,
       non-positive population) — a build that died mid-flight;
    2. population moved more than ±5% without a ``population_version`` bump;
    3. any sufficiently-large category lost more than 20% of its outcomes
       without a version bump;
    4. the well-traded/thin accuracy ordering flipped by more than the combined
       sampling tolerance, without a version bump.

    An explicit version bump is the operator's way of saying "this change is
    intended" — it suppresses 2-4 but never 1: an incomplete build is never
    publishable, whatever the version says.

    With no prior artifact (cold Redis, first publish after a flush) only rule 1
    applies. Refusing the first publish would leave the page permanently dark,
    which is the failure this whole queue exists to end.
    """
    cand = census(candidate)
    prev = census(published)
    verdict = PublishVerdict(ok=True, candidate=cand, published=prev)

    def reject(code: str, detail: str, **extra: Any) -> None:
        verdict.ok = False
        verdict.rejections.append({"code": code, "detail": detail, **extra})

    # --- Rule 1: structural completeness (never waived by a version bump) ---
    if cand["sections_missing"]:
        reject(
            "incomplete_sections",
            "candidate is missing required sections: "
            + ", ".join(sorted(cand["sections_missing"])),
            missing=sorted(cand["sections_missing"]),
        )
    if not cand["bucket_rows"]:
        reject("empty_curve", "candidate carries no buckets")
    if cand["duplicate_categories"]:
        reject(
            "duplicate_category",
            "candidate lists the same category twice (the build double-counted it, "
            "so its totals and rows disagree): "
            + ", ".join(cand["duplicate_categories"]),
            categories=cand["duplicate_categories"],
        )
    if cand["nonfinite_fields"]:
        reject(
            "nonfinite_value",
            "candidate carries NaN/Inf in: " + ", ".join(cand["nonfinite_fields"]),
            fields=cand["nonfinite_fields"],
        )
    cand_pop = cand["population"]
    if not isinstance(cand_pop, (int, float)) or cand_pop <= 0:
        reject(
            "empty_population",
            f"candidate total_outcomes is {cand_pop!r} (must be a positive number)",
        )

    prev_pop = prev["population"]
    have_baseline = (
        isinstance(published, dict)
        and isinstance(prev_pop, (int, float))
        and prev_pop > 0
        and not prev["sections_missing"]
    )
    if not have_baseline:
        # Nothing trustworthy to diff against. Structural checks above still
        # decided it; comparative rules simply do not apply.
        verdict.first_publish = True
        return verdict

    verdict.version_bumped = (
        cand["population_version"] != prev["population_version"]
        and cand["population_version"] is not None
    )

    # A structurally broken candidate is already rejected; skip the comparative
    # rules so the report names the real defect instead of its downstream noise.
    if not verdict.ok:
        return verdict

    if verdict.version_bumped:
        return verdict

    # --- Rule 2: population drift ---
    drift = (cand_pop - prev_pop) / prev_pop
    if abs(drift) > POPULATION_TOLERANCE:
        reject(
            "population_drift",
            f"population moved {drift * 100:+.1f}% "
            f"({prev_pop:,} -> {int(cand_pop):,}), limit "
            f"±{POPULATION_TOLERANCE * 100:.0f}%, and population_version was not bumped "
            f"(still {cand['population_version']!r})",
            previous=prev_pop,
            candidate=cand_pop,
            drift_pct=round(drift * 100, 2),
        )

    # --- Rule 3: per-category collapse ---
    for name, prev_n in sorted(prev["categories"].items()):
        if prev_n < CATEGORY_MIN_N:
            continue
        cand_n = cand["categories"].get(name, 0)
        drop = (prev_n - cand_n) / prev_n
        if drop > CATEGORY_DROP_TOLERANCE:
            reject(
                "category_collapse",
                f"category {name!r} fell {drop * 100:.1f}% "
                f"({prev_n:,} -> {cand_n:,}), limit "
                f"{CATEGORY_DROP_TOLERANCE * 100:.0f}%, without a version bump",
                category=name,
                previous=prev_n,
                candidate=cand_n,
                drop_pct=round(drop * 100, 2),
            )
            continue
        # Sample size held but accuracy fell off a cliff — the cricket shape. Only
        # judged where the cohort is big enough for the number to mean something.
        prev_ece = prev["category_ece"].get(name)
        cand_ece = cand["category_ece"].get(name)
        if (
            isinstance(prev_ece, (int, float))
            and isinstance(cand_ece, (int, float))
            and cand_n >= CATEGORY_MIN_N
            and cand_ece - prev_ece > CATEGORY_ECE_REGRESSION_PP
        ):
            reject(
                "category_ece_regression",
                f"category {name!r} ECE worsened {prev_ece:.1f}pp -> {cand_ece:.1f}pp "
                f"(+{cand_ece - prev_ece:.1f}pp, limit "
                f"{CATEGORY_ECE_REGRESSION_PP:.0f}pp) on a stable sample "
                f"({prev_n:,} -> {cand_n:,}), without a version bump",
                category=name,
                previous_ece_pp=round(float(prev_ece), 2),
                candidate_ece_pp=round(float(cand_ece), 2),
            )

    # --- Rule 4: well-traded / thin ordering inversion ---
    cand_order = _ordering(cand["cohorts"]["well_traded"], cand["cohorts"]["thin"])
    prev_order = _ordering(prev["cohorts"]["well_traded"], prev["cohorts"]["thin"])
    if cand_order is not None and prev_order is not None and cand_order != prev_order:
        cw = cand["cohorts"]["well_traded"]
        ct = cand["cohorts"]["thin"]
        reject(
            "liquidity_rank_inversion",
            f"well-traded/thin accuracy ordering flipped {prev_order} -> {cand_order} "
            f"beyond sampling tolerance (candidate well-traded MCE {cw['mce_pp']}pp "
            f"±{cw['tolerance_pp']}pp over n={cw['n']:,}; thin MCE {ct['mce_pp']}pp "
            f"±{ct['tolerance_pp']}pp over n={ct['n']:,})",
            previous_ordering=prev_order,
            candidate_ordering=cand_order,
        )

    return verdict


def rejection_issue_body(verdict: PublishVerdict, *, fingerprint_marker: str) -> str:
    """The evidence packet filed when a candidate is rejected.

    Carries the full before/after diff so triage starts from measured numbers
    rather than a re-derivation.
    """
    cand, prev = verdict.candidate, verdict.published
    lines = [
        "The calibration publish gate **rejected** a freshly computed candidate. "
        "The previously published snapshot was preserved and is still being served "
        "— the public page is not blank, but it is no longer advancing.",
        "",
        "## Why it was rejected",
        "",
    ]
    for r in verdict.rejections:
        lines.append(f"- **`{r['code']}`** — {r['detail']}")

    def _fmt(value: Any) -> str:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{int(value):,}"
        return str(value)

    lines += [
        "",
        "## Count bridge (published -> candidate)",
        "",
        "| Measure | Published | Candidate |",
        "|---|---|---|",
        f"| total_outcomes | {_fmt(prev.get('population'))} | {_fmt(cand.get('population'))} |",
        f"| total_markets | {_fmt(prev.get('markets'))} | {_fmt(cand.get('markets'))} |",
        f"| total_winners | {_fmt(prev.get('winners'))} | {_fmt(cand.get('winners'))} |",
        f"| bucket rows | {_fmt(prev.get('bucket_rows'))} | {_fmt(cand.get('bucket_rows'))} |",
        f"| population_version | {prev.get('population_version')} | {cand.get('population_version')} |",
        f"| generated_at | {prev.get('generated_at')} | {cand.get('generated_at')} |",
    ]

    for label, key in (("well-traded", "well_traded"), ("thin", "thin")):
        pc = prev.get("cohorts", {}).get(key, {})
        cc = cand.get("cohorts", {}).get(key, {})
        lines.append(
            f"| {label} MCE (n) | {pc.get('mce_pp')}pp ({_fmt(pc.get('n'))}) "
            f"| {cc.get('mce_pp')}pp ({_fmt(cc.get('n'))}) |"
        )

    changed = []
    for name, prev_n in sorted(prev.get("categories", {}).items()):
        cand_n = cand.get("categories", {}).get(name, 0)
        if prev_n and abs(cand_n - prev_n) / prev_n > 0.10:
            changed.append((name, prev_n, cand_n))
    if changed:
        lines += ["", "## Categories that moved more than 10%", "", "| Category | Published | Candidate |", "|---|---|---|"]
        for name, prev_n, cand_n in changed:
            lines.append(f"| {name} | {prev_n:,} | {cand_n:,} |")

    lines += [
        "",
        "## What to do",
        "",
        "1. Decide whether the change is **intended**. If it is, bump "
        "`CALIBRATION_POPULATION_VERSION` in `backend/app/tasks/precompute_calibration.py` "
        "so the new population is published under an explicit, versioned explanation.",
        "2. If it is not intended, find what changed the population — this gate reports "
        "the symptom, never repairs data or re-grades an outcome.",
        "",
        f"Gate fingerprint: `{fingerprint_marker}:{verdict.fingerprint}` — repeat builds of "
        "the same failure class comment here instead of filing a new issue.",
    ]
    return "\n".join(lines)
