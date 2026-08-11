/* eslint-disable */
/**
 * AUTO-EXTRACTED VERBATIM from `components/PlayerPropsDashboard.tsx` @ f46716ed,
 * the commit immediately BEFORE UX-P056's extraction.
 *
 * This is a reference ORACLE, not shipped code. Its only job is to answer
 * "did moving the grouping into a module change what it produces?" — and it can
 * answer that only because it is a mechanical copy of the pre-change body
 * rather than a re-description of it. Nothing imports it but the test.
 */
import { readPropGrade, type PropGrade, type PropGradeFields } from "@/lib/propGrade";
import { parsePropLabel } from "@/lib/otherMarketGroups";

interface StatRung {
  threshold: number;
  overProb: number;
  sources: number;
  movement: number | null;
  hit?: boolean | null;
}

interface PlayerStat {
  type: string;
  shape: "ladder" | "line";
  rungs?: StatRung[];
  threshold?: number;
  overProb?: number;
  sources: number;
  movement: number | null;
  actual?: number | null;
  // Queue #190 Item 3: authoritative settled grade from the server payload.
  serverActual?: number | null;
  serverHit?: boolean | null;
  serverIsWinner?: boolean | null;
  /** UX-P040 (#1638): the backend's typed grade, or `{graded:false}`. */
  grade?: PropGrade;
}

interface PlayerData {
  name: string;
  team: "home" | "away" | "unknown";
  initials: string;
  color: string;
  headshot?: string;
  stats: PlayerStat[];
}

const STAT_TYPES = [
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

const STAT_TO_BOX_SCORE: Record<string, string> = {
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
function parsePlayerName(
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
  // The parser is the one #1627 already shipped for the section next door, so
  // the event page has one definition of `Player: Statistic O/U Threshold`.
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


export function groupPlayerPropsLegacy(
  data: any,
  homeTeam?: string,
  awayTeam?: string,
  homeColor?: string,
  awayColor?: string,
  boxScore?: { players?: Array<{ name: string; team: string; stats: Record<string, number> }> } | null,
): PlayerData[] {

    const hasPlayerProps = data.player_props && data.player_props.length > 0;
    const hasOtherProps = data.other && data.other.length > 0;
    if (!hasPlayerProps && !hasOtherProps) return [];

    // Group props by player → stat type
    const playerMap = new Map<string, {
      name: string;
      team: "home" | "away" | "unknown";
      headshot?: string;
      stats: Map<string, { rungs: StatRung[]; sources: Set<string>; movement: number | null; serverActual?: number | null; serverIsWinner?: boolean | null; gradeRows: PropGradeFields[]; identified: boolean }>;
    }>();

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

    for (const p of data.player_props) {
      const parsed = parsePlayerName(p.market_name || "", p.outcome_name || "");
      if (!parsed || !parsed.player) continue;
      if (p.threshold == null) continue;

      const playerKey = parsed.player.toLowerCase();
      if (!playerMap.has(playerKey)) {
        const team: "home" | "away" | "unknown" = p.player_team ?? detectTeam(parsed.team || p.market_name || "");

        playerMap.set(playerKey, {
          name: parsed.player,
          team,
          headshot: p.player_headshot,
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
          overProb: p.over_probability,
          sources: 1,
          movement: p.movement,
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
      statEntry.sources.add(p.source);
      if (p.movement != null && (statEntry.movement == null || Math.abs(p.movement) > Math.abs(statEntry.movement))) {
        statEntry.movement = p.movement;
      }
    }

    // Scan "other" markets for player props (double/triple doubles, etc.)
    for (const o of (data.other || [])) {
      const parsed = parsePlayerName(o.market_name || "", o.outcome_name || "");
      if (!parsed || !parsed.player || !parsed.stat) continue;
      const statLower = parsed.stat.toLowerCase();
      if (!STAT_TYPES.some((st) => st.toLowerCase() === statLower)) continue;

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
      if (o.probability == null) continue;
      const playerEntry = playerMap.get(playerKey)!;
      if (!playerEntry.stats.has(statLower)) {
        playerEntry.stats.set(statLower, { rungs: [], sources: new Set(), movement: null, gradeRows: [], identified: true });
      }
      const statEntry = playerEntry.stats.get(statLower)!;
      statEntry.rungs.push({ threshold: 0.5, overProb: o.probability, sources: 1, movement: null });
      statEntry.sources.add(o.source);
    }

    // Build player data with box score actuals
    const boxPlayers = boxScore?.players ?? [];
    const result: PlayerData[] = [];

    for (const [, entry] of playerMap) {
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
    }

    // Sort by most props (interesting players first)
    result.sort((a, b) => b.stats.length - a.stats.length);
    return result;
    // UX-P055 (#1722 follow-up): `data.other` was MISSING here while the body
    // reads it twice (the `hasOtherProps` early return, and the "scan other
    // markets" pass). On a polling surface that means a stale card: when a
    // refetch changes only `other`, the memo hands back the previous result.
    // Reported on #1722 and deliberately left out of that diff to keep the
    // crash fix reviewable; this is where it gets paid.

}
