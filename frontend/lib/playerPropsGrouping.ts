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
  /**
   * UX-P058 Item 2 (C277) — WHY THERE ARE NO PLAYERS, when there are none.
   *
   * `players: []` had two utterly different meanings and one rendering. The
   * caller did `if (players.length === 0) return null`, so a game with no props
   * and a game whose props ALL FAILED TO PARSE both drew nothing — and the
   * "N props couldn't be read" line added in UX-P056 sat AFTER that return,
   * making it unreachable in exactly the case it was written for.
   *
   * This is gotcha #53 in the client: an empty is not an absence, and code that
   * infers a FACT ("this game has no player props") from the emptier reading is
   * inventing it. A poisoned section that renders as a clean absence is the worst
   * of the three states, because nothing anywhere says a thing went wrong.
   *
   *   - `"none"`      — no input rows at all. A genuine absence.
   *   - `"clean"`     — rows existed, nothing threw, nothing grouped (benign:
   *                     no thresholds, unpriced, unmatched stats).
   *   - `"unreadable"`— rows existed and at least one was DROPPED by a guard, and
   *                     nothing survived. The section must say so.
   *
   * Populated on every return, including the early one, so a caller cannot read
   * it as absent.
   */
  emptyReason: "none" | "clean" | "unreadable" | null;
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
 * UX-P058 Item 3 (C277) — a player is a NAME **and a side**, not a name.
 *
 * The bucket key was `parsed.player.toLowerCase()` alone, so two different people
 * who share a name — a Will Smith on each roster, a father/son, the very common
 * MLB/NFL surname collisions — merged into ONE card and pooled their stats. The
 * card then shows one person's line under the other's team colour, and
 * `readPropGrade` adjudicates over a `gradeRows` array spanning two humans.
 * That is a data-corruption shape, not a cosmetic one: it is silently wrong and
 * self-consistent, which is the class this lane's ordering rule makes
 * priority-eligible at any likelihood.
 *
 * Normalization is deliberately UNCHANGED (`toLowerCase()`, nothing else). This
 * queue adds the team dimension and touches nothing about how names fold —
 * widening normalization is how you MERGE players that were correctly separate,
 * the inverse defect, and the candidate-base work already recorded that trap.
 *
 * ── ONLY AN *AUTHORITATIVE* SIDE MAY KEY, AND THIS WAS MEASURED THE HARD WAY ──
 *
 * The first draft of this repair keyed on the side the row RESOLVED to, which is
 * `p.player_team ?? detectTeam(...)`. Held against the production oracle it
 * FRAGMENTED REAL PEOPLE: on event 15187845, `Mike Trout` and `Zach Neto` each
 * split into a home card and an away card, and the payload's player count went
 * 23 -> 26.
 *
 * The cause is that `detectTeam` reads a market name which NAMES BOTH TEAMS
 * ("Angels vs Athletics: Hits"), so its answer depends on word order and can
 * differ between two rows about the same person. It is a display-time heuristic,
 * never an identity.
 *
 * That inverse defect is strictly worse than the one being fixed: a same-name
 * collision needs two same-named players in one game, while fragmentation would
 * have hit ordinary games immediately and split a star's card in half.
 *
 * So identity uses `player_team` ONLY — a side the backend typed — and treats a
 * merely-detected side as unknown for keying while still using it for the card's
 * colour. STATED LIMITATION, not an oversight: when the backend supplies no side,
 * two same-named opponents still merge. We separate where we have authority and
 * refuse to guess where we do not, because the guess is what broke Mike Trout.
 */
type TeamSide = "home" | "away" | "unknown";

/**
 * The separator is a NUL (`\u0000`) because it is the one character a player name
 * cannot contain. A printable separator (`|`, `:`, `-`) is a character some name
 * eventually DOES contain, and then two different identities collide into one key
 * — the exact bug this function exists to prevent, reintroduced by its own
 * encoding. Written as an escape, never as a literal byte: a raw NUL in a source
 * file makes git treat it as binary and stops the diff being reviewable.
 */
function identityKey(name: string, team: TeamSide): string {
  return `${name.toLowerCase()}\u0000${team}`;
}

