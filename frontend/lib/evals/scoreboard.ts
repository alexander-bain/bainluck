/**
 * THE TEST LIBRARY'S SCOREBOARD, AS RECORDED (#12102 S4).
 *
 * `data/scoreboard-2026-11-03.json` is the unedited output of
 * `cd backend && python3 -m scripts.evals.scoreboard --json`, an offline
 * command that reads committed evidence only (`backend/scripts/evals/README.md`).
 * Its time and commit are the receipt's — when the tests were recorded — not
 * when the command ran. This module reads that file and puts plain words on
 * it; it never edits, sums across families or re-grades a number.
 *
 * Two rules from the command's own README hold here too:
 *   • A family's case count is the family's own total, which counts a shared
 *     case source once. Members are never summed into it.
 *   • A member with no recorded count makes the family's count a floor ("or
 *     more"), and a member with no recorded run is counted as unrecorded,
 *     never as a pass.
 */

import SCOREBOARD from "@/lib/evals/data/scoreboard-2026-11-03.json";
import { sourceLink } from "@/lib/evals/sources";
import type { MeasuredTruth } from "@/lib/evals/truth";

export const SCOREBOARD_SCHEMA = "eval-scoreboard/v1";

interface LastResult {
  passed: number;
  failed: number;
  skipped: number;
}

interface Member {
  name: string;
  cases: number | null;
  last_result: LastResult | null;
}

interface Family {
  canonical: string;
  domain: string;
  cases: number;
  members: Member[];
  unknown_case_counts: string[];
}

export interface Scoreboard {
  recordedAtPt: string;
  recordedSourceSha: string;
  families: Family[];
  golden: { passing: number; total: number; floor: number; declaredTotal: number };
  bite: { total: number; caught: number; realCode: number };
  registry: { registered: number; grandfathered: number; unregistered: number };
}

/** Plain words for each family, keyed by the registry's canonical contract. */
export const FAMILY_WORDS: Record<string, { name: string; checks: string }> = {
  eval_registry_contract: {
    name: "The tests' own rules",
    checks:
      "That every test is on the official list, that planted bugs get caught, and that no planted change is left behind in the code.",
  },
  admin_surface_truth_contract: {
    name: "Admin health pages",
    checks: "That the admin health pages report what the data says, and that admin-only actions stay locked.",
  },
  browser_audit_replacement_contract: {
    name: "Browser checks",
    checks: "That the automated browser checks of live pages record what they find and file it.",
  },
  cache_failure_resilience: {
    name: "When a cache fails",
    checks: "That pages keep serving correct data when a cache is slow, empty or down.",
  },
  calibration_population_integrity: {
    name: "The accuracy record",
    checks: "That the accuracy record counts the right outcomes and publishes only what passes its checks.",
  },
  feed_card_trust_contract: {
    name: "Cards and event pages",
    checks: "That cards and event pages show results, sources and markets the way the record has them.",
  },
  native_parity_inventory: {
    name: "iPhone app matches the web",
    checks: "That the iPhone app shows what the website shows.",
  },
  first_card_client_contract: {
    name: "Page speed",
    checks: "That the first card loads fast, and that what slows it down is measured correctly.",
  },
  discover_lead_order_contract: {
    name: "Discover's order",
    checks: "That Discover puts the right card first.",
  },
  search_truth_closure_contract: {
    name: "Search",
    checks: "That search finds the right answer, and says so plainly when it has none.",
  },
};

export interface FamilyView {
  canonical: string;
  name: string;
  checks: string;
  cases: number;
  /** A member's count is missing, so `cases` is a floor. */
  casesAtLeast: boolean;
  evals: number;
  /** Members with a recorded run, and the test results those runs recorded. */
  recorded: number;
  passed: number;
  failed: number;
  skipped: number;
  unrecorded: number;
}

const isCount = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

function lastResultOk(r: unknown): r is LastResult | null {
  if (r === null) return true;
  const o = r as Partial<LastResult> | undefined;
  return !!o && isCount(o.passed) && isCount(o.failed) && isCount(o.skipped);
}

/**
 * Why a scoreboard cannot be shown, or null when it can. The section is absent
 * on any problem: a half-read scoreboard is worse than none.
 */
