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
  /**
   * The server's verdict on the hourly beat. `null` means the payload did not
   * carry one — which is NOT "healthy", and no caller may read it as such.
   */
  producerStalled: boolean | null;
  /** Hourly beats that came and went without a newer artifact. `null` = unread. */
  beatsMissed: number | null;
  /**
   * Did the producer PROVE the served artifact is current — `stalled === false`
   * AND `beats_missed === 0`?
   *
   * Derived rather than re-derived: #4046 already needed this predicate to stop
   * a fallback serve being read as a dated copy, and #4113 needs the same one to
   * stop a main-tier serve being read as a current copy. Two callers computing
   * "current" from two fields is how the two halves drifted apart in the first
   * place. Positive proof, so every unreadable case is `false`.
   */
  producerProvenCurrent: boolean;
  /**
   * #5185: `staged.reason` verbatim, on every kind. `reason` above is the
   * banner's OWN why — `cache.reason` on a last-good, a constant on
   * frozen-inputs — so the staged block's answer was readable only on the
   * `undisclosed` branch and nowhere on the page. `null` = the payload carried
   * none; never defaulted to a word the server did not write.
   */
  stagedReason: string | null;
}

/**
 * The `producer` block, as `calibration_publish_gate._producer_block` builds it.
 *
 * `stalled` is the server's own verdict on whether the hourly beat is still
 * landing, and it is deliberately pessimistic: an UNKNOWN age publishes as
 * `stalled: true`, never as healthy (gotcha #53, and that module says so). This
 * mirrors it rather than importing it — same reason as everything else here.
 */
export interface CalibrationProducerDisclosure {
  stalled?: unknown;
  beats_missed?: unknown;
  /**
   * The artifact's age at SERVE time, in seconds. Tier-independent: `_serve`'s
   * docstring commits to it "on every answer, not only the dated ones", and it
   * is recomputed there from the payload's own `generated_at`. This is the
   * fallback `cache.age_s` needs — see `decideCalibrationStaleness`.
   */
  age_s?: unknown;
}

/** The shape this module needs. Deliberately narrower than `CalibrationData`. */
export interface CalibrationStalenessInput {
  availability?: unknown;
  /**
   * When the PRODUCER built this artifact, baked into the payload by the
   * producer itself. Present on every tier, unlike `cache.generated_at`.
   */
  generated_at?: unknown;
  staged?: CalibrationStagedDisclosure | null;
  producer?: CalibrationProducerDisclosure | null;
  cache?: {
    status?: unknown;
    /** The server's machine-readable why, republished as the notice's `reason`. */
    reason?: unknown;
    generated_at?: unknown;
    age_s?: unknown;
  } | null;
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
  // `availability` absent => no envelope on this payload => the only authority
  // is `cache.status`. Do NOT read absence as `fresh`, and do NOT read it as a
  // problem either: it is an older artifact, and it says so by saying nothing.
  const serverRefusedFresh = availability !== null && availability !== AVAILABILITY_FRESH;

  // Tri-state on purpose, and only a literal boolean counts. `undefined` (an
  // older payload with no `producer` block) and a non-boolean both land on
  // `null` = "the server did not tell us", which is a different claim from
  // "the beat is fine" and must never collapse into it.
  //
  // Read before `isLastGood` rather than after, because since #4046 the
  // producer verdict is an INPUT to that decision — see below.
  const producer = data?.producer;
  const producerStalled =
    typeof producer === "object" && producer !== null && typeof producer.stalled === "boolean"
      ? producer.stalled
      : null;
  const beatsMissed =
    typeof producer === "object" && producer !== null ? asCount(producer.beats_missed) : null;

