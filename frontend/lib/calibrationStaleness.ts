// #2007 item 1b (Fable ruling (c), CAL-P077) — the banner reads what
// `availability` actually discloses.
//
// ## The defect this closes
//
// CAL-P076 shipped the backend half: `/api/calibration` now carries a top-level
// `staged` block dating its own inputs, and `availability` is clamped down from
// `fresh` while the futures bank is frozen over undisclosed drift. The page did
// not move, and the page is where a reader is.
//
// Two things were wrong with leaving it there, and the second is the worse one:
//
//   1. **The banner could not fire at all on the new state.** The page's only
//      degradation authority is `cache.status === "stale"`, and `cache` is a
//      block the *fallback tiers* attach when they serve a dated last-good. The
//      staged clamp runs on the MAIN path, in `_serve`, and attaches no `cache`.
//      So a payload that the server has explicitly declared `availability:
//      "stale"` rendered with no banner whatsoever — the disclosure existed in
//      the JSON and nowhere a person could see it.
//
//   2. **If it HAD fired, it would have said something false.** Today's copy is
//      "These numbers were built <t> ... and are not being refreshed right now."
//      That is true of a dated last-good and it is a LIE about a frozen bank:
//      the curve is rebuilt every beat, on time, and republished with a brand-new
//      `generated_at`. What is old is the INPUT census behind it. Telling a
//      reader the page is not refreshing, when the failure is that it refreshes
//      while re-serialising the same six-hour-old bank, points them at the wrong
//      fact — and at a fact that will "resolve itself" on the next beat, which it
//      will not.
//
// So the two states are not one state with two reasons. They are different
// claims about different things and they get different sentences:
//
//   `last-good`     — the whole artifact is old and nothing is republishing it.
//   `frozen-inputs` — the artifact is current; its inputs are dated.
//   `undisclosed`   — the server refused `fresh` and could not tell us why.
//
// ## Why this is a separate module from `calibrationContract`
//
// `calibrationContract` answers *may this build put its labels on these
// numbers?* — a refusal question, whose answer is a rendered wall. This answers
// *what does the reader have to be told about what they are looking at?* — a
// disclosure question, whose answer is a sentence above numbers that still
// render. Ruling 025's clause-5 pairing is one rendering per state, and the two
// questions have different state sets; folding them together is how "degraded"
// ends up outranking a refusal because it happened to be checked first.
//
// The ordering between them is unchanged and still lives in the page: a
// contract refusal outranks every disclosure here, because a disclosure wrapped
// around numbers we will not stand behind reads as a minor caveat on a major
// refusal.
//
// ## What this module will not do
//
// It never infers a state the server did not declare. `availability` absent is
// not `fresh` — it is an older payload with no envelope, and the only authority
// left is `cache.status`, which is exactly the pre-#2007 behaviour. And a drift
// count that could not be read is reported as unknown, never as zero: a zero
// invented by a failed read is the empty-200 mistake (gotcha #53) that the whole
// `staged` block exists to stop.

/** The four availability words (ruling 025). Mirrored, not imported: this file
 *  has no backend to import from, and the set is closed by that ruling. */
export const AVAILABILITY_FRESH = "fresh";

/**
 * The `staged` block, as `app/utils/calibration_staged_disclosure.py` builds it.
 *
 * Every field optional and every number nullable on purpose. This shape crosses
 * a version boundary — an older cached payload carries none of it, and a
 * partially-readable bank carries `measured: false` and nothing else.
 */
export interface CalibrationStagedDisclosure {
  measured?: unknown;
  reason?: unknown;
  staged_at?: unknown;
  staged_age_s?: unknown;
  units_banked?: unknown;
  units_this_beat?: unknown;
  units_drifted?: unknown;
  units_drift_checkable?: unknown;
  units_drift_unknown?: unknown;
  units_drifted_as_of?: unknown;
  bank_advanced_this_beat?: unknown;
  frozen_over_drift?: unknown;
}

export type CalibrationStalenessKind =
  /** A dated last-good copy. The artifact is old AND nothing is republishing it. */
  | "last-good"
  /** The artifact is current; the inputs behind it are dated. */
  | "frozen-inputs"
  /** The server refused `fresh` and the reason could not be read. */
  | "undisclosed";

export interface CalibrationStalenessNotice {
  kind: CalibrationStalenessKind;
  /** Machine-readable why, published as a data attribute for the rail. */
  reason: string;
  /** When the served ARTIFACT was built, if the server dated it. */
  generatedAt: string | null;
  /** Age of the artifact in seconds, if the server measured it. */
  ageS: number | null;
  /** When the INPUT bank last advanced. Never the publish time. */
  stagedAt: string | null;
  stagedAgeS: number | null;
  /** Drifted units as of `stagedAt`. `null` means unreadable — never 0. */
  unitsDrifted: number | null;
  /** Banked units the drift check could not reach. `null` means unreadable. */
  unitsDriftUnknown: number | null;
  unitsBanked: number | null;
}

