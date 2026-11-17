/**
 * Direction 228 (#12885) — Numerical Scale Ordering.
 *
 * A market whose outcomes are values on one numerical scale — an "at least N"
 * ladder, disjoint ranges/bins, a count ("1, 2, 3, 4", "2 (50 bps)"), a rate
 * ("3.75%, 4.0%, 4.25%, ≥ 4.5%"), or signed policy/margin moves ("Cut 25bps",
 * "Fed maintains rate", "Hike 25bps") — lists its rows in ascending numerical
 * order (`low → high`), matching the iPhone margin/total maps
 * (`NBALadderCard9483.swift`: `$0.x < $1.x`).
 *
 * Fields of competitors (teams, nominees, candidates) return `null` from
 * `numericalScaleOrderIndices` and continue to run highest chance first.
 */

export interface NumericalScaleKey {
  kind: "signed_move" | "numeric";
  primary: number;
  boundRank: -1 | 0 | 1;
  secondary: number;
  skeleton: string;
}

const UNIT_MULT: Record<string, number> = {
  k: 1e3,
  thousand: 1e3,
  m: 1e6,
  mn: 1e6,
  million: 1e6,
  b: 1e9,
  bn: 1e9,
  billion: 1e9,
  t: 1e12,
  trillion: 1e12,
};

function unitMult(raw?: string): number {
  if (!raw) return 1;
  const clean = raw.replace(/%/g, "").trim().toLowerCase();
  return UNIT_MULT[clean] ?? 1;
}

function parseNum(raw: string): number {
  return parseFloat(raw.replace(/,/g, ""));
}

const NUM_CORE = "[-+]?\\d+(?:,\\d{3})*(?:\\.\\d+)?";
const MULT_UNIT =
  "(?:%|°[fc]?|\\s*(?:thousand|million|billion|trillion|bps|pts?|points?|goals?|wins?|cuts?|hikes?|days?|weeks?|months?|years?|seats?|[kmbtKMBT]|mn|bn|st|nd|rd|th)\\b)?";

const TRAILING_PAREN_RE = /\s*\([^()]*\)\s*$/;

// Signed policy / rate-move outcomes: "Cut 25bps", "Cut >25bps", "25 bps decrease",
// "50+ bps increase", "Hike 25bps", "Fed maintains rate", "No change"
const HOLD_MOVE_RE =
  /^(?:no\s+change|unchanged|hold|steady|(?:fed\s+)?maintains?\s+rates?)$/i;
const SIGNED_PREFIX_MOVE_RE = new RegExp(
  `^(cut|cuts|decrease|lower|hike|hikes|increase|raise)\\s*(?:by\\s*)?(>\\s*|≥\\s*|>=\\s*|at\\s+least\\s+)?(${NUM_CORE})(\\+)??\\s*(?:bps|basis\\s+points?|%|pts?)?$`,
  "i",
);
const SIGNED_SUFFIX_MOVE_RE = new RegExp(
  `^(>\\s*|≥\\s*|>=\\s*|at\\s+least\\s+)?(${NUM_CORE})(\\+)?\\s*(?:bps|basis\\s+points?|%|pts?)?\\s*(cut|cuts|decrease|hike|hikes|increase)(?:\\s+or\\s+(?:more|larger|greater))?$`,
  "i",
);

const RANGE_BETWEEN_RE = new RegExp(
  `^between\\s+[$€£]?(${NUM_CORE})(${MULT_UNIT})\\s+and\\s+[$€£]?(${NUM_CORE})(${MULT_UNIT})$`,
  "i",
);
const RANGE_DASH_RE = new RegExp(
  `^(?:rank\\s+)?[$€£]?(${NUM_CORE})(${MULT_UNIT})\\s*(?:to|[–—-])\\s*[$€£]?(${NUM_CORE})(${MULT_UNIT})$`,
  "i",
);

