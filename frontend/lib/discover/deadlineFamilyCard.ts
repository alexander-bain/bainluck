import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type {
  FeedDeadlineFamilyContract,
  FeedDeadlineMemberContract,
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

const SETTLED_STATUSES = new Set([
  "resolved",
  "closed",
  "settled",
  "finalized",
  "final",
]);

const MONTH_NUMBERS: Record<string, number> = {
  jan: 1,
  january: 1,
  feb: 2,
  february: 2,
  mar: 3,
  march: 3,
  apr: 4,
  april: 4,
  may: 5,
  jun: 6,
  june: 6,
  jul: 7,
  july: 7,
  aug: 8,
  august: 8,
  sep: 9,
  sept: 9,
  september: 9,
  oct: 10,
  october: 10,
  nov: 11,
  november: 11,
  dec: 12,
  december: 12,
};

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

const MONTH_PATTERN =
  "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?";

const CUMULATIVE_DEADLINE_QUESTION_RE =
  /^\s*(.+?)\s+\b(by)\s+([^?]+?)\s*\??\s*$/i;

const CALENDAR_DATE_DEADLINE_RE = new RegExp(
  `^(${MONTH_PATTERN})\\.?\\s+(\\d{1,2})(?:\\s*,\\s*(\\d{4})|\\s+(\\d{4}))?$`,
  "i",
);

const EXCLUSIVE_BUCKET_RE = new RegExp(
  `\\b(?:between\\s+.+\\s+and|from\\s+.+\\s+to|in\\s+(?:${MONTH_PATTERN})|during\\s+|q[1-4]\\b|quarter\\b|only\\b|or\\s+later\\b|or\\s+earlier\\b|after\\s+)\\b`,
  "i",
);

const NEGATIVE_STEM_RE =
  /\b(?:not|won't|will\s+not|cannot|can't|never|fail(?:s)?\s+to|stay(?:s)?\s+in|remain(?:s)?\s+(?:in|as))\b/i;

const MENTION_ONLY_STEM_RE =
  /\b(?:say|says|said|mention|mentions|mentioned|tweet|tweets|post|posts|utter|use\s+the\s+word)\b/i;

const LEADING_AUXILIARY_RE = /^(?:will|does|do|is|are|has|have)\s+/i;

const ISO_TIMEZONE_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

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

function daysInMonthUtc(year: number, month1To12: number): number {
  return new Date(Date.UTC(year, month1To12, 0)).getUTCDate();
}

function normalizeStem(rawStem: string): {
  stemKey: string;
  displayStem: string;
} {
  const collapsed = rawStem
    .trim()
    .replace(/\s+/g, " ")
    .replace(/[?.,:; ]+$/, "");
  const withoutAux = collapsed.replace(LEADING_AUXILIARY_RE, "").trim();
  if (!withoutAux) return { stemKey: "", displayStem: "" };
  const displayStem = withoutAux[0].toUpperCase() + withoutAux.slice(1);
  const stemKey = withoutAux
    .toLowerCase()
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return { stemKey, displayStem };
}

export interface ParsedCumulativeDeadlineQuestion {
  stemKey: string;
  displayStem: string;
  sharedQuestion: string;
  preposition: string;
  deadlineText: string;
  shortDeadline: string;
  deadlineLabel: string;
  calendarDate: string;
  deadlineInstant: string;
  deadlineEpochMs: number;
}

export function parseCumulativeDeadlineQuestion(
  name: string | null | undefined,
  resolutionDate: string | null | undefined,
): ParsedCumulativeDeadlineQuestion | null {
  if (typeof name !== "string") return null;
  const cleanedName = name.trim();
  if (!cleanedName || EXCLUSIVE_BUCKET_RE.test(cleanedName)) return null;

  const match = CUMULATIVE_DEADLINE_QUESTION_RE.exec(cleanedName);
  if (!match) return null;

  const rawStem = match[1].trim();
  const prep = match[2].trim().toLowerCase();
  const rawDeadline = match[3].trim();
  if (!rawStem || !rawDeadline) return null;
  if (EXCLUSIVE_BUCKET_RE.test(rawDeadline) || EXCLUSIVE_BUCKET_RE.test(rawStem)) {
    return null;
  }
  if (NEGATIVE_STEM_RE.test(rawStem) || NEGATIVE_STEM_RE.test(rawDeadline)) {
    return null;
  }
  if (MENTION_ONLY_STEM_RE.test(rawStem)) {
    return null;
  }

  const dateMatch = CALENDAR_DATE_DEADLINE_RE.exec(rawDeadline);
  if (!dateMatch) return null;

  const monthToken = dateMatch[1].replace(/\.$/, "").toLowerCase();
  const monthNum = MONTH_NUMBERS[monthToken];
  if (!monthNum) return null;

  const dayNum = Number(dateMatch[2]);
  if (!Number.isInteger(dayNum) || dayNum < 1 || dayNum > 31) return null;

  const explicitYearStr = dateMatch[3] || dateMatch[4];
  const explicitYear = explicitYearStr ? Number(explicitYearStr) : null;

  const deadlineEpochMs = parseTimezoneAwareEpochMs(resolutionDate);
  if (deadlineEpochMs == null || !resolutionDate) return null;

  const instantYear = new Date(deadlineEpochMs).getUTCFullYear();
  const candidateYears =
    explicitYear != null
      ? [explicitYear]
      : [instantYear, instantYear - 1, instantYear + 1];

  let matchedYear: number | null = null;
  for (const year of candidateYears) {
    if (year < 2000 || year > 2100) continue;
    const maxDay = daysInMonthUtc(year, monthNum);
    if (dayNum < 1 || dayNum > maxDay) continue;
    const dayStartMs = Date.UTC(year, monthNum - 1, dayNum, 0, 0, 0);
    const dayEndMs = Date.UTC(year, monthNum - 1, dayNum, 23, 59, 59);
    if (
      deadlineEpochMs >= dayStartMs - 14 * 3600_000 &&
      deadlineEpochMs <= dayEndMs + 36 * 3600_000
    ) {
      matchedYear = year;
      break;
    }
  }
  if (matchedYear == null) return null;

  const { stemKey, displayStem } = normalizeStem(rawStem);
  if (!stemKey || stemKey.split(" ").length < 2) return null;

  const shortMonth = SHORT_MONTH_NAMES[monthNum];
  const shortDeadline =
    explicitYear != null
      ? `${shortMonth} ${dayNum}, ${explicitYear}`
      : `${shortMonth} ${dayNum}`;
  const deadlineLabel = `By ${shortDeadline}`;
  const calendarDate = `${String(matchedYear).padStart(4, "0")}-${String(
    monthNum,
  ).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;

  return {
    stemKey,
    displayStem,
    sharedQuestion: `${displayStem} by…?`,
    preposition: prep,
    deadlineText: rawDeadline,
    shortDeadline,
    deadlineLabel,
    calendarDate,
    deadlineInstant: resolutionDate.trim(),
    deadlineEpochMs,
  };
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
): DeadlineMovementTimeframe {
  const resolvedTz =
    timeZone ||
    (typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC") ||
    "UTC";

  const basisMs = parseTimezoneAwareEpochMs(basisObservedAt);
  const refMs = parseTimezoneAwareEpochMs(referenceAt);
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
  try {
    basisLocal = localDateParts(basisMs, effectiveTz);
    refLocal = localDateParts(refMs, effectiveTz);
  } catch {
    effectiveTz = "UTC";
    basisLocal = localDateParts(basisMs, "UTC");
    refLocal = localDateParts(refMs, "UTC");
  }

  const basisDayUtc = Date.UTC(
    basisLocal.year,
    basisLocal.month - 1,
    basisLocal.day,
  );
  const refDayUtc = Date.UTC(refLocal.year, refLocal.month - 1, refLocal.day);
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

  if (dayDiff === 1) {
    return {
      valid: true,
      calendarDayDiff: 1,
      crossesPreviousCalendarDay: true,
      chipTimeframe: "since yesterday",
      sentenceTimeframe: "since yesterday",
      timeZone: effectiveTz,
    };
  }

  if (dayDiff === 0) {
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
  isSettled: boolean;
  settledText: string | null;
  laggingLocalStatus: boolean;
  isNearCertain: boolean;
  nearCertainOpenEligible: boolean;
  isRepresentative: boolean;
  detailHref: string;
  accessibleLabel: string;
  providerMarketCount: number | null;
}

export interface DeadlineFamilyCardModel {
  storyKey: string;
  source: string;
  groupId: string;
  title: string;
  sharedQuestion: string;
  category: string | null;
  familyState: "open" | "settled";
  selectionReason:
    | "largest_supported_dated_move"
    | "nearest_50_pct_fallback"
    | "settled_family";
  selectionBadgeText: string;
  tieBreakRule: string;
  representative: DeadlineFamilyMemberViewModel;
  members: DeadlineFamilyMemberViewModel[];
  representedCount: number;
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

  const parsedQuestion = parseCumulativeDeadlineQuestion(
    contract.name,
    contract.deadline_instant,
  );
  if (!parsedQuestion) {
    return { member: null, reason: "question_or_deadline_verification_failed" };
  }

  // Re-verify settlement precedence (6D): authoritative terminal evidence wins
  // over a lagging local status="open" or null winner.
  const itemStatus = (itemData?.status ?? contract.settlement?.status ?? "open")
    .trim()
    .toLowerCase();
  const itemWinner = (
    itemData?.winner ??
    contract.settlement?.result ??
    contract.settlement?.winner ??
    ""
  ).trim();
  const isSettled = Boolean(
    contract.settlement?.is_settled === true ||
      itemData?.resolved === true ||
      SETTLED_STATUSES.has(itemStatus) ||
      itemWinner.length > 0,
  );
  const settledResult =
    contract.settlement?.result ??
    contract.settlement?.winner ??
    (itemWinner || null);
  const settledText = isSettled
    ? settledResult
      ? `Resolved · ${settledResult}`
      : "Resolved"
    : null;
  const laggingLocalStatus = Boolean(
    contract.settlement?.lagging_local_status ||
      (isSettled &&
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

  // Verify stored movement claim AND outcome-bound dated comparison basis (6A / 6C / 6D / 6E).
  const storedClaim =
    typeof contract.stored_movement_claim === "number" &&
    Number.isFinite(contract.stored_movement_claim)
      ? contract.stored_movement_claim
      : null;
  const basis = contract.movement_basis;
  const referenceIso =
    options.nowIso ??
    contract.price_observed_at ??
    itemData?.price_observed_at ??
    null;
  const referenceMs = parseTimezoneAwareEpochMs(referenceIso);
  const basisMs = basis ? parseTimezoneAwareEpochMs(basis.observed_at) : null;

  let ageHours: number | null = null;
  if (referenceMs != null && basisMs != null) {
    ageHours = (referenceMs - basisMs) / 3600_000;
  } else if (
    basis &&
    typeof basis.age_hours === "number" &&
    Number.isFinite(basis.age_hours)
  ) {
    ageHours = basis.age_hours;
  }

  const basisBoundToYes = Boolean(
    basis &&
      basis.outcome_id === contract.yes_outcome_id &&
      typeof basis.basis_price === "number" &&
      Number.isFinite(basis.basis_price) &&
      basis.basis_price >= 0 &&
      basis.basis_price <= 1 &&
      basisMs != null &&
      ageHours != null &&
      ageHours >= DATED_BASIS_MIN_AGE_HOURS &&
      ageHours <= DATED_BASIS_WINDOW_HOURS,
  );

  const admitsZero = Boolean(basis?.admits_zero || source === "datagolf");
  const hasStoredClaim =
    storedClaim != null && (storedClaim !== 0 || admitsZero);

  let movementStatus: DeadlineFamilyMemberViewModel["movementStatus"] = "none";
  let supportedMoveFraction: number | null = null;
  let supportedMovePoints: number | null = null;
  let timeframe: DeadlineMovementTimeframe | null = null;

  if (!isSettled && yesProbability != null && hasStoredClaim && basisBoundToYes && basis) {
    const rawMove = yesProbability - basis.basis_price;
    const tf = formatDeadlineMovementTimeframe(
      basis.observed_at,
      contract.price_observed_at ?? itemData?.price_observed_at ?? options.nowIso,
      options.timeZone,
    );
    if (tf.valid) {
      timeframe = tf;
      supportedMoveFraction = Math.round(rawMove * 1e6) / 1e6;
      supportedMovePoints = Math.round(rawMove * 1000) / 10;
      const absMove = Math.abs(rawMove);
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
    !isSettled &&
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
    !isSettled &&
    (movementStatus === "hero" || movementStatus === "moderate") &&
    supportedMoveFraction != null;
  const rowMovementFraction = showRowMovementBadge ? supportedMoveFraction : null;

  const unchangedPhrase = timeframe?.sentenceTimeframe
    ? `Unchanged ${timeframe.sentenceTimeframe}`
    : "Unchanged";

  let narrativeCaption: string;
  if (isSettled) {
    narrativeCaption = settledText ?? "Resolved";
  } else if (yesProbability == null) {
    narrativeCaption = `Price unavailable · ${parsedQuestion.deadlineLabel}`;
  } else if (movementSentenceSummary) {
    narrativeCaption = `${movementSentenceSummary} — ${yesPercentText} chance by ${parsedQuestion.shortDeadline}`;
  } else if (movementStatus === "measured_zero") {
    narrativeCaption = `${unchangedPhrase} — ${yesPercentText} chance by ${parsedQuestion.shortDeadline}`;
  } else {
    narrativeCaption = `${yesPercentText} chance by ${parsedQuestion.shortDeadline}`;
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

  const deadlineInFuture =
    referenceMs == null || parsedQuestion.deadlineEpochMs > referenceMs;
  const nearCertainOpenEligible = Boolean(
    !isSettled &&
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
    ? `${contract.name} — ${settledText ?? "Resolved"}`
    : yesProbability != null
      ? `${contract.name} — Yes (${yesPercentText})${accessibleMovementSuffix}`
      : `${contract.name} — price unavailable`;

  const providerMarketCount =
    typeof contract.provider_market_count === "number" &&
    Number.isInteger(contract.provider_market_count) &&
    contract.provider_market_count > 0
      ? contract.provider_market_count
      : null;

  return {
    member: {
      marketId: contract.market_id,
      name: contract.name.trim(),
      source,
      externalId,
      groupId,
      stemKey: parsedQuestion.stemKey,
      displayStem: parsedQuestion.displayStem,
      sharedQuestion: parsedQuestion.sharedQuestion,
      preposition: parsedQuestion.preposition,
      deadlineLabel: parsedQuestion.deadlineLabel,
      shortDeadline: parsedQuestion.shortDeadline,
      calendarDate: parsedQuestion.calendarDate,
      deadlineInstant: parsedQuestion.deadlineInstant,
      deadlineEpochMs: parsedQuestion.deadlineEpochMs,
      yesOutcomeId: contract.yes_outcome_id,
      noOutcomeId: contract.no_outcome_id,
      yesProbability,
      yesRenderedPercent,
      yesPercentText,
      barWidthPercent,
      priceObservedAt:
        contract.price_observed_at ?? itemData?.price_observed_at ?? null,
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
      isSettled,
      settledText,
      laggingLocalStatus,
      isNearCertain,
      nearCertainOpenEligible,
      detailHref,
      accessibleLabel,
      providerMarketCount,
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

  const allSettled = ascending.every((m) => m.isSettled);
  let selectedMarketId: number;
  let selectionReason: DeadlineFamilyCardModel["selectionReason"];
  let selectionBadgeText: string;
  let familyState: DeadlineFamilyCardModel["familyState"];

  if (allSettled) {
    familyState = "settled";
    const yesWinner = ascending.find((m) => m.settledText === "Resolved · Yes");
    const chosen = yesWinner ?? ascending[ascending.length - 1];
    selectedMarketId = chosen.marketId;
    selectionReason = "settled_family";
    selectionBadgeText = "Resolved";
  } else {
    familyState = "open";
    const eligibleOpenPriced = ascending.filter(
      (m) =>
        !m.isSettled &&
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
      selectionBadgeText = "Largest 24h move";
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
      isSettled: m.isSettled,
      settledText: m.settledText,
      laggingLocalStatus: m.laggingLocalStatus,
      isNearCertain: m.isNearCertain,
      nearCertainOpenEligible: m.nearCertainOpenEligible,
      isRepresentative: m.marketId === selectedMarketId,
      detailHref: m.detailHref,
      accessibleLabel: m.accessibleLabel,
      providerMarketCount: m.providerMarketCount,
    }),
  );

  const representative =
    membersWithRepFlag.find((m) => m.isRepresentative) ??
    membersWithRepFlag[0];

  // 6F: Distinguish represented family members from complete provider inventory.
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

  const expandLabel =
    providerMarketCount != null && providerMarketCount > representedCount
      ? `Compare ${representedCount} of ${providerMarketCount} deadlines`
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
      selectionReason,
      selectionBadgeText,
      tieBreakRule: DETERMINISTIC_TIE_BREAK_RULE,
      representative,
      members: membersWithRepFlag,
      representedCount,
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