  // #4046 — the serving TIER and the artifact's AGE are different facts, and
  // this line used to state the second by reading the first.
  //
  // `cache` is the block a fallback tier attaches when it answers. For three
  // days that was only ever true of a genuinely dated copy, so `cache.status
  // === "stale"` and "the artifact is old" were the same bit and nobody had to
  // separate them. Then publishing was repaired (#3893) and the page went on
  // telling readers, over a seven-minute-old curve, that these numbers "are not
  // being refreshed right now" — because `main` (2h TTL) is evicted ahead of
  // `last_good` (7d) on a 50MB `allkeys-lru` instance, so a fallback serve is
  // documented steady state (`precompute_calibration.py`, "Prefers the fresh
  // `main` key and falls back to the durable `last_good`"). Which tier answered
  // is our storage's business; it is not a claim about the numbers.
  //
  // So the tier still OPENS the question and the producer settles it. The
  // `last-good` sentence asserts two things — the artifact is old, and nothing
  // is replacing it — and `beats_missed` is the server's own arithmetic on
  // exactly that: it is `age // interval_s`, recomputed at serve time in
  // `_serve` from the payload's `generated_at`, on the durable path as much as
  // the main one. `beats_missed === 0` means not one scheduled hourly publish
  // has been missed, which refutes both halves of the sentence at once.
  //
  // Deliberately a POSITIVE proof of health, so every unreadable case keeps
  // today's behaviour: `null` (no producer block, or an unknown artifact age —
  // which the server publishes as `stalled: true`, never as healthy) leaves
  // `isLastGood` set. Gotcha #53: absence is not the reassuring reading, and
  // this must not become the one place that reads it that way.
  const servedFromFallbackTier = data?.cache?.status === "stale";
  const producerProvenCurrent = producerStalled === false && beatsMissed === 0;
  const isLastGood = servedFromFallbackTier && !producerProvenCurrent;

  if (!isLastGood && !serverRefusedFresh) return null;

  const staged = data?.staged;
  const stagedIsObject = typeof staged === "object" && staged !== null;
  const stagedMeasured = stagedIsObject && staged.measured === true;

  // #7696 — the artifact's DATE was the last thing still behind the tier-gated
  // door #4113 opened for the artifact's HEALTH.
  //
  // `cache` is attached by `_dated()` and by nothing else, so it exists only on
  // a fallback tier. The main tier can still refuse `fresh`: `_serve` clamps the
  // declaration down for a stalled producer OR for a staged bank it could not
  // read (`availability_floor`, `measured is not True` -> stale), and attaches
  // no `cache` doing it. So on that path both of these read `null` and the
  // banner could not date the artifact it was warning about.
  //
  // Measured on the real production envelope, 2026-09-21T05:30Z: the same bytes
  // served by the dated tier give the reader "built Sep 15, 4:16 AM (5 days
  // ago)"; served by the main tier they give "We can't confirm how current this
  // is" and no date at all — while `generated_at` and `producer.age_s` sit in
  // that same payload stating the answer exactly.
  //
  // The fallbacks are the tier-independent statements of the same two facts:
  // top-level `generated_at` is baked in by the producer, and `producer.age_s`
  // is `_serve`'s own serve-time arithmetic over it, promised "on every answer".
  // `cache` still wins where it exists — a fallback tier measured the age of the
  // copy it is actually serving, which is the more specific claim.
  //
  // Order matters and absence still means absence: an unreadable value falls
  // through to `null` exactly as before, so nothing here invents a date (gotcha
  // #53). The states that never had a date keep not having one.
  const generatedAt = asString(data?.cache?.generated_at) ?? asString(data?.generated_at);
  const ageS = asCount(data?.cache?.age_s) ?? asCount(producer?.age_s);
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
    producerStalled,
    beatsMissed,
    producerProvenCurrent,
    stagedReason: stagedIsObject ? asString(staged.reason) : null,
  };

  // Precedence, and it is this way round deliberately. A dated last-good is the
  // STRONGER fact: the whole artifact is old and no beat is replacing it, which
  // subsumes "its inputs are old". Leading with the frozen-inputs sentence there
  // would tell a reader the curve is being refreshed while the server is
  // explicitly serving a copy that is not.
  //
  // #4046 narrowed what reaches here rather than reordering it: the precedence
  // was never wrong, its GUARD was — it fired on a fallback serve of a current
  // artifact, where "no beat is replacing it" is simply untrue and the stronger
  // fact is therefore not a fact at all. A dated last-good still outranks
  // everything below.
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
      //
      // #4113: and the first half of that is a CLAIM, so it needs proving. What
      // `frozen_over_drift` establishes is that the INPUT bank is frozen. It
      // says nothing about whether the curve sitting on top of it published
      // this hour, and this sentence asserted that it had, for free.
      //
      // Measured 2026-09-09 00:37Z: the page said "The curve is current." in
      // bold over a 76-minute-old artifact whose own payload carried
      // `beats_missed: 1` — the refutation was in the same JSON object and the
      // sentence did not look at it. It could not: `cache` is null on the main
      // tier, so `producerProvenCurrent` only ever reached `isLastGood`, where
      // it can DOWNGRADE a warning (#4046) and never withhold a reassurance.
      // A missed beat is tier-independent and now gates both.
      //
      // Unproven keeps the second half — the inputs really are dated, and that
      // is still the reader's subject — and replaces the assertion with the
      // absence of one. Distinct from `undisclosed`, which is a different state:
      // there we could not read the inputs at all.
      return notice.producerProvenCurrent
        ? "The curve is current. The data behind it is older."
        : "We can't confirm the curve is current. The data behind it is older.";
    case "undisclosed":
      // #7696: "how current THIS is" is a claim about the artifact, and once
      // the date fallback above reaches the main tier we know exactly how
      // current the artifact is — the very next sentence prints the day and the
      // hour. Confessing ignorance of a fact you are about to state is the
      // mirror image of #4113's defect: there the page asserted currency it had
      // not proven, here it disclaims currency it had measured, and a reader who
      // believes either one is misled about what we know.
      //
      // What is genuinely unread in this state is the INPUT staging — which is
      // what the body sentence has always said, and what the headline now
      // scopes itself to. Undated, nothing changed: no date follows, the broad
      // sentence is the honest one, and it is returned verbatim.
      return notice.generatedAt !== null
        ? "We can't confirm how current the data behind this is."
        : "We can't confirm how current this is.";
  }
}