/**
 * THE UNKNOWN-TEAM POLICY, stated rather than left to insertion order.
 *
 * A row whose side we could not detect carries no evidence about which of two
 * same-named people it belongs to. Insertion order must not decide that, because
 * it is a property of the payload's ordering, not of the world. So:
 *
 *   - a KNOWN-team row claims `name|team`, and ABSORBS an existing `name|unknown`
 *     bucket **only when no other known bucket for that name exists** (the
 *     ordinary case: one real player, some rows missing a side);
 *   - an UNKNOWN-team row joins the single known bucket for that name when there
 *     is EXACTLY ONE, and otherwise stands alone in `name|unknown`.
 *
 * With two or more known sides for a name the unknown row is genuinely ambiguous,
 * and it is left in its own bucket rather than assigned by a coin flip. An
 * unattributable row is not evidence for either side.
 */
/**
 * ── WHY AN ALIAS TABLE AND NOT A RENAME ──
 *
 * Absorbing was first written as `playerMap.set(newKey, entry); delete(oldKey)`.
 * That is correct about grouping and WRONG about order: deleting and re-inserting
 * moves the key to the END of a Map, the final `sort` is stable, so cards with an
 * equal stat count silently REORDERED on screen. The oracle caught it — same set
 * of players, different sequence.
 *
 * So identity keys are ALIASES onto a bucket id and `playerMap` is never deleted
 * from. Insertion order is exactly what it was before this queue.
 */