const LOWER_PREFIX_RE = new RegExp(
  `^(?:<\\s*|≤\\s*|<=\\s*|below\\s+|under\\s+|less\\s+than\\s+|fewer\\s+than\\s+|at\\s+most\\s+|up\\s+to\\s+|no\\s+more\\s+than\\s+)[$€£]?(${NUM_CORE})(${MULT_UNIT})$`,
  "i",
);
const LOWER_SUFFIX_RE = new RegExp(
  `^[$€£]?(${NUM_CORE})(${MULT_UNIT})\\s+(?:or\\s+(?:below|less|lower|under|fewer)|and\\s+(?:below|under))$`,
  "i",
);

const UPPER_PREFIX_RE = new RegExp(
  `^(?:>\\s*|≥\\s*|>=\\s*|above\\s+|at\\s+least\\s+|over\\s+|more\\s+than\\s+|greater\\s+than\\s+|exceeds?\\s+|reaches?\\s+|hits?\\s+)[$€£]?(${NUM_CORE})(${MULT_UNIT})$`,
  "i",
);
const UPPER_SUFFIX_RE = new RegExp(
  `^(?<prefix>(?:category|cat|tier|level|stage|grade|top)\\s+)?[$€£]?(?<num>${NUM_CORE})(?<unit>${MULT_UNIT})(?:\\+|\\s+or\\s+(?:above|more|higher|greater)|\\s+and\\s+(?:above|more|higher))(?<tail>\\s+[a-z][a-z\\s-]*)?$`,
  "i",
);

const ORDINAL_HIGHER_RE = /^(\d+)\s*(?:st|nd|rd|th)\s+or\s+higher$/i;
const ORDINAL_BELOW_RE = /^below\s+(\d+)\s*(?:st|nd|rd|th)$/i;

const EXACT_RE = new RegExp(
  `^(?:exactly\\s+)?(?<prefix>(?:category|cat|tier|level|stage|grade)\\s+)?[$€£]?(?<num>${NUM_CORE})(?<unit>${MULT_UNIT})$`,
  "i",
);

const ZERO_COUNT_WORD_RE =
  /^(?:none|zero|no\s+(?:cuts?|hikes?|wins?|goals?|points?|medals?|titles?|changes?|rate\s+(?:cuts?|hikes?)))$/i;

