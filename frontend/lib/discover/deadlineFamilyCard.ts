import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type {
  FeedDeadlineFamilyContract,
  FeedDeadlineMemberContract,
  FeedDeadlineSettlementState,
  FeedFuturesData,
  FeedItem,
} from "@/lib/types";

export const DEADLINE_FAMILY_STORY_PREFIX = "story:deadline_family:";

/**
 * Q7: The new deadline-family story hero chip has a 5-percentage-point threshold.
 * Global `HERO_MIN_MOVEMENT_POINTS` (10) and `MovementBadge` (2) remain unchanged.
 */
export const DEADLINE_HERO_MIN_MOVEMENT_POINTS = 5;
export const DEADLINE_HERO_MIN_MOVEMENT_FRACTION = 0.05;

/**
 * 2-percentage-point floor for eligible supported dated movement under Q1 and 6E.
 */
export const DEADLINE_MODERATE_MIN_MOVEMENT_POINTS = 2;
export const DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION = 0.02;

export const DATED_BASIS_MIN_AGE_HOURS = 12;
export const DATED_BASIS_WINDOW_HOURS = 24;
export const NEAR_CERTAIN_THRESHOLD = 0.97;

export const DETERMINISTIC_TIE_BREAK_RULE =
  "abs_supported_move_desc -> distance_from_50pct_asc -> deadline_instant_asc -> market_id_asc";

const SHORT_MONTH_NAMES: Record<number, string> = {
  1: "Jan",
  2: "Feb",
  3: "Mar",
  4: "Apr",
  5: "May",
  6: "Jun",
  7: "Jul",
  8: "Aug",
  9: "Sep",
  10: "Oct",
  11: "Nov",
  12: "Dec",
};

const ISO_TIMEZONE_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;
const CALENDAR_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const LOCAL_TIME_RE = /^\d{2}:\d{2}$/;

export function isDeadlineFamilyStoryKey(
  storyKey: string | null | undefined,
): boolean {
  return (
    typeof storyKey === "string" &&
    storyKey.startsWith(DEADLINE_FAMILY_STORY_PREFIX)
  );
}

/**
 * Parse an ISO timestamp requiring an explicit timezone suffix (`Z` or `±HH:MM`).
 * Timezone-naive strings are rejected (`null`) rather than interpreted in host local time.
 */
export function parseTimezoneAwareEpochMs(
  iso: string | null | undefined,
): number | null {
  if (typeof iso !== "string") return null;
  const trimmed = iso.trim();
  if (!trimmed || !ISO_TIMEZONE_SUFFIX_RE.test(trimmed)) return null;
  const ms = Date.parse(trimmed);
  return Number.isFinite(ms) ? ms : null;
}

export interface DeadlineMovementTimeframe {
  valid: boolean;
  calendarDayDiff: number | null;
  crossesPreviousCalendarDay: boolean;
  chipTimeframe: string | null;
  sentenceTimeframe: string | null;
  timeZone: string;
}

function localDateParts(
  epochMs: number,
  timeZone: string,
): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
} {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(epochMs));

  const map: Record<string, number> = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      map[part.type] = Number(part.value);
    }
  }
  return {
    year: map.year,
    month: map.month,
    day: map.day,
    hour: map.hour === 24 ? 0 : map.hour,
    minute: map.minute,
  };
}

/**
 * Verify that `deadlineEpochMs` converts to the exact contractual `calendarDate` (`YYYY-MM-DD`)
 * and `cutoffLocalTime` (`HH:MM`) in `cutoffTimezone` (Section 3B).
 */