/** The shape this module needs. Deliberately narrower than `CalibrationData`. */
export interface CalibrationStalenessInput {
  availability?: unknown;
  staged?: CalibrationStagedDisclosure | null;
  cache?: { status?: unknown; generated_at?: unknown; age_s?: unknown } | null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/** A finite number, or `null`. `NaN`/`Infinity`/`true` are not counts. */
function asCount(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

/**
 * What must the reader be told about this payload? `null` for "nothing".
 *
 * Pure and total: every input — `null`, a payload with a numeric
 * `availability`, a `staged` block of the wrong shape — produces an answer,
 * because the caller is a render path and a throw there is a blank page.
 */
export function decideCalibrationStaleness(
  data: CalibrationStalenessInput | null | undefined,
): CalibrationStalenessNotice | null {
  const availability = asString(data?.availability);
  const cacheStatus = data?.cache?.status;
  const isLastGood = cacheStatus === "stale";
  // `availability` absent => no envelope on this payload => the only authority
  // is `cache.status`. Do NOT read absence as `fresh`, and do NOT read it as a
  // problem either: it is an older artifact, and it says so by saying nothing.
  const serverRefusedFresh = availability !== null && availability !== AVAILABILITY_FRESH;

  if (!isLastGood && !serverRefusedFresh) return null;

  const staged = data?.staged;
  const stagedIsObject = typeof staged === "object" && staged !== null;
  const stagedMeasured = stagedIsObject && staged.measured === true;

  const generatedAt = asString(data?.cache?.generated_at);
  const ageS = asCount(data?.cache?.age_s);
  const stagedAt = stagedMeasured ? asString(staged.staged_at) : null;
  const stagedAgeS = stagedMeasured ? asCount(staged.staged_age_s) : null;
  const unitsDrifted = stagedMeasured ? asCount(staged.units_drifted) : null;
  const unitsDriftUnknown = stagedMeasured ? asCount(staged.units_drift_unknown) : null;
  const unitsBanked = stagedMeasured ? asCount(staged.units_banked) : null;

  const common = {
    generatedAt,
    ageS,
    stagedAt,
    stagedAgeS,
    unitsDrifted,
    unitsDriftUnknown,
    unitsBanked,
  };

  // Precedence, and it is this way round deliberately. A dated last-good is the
  // STRONGER fact: the whole artifact is old and no beat is replacing it, which
  // subsumes "its inputs are old". Leading with the frozen-inputs sentence there
  // would tell a reader the curve is being refreshed while the server is
  // explicitly serving a copy that is not.
  if (isLastGood) {
    return {
      kind: "last-good",
      reason: asString(data?.cache?.reason) ?? "last_good",
      ...common,
    };
  }

  if (stagedMeasured && staged.frozen_over_drift === true) {
    return { kind: "frozen-inputs", reason: "frozen_over_drift", ...common };
  }

  // The server declared not-fresh and the staged block cannot explain it —
  // either it is absent (an older build), unreadable (`measured: false`), or
  // measured-and-not-frozen (a producer stall, which `producer` carries). All
  // three are the same thing to a reader: we are dating this rather than
  // claiming it is current, and we will not guess at why.
  return {
    kind: "undisclosed",
    reason: stagedIsObject ? asString(staged.reason) ?? "not_fresh" : "not_fresh",
    ...common,
  };
}

/**
 * The banner's lead, as a bold clause. Split from the body so the page can put
 * one in `<strong>` without the test having to match across an element boundary.
 */
export function stalenessHeadline(notice: CalibrationStalenessNotice): string {
  switch (notice.kind) {
    case "last-good":
      return "Showing the last complete snapshot.";
    case "frozen-inputs":
      // Fable, ruling (c): the honest copy is "curve refreshed; inputs staged
      // <staged_at>, N units drifted" — NOT "not being refreshed".
      return "The curve is current. The data behind it is older.";
    case "undisclosed":
      return "We can't confirm how current this is.";
  }
}

/**
 * The drift clause, or `null` when there is nothing honest to say.
 *
 * Three readings and they are not interchangeable:
 *   * a real count            -> "115 of 128 units have drifted"
 *   * a count we could not get -> "an unknown number of units have drifted"
 *   * no block at all          -> nothing (do not invent a clause)
 *
 * `unitsDriftUnknown > 0` is reported alongside a real count rather than
 * folded into it: CAL-P069's find was six unmeasurable units publishing as
 * `units_drifted: 0`, and a partial count presented as a whole one is that
 * failure with extra steps.
 */
export function stalenessDriftClause(notice: CalibrationStalenessNotice): string | null {
  const { unitsDrifted, unitsBanked, unitsDriftUnknown } = notice;
  if (unitsDrifted === null) {
    // Silence and "we don't know" are different claims, and which one is honest
    // depends on what the server asserted. `frozen-inputs` means the server
    // REFUSED `fresh` *because of drift* — so drift is the stated cause and
    // saying nothing about it would leave the sentence hanging. Anywhere else,
    // an absent count is simply not this banner's subject.
    if (notice.kind !== "frozen-inputs") return null;
    return "an unknown number of its units have drifted since";
  }
  const of = unitsBanked !== null ? ` of ${unitsBanked.toLocaleString()}` : "";
  const unknown =
    unitsDriftUnknown !== null && unitsDriftUnknown > 0
      ? ` (${unitsDriftUnknown.toLocaleString()} more couldn't be checked)`
      : "";
  const unit = unitsDrifted === 1 ? "unit has" : "units have";
  return `${unitsDrifted.toLocaleString()}${of} ${unit} drifted since${unknown}`;
}