function normalizeSkeleton(raw: string): string {
  return raw
    .replace(TRAILING_PAREN_RE, "")
    .toLowerCase()
    .replace(
      /\b(?:exactly|at\s+least|at\s+most|more\s+than|less\s+than|fewer\s+than|greater\s+than|no\s+more\s+than|up\s+to|or\s+(?:above|more|higher|greater|below|less|lower|under|fewer)|and\s+(?:above|more|higher|below|under)|above|below|over|under|between|and|to)\b/g,
      " ",
    )
    .replace(/[<>≤≥=+–—-]/g, " ")
    .replace(/\d[\d,.]*/g, "#")
    .replace(/\b(cut|hike|win|goal|point|pt|day|week|month|year|seat)s\b/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseNumericalScaleKey(
  rawLabel: string | null | undefined,
): NumericalScaleKey | null {
  const full = (rawLabel ?? "").trim();
  if (!full) return null;
  // Multi-leg combo outcomes ("Headline: 0.5% or above, Core: 0.3% or above")
  if (full.includes(",") && full.includes(":")) return null;
  // Pure Yes/No binary claims are never a numeric scale
  if (/^(?:yes|no)$/i.test(full)) return null;
  // Exclude calendar years / dates ("Before 2027", "2028", "March 2027") — date
  // ladders belong to `chronologicalRanks` / `distribution_order === "chronological"`.
  if (
    /\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b/i.test(
      full,
    ) ||
    /^(?:before|after|by|in|prior\s+to|on\s+or\s+before)\s+\d{4}\b/i.test(full)
  ) {
    return null;
  }

  const stripped = full.replace(TRAILING_PAREN_RE, "").trim();
  if (!stripped) return null;

  // 1. Signed rate / policy moves
  if (HOLD_MOVE_RE.test(stripped)) {
    return {
      kind: "signed_move",
      primary: 0,
      boundRank: 0,
      secondary: 0,
      skeleton: "signed_move",
    };
  }
  let m = SIGNED_PREFIX_MOVE_RE.exec(stripped);
  if (m) {
    const dir = /^(?:cut|cuts|decrease|lower)$/i.test(m[1]) ? -1 : 1;
    const isOpen = Boolean(m[2] || m[4]);
    const val = parseNum(m[3]);
    if (!Number.isFinite(val)) return null;
    return {
      kind: "signed_move",
      primary: dir * val,
      boundRank: isOpen ? (dir < 0 ? -1 : 1) : 0,
      secondary: dir * val,
      skeleton: "signed_move",
    };
  }
  m = SIGNED_SUFFIX_MOVE_RE.exec(stripped);
  if (m) {
    const dir = /^(?:cut|cuts|decrease)$/i.test(m[4]) ? -1 : 1;
    const isOpen = Boolean(m[1] || m[3] || /\bor\s+(?:more|larger|greater)$/i.test(stripped));
    const val = parseNum(m[2]);
    if (!Number.isFinite(val)) return null;
    return {
      kind: "signed_move",
      primary: dir * val,
      boundRank: isOpen ? (dir < 0 ? -1 : 1) : 0,
      secondary: dir * val,
      skeleton: "signed_move",
    };
  }

  // 2. Ordinal ladders ("1st or higher", "Below 5th")
  m = ORDINAL_HIGHER_RE.exec(stripped);
  if (m) {
    const v = parseNum(m[1]);
    return {
      kind: "numeric",
      primary: v,
      boundRank: -1,
      secondary: v,
      skeleton: "#ordinal",
    };
  }
  m = ORDINAL_BELOW_RE.exec(stripped);
  if (m) {
    const v = parseNum(m[1]);
    return {
      kind: "numeric",
      primary: v,
      boundRank: 1,
      secondary: v,
      skeleton: "#ordinal",
    };
  }

  // 3. Explicit numeric ranges ("0-10", "$1.2M-$1.5M", "Between 95 and 96")
  for (const rx of [RANGE_BETWEEN_RE, RANGE_DASH_RE]) {
    m = rx.exec(stripped);
    if (m) {
      const u1 = (m[2] || "").trim() || (m[4] || "").trim();
      const u2 = (m[4] || "").trim() || u1;
      const v1 = parseNum(m[1]) * unitMult(u1);
      const v2 = parseNum(m[3]) * unitMult(u2);
      if (!Number.isFinite(v1) || !Number.isFinite(v2)) return null;
      return {
        kind: "numeric",
        primary: v1,
        boundRank: 0,
        secondary: v2,
        skeleton: normalizeSkeleton(stripped),
      };
    }
  }

  // 4. Lower-bounded thresholds ("< 40", "≤ 3.5%", "3.5% or below", "Under 98")
  for (const rx of [LOWER_PREFIX_RE, LOWER_SUFFIX_RE]) {
    m = rx.exec(stripped);
    if (m) {
      const v = parseNum(m[1]) * unitMult(m[2]);
      if (!Number.isFinite(v)) return null;
      return {
        kind: "numeric",
        primary: v,
        boundRank: -1,
        secondary: v,
        skeleton: normalizeSkeleton(stripped),
      };
    }
  }

  // 5. Upper-bounded thresholds ("≥ 4.5%", "Above $102.50", "7+ wins", "Category 3 or above")
  m = UPPER_PREFIX_RE.exec(stripped);
  if (m) {
    const v = parseNum(m[1]) * unitMult(m[2]);
    if (!Number.isFinite(v)) return null;
    return {
      kind: "numeric",
      primary: v,
      boundRank: 1,
      secondary: v,
      skeleton: normalizeSkeleton(stripped),
    };
  }
  m = UPPER_SUFFIX_RE.exec(stripped);
  if (m?.groups) {
    const v = parseNum(m.groups.num) * unitMult(m.groups.unit);
    if (!Number.isFinite(v)) return null;
    return {
      kind: "numeric",
      primary: v,
      boundRank: 1,
      secondary: v,
      skeleton: normalizeSkeleton(stripped),
    };
  }

  // 6. Exact number / rate / count ("3.75%", "2" from "2 (50 bps)", "2 cuts", "$100M")
  m = EXACT_RE.exec(stripped);
  if (m?.groups) {
    const v = parseNum(m.groups.num) * unitMult(m.groups.unit);
    if (!Number.isFinite(v)) return null;
    return {
      kind: "numeric",
      primary: v,
      boundRank: 0,
      secondary: v,
      skeleton: normalizeSkeleton(stripped),
    };
  }

  // 7. Zero-count word ("None", "Zero", "No cuts", "No hikes")
  if (ZERO_COUNT_WORD_RE.test(stripped)) {
    return {
      kind: "numeric",
      primary: 0,
      boundRank: 0,
      secondary: 0,
      skeleton: "zero_word",
    };
  }

  return null;
}

export interface ScaleLabelItem {
  name?: string | null;
  label?: string | null;
}

/**
 * Returns the ascending numerical-scale index permutation `[i0, i1, ...]` for `rows`,
 * or `null` when `rows` is NOT a coherent single-scale numerical market (e.g., a field
 * of teams, nominees, or candidates, or a date ladder).
 */
export function numericalScaleOrderIndices<T extends ScaleLabelItem>(
  rows: readonly T[],
  opts?: { marketType?: string | null },
): number[] | null {
  if (rows.length < 2) return null;

  const parsed: { idx: number; key: NumericalScaleKey }[] = [];
  for (let i = 0; i < rows.length; i++) {
    const raw = rows[i].name ?? rows[i].label ?? "";
    const key = parseNumericalScaleKey(raw);
    if (!key) return null;
    parsed.push({ idx: i, key });
  }

  // Scale coherence check so two unrelated digit-bearing labels never collide:
  const allSignedMove = parsed.every((p) => p.key.kind === "signed_move");
  const hasNonZeroSigned =
    allSignedMove && parsed.some((p) => p.key.primary !== 0);

  if (!hasNonZeroSigned && opts?.marketType !== "quantity") {
    if (parsed.some((p) => p.key.kind === "signed_move")) return null;
    const nonZeroSkeletons = parsed
      .map((p) => p.key.skeleton)
      .filter((sk) => sk !== "zero_word");
    if (nonZeroSkeletons.length === 0) return null;
    const counts = new Map<string, number>();
    let shared = false;
    for (const sk of nonZeroSkeletons) {
      // Collapse range "# #%" and single "#%" when sharing unit tail
      const unitCanon = sk.replace(/#\s+#/g, "#");
      const next = (counts.get(unitCanon) ?? 0) + 1;
      if (next >= 2) shared = true;
      counts.set(unitCanon, next);
    }
    if (!shared && !(nonZeroSkeletons.length === 1 && parsed.length === 2)) {
      return null;
    }
  }

  return [...parsed]
    .sort(
      (a, b) =>
        a.key.primary - b.key.primary ||
        a.key.boundRank - b.key.boundRank ||
        a.key.secondary - b.key.secondary ||
        a.idx - b.idx,
    )
    .map((p) => p.idx);
}

/**
 * Return a copy of `rows` ordered in ascending numerical-scale order when `rows`
 * forms a numerical scale, or `[...rows]` unchanged otherwise.
 */
export function orderByNumericalScale<T extends ScaleLabelItem>(
  rows: readonly T[],
  opts?: { marketType?: string | null },
): T[] {
  const indices = numericalScaleOrderIndices(rows, opts);
  if (!indices) return [...rows];
  return indices.map((i) => rows[i]);
}