/** `staged.reason` for a served bank with nothing in it (#5043's contract). */
export const STAGED_REASON_SERVED_BANK_EMPTY = "served_bank_empty";

/**
 * The `undisclosed` banner's sentence about the market data behind the curve.
 *
 * ## The defect this closes (#5185)
 *
 * #5043 split the server's answer in two: `served_bank_empty` is a served bank
 * that was cleared so its census could be gathered again from scratch — the
 * normal state after a population fingerprint change — and `served_at_absent`
 * is a bank that exists and lost its date. The page rendered both, and every
 * other unreadable reason, as "We couldn't read when ... was last staged".
 * For the empty bank that is false: nothing failed to read. There is no date
 * because there is no census yet to date.
 *
 * Describes, never predicts (the banner's standing rule): on production this
 * state has sat under a stalled producer — 138 beats missed on 2026-09-21 — so
 * "a rebuild is underway" or "back shortly" would be a claim this render
 * cannot support. What IS measured is that the bank is empty, and that is all
 * the sentence says. And no date is invented for it — that is #2007.
 */
export function stalenessInputSentence(notice: CalibrationStalenessNotice): string {
  return notice.stagedReason === STAGED_REASON_SERVED_BANK_EMPTY
    ? "The market data behind it is being gathered again from scratch, so it has no date to show."
    : "We couldn’t read when the market data behind it was last staged.";
}

/**
 * The closing sentence about the hourly SCHEDULE, or `null` for "say nothing".
 *
 * ## The defect this closes (#2649)
 *
 * The banner used to end, unconditionally, with "The curve rebuilds hourly."
 * On 2026-09-02 production served that sentence over a payload that said, in
 * the same JSON object, `producer: { stalled: true, beats_missed: 51 }`. A
 * reader was told to come back in an hour, 51 hours running — and it could not
 * self-resolve, because under `q268` the publish gate refused every rebuild and
 * binned the work that earned it. The page had the refutation in hand and
 * printed the promise anyway.
 *
 * `calibrationBannerCopy.test.tsx` had deliberately exempted this sentence from
 * its forward-looking ban, on the reasoning that it is "present tense about a
 * SCHEDULE that is externally true (the beat fires at :15 every hour)". That
 * reasoning is right, and it rests on a premise — *the beat fires* — which the
 * payload can measure and which `beats_missed: 51` refutes. So the fix is not
 * to delete the sentence: when the beat really is firing, telling a reader the
 * cadence is useful and true. The fix is to stop asserting the premise for
 * free.
 *
 * Hence three readings, and the middle one is the whole point:
 *
 *   * `stalled === false` -> the schedule is real; state it.
 *   * `stalled === true`  -> DESCRIBE the failure; never predict a recovery.
 *   * `stalled === null`  -> the server did not say; say nothing.
 *
 * The third is the gotcha #53 case and it is why absence does not fall through
 * to the reassuring branch. An older payload carrying no `producer` block is
 * not evidence of a healthy beat, and a sentence we cannot support is worse
 * than a shorter banner. The reader still gets the dated artifact either way.
 *
 * Same rule as CAL-P080 settled for the `frozen-inputs` copy, applied to the
 * branch that never got it: THE BANNER MAY DESCRIBE, IT MAY NOT PREDICT.
 */