function resolveBucketKey(
  aliasToBucket: Map<string, string>,
  name: string,
  team: TeamSide,
): string {
  const unknownKey = identityKey(name, "unknown");
  const known = (["home", "away"] as const)
    .map((side) => identityKey(name, side))
    .filter((k) => aliasToBucket.has(k));

  if (team === "unknown") {
    if (aliasToBucket.has(unknownKey)) return aliasToBucket.get(unknownKey)!;
    // Exactly one known side for this name: unambiguous, so join it. Two or more
    // is genuinely ambiguous and the row stands alone rather than being assigned.
    if (known.length === 1) return aliasToBucket.get(known[0])!;
    aliasToBucket.set(unknownKey, unknownKey);
    return unknownKey;
  }

  const target = identityKey(name, team);
  if (aliasToBucket.has(target)) return aliasToBucket.get(target)!;
  if (known.length === 0 && aliasToBucket.has(unknownKey)) {
    // The same person's side just became known: alias onto the SAME bucket.
    const bucket = aliasToBucket.get(unknownKey)!;
    aliasToBucket.set(target, bucket);
    return bucket;
  }
  aliasToBucket.set(target, target);
  return target;
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
  // No rows at all is the one honest absence, and it is decided BEFORE any
  // parsing so it can never be confused with "everything we had was unreadable".
  if (!hasPlayerProps && !hasOtherProps) {
    return { players: [], dropped, emptyReason: "none" };
  }

  const playerMap = new Map<string, PlayerAccumulator>();
  /** identity key -> bucket id. See `resolveBucketKey`: aliases, never renames. */
  const aliasToBucket = new Map<string, string>();

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

  /**
   * UX-P058 Item 1 (C277) — THE ROW COMMIT IS ATOMIC, and this is a repair of the
   * guard itself, not a new feature.
   *
   * The per-item `try` (gotcha #42) contained the blast radius of a throw to one
   * row. It did NOT contain the row's PARTIAL WRITES: `playerMap.set` and
   * `stats.set` ran near the top, and a dozen further reads followed — the grade
   * fields, `p.source`, `Math.abs(p.movement)`, any of which can throw on a
   * hostile payload (a throwing getter, a Proxy, a poisoned prototype). A late
   * throw therefore left a player entry, and a stat bucket, ALREADY COMMITTED —
   * with ZERO RUNGS pushed.
   *
   * A zero-rung stat is exactly #1722's precondition. The downstream `continue`
   * added in UX-P056 stops it killing the page, but the guard meant to contain
   * #1722 could still manufacture #1722's input, and a phantom player card with
   * no stats is a claim we never had data for.
   *
   * So the row is read into an immutable candidate FIRST — every field, including
   * the constructed grade row — and only a fully-read row is committed. The read
   * phase can throw and costs exactly one row; the commit phase touches nothing
   * that can throw, because every value in it has already been read.
   */
  interface RowCandidate {
    readonly playerName: string;
    /** Display side; may be a heuristic. */
    readonly team: TeamSide;
    /** Identity side; authoritative (`player_team`) or "unknown". */
    readonly keyTeam: TeamSide;
    readonly headshot: string | undefined;
    readonly statKey: string;
    readonly identified: boolean;
    readonly threshold: number;
    readonly overProb: number;
    readonly movement: number | null;
    readonly hit: boolean | null;
    readonly actual: number | null;
    readonly isWinner: boolean | null;
    readonly gradeRow: PropGradeFields;
    readonly source: string;
  }

  /** PURE READ. Returns null for a benign skip; throws only on a hostile row. */
  function readPlayerPropRow(p: PlayerPropRow): RowCandidate | null {
    const parsed = parsePlayerName(p.market_name || "", p.outcome_name || "");
    if (!parsed || !parsed.player) return null;
    if (p.threshold == null) return null;

    // `team` is for DISPLAY (card colour, team filter) and may be a heuristic.
    // `keyTeam` is for IDENTITY and is authoritative-or-nothing — see the header.
    const team: TeamSide = p.player_team ?? detectTeam(parsed.team || p.market_name || "");
    const keyTeam: TeamSide =
      p.player_team === "home" || p.player_team === "away" ? p.player_team : "unknown";
    const movement = p.movement ?? null;
    const candidate: RowCandidate = {
      playerName: parsed.player,
      team,
      keyTeam,
      headshot: p.player_headshot ?? undefined,
      statKey: (parsed.stat || "prop").toLowerCase(),
      identified: parsed.identified,
      threshold: p.threshold,
      overProb: p.over_probability as number,
      movement,
      hit: p.hit ?? null,
      actual: p.actual ?? null,
      isWinner: p.is_winner ?? null,
      // Constructed HERE, in the read phase, so a throwing grade field cannot
      // leave a half-built player behind.
      gradeRow: {
        actual: p.actual ?? null,
        hit: p.hit ?? null,
        is_winner: p.is_winner ?? null,
        resolution_source: p.resolution_source ?? null,
      },
      source: p.source as string,
      // `movement` is read above rather than inside the commit, because
      // `Math.abs` on a hostile value is a read that can throw.
    };
    if (candidate.movement != null) Math.abs(candidate.movement);
    return Object.freeze(candidate);
  }

  /** MUTATION ONLY. Every value here was already read; nothing here can throw. */
  function commitPlayerPropRow(c: RowCandidate): void {
    const playerKey = resolveBucketKey(aliasToBucket, c.playerName, c.keyTeam);
    if (!playerMap.has(playerKey)) {
      playerMap.set(playerKey, {
        name: c.playerName,
        team: c.team,
        headshot: c.headshot,
        stats: new Map(),
      });
    }

    const playerEntry = playerMap.get(playerKey)!;
    if (c.headshot && !playerEntry.headshot) playerEntry.headshot = c.headshot;

    if (!playerEntry.stats.has(c.statKey)) {
      playerEntry.stats.set(c.statKey, { rungs: [], sources: new Set(), movement: null, gradeRows: [], identified: true });
    }

    const statEntry = playerEntry.stats.get(c.statKey)!;
    // #1642 P1b: one unidentified row poisons the bucket for all of them —
    // the bucket is only a person if every row that landed in it named one.
    if (!c.identified) statEntry.identified = false;
    const existingRung = statEntry.rungs.find((r) => r.threshold === c.threshold);
    if (existingRung) {
      if (c.overProb != null && (existingRung.overProb == null || c.overProb > existingRung.overProb)) {
        existingRung.overProb = c.overProb;
      }
      if (c.hit != null && existingRung.hit == null) existingRung.hit = c.hit;
    } else {
      statEntry.rungs.push({
        threshold: c.threshold,
        overProb: c.overProb,
        sources: 1,
        movement: c.movement,
        hit: c.hit,
      });
    }
    // Queue #190 Item 3: carry the server-side settled grade (actual stat +
    // is_winner) at the player+stat level (same actual across all thresholds).
    if (c.actual != null) statEntry.serverActual = c.actual;
    if (c.isWinner != null && statEntry.serverIsWinner == null) statEntry.serverIsWinner = c.isWinner;
    // UX-P040 (#1638): keep the raw grading fields so `readPropGrade` can tell
    // "graded a loser" from "never graded" — `is_winner` alone cannot, being a
    // non-nullable column defaulted to false.
    statEntry.gradeRows.push(c.gradeRow);
    statEntry.sources.add(c.source);
    if (c.movement != null && (statEntry.movement == null || Math.abs(c.movement) > Math.abs(statEntry.movement))) {
      statEntry.movement = c.movement;
    }
  }

  rows.forEach((p, index) => {
    let candidate: RowCandidate | null;
    try {
      candidate = readPlayerPropRow(p);
    } catch (err) {
      dropped.push({ kind: "player_prop_row", at: String(index), message: messageOf(err) });
      return;
    }
    if (candidate) commitPlayerPropRow(candidate);
  });

  // Scan "other" markets for player props (double/triple doubles, etc.)
  interface OtherCandidate {
    readonly playerName: string;
    readonly team: TeamSide;
    readonly statKey: string;
    /**
     * `null` for an unpriced row. The row still names a PLAYER, and the player
     * bucket is still created for it — see `commitOtherRow`.
     */
    readonly probability: number | null;
    readonly source: string;
  }

  /**
   * UX-P058 Item 1, the `other[]` half. Same rule: read everything, then commit.
   * This pass is where #1722 came from, so it is the last place a partial write
   * belongs — and note the ORDER below is load-bearing. The unpriced check
   * (`probability == null`) must happen in the READ phase, because that is the
   * check UX-P056 added to stop an unpriced row creating a zero-rung stat; doing
   * it after a commit would restore the original bug exactly.
   */
  function readOtherRow(o: OtherMarketRow): OtherCandidate | null {
    const parsed = parsePlayerName(o.market_name || "", o.outcome_name || "");
    if (!parsed || !parsed.player || !parsed.stat) return null;
    const statLower = parsed.stat.toLowerCase();
    if (!STAT_TYPES.some((st) => st.toLowerCase() === statLower)) return null;
    return Object.freeze({
      playerName: parsed.player,
      team: detectTeam(parsed.team || o.market_name || ""),
      statKey: statLower,
      probability: o.probability ?? null,
      source: o.source as string,
    });
  }

  function commitOtherRow(c: OtherCandidate): void {
    // `other[]` rows carry no `player_team`, so identity is always unknown here
    // and this pass groups exactly as it did before.
    const playerKey = resolveBucketKey(aliasToBucket, c.playerName, "unknown");
    if (!playerMap.has(playerKey)) {
      playerMap.set(playerKey, {
        name: c.playerName,
        team: c.team,
        stats: new Map(),
      });
    }
    // UNPRICED ROWS STOP HERE, and the placement of this line is load-bearing
    // twice over.
    //
    // It must come AFTER the player bucket exists, because that is what the
    // pre-change code did and the bucket's creation order decides CARD ORDER: on
    // event 15191146 an unpriced Rhys Hoskins row at `other[43]` creates his
    // bucket before Angel Genao's at `other[55]`, and skipping the row outright
    // moved Hoskins to `other[57]` and swapped two cards on screen. The oracle
    // caught that; it is a real if small user-visible change, and this is a
    // repair queue, not a re-ranking of the dashboard.
    //
    // It must come BEFORE the STAT is created, because that is #1722 itself: a
    // row with no price cannot contribute a rung, and a stat with zero rungs is
    // what dereferenced `sortedRungs[0]` and killed the page.
    //
    // So: an unpriced row names a player and nothing more. `sources` is credited
    // only for rows that made it in — counting a source for a price we never got
    // would overstate the card.
    if (c.probability == null) return;

    const playerEntry = playerMap.get(playerKey)!;
    if (!playerEntry.stats.has(c.statKey)) {
      playerEntry.stats.set(c.statKey, { rungs: [], sources: new Set(), movement: null, gradeRows: [], identified: true });
    }
    const statEntry = playerEntry.stats.get(c.statKey)!;
    statEntry.rungs.push({ threshold: 0.5, overProb: c.probability, sources: 1, movement: null });
    statEntry.sources.add(c.source);
  }

  otherRows.forEach((o, index) => {
    let candidate: OtherCandidate | null;
    try {
      candidate = readOtherRow(o);
    } catch (err) {
      dropped.push({ kind: "other_row", at: String(index), message: messageOf(err) });
      return;
    }
    if (candidate) commitOtherRow(candidate);
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

  // UX-P058 Item 2: decided from what actually happened, not guessed at by the
  // caller. `dropped` non-empty with nothing surviving means a guard ate the
  // section — POISON, and the surface must say so rather than draw a blank.
  // Note the drop can come from any of the three kinds, including `player`:
  // a throw while BUILDING the last surviving card empties the section just as
  // completely as a row that never parsed.
  const emptyReason: GroupPlayerPropsResult["emptyReason"] =
    result.length > 0 ? null : dropped.length > 0 ? "unreadable" : "clean";

  return { players: result, dropped, emptyReason };
}
