import RAW_SCORECARD from "@/lib/evals/data/cu-scorecard.json";
import { sourceLink } from "@/lib/evals/sources";
import { issueRef, type MeasuredTruth, type Truth } from "@/lib/evals/truth";

export interface CuCountBucket {
  right: number;
  wrong: number;
  blank: number;
  said_not_known: number;
  total: number;
}

export interface CuFieldScoreRow {
  field: string;
  label: string;
  decided_by: "code" | "model" | "code_and_model";
  code: CuCountBucket;
  model: CuCountBucket;
  total: CuCountBucket;
}

export interface CuSliceGroup {
  market_count: number;
  decider_totals: {
    code: CuCountBucket;
    model: CuCountBucket;
  };
}

export interface CuScorecard {
  status: "not_measured_yet" | "measured";
  asOf: string;
  dataset: string;
  writerRev: number | string | null;
  model: string | null;
  marketCount: number;
  cost: {
    totalUsd: number | null;
    perMarketUsd: number | null;
  };
  deciderTotals: {
    code: CuCountBucket;
    model: CuCountBucket;
  };
  fields: readonly CuFieldScoreRow[];
  slices: Record<string, Record<string, CuSliceGroup>>;
}

export const CU_FIELD_WORDS: Record<string, string> = {
  topic: "Topic",
  subtopic: "Specific area",
  geography: "Region",
  temporal_class: "How time works",
  event_date: "Day of the event",
  recurrence: "How often it repeats",
  stakes: "Real-world stakes",
  breadth: "How wide the audience is",
  oddity: "How unusual it is",
  arc: "Kind of story",
  junk_flags: "Format warnings",
  liveness: "Trading activity",
  subject_ref: "Main subject link",
  frame: "Number and comparison",
  series_key: "Recurring series",
  story_key: "Story group",
  entities: "Named subjects",
};

export const CU_SLICE_ORDER = [
  "by_venue",
  "by_category",
  "by_market_shape",
  "by_exposure",
] as const;

export const CU_SLICE_WORDS: Record<(typeof CU_SLICE_ORDER)[number], string> = {
  by_venue: "By site",
  by_category: "By topic",
  by_market_shape: "By market shape",
  by_exposure: "What readers see vs the rest",
};

export const CU_SLICE_GROUP_WORDS: Record<string, string> = {
  readers_see: "What readers see",
  rest: "The rest",
  binary: "Two-choice",
  multi_outcome: "Multi-choice",
  ladder: "Stepped rungs",
  dated_bucket: "Date buckets",
  unknown: "Unclassified shape",
};

export function plainCuFieldLabel(field: string, fallback: string): string {
  return CU_FIELD_WORDS[field] ?? fallback;
}

export function plainCuSliceGroupLabel(groupKey: string): string {
  const known = CU_SLICE_GROUP_WORDS[groupKey];
  if (known) return known;
  return groupKey
    .replace(/_/g, " ")
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());
}

export function formatCuCostUsd(value: number): string {
  return `$${value.toFixed(value >= 1 ? 2 : 3)}`;
}

function emptyBucket(): CuCountBucket {
  return { right: 0, wrong: 0, blank: 0, said_not_known: 0, total: 0 };
}

function parseBucket(raw: unknown): CuCountBucket {
  if (!raw || typeof raw !== "object") return emptyBucket();
  const rec = raw as Record<string, unknown>;
  const num = (k: string) => (typeof rec[k] === "number" ? (rec[k] as number) : 0);
  return {
    right: num("right"),
    wrong: num("wrong"),
    blank: num("blank"),
    said_not_known: num("said_not_known"),
    total: num("total"),
  };
}

export function parseCuScorecard(raw: unknown): CuScorecard | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const status = r.status === "measured" ? "measured" : "not_measured_yet";
  const asOf = typeof r.as_of === "string" ? r.as_of : "";
  if (!asOf) return null;

  const rawFields = Array.isArray(r.fields) ? r.fields : [];
  const fields: CuFieldScoreRow[] = rawFields
    .filter((f): f is Record<string, unknown> => Boolean(f && typeof f === "object"))
    .map((f): CuFieldScoreRow => {
      const decidedBy: CuFieldScoreRow["decided_by"] =
        f.decided_by === "code" || f.decided_by === "code_and_model"
          ? f.decided_by
          : "model";
      return {
        field: String(f.field ?? ""),
        label: plainCuFieldLabel(String(f.field ?? ""), String(f.label ?? "")),
        decided_by: decidedBy,
        code: parseBucket(f.code),
        model: parseBucket(f.model),
        total: parseBucket(f.total),
      };
    })
    .filter((f) => f.field.length > 0);

  const rawCost = (r.cost && typeof r.cost === "object" ? r.cost : {}) as Record<string, unknown>;
  const rawDt = (
    r.decider_totals && typeof r.decider_totals === "object" ? r.decider_totals : {}
  ) as Record<string, unknown>;

  const slices: Record<string, Record<string, CuSliceGroup>> = {};
  if (r.slices && typeof r.slices === "object") {
    for (const [sliceKey, rawGroups] of Object.entries(r.slices as Record<string, unknown>)) {
      if (!rawGroups || typeof rawGroups !== "object") continue;
      const groupsOut: Record<string, CuSliceGroup> = {};
      for (const [groupKey, rawGroup] of Object.entries(rawGroups as Record<string, unknown>)) {
        if (!rawGroup || typeof rawGroup !== "object") continue;
        const gRec = rawGroup as Record<string, unknown>;
        const gDt = (
          gRec.decider_totals && typeof gRec.decider_totals === "object" ? gRec.decider_totals : {}
        ) as Record<string, unknown>;
        groupsOut[groupKey] = {
          market_count: typeof gRec.market_count === "number" ? gRec.market_count : 0,
          decider_totals: {
            code: parseBucket(gDt.code),
            model: parseBucket(gDt.model),
          },
        };
      }
      slices[sliceKey] = groupsOut;
    }
  }

  return {
    status,
    asOf,
    dataset: typeof r.dataset === "string" ? r.dataset : "sealed",
    writerRev:
      typeof r.writer_rev === "number" || typeof r.writer_rev === "string" ? r.writer_rev : null,
    model: typeof r.model === "string" ? r.model : null,
    marketCount: typeof r.market_count === "number" ? r.market_count : 0,
    cost: {
      totalUsd: typeof rawCost.total_usd === "number" ? rawCost.total_usd : null,
      perMarketUsd: typeof rawCost.per_market_usd === "number" ? rawCost.per_market_usd : null,
    },
    deciderTotals: {
      code: parseBucket(rawDt.code),
      model: parseBucket(rawDt.model),
    },
    fields,
    slices,
  };
}

export function loadCuScorecard(): CuScorecard | null {
  return parseCuScorecard(RAW_SCORECARD);
}

export function cuScorecardTruth(scorecard: CuScorecard): Truth {
  if (scorecard.status === "measured") {
    return {
      kind: "last_run",
      asOf: scorecard.asOf,
      source: sourceLink("cu-scorecard-record"),
    } satisfies MeasuredTruth;
  }
  return {
    kind: "planned",
    waitingOn: "two-person labels on the sealed set",
    ref: issueRef(13900),
  };
}