export function stalenessScheduleClause(notice: CalibrationStalenessNotice): string | null {
  if (notice.producerStalled === false) {
    // #4113, same class as the headline above: `stalled` is a FOUR-HOUR verdict
    // (`stall_after_s: 14400`), so a beat can be two hours late and still
    // publish `stalled: false`. `beats_missed` is the payload's own arithmetic
    // on exactly the hour this sentence promises, and it was not consulted.
    //
    // Withheld rather than replaced. The count is `age // interval_s`, not a
    // tally of failed runs, so it can read 1 for the minutes a healthy but slow
    // beat spends the wrong side of an hour boundary — loud enough to describe
    // a failure it has not measured. Saying nothing costs a reader a true
    // sentence; saying it anyway costs them the reason they are reading a
    // staleness banner at all.
    return notice.beatsMissed === 0 ? "The curve rebuilds hourly." : null;
  }
  if (notice.producerStalled !== true) return null;
  // Stalled. Report the measured count when we have one; the count is the whole
  // reason this sentence is credible, so an unread count gets the vaguer
  // sentence rather than a fabricated number.
  //
  // #5042: and say what the count MEASURES. `beats_missed` is `age //
  // interval_s` — the field's own doc comment above calls it "hourly beats that
  // came and went without a newer artifact" — so "without one succeeding" is a
  // tally of failed RUNS that nothing here counted. The branch above withholds
  // a sentence for exactly this reason ("loud enough to describe a failure it
  // has not measured"); this branch asserted it anyway.
  //
  // Measured 2026-09-11 02:30Z: the page read "4 hourly rebuilds have come and
  // gone without one succeeding" while the 00:31Z and 01:37Z beats had each
  // banked five units. Both succeeded. What had not happened was a PUBLISH —
  // a release changed the population fingerprint, the re-stage emptied the
  // served bank D45 publishes from, and the fresh generation was 10/128 through
  // (#5043). The reader was told the system was broken while it was working,
  // and the same state recurs on every fingerprint change.
  //
  // So: describe the artifact, which is what the number is about, and make no
  // claim about the runs, which it is not. Still a description, never a
  // prediction — the rule this function's docstring ends on is untouched.
  if (notice.beatsMissed === null || notice.beatsMissed <= 0) {
    return "Hourly rebuilds have not produced a new snapshot.";
  }
  const beats = notice.beatsMissed.toLocaleString();
  const rebuild = notice.beatsMissed === 1 ? "hourly rebuild has" : "hourly rebuilds have";
  return `${beats} ${rebuild} come and gone without a new snapshot.`;
}

/**
 * The methodology card's refresh-cadence sentence, or `null` for "say nothing".
 *
 * ## The defect this closes (#7612)
 *
 * `stalenessScheduleClause` above stopped the BANNER promising an hourly
 * rebuild it could not support. The same promise survived one card down the
 * page, as a string literal at the end of "What's included?", reading nothing
 * from the payload:
 *
 *   > A price without participants isn't a prediction … Data refreshes hourly.
 *
 * Measured on production 2026-09-20 21:45Z: the page printed that over
 * `producer: {stalled: true, beats_missed: 130}` — five days after the last
 * refresh — while its own banner, in the same view, read "130 hourly rebuilds
 * have come and gone without a new snapshot". Two sentences on one page load,
 * each refuting the other.
 *
 * The rule is `stalenessScheduleClause`'s, applied to the surface that never
 * got it: THE PAGE MAY DESCRIBE, IT MAY NOT PREDICT.
 *
 * The gate is the presence of a notice, not `producerProvenCurrent`, and that
 * is deliberate — this sentence is about the DATA, not the curve. Under
 * `frozen-inputs` the banner's own words are "The curve is current. The data
 * behind it is older", so a card claiming the data refreshes hourly contradicts
 * it just as squarely as under `last-good`, even though the producer is proven
 * healthy. `null` in, the server said `fresh`, and the sentence is supported.
 *
 * Withheld rather than replaced, for #4113's reason: the banner directly above
 * already describes the real state, and a paragraph explaining the absence is
 * what notice 34 bans. A reader loses a true sentence on a fresh page and
 * nothing else.
 */