function verifyContractualCutoffInTimezone(
  deadlineEpochMs: number,
  calendarDate: string,
  cutoffTimezone: string,
  cutoffLocalTime: string,
): boolean {
  if (
    !CALENDAR_DATE_RE.test(calendarDate) ||
    !LOCAL_TIME_RE.test(cutoffLocalTime) ||
    !cutoffTimezone
  ) {
    return false;
  }
  try {
    const parts = localDateParts(deadlineEpochMs, cutoffTimezone);
    const localDate = `${String(parts.year).padStart(4, "0")}-${String(
      parts.month,
    ).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
    const localTime = `${String(parts.hour).padStart(2, "0")}:${String(
      parts.minute,
    ).padStart(2, "0")}`;
    return localDate === calendarDate && localTime === cutoffLocalTime;
  } catch {
    return false;
  }
}

/**
 * Direct user decision Q4:
 * - Use `"since yesterday"` on this NEW card ONLY when the comparison genuinely
 *   crosses from the previous reader-local calendar date (`calendarDayDiff === 1`).
 * - A 12–24-hour-old observation on the same reader-local calendar date
 *   (`calendarDayDiff === 0`) uses truthful same-day time wording (`"today since 3:50 AM"`
 *   / `"since 3:50 AM"`), never `"since yesterday"`.
 */
export function formatDeadlineMovementTimeframe(
  basisObservedAt: string | null | undefined,
  referenceAt: string | null | undefined,
  timeZone?: string,
  nowIso?: string | null,
): DeadlineMovementTimeframe {
  const resolvedTz =
    timeZone ||
    (typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC") ||
    "UTC";

  const basisMs = parseTimezoneAwareEpochMs(basisObservedAt);
  const refMs = parseTimezoneAwareEpochMs(referenceAt);
  const nowMs = parseTimezoneAwareEpochMs(nowIso);
  if (basisMs == null || refMs == null) {
    return {
      valid: false,
      calendarDayDiff: null,
      crossesPreviousCalendarDay: false,
      chipTimeframe: null,
      sentenceTimeframe: null,
      timeZone: resolvedTz,
    };
  }

  let effectiveTz = resolvedTz;
  let basisLocal: ReturnType<typeof localDateParts>;
  let refLocal: ReturnType<typeof localDateParts>;
  let nowLocal: ReturnType<typeof localDateParts> | null = null;
  try {
    basisLocal = localDateParts(basisMs, effectiveTz);
    refLocal = localDateParts(refMs, effectiveTz);
    if (nowMs != null) {
      nowLocal = localDateParts(nowMs, effectiveTz);
    }
  } catch {
    effectiveTz = "UTC";
    basisLocal = localDateParts(basisMs, "UTC");
    refLocal = localDateParts(refMs, "UTC");
    if (nowMs != null) {
      nowLocal = localDateParts(nowMs, "UTC");
    }
  }

  const basisDayUtc = Date.UTC(
    basisLocal.year,
    basisLocal.month - 1,
    basisLocal.day,
  );
  const refDayUtc = Date.UTC(refLocal.year, refLocal.month - 1, refLocal.day);
  const nowDayUtc =
    nowLocal != null
      ? Date.UTC(nowLocal.year, nowLocal.month - 1, nowLocal.day)
      : refDayUtc;
  const refMatchesReaderToday = nowDayUtc === refDayUtc;
  const dayDiff = Math.round((refDayUtc - basisDayUtc) / 86_400_000);

  if (dayDiff < 0) {
    return {
      valid: false,
      calendarDayDiff: dayDiff,
      crossesPreviousCalendarDay: false,
      chipTimeframe: null,
      sentenceTimeframe: null,
      timeZone: effectiveTz,
    };
  }

  if (dayDiff === 1 && refMatchesReaderToday) {
    return {
      valid: true,
      calendarDayDiff: 1,
      crossesPreviousCalendarDay: true,
      chipTimeframe: "since yesterday",
      sentenceTimeframe: "since yesterday",
      timeZone: effectiveTz,
    };
  }

  if (dayDiff === 0 && refMatchesReaderToday) {
    const hour12 = basisLocal.hour % 12 || 12;
    const amPm = basisLocal.hour < 12 ? "AM" : "PM";
    const minuteStr = String(basisLocal.minute).padStart(2, "0");
    const timeLabel = `${hour12}:${minuteStr} ${amPm}`;
    return {
      valid: true,
      calendarDayDiff: 0,
      crossesPreviousCalendarDay: false,
      chipTimeframe: `since ${timeLabel}`,
      sentenceTimeframe: `today since ${timeLabel}`,
      timeZone: effectiveTz,
    };
  }

  const monthName = SHORT_MONTH_NAMES[basisLocal.month] || "Jan";
  const dateLabel = `${monthName} ${basisLocal.day}`;
  return {
    valid: true,
    calendarDayDiff: dayDiff,
    crossesPreviousCalendarDay: false,
    chipTimeframe: `since ${dateLabel}`,
    sentenceTimeframe: `since ${dateLabel}`,
    timeZone: effectiveTz,
  };
}

export function formatDeadlinePointsText(moveFraction: number): string {
  const absPts = Math.round(Math.abs(moveFraction) * 1000) / 10;
  const formatted = Number.isInteger(absPts)
    ? String(absPts)
    : absPts.toFixed(1);
  return formatted;
}

function formatPointsUnit(moveFraction: number): string {
  const absPts = Math.round(Math.abs(moveFraction) * 1000) / 10;
  const formatted = Number.isInteger(absPts)
    ? String(absPts)
    : absPts.toFixed(1);
  return `${formatted} ${absPts === 1 ? "point" : "points"}`;
}

export interface DeadlineFamilyMemberViewModel {
  marketId: number;
  name: string;
  source: string;
  externalId: string;
  groupId: string;
  deadlineLabel: string;
  shortDeadline: string;
  calendarDate: string;
  deadlineInstant: string;
  deadlineEpochMs: number;
  cutoffTimezone: string;
  cutoffLocalTime: string;
  ruleTemplateHash: string;
  yesOutcomeId: number;
  noOutcomeId: number;
  yesProbability: number | null;
  yesRenderedPercent: number | null;
  yesPercentText: string;
  barWidthPercent: number;
  priceObservedAt: string | null;
  movementStatus:
    | "hero"
    | "moderate"
    | "sub_threshold"
    | "measured_zero"
    | "none";
  supportedMoveFraction: number | null;
  supportedMovePoints: number | null;
  showHeroMovementChip: boolean;
  heroMovementChipText: string | null;
  heroMovementUp: boolean;
  heroTimeframeText: string | null;
  heroMovementAriaLabel: string | null;
  showRowMovementBadge: boolean;
  rowMovementFraction: number | null;
  narrativeCaption: string;
  settlementState: FeedDeadlineSettlementState;
  isSettled: boolean;
  isTradingClosed: boolean;
  isDeadlinePassed: boolean;
  settledText: string | null;
  laggingLocalStatus: boolean;
  isNearCertain: boolean;
  nearCertainOpenEligible: boolean;
  isRepresentative: boolean;
  detailHref: string;
  accessibleLabel: string;
  providerMarketCount: number | null;
  verifiedFamilyCount: number | null;
}

export interface DeadlineFamilyCardModel {
  storyKey: string;
  source: string;
  groupId: string;
  title: string;
  sharedQuestion: string;
  category: string | null;
  familyState: "open" | "settled";
  ruleTemplateHash: string;
  cutoffTimezone: string;
  cutoffLocalTime: string;
  selectionReason:
    | "largest_supported_dated_move"
    | "nearest_50_pct_fallback"
    | "settled_family";
  selectionBadgeText: string;
  tieBreakRule: string;
  representative: DeadlineFamilyMemberViewModel;
  members: DeadlineFamilyMemberViewModel[];
  representedCount: number;
  verifiedFamilyCount: number | null;
  providerMarketCount: number | null;
  inventoryComplete: boolean | null;
  expandLabel: string;
  collapseLabel: string;
}

export interface BuildDeadlineFamilyOptions {
  nowIso?: string;
  timeZone?: string;
}

export interface DeadlineFamilyInput {
  items: FeedItem[];
  title?: string | null;
  sharedQuestion?: string | null;
  storyKey?: string | null;
  deadlineFamily?: FeedDeadlineFamilyContract | null;
}

interface VerifiedMemberInternal extends Omit<
  DeadlineFamilyMemberViewModel,
  "isRepresentative"
> {
  stemKey: string;
  displayStem: string;
  sharedQuestion: string;
  preposition: string;
}

function verifySingleMember(
  contract: FeedDeadlineMemberContract | null | undefined,
  itemData: FeedFuturesData | null | undefined,
  options: BuildDeadlineFamilyOptions,
): { member: VerifiedMemberInternal | null; reason: string | null } {
  if (!contract || typeof contract !== "object") {
    return { member: null, reason: "missing_producer_member_contract" };
  }
  if (
    typeof contract.market_id !== "number" ||
    !Number.isInteger(contract.market_id)
  ) {
    return { member: null, reason: "invalid_market_id" };
  }
  if (itemData && itemData.id !== contract.market_id) {
    return { member: null, reason: "member_market_id_mismatch" };
  }

  const source = (contract.source ?? "").trim().toLowerCase();
  const groupId = (contract.group_id ?? "").trim();
  const externalId = (contract.external_id ?? "").trim();
  if (!source || !groupId || !externalId) {
    return { member: null, reason: "missing_provider_or_condition_identity" };
  }

  if (
    typeof contract.yes_outcome_id !== "number" ||
    !Number.isInteger(contract.yes_outcome_id) ||
    typeof contract.no_outcome_id !== "number" ||
    !Number.isInteger(contract.no_outcome_id) ||
    contract.yes_outcome_id === contract.no_outcome_id ||
    contract.yes_outcome_name !== "Yes"
  ) {
    return { member: null, reason: "invalid_or_missing_yes_outcome_binding" };
  }

  // Section 3A: Verify producer rule equivalence evidence (`rule_verification` + `rule_template_hash`).
  const ruleVer = contract.rule_verification;
  const ruleTemplateHash = (
    contract.rule_template_hash ??
    ruleVer?.rule_template_hash ??
    ""
  ).trim();
  const cutoffTimezone = (
    contract.cutoff_timezone ??
    ruleVer?.cutoff_timezone ??
    ""
  ).trim();
  const cutoffLocalTime = (
    contract.cutoff_local_time ??
    ruleVer?.cutoff_local_time ??
    ""
  ).trim();

  if (
    !ruleVer ||
    ruleVer.verified !== true ||
    !ruleTemplateHash ||
    !cutoffTimezone ||
    !cutoffLocalTime
  ) {
    return { member: null, reason: "missing_rule_equivalence_proof" };
  }

  const name = (contract.name ?? "").trim();
  const stemKey = (contract.stem_key ?? "").trim();
  const displayStem = (contract.display_stem ?? "").trim();
  const sharedQuestion = (contract.shared_question ?? "").trim();
  const preposition = (contract.preposition ?? "").trim().toLowerCase();
  const deadlineLabel = (contract.deadline_label ?? "").trim();
  const shortDeadline = (contract.short_deadline ?? "").trim();
  const calendarDate = (contract.calendar_date ?? "").trim();
  const deadlineInstant = (contract.deadline_instant ?? "").trim();
  const deadlineEpochMs = parseTimezoneAwareEpochMs(deadlineInstant);

  if (
    !name ||
    !stemKey ||
    !displayStem ||
    !sharedQuestion ||
    preposition !== "by" ||
    !deadlineLabel ||
    !shortDeadline ||
    !calendarDate ||
    deadlineEpochMs == null
  ) {
    return { member: null, reason: "question_or_deadline_verification_failed" };
  }

  // Section 3B: Verify that `deadline_instant` matches `calendar_date` and `cutoff_local_time`
  // in `cutoff_timezone` without any `[-14h, +36h]` tolerance window.
  if (
    !verifyContractualCutoffInTimezone(
      deadlineEpochMs,
      calendarDate,
      cutoffTimezone,
      cutoffLocalTime,
    )
  ) {
    return {
      member: null,
      reason: "deadline_instant_cutoff_mismatch",
    };
  }

  // Section 3C: Keep `open`, `deadline_passed`, `trading_closed`, `resolved`, `void`, and `unknown` distinct.
  const rawSettlement = contract.settlement;
  if (!rawSettlement || typeof rawSettlement !== "object") {
    return { member: null, reason: "missing_settlement_evidence" };
  }
  if (
    rawSettlement.untrusted_local_grade === true ||
    rawSettlement.conflicting_settlement_evidence === true
  ) {
    return { member: null, reason: "member_settlement_unknown" };
  }

  const nowMs = parseTimezoneAwareEpochMs(options.nowIso);
  const itemStatus = (itemData?.status ?? rawSettlement.status ?? "open")
    .trim()
    .toLowerCase();
  const rawWinner = (
    rawSettlement.result ??
    rawSettlement.winner ??
    itemData?.winner ??
    ""
  ).trim();
  const normalizedWinner =
    rawWinner === "Yes" || rawWinner === "No" ? rawWinner : null;
  const hasVenueClosure =
    rawSettlement.venue_closure_evidence === true ||
    itemStatus === "closed" ||
    itemStatus === "trading_closed" ||
    (rawSettlement.is_trading_closed === true &&
      rawSettlement.venue_closure_evidence !== false);

  let settlementState: FeedDeadlineSettlementState;
  if (rawSettlement.state) {
    if (
      rawSettlement.state === "trading_closed" &&
      rawSettlement.venue_closure_evidence === false &&
      itemStatus === "open"
    ) {
      settlementState = "deadline_passed";
    } else {
      settlementState = rawSettlement.state;
    }
  } else if (rawSettlement.is_settled === true || itemData?.resolved === true) {
    settlementState = "resolved";
  } else if (hasVenueClosure) {
    settlementState = "trading_closed";
  } else if (rawSettlement.is_deadline_passed === true) {
    settlementState = "deadline_passed";
  } else {
    settlementState = "open";
  }

  if (settlementState === "void") {
    return { member: null, reason: "member_settlement_void" };
  }
  if (settlementState === "unknown") {
    return { member: null, reason: "member_settlement_unknown" };
  }
  if (settlementState === "resolved" && normalizedWinner == null) {
    return {
      member: null,
      reason: "resolved_without_authoritative_winner",
    };
  }
  // If outer item says `closed` without an authoritative resolved state, treat as `trading_closed`.
  if (
    (settlementState === "open" || settlementState === "deadline_passed") &&
    (itemStatus === "closed" || itemStatus === "trading_closed")
  ) {
    settlementState = "trading_closed";
  }
  // A passed condition cutoff without venue closure or result is `deadline_passed`, never `trading_closed`.
  if (
    settlementState === "open" &&
    nowMs != null &&
    nowMs >= deadlineEpochMs
  ) {
    settlementState = "deadline_passed";
  }

  const isSettled = settlementState === "resolved";
  const isTradingClosed = settlementState === "trading_closed";
  const isDeadlinePassed = settlementState === "deadline_passed";
  const settledText = isSettled
    ? `Resolved · ${normalizedWinner}`
    : isTradingClosed
      ? "Trading closed"
      : isDeadlinePassed
        ? "Deadline passed"
        : null;
  const laggingLocalStatus = Boolean(
    rawSettlement.lagging_local_status ||
      ((isSettled || isTradingClosed) &&
        (itemData?.status ?? "open").toLowerCase() === "open" &&
        !itemData?.winner),
  );

  // Verify exact outcome binding (6C): never read top_outcomes[0] unless its ID
  // is `yes_outcome_id`, and never complement `no_probability`.
  let yesProbability: number | null =
    typeof contract.yes_probability === "number" &&
    Number.isFinite(contract.yes_probability) &&
    contract.yes_probability >= 0 &&
    contract.yes_probability <= 1
      ? contract.yes_probability
      : null;

  let yesRenderedPercent: number | null =
    typeof contract.yes_rendered_percent === "number" &&
    Number.isInteger(contract.yes_rendered_percent)
      ? contract.yes_rendered_percent
      : null;

  if (itemData?.top_outcomes?.length) {
    const matchedOutcome = itemData.top_outcomes.find(
      (o) => o.id === contract.yes_outcome_id,
    );
    if (matchedOutcome) {
      if (
        yesProbability == null &&
        typeof matchedOutcome.probability === "number" &&
        Number.isFinite(matchedOutcome.probability)
      ) {
        yesProbability = matchedOutcome.probability;
      }
      if (
        yesRenderedPercent == null &&
        typeof matchedOutcome.rendered_percent === "number"
      ) {
        yesRenderedPercent = matchedOutcome.rendered_percent;
      }
    }
  }

  if (yesRenderedPercent == null && yesProbability != null) {
    yesRenderedPercent = Math.round(yesProbability * 100);
  }

  const yesPercentText =
    yesProbability != null
      ? formatProbabilityPercent(yesProbability, {
          rendered: yesRenderedPercent,
        })
      : "—";
  const barWidthPercent =
    yesProbability != null
      ? Math.max(0, Math.min(100, Math.round(yesProbability * 100)))
      : 0;

  // Section 3D: Observation timestamps come strictly from `contract.price_observed_at`.
  // Never substitute `options.nowIso` or `new Date()` when `price_observed_at` is missing!
  const priceObservedAt =
    typeof contract.price_observed_at === "string" &&
    contract.price_observed_at.trim()
      ? contract.price_observed_at.trim()
      : null;
  const observedMs = parseTimezoneAwareEpochMs(priceObservedAt);

  const observationFresh = Boolean(
    observedMs != null &&
      rawSettlement.stale_observation !== true &&
      (nowMs == null ||
        (nowMs - observedMs >= -300_000 &&
          (nowMs - observedMs) / 3600_000 <= DATED_BASIS_WINDOW_HOURS)),
  );

  // Verify stored movement claim AND outcome-bound dated comparison basis (6A / 6C / 6D / 6E).
  const storedClaim =
    typeof contract.stored_movement_claim === "number" &&
    Number.isFinite(contract.stored_movement_claim)
      ? contract.stored_movement_claim
      : null;
  const basis = contract.movement_basis;
  const basisMs = basis ? parseTimezoneAwareEpochMs(basis.observed_at) : null;

  let ageHoursAtObservation: number | null = null;
  if (observedMs != null && basisMs != null) {
    ageHoursAtObservation = (observedMs - basisMs) / 3600_000;
  }

  const basisFreshNow =
    nowMs == null ||
    basisMs == null ||
    ((nowMs - basisMs) / 3600_000 >= DATED_BASIS_MIN_AGE_HOURS &&
      (nowMs - basisMs) / 3600_000 <= DATED_BASIS_WINDOW_HOURS);

  const basisBoundToYes = Boolean(
    basis &&
      basis.outcome_id === contract.yes_outcome_id &&
      typeof basis.basis_price === "number" &&
      Number.isFinite(basis.basis_price) &&
      basis.basis_price >= 0 &&
      basis.basis_price <= 1 &&
      basisMs != null &&
      ageHoursAtObservation != null &&
      ageHoursAtObservation >= DATED_BASIS_MIN_AGE_HOURS &&
      ageHoursAtObservation <= DATED_BASIS_WINDOW_HOURS &&
      basisFreshNow,
  );

  const admitsZero = Boolean(basis?.admits_zero || source === "datagolf");
  const hasStoredClaim =
    storedClaim != null && (storedClaim !== 0 || admitsZero);

  let movementStatus: DeadlineFamilyMemberViewModel["movementStatus"] = "none";
  let supportedMoveFraction: number | null = null;
  let supportedMovePoints: number | null = null;
  let timeframe: DeadlineMovementTimeframe | null = null;

  if (
    settlementState === "open" &&
    yesProbability != null &&
    observationFresh &&
    priceObservedAt != null &&
    hasStoredClaim &&
    basisBoundToYes &&
    basis
  ) {
    const rawMove = yesProbability - basis.basis_price;
    const tf = formatDeadlineMovementTimeframe(
      basis.observed_at,
      priceObservedAt,
      options.timeZone,
      options.nowIso,
    );
    if (tf.valid) {
      timeframe = tf;
      supportedMoveFraction = Math.round(rawMove * 1e6) / 1e6;
      supportedMovePoints = Math.round(rawMove * 1000) / 10;
      const absMove = Math.abs(supportedMoveFraction);
      if (absMove < 1e-9) {
        movementStatus = "measured_zero";
      } else if (absMove < DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION) {
        movementStatus = "sub_threshold";
      } else if (absMove < DEADLINE_HERO_MIN_MOVEMENT_FRACTION) {
        movementStatus = "moderate";
      } else {
        movementStatus = "hero";
      }
    }
  }

  const showHeroMovementChip =
    settlementState === "open" &&
    movementStatus === "hero" &&
    supportedMoveFraction != null &&
    timeframe?.chipTimeframe != null;
  const heroMovementUp =
    supportedMoveFraction != null && supportedMoveFraction > 0;
  const ptsText =
    supportedMoveFraction != null
      ? formatDeadlinePointsText(supportedMoveFraction)
      : null;
  const heroMovementChipText =
    showHeroMovementChip && ptsText
      ? `${heroMovementUp ? "↑" : "↓"} ${ptsText} pts`
      : null;
  const heroTimeframeText = showHeroMovementChip
    ? (timeframe?.chipTimeframe ?? null)
    : null;
  const movementSentenceSummary =
    (movementStatus === "hero" || movementStatus === "moderate") &&
    supportedMoveFraction != null &&
    timeframe?.sentenceTimeframe
      ? `${supportedMoveFraction > 0 ? "Up" : "Down"} ${formatPointsUnit(supportedMoveFraction)} ${timeframe.sentenceTimeframe}`
      : null;
  const heroMovementAriaLabel = showHeroMovementChip
    ? movementSentenceSummary
    : null;

  const showRowMovementBadge =
    settlementState === "open" &&
    (movementStatus === "hero" || movementStatus === "moderate") &&
    supportedMoveFraction != null;
  const rowMovementFraction = showRowMovementBadge ? supportedMoveFraction : null;

  const unchangedPhrase = timeframe?.sentenceTimeframe
    ? `Unchanged ${timeframe.sentenceTimeframe}`
    : "Unchanged";

  let narrativeCaption: string;
  if (isSettled) {
    narrativeCaption = settledText ?? "Resolved";
  } else if (isTradingClosed) {
    narrativeCaption = "Trading closed · awaiting resolution";
  } else if (isDeadlinePassed) {
    narrativeCaption = "Deadline passed · awaiting result";
  } else if (yesProbability == null) {
    narrativeCaption = `Price unavailable · ${deadlineLabel}`;
  } else if (movementSentenceSummary) {
    narrativeCaption = `${movementSentenceSummary} — ${yesPercentText} chance by ${shortDeadline}`;
  } else if (movementStatus === "measured_zero") {
    narrativeCaption = `${unchangedPhrase} — ${yesPercentText} chance by ${shortDeadline}`;
  } else {
    narrativeCaption = `${yesPercentText} chance by ${shortDeadline}`;
  }

  const noProb =
    typeof contract.no_probability === "number" &&
    Number.isFinite(contract.no_probability)
      ? contract.no_probability
      : null;
  const maxSideProb = Math.max(yesProbability ?? -1, noProb ?? -1);
  const isNearCertain =
    maxSideProb >= NEAR_CERTAIN_THRESHOLD ||
    (yesProbability != null && yesProbability <= 1 - NEAR_CERTAIN_THRESHOLD);

  const referenceForFutureMs = nowMs ?? observedMs;
  const deadlineInFuture =
    referenceForFutureMs != null && deadlineEpochMs > referenceForFutureMs;
  const nearCertainOpenEligible = Boolean(
    settlementState === "open" &&
      observationFresh &&
      deadlineInFuture &&
      isNearCertain &&
      (movementStatus === "hero" || movementStatus === "moderate") &&
      supportedMoveFraction != null &&
      Math.abs(supportedMoveFraction) >= DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION,
  );

  const detailHref = `/futures/${contract.market_id}`;
  const accessibleMovementSuffix = movementSentenceSummary
    ? `, ${movementSentenceSummary}`
    : movementStatus === "measured_zero"
      ? `, ${unchangedPhrase}`
      : "";
  const accessibleLabel = isSettled
    ? `${name} — ${settledText ?? "Resolved"}`
    : isTradingClosed
      ? `${name} — Trading closed (awaiting resolution)`
      : isDeadlinePassed
        ? `${name} — Deadline passed (awaiting result)`
        : yesProbability != null
          ? `${name} — Yes (${yesPercentText})${accessibleMovementSuffix}`
          : `${name} — price unavailable`;

  const providerMarketCount =
    typeof contract.provider_market_count === "number" &&
    Number.isInteger(contract.provider_market_count) &&
    contract.provider_market_count > 0
      ? contract.provider_market_count
      : null;
  const verifiedFamilyCount =
    typeof contract.verified_family_count === "number" &&
    Number.isInteger(contract.verified_family_count) &&
    contract.verified_family_count > 0
      ? contract.verified_family_count
      : null;

  return {
    member: {
      marketId: contract.market_id,
      name,
      source,
      externalId,
      groupId,
      stemKey,
      displayStem,
      sharedQuestion,
      preposition,
      deadlineLabel,
      shortDeadline,
      calendarDate,
      deadlineInstant,
      deadlineEpochMs,
      cutoffTimezone,
      cutoffLocalTime,
      ruleTemplateHash,
      yesOutcomeId: contract.yes_outcome_id,
      noOutcomeId: contract.no_outcome_id,
      yesProbability,
      yesRenderedPercent,
      yesPercentText,
      barWidthPercent,
      priceObservedAt,
      movementStatus,
      supportedMoveFraction,
      supportedMovePoints,
      showHeroMovementChip,
      heroMovementChipText,
      heroMovementUp,
      heroTimeframeText,
      heroMovementAriaLabel,
      showRowMovementBadge,
      rowMovementFraction,
      narrativeCaption,
      settlementState,
      isSettled,
      isTradingClosed,
      isDeadlinePassed,
      settledText,
      laggingLocalStatus,
      isNearCertain,
      nearCertainOpenEligible,
      detailHref,
      accessibleLabel,
      providerMarketCount,
      verifiedFamilyCount,
    },
    reason: null,
  };
}

export function validateAndBuildDeadlineFamilyCardModel(
  input: DeadlineFamilyInput,
  options: BuildDeadlineFamilyOptions = {},
): { model: DeadlineFamilyCardModel | null; rejectionReason: string | null } {
  const items = input.items ?? [];
  const familyContract = input.deadlineFamily ?? null;

  const futuresById = new Map<number, FeedFuturesData>();
  const contractsFromItems: FeedDeadlineMemberContract[] = [];

  for (const item of items) {
    if (item?.type !== "futures" || !item.data) continue;
    const fData = item.data as FeedFuturesData;
    if (typeof fData.id === "number") {
      futuresById.set(fData.id, fData);
    }
    if (fData.deadline_member) {
      contractsFromItems.push(fData.deadline_member);
    }
  }

  const rawContracts =
    familyContract?.members?.length
      ? familyContract.members
      : contractsFromItems;

  if (items.length < 2 && rawContracts.length < 2) {
    return { model: null, rejectionReason: "fewer_than_two_members" };
  }
  if (rawContracts.length < 2 || rawContracts.length < items.length) {
    return { model: null, rejectionReason: "missing_producer_member_contract" };
  }

  const verifiedMembers: VerifiedMemberInternal[] = [];
  for (const rawContract of rawContracts) {
    const fData =
      rawContract && typeof rawContract.market_id === "number"
        ? futuresById.get(rawContract.market_id)
        : undefined;
    const { member, reason } = verifySingleMember(rawContract, fData, options);
    if (!member) {
      return { model: null, rejectionReason: reason ?? "invalid_member" };
    }
    verifiedMembers.push(member);
  }

  const sources = new Set(verifiedMembers.map((m) => m.source));
  const groupIds = new Set(verifiedMembers.map((m) => m.groupId));
  if (sources.size !== 1 || groupIds.size !== 1) {
    return { model: null, rejectionReason: "mixed_provider_or_group_id" };
  }

  const marketIds = new Set(verifiedMembers.map((m) => m.marketId));
  const externalIds = new Set(verifiedMembers.map((m) => m.externalId));
  const yesOutcomeIds = new Set(verifiedMembers.map((m) => m.yesOutcomeId));
  if (
    marketIds.size !== verifiedMembers.length ||
    externalIds.size !== verifiedMembers.length ||
    yesOutcomeIds.size !== verifiedMembers.length
  ) {
    return {
      model: null,
      rejectionReason: "duplicate_market_condition_or_outcome_id",
    };
  }

  const stems = new Set(verifiedMembers.map((m) => m.stemKey));
  const preps = new Set(verifiedMembers.map((m) => m.preposition));
  if (stems.size !== 1 || preps.size !== 1) {
    return { model: null, rejectionReason: "mixed_subject_or_predicate" };
  }

  // Section 3A: All members must share the exact same rule_template_hash, cutoff_timezone, and cutoff_local_time.
  const ruleHashes = new Set(verifiedMembers.map((m) => m.ruleTemplateHash));
  const cutoffTzs = new Set(verifiedMembers.map((m) => m.cutoffTimezone));
  const cutoffTimes = new Set(verifiedMembers.map((m) => m.cutoffLocalTime));
  if (
    ruleHashes.size !== 1 ||
    cutoffTzs.size !== 1 ||
    cutoffTimes.size !== 1
  ) {
    return { model: null, rejectionReason: "mixed_rule_template_or_cutoff" };
  }

  const calendarDates = new Set(verifiedMembers.map((m) => m.calendarDate));
  const deadlineEpochs = new Set(verifiedMembers.map((m) => m.deadlineEpochMs));
  if (
    calendarDates.size !== verifiedMembers.length ||
    deadlineEpochs.size !== verifiedMembers.length
  ) {
    return { model: null, rejectionReason: "duplicate_or_ambiguous_deadline" };
  }

  // Sort in ascending deadline_instant order (Q2)
  const ascending = [...verifiedMembers].sort(
    (a, b) => a.deadlineEpochMs - b.deadlineEpochMs || a.marketId - b.marketId,
  );
  const sortedCalendarDates = [...verifiedMembers]
    .map((m) => m.calendarDate)
    .sort();
  if (
    ascending.some((m, idx) => m.calendarDate !== sortedCalendarDates[idx])
  ) {
    return {
      model: null,
      rejectionReason: "deadline_instant_contradicts_calendar_order",
    };
  }

  const allResolved = ascending.every((m) => m.settlementState === "resolved");
  let selectedMarketId: number;
  let selectionReason: DeadlineFamilyCardModel["selectionReason"];
  let selectionBadgeText: string;
  let familyState: DeadlineFamilyCardModel["familyState"];

  if (allResolved) {
    familyState = "settled";
    const yesWinner = ascending.find((m) => m.settledText === "Resolved · Yes");
    const chosen = yesWinner ?? ascending[ascending.length - 1];
    selectedMarketId = chosen.marketId;
    selectionReason = "settled_family";
    selectionBadgeText = "Resolved";
  } else {
    familyState = "open";
    // Only genuinely `open` members (never `trading_closed` or `resolved`) are eligible for representative selection.
    const eligibleOpenPriced = ascending.filter(
      (m) =>
        m.settlementState === "open" &&
        m.yesProbability != null &&
        (!m.isNearCertain || m.nearCertainOpenEligible),
    );
    if (eligibleOpenPriced.length === 0) {
      return {
        model: null,
        rejectionReason: "no_eligible_open_priced_member",
      };
    }

    // Q1: Select the open deadline with the largest eligible supported dated move (>= 2 pts).
    // Fallback: open priced proposition nearest 50%.
    // Deterministic tie-break: abs(move) desc -> abs(prob - 0.50) asc -> deadlineEpoch asc -> marketId asc.
    const eligibleMovers = eligibleOpenPriced.filter(
      (m) =>
        (m.movementStatus === "hero" || m.movementStatus === "moderate") &&
        m.supportedMoveFraction != null &&
        Math.abs(m.supportedMoveFraction) >=
          DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION,
    );

    if (eligibleMovers.length > 0) {
      eligibleMovers.sort((a, b) => {
        const moveDiff =
          Math.round(Math.abs(b.supportedMoveFraction ?? 0) * 1e6) -
          Math.round(Math.abs(a.supportedMoveFraction ?? 0) * 1e6);
        if (moveDiff !== 0) return moveDiff;
        const distDiff =
          Math.round(Math.abs((a.yesProbability ?? 0) - 0.5) * 1e6) -
          Math.round(Math.abs((b.yesProbability ?? 0) - 0.5) * 1e6);
        if (distDiff !== 0) return distDiff;
        if (a.deadlineEpochMs !== b.deadlineEpochMs) {
          return a.deadlineEpochMs - b.deadlineEpochMs;
        }
        return a.marketId - b.marketId;
      });
      selectedMarketId = eligibleMovers[0].marketId;
      selectionReason = "largest_supported_dated_move";
      selectionBadgeText = "Largest recent move";
    } else {
      eligibleOpenPriced.sort((a, b) => {
        const distDiff =
          Math.round(Math.abs((a.yesProbability ?? 0) - 0.5) * 1e6) -
          Math.round(Math.abs((b.yesProbability ?? 0) - 0.5) * 1e6);
        if (distDiff !== 0) return distDiff;
        if (a.deadlineEpochMs !== b.deadlineEpochMs) {
          return a.deadlineEpochMs - b.deadlineEpochMs;
        }
        return a.marketId - b.marketId;
      });
      selectedMarketId = eligibleOpenPriced[0].marketId;
      selectionReason = "nearest_50_pct_fallback";
      selectionBadgeText = "Selected deadline";
    }
  }

  const membersWithRepFlag: DeadlineFamilyMemberViewModel[] = ascending.map(
    (m) => ({
      marketId: m.marketId,
      name: m.name,
      source: m.source,
      externalId: m.externalId,
      groupId: m.groupId,
      deadlineLabel: m.deadlineLabel,
      shortDeadline: m.shortDeadline,
      calendarDate: m.calendarDate,
      deadlineInstant: m.deadlineInstant,
      deadlineEpochMs: m.deadlineEpochMs,
      cutoffTimezone: m.cutoffTimezone,
      cutoffLocalTime: m.cutoffLocalTime,
      ruleTemplateHash: m.ruleTemplateHash,
      yesOutcomeId: m.yesOutcomeId,
      noOutcomeId: m.noOutcomeId,
      yesProbability: m.yesProbability,
      yesRenderedPercent: m.yesRenderedPercent,
      yesPercentText: m.yesPercentText,
      barWidthPercent: m.barWidthPercent,
      priceObservedAt: m.priceObservedAt,
      movementStatus: m.movementStatus,
      supportedMoveFraction: m.supportedMoveFraction,
      supportedMovePoints: m.supportedMovePoints,
      showHeroMovementChip: m.showHeroMovementChip,
      heroMovementChipText: m.heroMovementChipText,
      heroMovementUp: m.heroMovementUp,
      heroTimeframeText: m.heroTimeframeText,
      heroMovementAriaLabel: m.heroMovementAriaLabel,
      showRowMovementBadge: m.showRowMovementBadge,
      rowMovementFraction: m.rowMovementFraction,
      narrativeCaption: m.narrativeCaption,
      settlementState: m.settlementState,
      isSettled: m.isSettled,
      isTradingClosed: m.isTradingClosed,
      isDeadlinePassed: m.isDeadlinePassed,
      settledText: m.settledText,
      laggingLocalStatus: m.laggingLocalStatus,
      isNearCertain: m.isNearCertain,
      nearCertainOpenEligible: m.nearCertainOpenEligible,
      isRepresentative: m.marketId === selectedMarketId,
      detailHref: m.detailHref,
      accessibleLabel: m.accessibleLabel,
      providerMarketCount: m.providerMarketCount,
      verifiedFamilyCount: m.verifiedFamilyCount,
    }),
  );

  const representative =
    membersWithRepFlag.find((m) => m.isRepresentative) ??
    membersWithRepFlag[0];

  // 6F: Distinguish represented family members, verified family total, and raw provider inventory.
  const representedCount = membersWithRepFlag.length;
  const candidateCounts = new Set<number>();
  if (
    typeof familyContract?.provider_market_count === "number" &&
    familyContract.provider_market_count >= representedCount
  ) {
    candidateCounts.add(familyContract.provider_market_count);
  }
  for (const m of membersWithRepFlag) {
    if (
      m.providerMarketCount != null &&
      m.providerMarketCount >= representedCount
    ) {
      candidateCounts.add(m.providerMarketCount);
    }
  }
  const providerMarketCount =
    candidateCounts.size === 1 ? Array.from(candidateCounts)[0] : null;
  const inventoryComplete =
    providerMarketCount != null
      ? providerMarketCount === representedCount
      : null;

  const verifiedFamilyCounts = new Set<number>();
  if (
    typeof familyContract?.verified_family_count === "number" &&
    Number.isInteger(familyContract.verified_family_count) &&
    familyContract.verified_family_count >= representedCount
  ) {
    verifiedFamilyCounts.add(familyContract.verified_family_count);
  }
  for (const m of membersWithRepFlag) {
    if (
      m.verifiedFamilyCount != null &&
      m.verifiedFamilyCount >= representedCount
    ) {
      verifiedFamilyCounts.add(m.verifiedFamilyCount);
    }
  }
  const verifiedFamilyCount =
    verifiedFamilyCounts.size === 1
      ? Array.from(verifiedFamilyCounts)[0]
      : representedCount;

  const expandLabel =
    verifiedFamilyCount != null && verifiedFamilyCount > representedCount
      ? `Compare ${representedCount} of ${verifiedFamilyCount} deadlines`
      : `Compare ${representedCount} deadlines`;
  const collapseLabel = "Hide deadlines";

  const firstFutures =
    items.find((it) => it?.type === "futures")?.data as
      | FeedFuturesData
      | undefined;
  const category = firstFutures?.llm_sport_category ?? null;
  const source = ascending[0].source;
  const groupId = ascending[0].groupId;
  const fallbackStoryKey = groupId.toLowerCase().startsWith(`${source}:`)
    ? `${DEADLINE_FAMILY_STORY_PREFIX}${groupId}`
    : `${DEADLINE_FAMILY_STORY_PREFIX}${source}:${groupId}`;
  const storyKey =
    familyContract?.story_key ||
    (isDeadlineFamilyStoryKey(input.storyKey)
      ? input.storyKey!
      : fallbackStoryKey);

  return {
    model: {
      storyKey,
      source,
      groupId,
      title: input.title?.trim() || ascending[0].displayStem,
      sharedQuestion:
        input.sharedQuestion?.trim() || ascending[0].sharedQuestion,
      category,
      familyState,
      ruleTemplateHash: ascending[0].ruleTemplateHash,
      cutoffTimezone: ascending[0].cutoffTimezone,
      cutoffLocalTime: ascending[0].cutoffLocalTime,
      selectionReason,
      selectionBadgeText,
      tieBreakRule: DETERMINISTIC_TIE_BREAK_RULE,
      representative,
      members: membersWithRepFlag,
      representedCount,
      verifiedFamilyCount,
      providerMarketCount,
      inventoryComplete,
      expandLabel,
      collapseLabel,
    },
    rejectionReason: null,
  };
}

export function buildDeadlineFamilyCardModel(
  input: DeadlineFamilyInput,
  options: BuildDeadlineFamilyOptions = {},
): DeadlineFamilyCardModel | null {
  return validateAndBuildDeadlineFamilyCardModel(input, options).model;
}
