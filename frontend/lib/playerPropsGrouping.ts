/**
 * playerPropsGrouping — the pure grouping behind the Player Props dashboard.
 *
 * UX-P056 (#1722's class, one level down). Cycle 55 stopped one bad prop row
 * from taking the whole event page: eleven sections now carry their own error
 * boundary, so a throw costs a section rather than the route. The section it
 * most often costs is this one, and inside it the blast radius was still total —
 * every player, from any single row.
 *
 * ── WHY THIS IS A MODULE AND NOT A `useMemo` ──
 *
 * The ranked follow-up after cycle 55 was "a per-CARD error boundary", and
 * measuring it first is what changed this queue. **A per-card boundary would not
 * have caught #1722.** That throw happened while GROUPING — three loops over
 * free text (`parsePlayerName` reads `market_name` / `outcome_name`), building
 * all seventeen players — which runs to completion before the first card
 * renders. A boundary around a card cannot catch an exception thrown before any
 * card exists.
 *
 * Gotcha #42's actual prescription is per-ITEM guards inside the loop, and that
 * needs a loop you can reach. Inline in a `useMemo`, this code could not be
 * tested at all: there is no jsdom, no react-test-renderer, and the npm registry
 * is unreachable from here, so the only executable description of the riskiest
 * code on the props path was "render the component and see". Extracting it is
 * what makes both the guard and its proof possible.
 *
 * ── WHAT IS AND IS NOT DIFFERENT ──
 *
 * This is an EXTRACTION. `parsePlayerName`, the `identified` poisoning rule
 * (#1642 P1b), the unpriced-`other` skip and the zero-rung `continue` (both
 * #1722), the sort, and the `readPropGrade` call are all moved unchanged — a
 * grouping that differs from today's cannot be measured against production
 * payloads, which is the whole acceptance. The one addition is the guards.
 *
 * A dropped row or player is recorded on `dropped`, not swallowed. A guard whose
 * failures are invisible is how a section quietly empties and nobody learns why.
 *
 * ── RULING 003 ──
 *
 * This module formats and groups; it never adjudicates. It does not read a box
 * score (`PlayerPropsSettledGrade.test.tsx` pins that path OFF, deliberately),
 * and every settled verdict comes from `readPropGrade` reading a `hit` the
 * backend typed. That matters especially now: #1728 records that the backend
 * publishes a confidently WRONG verdict on `Hits + Runs + RBIs` props, and the
 * correct client behaviour is still to print what it was given.
 *
 * PURE: no I/O, no clock, no React.
 */

import { readPropGrade, type PropGrade, type PropGradeFields } from "./propGrade";
import { parsePropLabel } from "./otherMarketGroups";

export interface StatRung {
  threshold: number;
  overProb: number;
  sources: number;
  movement: number | null;
  hit?: boolean | null;
}

export interface PlayerStat {
  type: string;
  shape: "ladder" | "line";
  rungs?: StatRung[];
  threshold?: number;
  overProb?: number;
  sources: number;
  movement: number | null;
  actual?: number | null;
  /** Queue #190 Item 3: authoritative settled grade from the server payload. */
  serverActual?: number | null;
  serverHit?: boolean | null;
  serverIsWinner?: boolean | null;
  /** UX-P040 (#1638): the backend's typed grade, or `{graded:false}`. */
  grade?: PropGrade;
}

export interface PlayerData {
  name: string;
  team: "home" | "away" | "unknown";
  initials: string;
  color: string;
  headshot?: string;
  stats: PlayerStat[];
}

/** A `player_props[]` row, as much of it as the grouping reads. */
export interface PlayerPropRow extends PropGradeFields {
  market_name?: string | null;
  outcome_name?: string | null;
  threshold?: number | null;
  over_probability?: number | null;
  movement?: number | null;
  source?: string | null;
  player_team?: "home" | "away" | "unknown" | null;
  player_headshot?: string | null;
}

/** An `other[]` row — the bucket #1722 came out of. */
export interface OtherMarketRow {
  market_name?: string | null;
  outcome_name?: string | null;
  probability?: number | null;
  source?: string | null;
}

export interface BoxScorePlayer {
  name: string;
  team: string;
  stats: Record<string, number>;
}