export function methodologyRefreshClause(
  notice: CalibrationStalenessNotice | null | undefined,
): string | null {
  return notice ? null : "Data refreshes hourly.";
}

/**
 * How old a served snapshot is, in plain words: "moments" / "14 min" / "3 hr" /
 * "5 days". The caller supplies the " ago".
 *
 * ## The defect this closes (#7634)
 *
 * This ladder lived as a module-private `formatAge` inside
 * `app/calibration/page.tsx`, a `"use client"` component, so no guard could
 * call it — the same reason CAL-P1024 (#1865) moved `sourceLabel` out of that
 * file after `datagolf` had been rendering its raw payload key for weeks. It
 * was the only age ladder in the repo that ROUNDED, and it got two separate
 * things wrong.
 *
 * Measured on production 2026-09-20 23:40Z: the banner read "These numbers were
 * built **Sep 15, 4:16 AM (6 days ago)**" while today was Sep 20. The artifact
 * is 479,048 s = 5.54 d, and `Math.round(5.54)` is 6. A reader who counts from
 * the date the same sentence prints gets 5. The parenthetical exists to save
 * them that arithmetic and it contradicted the date it annotates.
 *
 * ### Mistake 1 — round, where every sibling floors
 *
 * `lib/matchDetail.ts`, `lib/tournamentProps.ts`, `lib/slate.ts`,
 * `lib/tournament.ts` and `lib/sourceAge.ts` all floor, and four carry the same
 * comment verbatim: *"Human age, rounded DOWN — '8 days ago' must never flatter
 * to '7'."* Over every age from 0 to 10 days at one-second steps, this ladder
 * disagreed with a floored one on 432,870 of 864,000 readings — **50.1%** —
 * reading older on 432,840 of them, by as much as **24 hours** (at 2.5 d it
 * said "3 days").
 *
 * ### Mistake 2 — the rung threshold was tested against the ROUNDED value
 *
 * `const hours = Math.round(seconds / 3600); if (hours < 48)` opens the days
 * rung at 47.5 h, so a 47 h 59 m artifact read "2 days". The siblings test the
 * raw quantity and floor only for display. This is why the repair is not a
 * one-word swap: fixing the arithmetic alone leaves every boundary half a rung
 * early.
 *
 * Two strings were unreachable as a consequence, and the second is the tell:
 *
 *   * `"1 min"` could never print at all — the `moments` guard releases at 90 s
 *     and `Math.round(90 / 60)` is 2.
 *   * `"1 hr"` printed for 30 seconds of the 1,800 it is the true reading: the
 *     window `[5370, 5399]` where the minutes rung has already rounded up to 90
 *     but the hours rung has not yet rounded up to 2. The banner otherwise
 *     jumped `89 min` -> `2 hr`.
 *
 * That 30-second window is also the one place the old ladder FLATTERED — it
 * printed "1 hr" over an artifact 89½ minutes old, which is the exact failure
 * the convention's comment names. A ladder wrong in both directions is not a
 * rounding preference; it is an unstated one.
 *
 * ### Why the rungs themselves did not move
 *
 * 90 s / 90 min / 48 h and the words "moments", "min", "hr", "days" are
 * unchanged, because they were never the defect and this banner's copy is
 * load-bearing (#2649, #4046, #4113, #7612 all landed on sentences around it).
 * Only the arithmetic and the threshold's subject change.
 *
 * `"1 days"` stays unreachable and that is a property of the rungs, not an
 * accident: the days rung opens at 48 h, so the floor is at least 2. The test
 * asserts it rather than a singular branch being added for a string nothing can
 * produce — if a rung ever moves, the assertion fails instead of the grammar.
 *
 * Total on every finite input. A negative age (clock skew between the server's
 * `age_s` and nothing at all — the value is the server's own arithmetic) lands
 * on "moments" via the first guard rather than printing a negative count.
 */
export function stalenessAgeLabel(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 90) return "moments";
  if (seconds < 90 * 60) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 48 * 3600) return `${Math.floor(seconds / 3600)} hr`;
  return `${Math.floor(seconds / 86400)} days`;
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
