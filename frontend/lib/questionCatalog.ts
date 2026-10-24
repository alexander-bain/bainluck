/**
 * #10809 / #10868 (Atlas v6, first adoption slice) — every question a game
 * page serves, reachable from one catalog.
 *
 * The maps and cards above draw the questions they can draw. Some served rows
 * reach no card at all: a map refuses a line in the wrong unit (#2555), a map
 * with nothing on it stops drawing (#10350). The catalog is the escape hatch:
 * every row of `/game-markets` lands in exactly one group, and a reader can find
 * it by family or by search.
 *
 * GROUPING. A group is one venue's one original question: family, source, the
 * question text exactly as served, period, and the venue market id where the
 * row carries one — Kalshi serves three separate "Both teams to score"
 * contracts under one title, and without the id their outcomes read as one
 * question with two "Yes" answers. Two venues asking the same
 * thing stay two groups — matching titles is not evidence that two contracts
 * settle the same way, and the catalog never declares that they do.
 *
 * QUOTES. No new price rule. The number a row prints is the number the
 * existing flat list (`GameLineBrowser`) would print for it:
 *   - a direct per-outcome `probability` wins;
 *   - otherwise `over_probability`, which is the OVER chance of the line even
 *     on a row named Under (gotcha #17), only on an outcome that names the over
 *     side — never attached to the Under leg and never complemented;
 *   - during play, a price last seen before the game moved on prints nothing;
 *   - after the final, nothing: a settlement-era trade is not a forecast, and
 *     the graded cards above own results (settled means settled);
 *   - a closed period row is never priced (#10850).
 *
 * PURE: no I/O, no React. `now` is a parameter.
 */

import type { GameMarketsResponse } from "./api";
import { propOutcomeSide } from "./propOutcomeSide";
import { isPregameStatus, isSettledStatus } from "./settledQuote";
import { sourceIsStale } from "./sourceAge";
import { sourceLabel } from "./sourceLabels";

/** The family chips, in the order a reader meets them on the page. */
export const CATALOG_FAMILIES = [
  "Game lines",
  "Team scoring",
  "Periods",
  "Player props",
  "Matchups",
  "Other",
] as const;
export type CatalogFamily = (typeof CATALOG_FAMILIES)[number];

export interface CatalogOutcome {
  label: string;
  threshold: number | null;
  /** The number to print, or null when this row may not print one. */
  probability: number | null;
  observedAt: string | null;
}

export interface CatalogGroup {
  key: string;
  family: CatalogFamily;
  question: string;
  /** Reader-facing venue name, or null when we cannot name the source. */
  source: string | null;
  period: string | null;
  outcomes: CatalogOutcome[];
}

/** One served row, as much of it as the catalog reads. */
interface LooseRow {
  market_name?: string | null;
  outcome_name?: string | null;
  threshold?: number | null;
  probability?: number | null;
  over_probability?: number | null;
  source?: string | null;
  period?: string | null;
  observed_at?: string | null;
  _inverted?: boolean | null;
  _market_id?: number | null;
  market_type?: string | null;
}

type Side = "over" | "under" | "unreadable";

/** Which side of the line an outcome names; unreadable prints no over price. */
function lineSide(row: LooseRow): Side {
  if (row._inverted === true) return "under";
  const side = propOutcomeSide(row.outcome_name);
  if (side !== "unreadable") return side;
  const o = row.outcome_name ?? "";
  if (/\bunder\b/i.test(o)) return "under";
  if (/\bover\b/i.test(o)) return "over";
  return "unreadable";
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function catalogQuote(
  row: LooseRow,
  status: string | null | undefined,
  now: number,
  closed = false,
): number | null {
  if (closed || isSettledStatus(status)) return null;
  const live = !isPregameStatus(status);
  if (live && sourceIsStale(row.observed_at ?? null, now)) return null;
  if ("probability" in row) return finite(row.probability);
  return lineSide(row) === "over" ? finite(row.over_probability) : null;
}

export function buildQuestionCatalog(
  data: GameMarketsResponse,
  status: string | null | undefined,
  now: number,
): CatalogGroup[] {
  const groups = new Map<string, CatalogGroup>();

  const add = (
    family: CatalogFamily,
    row: LooseRow,
    probability: number | null,
    label: string,
  ) => {
    const question = (row.market_name ?? "").trim();
    if (!question) return;
    const period = row.period ?? null;
    const key = JSON.stringify([family, row.source ?? null, question, period, row._market_id ?? null]);
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        family,
        question,
        source: sourceLabel(row.source),
        period,
        outcomes: [],
      };
      groups.set(key, group);
    }
    group.outcomes.push({
      label,
      threshold: finite(row.threshold),
      probability,
      observedAt: row.observed_at ?? null,
    });
  };

  const addRows = (
    family: CatalogFamily,
    rows: readonly LooseRow[] | null | undefined,
    closed = false,
  ) => {
    const list = rows ?? [];
    // An Under row carries its Over twin's price, so beside that twin it adds
    // a blank outcome and nothing else (GameLineBrowser's rule). An Under with
    // no Over twin stays listed: the question must remain reachable.
    const lineKey = (row: LooseRow) =>
      JSON.stringify([row.source ?? null, row.market_name ?? null, row.period ?? null, row.threshold ?? null]);
    const overLines = new Set(
      list.filter((row) => lineSide(row) === "over").map(lineKey),
    );
    for (const row of list) {
      if (
        !("probability" in row) &&
        lineSide(row) === "under" &&
        overLines.has(lineKey(row))
      ) {
        continue;
      }
      add(
        family,
        row,
        catalogQuote(row, status, now, closed),
        (row.outcome_name ?? "").trim() || row.market_name || "",
      );
    }
  };

  addRows("Game lines", data.totals as LooseRow[]);
  addRows("Game lines", data.spreads as LooseRow[]);
  addRows("Team scoring", data.team_totals as LooseRow[]);
  addRows("Periods", data.period_markets as LooseRow[]);
  addRows("Periods", (data.closed_period_markets ?? []) as LooseRow[], true);
  addRows("Player props", data.player_props as LooseRow[]);
  for (const matchup of data.matchups ?? []) {
    for (const outcome of matchup.outcomes ?? []) {
      const row: LooseRow = {
        market_name: matchup.market_name,
        outcome_name: outcome.name,
        probability: outcome.probability,
        source: matchup.source,
      };
      add("Matchups", row, catalogQuote(row, status, now), outcome.name);
    }
  }
  // #1529: the game's winner is served in `other` (it has no section of its
  // own) with the class the server established. Only that class moves; the
  // title is never read here, so an unclassified question stays in Other.
  const other = (data.other ?? []) as LooseRow[];
  addRows("Game lines", other.filter((row) => row.market_type === "moneyline"));
  addRows("Other", other.filter((row) => row.market_type !== "moneyline"));

  return [...groups.values()].sort(
    (a, b) =>
      CATALOG_FAMILIES.indexOf(a.family) - CATALOG_FAMILIES.indexOf(b.family),
  );
}