export function scoreboardProblem(raw: unknown): string | null {
  const b = raw as Record<string, unknown> | null;
  if (!b || typeof b !== "object") return "not an object";
  if (b.schema_version !== SCOREBOARD_SCHEMA) return `schema is not ${SCOREBOARD_SCHEMA}`;
  if (!recordedDate(String(b.recorded_at_pt ?? ""))) return "recorded_at_pt is unreadable";
  if (!/^[0-9a-f]{40}$/.test(String(b.recorded_source_sha ?? ""))) return "recorded_source_sha is not a full commit";
  const families = b.families as unknown[];
  if (!Array.isArray(families) || families.length === 0) return "no families";
  for (const f of families as Family[]) {
    if (!f || typeof f.canonical !== "string" || !isCount(f.cases)) return "a family has no canonical or case count";
    if (!Array.isArray(f.members) || f.members.length === 0) return `${f.canonical} has no members`;
    if (!Array.isArray(f.unknown_case_counts)) return `${f.canonical} has no unknown_case_counts list`;
    for (const m of f.members) {
      if (!lastResultOk(m?.last_result)) return `${f.canonical}: a member's last result is unreadable`;
    }
  }
  const g = b.golden as Record<string, unknown> | undefined;
  if (!g || !isCount(g.passing) || !isCount(g.total) || !isCount(g.floor) || !isCount(g.declared_total)) {
    return "golden is unreadable";
  }
  if ((g.passing as number) > (g.total as number)) return "golden passes more pairs than it has";
  const bite = b.bite_rate as Record<string, unknown> | undefined;
  if (!bite || !isCount(bite.total) || !isCount(bite.mutation_bites) || !isCount(bite.real_boundaries)) {
    return "bite_rate is unreadable";
  }
  if ((bite.mutation_bites as number) > (bite.total as number) || (bite.real_boundaries as number) > (bite.total as number)) {
    return "bite_rate counts exceed its sample";
  }
  const r = b.registry as Record<string, unknown> | undefined;
  if (!r || !isCount(r.registered) || !isCount(r.grandfathered) || !isCount(r.unregistered)) {
    return "registry is unreadable";
  }
  return null;
}

/** "2026-11-03 8:48:47 PM PT" → "2026-11-03", or null when it is not that shape. */
export function recordedDate(recordedAtPt: string): string | null {
  const m = /^(\d{4}-\d{2}-\d{2}) \d{1,2}:\d{2}:\d{2} [AP]M PT$/.exec(recordedAtPt);
  return m ? m[1] : null;
}

/** "2026-11-03 8:48:47 PM PT" → "8:48 PM PT", the way the page prints a clock. */
export function recordedClock(recordedAtPt: string): string | null {
  const m = /^\d{4}-\d{2}-\d{2} (\d{1,2}:\d{2}):\d{2} ([AP]M) PT$/.exec(recordedAtPt);
  return m ? `${m[1]} ${m[2]} PT` : null;
}

export function loadScoreboard(raw: unknown = SCOREBOARD): Scoreboard | null {
  if (scoreboardProblem(raw)) return null;
  const b = raw as {
    recorded_at_pt: string;
    recorded_source_sha: string;
    families: Family[];
    golden: { passing: number; total: number; floor: number; declared_total: number };
    bite_rate: { total: number; mutation_bites: number; real_boundaries: number };
    registry: { registered: number; grandfathered: number; unregistered: number };
  };
  return {
    recordedAtPt: b.recorded_at_pt,
    recordedSourceSha: b.recorded_source_sha,
    families: b.families,
    golden: {
      passing: b.golden.passing,
      total: b.golden.total,
      floor: b.golden.floor,
      declaredTotal: b.golden.declared_total,
    },
    bite: { total: b.bite_rate.total, caught: b.bite_rate.mutation_bites, realCode: b.bite_rate.real_boundaries },
    registry: {
      registered: b.registry.registered,
      grandfathered: b.registry.grandfathered,
      unregistered: b.registry.unregistered,
    },
  };
}

/** One family in plain words. A family with no words keeps its registry name. */
export function familyView(f: Family): FamilyView {
  const words = FAMILY_WORDS[f.canonical];
  const recorded = f.members.filter((m) => m.last_result !== null);
  const sum = (k: keyof LastResult) => recorded.reduce((s, m) => s + (m.last_result as LastResult)[k], 0);
  return {
    canonical: f.canonical,
    name: words?.name ?? f.canonical,
    checks: words?.checks ?? "",
    cases: f.cases,
    casesAtLeast: f.unknown_case_counts.length > 0,
    evals: f.members.length,
    recorded: recorded.length,
    passed: sum("passed"),
    failed: sum("failed"),
    skipped: sum("skipped"),
    unrecorded: f.members.length - recorded.length,
  };
}

/** The library's label: LAST RUN on the day the scoreboard's tests were recorded. */
export function libraryTruth(board: Scoreboard): MeasuredTruth {
  return { kind: "last_run", asOf: recordedDate(board.recordedAtPt) ?? "", source: sourceLink("scoreboard-record") };
}

/** The bite audit's label: the same recorded run, linked to the test that asserts its two numbers. */
export function biteTruth(board: Scoreboard): MeasuredTruth {
  return { kind: "last_run", asOf: recordedDate(board.recordedAtPt) ?? "", source: sourceLink("bite-audit") };
}