export interface GroupPlayerPropsInput {
  playerProps?: readonly PlayerPropRow[] | null;
  other?: readonly OtherMarketRow[] | null;
  homeTeam?: string;
  awayTeam?: string;
  homeColor?: string;
  awayColor?: string;
  boxScorePlayers?: readonly BoxScorePlayer[] | null;
}

/** What a guard caught, so a silent drop is never mistaken for absent data. */
export interface DroppedItem {
  kind: "player_prop_row" | "other_row" | "player";
  /** Row index for a row, player name for a player. */
  at: string;
  message: string;
}

export interface GroupPlayerPropsResult {
  players: PlayerData[];
  dropped: DroppedItem[];
}

export const STAT_TYPES = [
  "Points", "Assists", "Rebounds", "Steals", "Blocks",
  "Three Pointers", "3-Pointers", "3PM", "Turnovers",
  "Strikeouts", "Hits", "Runs", "Home Runs", "RBIs",
  "Hits + Runs + RBIs", "Total Bases", "Stolen Bases",
  "Goals", "Saves", "Shots",
  "Passing Yards", "Pass Yds", "Rushing Yards", "Rush Yds",
  "Receiving Yards", "Rec Yds", "Touchdowns", "TDs",
  "Receptions", "Interceptions", "Sacks",
  "Double Doubles", "Triple Doubles",
  "Points Leader", "Assists Leader",
];

export const STAT_TO_BOX_SCORE: Record<string, string> = {
  "points": "points",
  "rebounds": "rebounds",
  "assists": "assists",
  "steals": "steals",
  "blocks": "blocks",
  "three pointers": "three_pointers_made",
  "3-pointers": "three_pointers_made",
  "3pm": "three_pointers_made",
  "hits": "hits",
  "home runs": "home_runs",
  "rbis": "rbis",
  "strikeouts": "strikeouts",
  "goals": "goals",
  "passing yards": "passing_yards",
  "pass yds": "passing_yards",
  "rushing yards": "rushing_yards",
  "rush yds": "rushing_yards",
  "receiving yards": "receiving_yards",
  "rec yds": "receiving_yards",
  "receptions": "receptions",
  "interceptions": "interceptions",
  "touchdowns": "touchdowns",
  "tds": "touchdowns",
};

/**
 * The player, statistic and team a prop row is about.
 *
 * `identified` (UX-P044, #1642 P1b) is false when the parse never found a
 * person: `market_name` carries no colon AND no statistic matched, so `player`
 * falls back to the ENTIRE market name — which for MLB/Polymarket is the
 * matchup ("Tampa Bay Rays vs. Seattle Mariners - Player Props"). Every such
 * row hashes to one bucket, and a grade published on any one of them would be
 * attached to all the others. A wrong name against a real stat is worse than a
 * blank, so the caller refuses the group's verdict rather than borrowing it.
 */
export function parsePlayerName(
  marketName: string,
  outcomeName: string,
): { player: string; stat: string; team: string; identified: boolean } | null {
  const colonIdx = marketName.indexOf(":");
  const afterColon = colonIdx >= 0 ? marketName.slice(colonIdx + 1).trim() : marketName;
  const beforeColon = colonIdx >= 0 ? marketName.slice(0, colonIdx) : "";

  let player = "";
  let stat = "";

  const exactStatMatch = STAT_TYPES.find(
    (st) => afterColon.toLowerCase() === st.toLowerCase(),
  );
  if (exactStatMatch) {
    stat = exactStatMatch;
    const outcomeColon = (outcomeName || "").indexOf(":");
    if (outcomeColon > 0) {
      player = outcomeName.slice(0, outcomeColon).trim();
    }
  } else {
    player = afterColon;
    for (const st of STAT_TYPES) {
      if (afterColon.toLowerCase().endsWith(st.toLowerCase())) {
        player = afterColon.slice(0, -st.length).trim();
        stat = st;
        break;
      }
    }
  }

  // #1639: MLB/Polymarket rows encode the player in `outcome_name`, not
  // `market_name`. `market_name` is the MATCHUP ("Tampa Bay Rays vs. Seattle
  // Mariners - Player Props"), which has no colon and matches no STAT_TYPE — so
  // every row hashed to the same key and 17 distinct players collapsed into ONE
  // card, titled with the matchup and wearing whichever headshot arrived first.
  //
  // Only consulted when the logic above found NO statistic, so this is strictly
  // additive: any row that parses today keeps its existing parse (gotcha #43).
  if (!stat) {
    const fromOutcome = parsePropLabel(outcomeName);
    if (fromOutcome) {
      return {
        player: fromOutcome.player,
        stat: fromOutcome.statistic,
        team: beforeColon,
        identified: true,
      };
    }
  }

  if (!player) return null;
  // No colon to split on AND no statistic found → `player` is the whole market
  // name, i.e. a matchup, not a person. See the docblock.
  const identified = colonIdx >= 0 || stat !== "";
  return { player, stat, team: beforeColon, identified };
}

interface StatAccumulator {
  rungs: StatRung[];
  sources: Set<string>;
  movement: number | null;
  serverActual?: number | null;
  serverIsWinner?: boolean | null;
  gradeRows: PropGradeFields[];
  identified: boolean;
}

interface PlayerAccumulator {
  name: string;
  team: "home" | "away" | "unknown";
  headshot?: string;
  stats: Map<string, StatAccumulator>;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * Group raw prop rows into the player cards the dashboard renders.
 *
 * Guarded per item (gotcha #42): one row that throws costs that row, one player
 * that throws costs that player, and every healthy sibling still renders.
 */
export function groupPlayerProps(input: GroupPlayerPropsInput): GroupPlayerPropsResult {
  const {
    playerProps,
    other,
    homeTeam,
    awayTeam,
    homeColor,
    awayColor,
    boxScorePlayers,
  } = input;

  const dropped: DroppedItem[] = [];
  const rows = playerProps ?? [];
  const otherRows = other ?? [];

  const hasPlayerProps = rows.length > 0;
  const hasOtherProps = otherRows.length > 0;
  if (!hasPlayerProps && !hasOtherProps) return { players: [], dropped };

  const playerMap = new Map<string, PlayerAccumulator>();

  const homeLower = homeTeam?.toLowerCase() ?? "";
  const awayLower = awayTeam?.toLowerCase() ?? "";
  const homeWords = homeLower.split(/\s+/).filter((w) => w.length >= 3);
  const awayWords = awayLower.split(/\s+/).filter((w) => w.length >= 3);

  function detectTeam(marketContext: string): "home" | "away" | "unknown" {
    const ctx = marketContext.toLowerCase();
    const homeMatch = homeWords.some((w) => ctx.includes(w)) || ctx.includes(homeLower);
    const awayMatch = awayWords.some((w) => ctx.includes(w)) || ctx.includes(awayLower);
    if (homeMatch && !awayMatch) return "home";
    if (awayMatch && !homeMatch) return "away";
    // Both match (e.g., "NYY vs BOS") — check ordering: first team mentioned is typically away (visitor)
    if (homeMatch && awayMatch) {
      const homeIdx = homeWords.reduce((min, w) => { const i = ctx.indexOf(w); return i >= 0 && i < min ? i : min; }, 999);
      const awayIdx = awayWords.reduce((min, w) => { const i = ctx.indexOf(w); return i >= 0 && i < min ? i : min; }, 999);
      return homeIdx < awayIdx ? "home" : "away";
    }
    return "unknown";
  }

  rows.forEach((p, index) => {
    try {
      const parsed = parsePlayerName(p.market_name || "", p.outcome_name || "");
      if (!parsed || !parsed.player) return;
      if (p.threshold == null) return;

      const playerKey = parsed.player.toLowerCase();
      if (!playerMap.has(playerKey)) {
        const team: "home" | "away" | "unknown" =
          p.player_team ?? detectTeam(parsed.team || p.market_name || "");

        playerMap.set(playerKey, {
          name: parsed.player,
          team,
          headshot: p.player_headshot ?? undefined,
          stats: new Map(),
        });
      }

      const playerEntry = playerMap.get(playerKey)!;
      if (p.player_headshot && !playerEntry.headshot) {
        playerEntry.headshot = p.player_headshot;
      }

      const statKey = (parsed.stat || "prop").toLowerCase();
      if (!playerEntry.stats.has(statKey)) {
        playerEntry.stats.set(statKey, { rungs: [], sources: new Set(), movement: null, gradeRows: [], identified: true });
      }

      const statEntry = playerEntry.stats.get(statKey)!;
      // #1642 P1b: one unidentified row poisons the bucket for all of them —
      // the bucket is only a person if every row that landed in it named one.
      if (!parsed.identified) statEntry.identified = false;
      const existingRung = statEntry.rungs.find((r) => r.threshold === p.threshold);
      if (existingRung) {
        if (p.over_probability != null && (existingRung.overProb == null || p.over_probability > existingRung.overProb)) {
          existingRung.overProb = p.over_probability;
        }
        if (p.hit != null && existingRung.hit == null) existingRung.hit = p.hit;
      } else {
        statEntry.rungs.push({
          threshold: p.threshold,
          overProb: p.over_probability as number,
          sources: 1,
          movement: p.movement ?? null,
          hit: p.hit ?? null,
        });
      }
      // Queue #190 Item 3: carry the server-side settled grade (actual stat +
      // is_winner) at the player+stat level (same actual across all thresholds).
      if (p.actual != null) statEntry.serverActual = p.actual;
      if (p.is_winner != null && statEntry.serverIsWinner == null) statEntry.serverIsWinner = p.is_winner;
      // UX-P040 (#1638): keep the raw grading fields so `readPropGrade` can tell
      // "graded a loser" from "never graded" — `is_winner` alone cannot, being a
      // non-nullable column defaulted to false.
      statEntry.gradeRows.push({
        actual: p.actual ?? null,
        hit: p.hit ?? null,
        is_winner: p.is_winner ?? null,
        resolution_source: p.resolution_source ?? null,
      });
      statEntry.sources.add(p.source as string);
      if (p.movement != null && (statEntry.movement == null || Math.abs(p.movement) > Math.abs(statEntry.movement))) {
        statEntry.movement = p.movement;
      }
    } catch (err) {
      dropped.push({ kind: "player_prop_row", at: String(index), message: messageOf(err) });
    }
  });

  // Scan "other" markets for player props (double/triple doubles, etc.)
  otherRows.forEach((o, index) => {
    try {
      const parsed = parsePlayerName(o.market_name || "", o.outcome_name || "");
      if (!parsed || !parsed.player || !parsed.stat) return;
      const statLower = parsed.stat.toLowerCase();
      if (!STAT_TYPES.some((st) => st.toLowerCase() === statLower)) return;

      const playerKey = parsed.player.toLowerCase();
      if (!playerMap.has(playerKey)) {
        playerMap.set(playerKey, {
          name: parsed.player,
          team: detectTeam(parsed.team || o.market_name || ""),
          stats: new Map(),
        });
      }
      // #1722 — THE CAUSE. The bucket used to be created unconditionally while
      // the rung was pushed only when `o.probability != null`, so an unpriced
      // row left a stat with ZERO rungs behind it. Downstream that picks the
      // "line" shape (0 < 3) and dereferences `sortedRungs[0]`, which killed the
      // ENTIRE page — not the card — with `Cannot read properties of undefined
      // (reading 'threshold')`. Event 15191146 carried 64 such rows.
      //
      // A row that cannot contribute a rung is not a stat, so it no longer
      // creates one. `sources` is still credited only for rows that made it in;
      // counting a source for a price we never got would overstate the card.
      if (o.probability == null) return;
      const playerEntry = playerMap.get(playerKey)!;
      if (!playerEntry.stats.has(statLower)) {
        playerEntry.stats.set(statLower, { rungs: [], sources: new Set(), movement: null, gradeRows: [], identified: true });
      }
      const statEntry = playerEntry.stats.get(statLower)!;
      statEntry.rungs.push({ threshold: 0.5, overProb: o.probability, sources: 1, movement: null });
      statEntry.sources.add(o.source as string);
    } catch (err) {
      dropped.push({ kind: "other_row", at: String(index), message: messageOf(err) });
    }
  });

  // Build player data with box score actuals
  const boxPlayers = boxScorePlayers ?? [];
  const result: PlayerData[] = [];

  for (const [, entry] of playerMap) {
    try {
      const stats: PlayerStat[] = [];

      for (const [statKey, statData] of entry.stats) {
        const sortedRungs = statData.rungs.sort((a, b) => a.threshold - b.threshold);
        // #1722 — THE INVARIANT, kept separate from the cause on purpose.
        //
        // `shape` is "line" whenever there are fewer than 3 rungs, and that
        // INCLUDES ZERO — so the else-branch below reads `sortedRungs[0]` on an
        // empty array. The sibling ladder branch was already written defensively
        // (`sortedRungs[0]?.hit`); the branch that could actually be reached
        // empty was not, which is the whole bug.
        //
        // Fixing only the upstream cause would leave that dereference one future
        // caller away from killing the page again. A stat with no rungs is not a
        // stat, so it never reaches the shape decision.
        if (sortedRungs.length === 0) continue;
        const shape: "ladder" | "line" = sortedRungs.length >= 3 ? "ladder" : "line";

        // Find actual from box score — match by meaningful last name (skip Jr/Sr/III)
        //
        // Dead in production TODAY and deliberately so: `box_score_data.players`
        // is a dict keyed by player name, `.length` on it is undefined, and the
        // caller's `hasBoxScore` therefore never lets this path run. That is
        // ruling 003 — grading a prop by matching player names is adjudication —
        // and `PlayerPropsSettledGrade.test.tsx` pins it OFF. Carried unchanged
        // rather than deleted, because deleting it would hide the decision.
        let actual: number | null = null;
        const boxKey = STAT_TO_BOX_SCORE[statKey];
        if (boxKey && boxPlayers.length > 0) {
          const suffixes = new Set(["jr", "jr.", "sr", "sr.", "ii", "iii", "iv"]);
          const parts = entry.name.split(" ").filter(w => !suffixes.has(w.toLowerCase()));
          const lastName = (parts.pop() || "").toLowerCase();
          if (lastName.length >= 2) {
            const match = boxPlayers.find((bp) => {
              const bpParts = bp.name.split(" ").filter(w => !suffixes.has(w.toLowerCase()));
              const bpLast = (bpParts.pop() || "").toLowerCase();
              return bpLast === lastName;
            });
            if (match?.stats?.[boxKey] != null) {
              actual = match.stats[boxKey];
            }
          }
        }

        if (shape === "ladder") {
          stats.push({
            type: statKey.replace(/\b\w/g, (c) => c.toUpperCase()),
            shape: "ladder",
            rungs: sortedRungs,
            sources: statData.sources.size,
            movement: statData.movement,
            actual,
            serverActual: statData.serverActual ?? null,
            serverHit: sortedRungs[0]?.hit ?? null,
            serverIsWinner: statData.serverIsWinner ?? null,
            grade: readPropGrade(statData.gradeRows, { samePlayerStat: statData.identified }),
          });
        } else {
          const best = sortedRungs[0];
          stats.push({
            type: statKey.replace(/\b\w/g, (c) => c.toUpperCase()),
            shape: "line",
            threshold: best.threshold,
            overProb: best.overProb,
            sources: statData.sources.size,
            movement: statData.movement,
            actual,
            serverActual: statData.serverActual ?? null,
            serverHit: best.hit ?? null,
            serverIsWinner: statData.serverIsWinner ?? null,
            grade: readPropGrade(statData.gradeRows, { samePlayerStat: statData.identified }),
          });
        }
      }

      if (stats.length === 0) continue;

      const initials = entry.name
        .split(" ")
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();

      const color = entry.team === "home" ? (homeColor || "#3B82F6") :
                    entry.team === "away" ? (awayColor || "#EF4444") :
                    (homeColor || awayColor || "#3B82F6");

      result.push({
        name: entry.name,
        team: entry.team,
        initials,
        color,
        headshot: entry.headshot,
        stats,
      });
    } catch (err) {
      dropped.push({ kind: "player", at: entry.name, message: messageOf(err) });
    }
  }

  // Sort by most props (interesting players first)
  result.sort((a, b) => b.stats.length - a.stats.length);
  return { players: result, dropped };
}
