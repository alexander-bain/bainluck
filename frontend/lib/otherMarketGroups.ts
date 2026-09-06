/**
 * Grouping and duplicate-merging for the event page's "Additional Markets"
 * section (UX-P037, gaps K10 + K11).
 *
 * Why this module exists — four things measured on SIX live games, 2026-08-09:
 *
 * 1. The category patterns below are NFL/NBA-shaped (coin toss, gatorade,
 *    halftime, MVP) and match nothing MLB emits, so 100% of rows on 6/6 games
 *    fell into one bucket titled "Other Markets". That is gap K11.
 * 2. A single card rendered 34–61 outcome bars, because the old cap limited
 *    CARDS per category, never OUTCOMES per card. That is gap K10.
 * 3. The header counted `market_name` groups, so it read "1 markets grouped by
 *    category" above 34 bars.
 * 4. Worst: outcomes merged by label kept whichever probability was FURTHEST
 *    FROM 0.5. Across the six games there were 92 duplicate label pairs, 86% of
 *    them materially disagreeing, so the page rendered
 *    "Ronald Acuña Jr.: Home Runs O/U 0.5 — 91%" (the wire carried 0.095, 0.125
 *    and 0.905). Preferring the extreme systematically prefers exactly what a
 *    stale or illiquid Polymarket midpoint looks like — gotcha #19.
 *
 * The statistic was on the wire the whole time: every Polymarket prop label is
 * `Player: Statistic O/U Threshold`. Same shape as UX-P036's finding on the
 * divergence section — data we fetched and declined to show.
 *
 * PURE: no I/O, no React, no DB.
 */

/**
 * How far two probabilities carrying the SAME label may differ and still be
 * treated as one price.
 *
 * Above this, the client cannot say which is right: `other` rows carry only
 * `market_name`, `outcome_name`, `probability` and `source`, so there is no
 * field that distinguishes them. Showing both would be showing source
 * divergence, which the standing *"the blend is the product"* ruling forbids;
 * showing the extreme is the bug this module exists to remove. So a
 * materially-disagreeing label is WITHHELD and counted — never silently
 * dropped, and never guessed at.
 */
export const AGREEMENT_TOLERANCE = 0.02;

/**
 * Float slack on the tolerance comparison. `0.52 - 0.5` is `0.020000000000000018`
 * in IEEE 754, so a bare `>` withholds a pair that is EXACTLY at tolerance.
 */
const TOLERANCE_EPSILON = 1e-9;

/** Outcome bars shown up-front on one card; the rest sit in a disclosure. */
export const MAX_OUTCOMES_PER_CARD = 8;

/** Cards shown up-front in one category; the rest sit in a disclosure. */
export const MAX_CARDS_PER_CATEGORY = 5;

/** Category that collects rows whose label names a player statistic. */
export const PLAYER_PROPS_CATEGORY = "Player Props";

export interface OtherMarketRow {
  market_name?: string | null;
  outcome_name?: string | null;
  probability?: number | null;
  source?: string | null;
}

export interface ParsedPropLabel {
  player: string;
  statistic: string;
  /** Kept as the source string so "0.5" never renders as "0.5000000001". */
  threshold: string;
}

/** `Ronald Acuña Jr.: Home Runs O/U 0.5` → player / statistic / threshold. */
const PROP_LABEL_RE = /^(.+?):\s*(.+?)\s+O\/U\s+(\d+(?:\.\d+)?)\s*$/;

/**
 * Separators a child title may be joined to its parent's with, once the parent
 * has been removed: `Parent: Child`, `Parent - Child`, `Parent — Child`,
 * `Parent · Child`, or the tennis case, a bare space.
 */
const PREFIX_JOINERS = /^[\s:·\-–—|]+/;

/** `Total Sets: O/U 2.5` → `Total Sets O/U 2.5`. */
const COLON_BEFORE_OU = /:\s+(?=O\/U\b)/;

/** Escape a wire string so it can be spliced into a RegExp as a literal. */
function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * The outcome's own name, with its card's name removed from the front.
 *
 * ── THE WIRE, VERBATIM (live US Open match `15301138`, 2026-09-04 09:58 PT) ──
 *
 *     market_name  US Open WTA: Jessica Pegula vs Leylah Fernandez
 *     outcome_name US Open WTA: Jessica Pegula vs Leylah Fernandez Set 2 Winner
 *     outcome_name US Open WTA: Jessica Pegula vs Leylah Fernandez Set 1 Winner
 *     outcome_name US Open WTA: Jessica Pegula vs Leylah Fernandez Game Spread +/-4.5
 *     outcome_name US Open WTA: Jessica Pegula vs Leylah Fernandez Total Sets: O/U 2.5
 *     outcome_name US Open WTA: Jessica Pegula vs Leylah Fernandez Match O/U 21.5
 *
 * A Polymarket tennis event is a parent market with nested children (gotcha
 * #18), and every child arrives carrying the parent's whole title. Printed
 * unaltered inside a card ALREADY HEADED with that title, each row wrapped over
 * four lines on a phone and the thing that distinguished it — `Set 2 Winner` —
 * came last, after 46 characters the reader had already read on the line above.
 *
 * Two properties that must survive edits here:
 *
 * - **A row never loses its name.** If the child title is nothing but the
 *   parent's, the original string is kept: a blank label is worse than a
 *   repetitive one.
 * - **Only a real prefix is removed.** The match is anchored at position 0 and
 *   compared on collapsed whitespace/case, so `Yes`, `No`, `Jessica Pegula` and
 *   every MLB/NFL prop label — none of which begin with their market's name —
 *   come through byte-identical.
 */
export function stripCardPrefix(
  marketName: string | null | undefined,
  outcomeName: string | null | undefined,
): string {
  return childTitleRemainder(marketName, outcomeName) ?? (outcomeName ?? "").trim();
}

/**
 * The child market's own title, when this "outcome" is really an undecomposed
 * nested child — otherwise null.
 *
 * This is `stripCardPrefix`'s decision, exposed so a caller can act on the
 * DISTINCTION rather than only on the shortened string. The two answers differ
 * in kind and the section needs both:
 *
 * - non-null → the wire row is a child market's TITLE, so the text names a
 *   QUESTION and no side of it. `Set 1 Winner` does not say for whom.
 * - null → the wire row is a real outcome (`Yes`, `No`, `Iga Swiatek`, every
 *   MLB/NFL prop label), and its text already names a side.
 */
export function childTitleRemainder(
  marketName: string | null | undefined,
  outcomeName: string | null | undefined,
): string | null {
  const outcome = (outcomeName ?? "").trim();
  const market = (marketName ?? "").trim();
  if (!outcome || !market) return null;

  // Built from the market's own tokens with `\s+` between them, so the match is
  // insensitive to case and to run-length of whitespace while still being
  // anchored: only a genuine prefix is consumed, and the REMAINDER keeps the
  // wire's own casing.
  const prefix = new RegExp(
    `^${market.split(/\s+/).map(escapeRegExp).join("\\s+")}`,
    "i",
  );
  const head = prefix.exec(outcome);
  if (!head) return null;

  const rest = outcome.slice(head[0].length).replace(PREFIX_JOINERS, "").trim();
  // Nothing but the parent's own name is not a child title, it is a row whose
  // name happens to equal its card's. It keeps its original string (a blank
  // label is worse than a repetitive one) and is NOT treated as a question.
  if (!rest) return null;
  return rest.replace(COLON_BEFORE_OU, " ");
}

/**
 * The set a row is about — `Set 1 Winner` → 1 — or null when it names no set.
 *
 * Anchored, so `Set Handicap +/-1.5` (no number) and `Total Sets O/U 2.5` (the
 * word is not first) are both correctly null: neither is about one named set,
 * and neither is decided by a set finishing.
 */
export function setNumberFromLabel(label: string | null | undefined): number | null {
  const match = /^set\s*(\d+)\b/i.exec((label ?? "").trim());
  if (!match) return null;
  const n = Number(match[1]);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/**
 * The player, statistic and threshold encoded in a Polymarket prop label, or
 * null when the label carries none.
 *
 * Null is the IMPORTANT case, not the edge case: NFL novelty props, golf and
 * the bare `Yes` / `No` / `NRFI` rows all land here, and every one of them must
 * keep rendering exactly as it does today.
 */
export function parsePropLabel(
  outcomeName: string | null | undefined,
): ParsedPropLabel | null {
  if (typeof outcomeName !== "string") return null;
  const match = PROP_LABEL_RE.exec(outcomeName.trim());
  if (!match) return null;
  const [, player, statistic, threshold] = match;
  if (!player.trim() || !statistic.trim()) return null;
  return { player: player.trim(), statistic: statistic.trim(), threshold };
}

const CATEGORY_PATTERNS: Array<{ pattern: RegExp; category: string; subtitle: string }> = [
  { pattern: /first\s*(score|td|touchdown|goal|basket)/i, category: "Game Props", subtitle: "scoring & flow" },
  { pattern: /halftime|half\s*time|leader\s*at/i, category: "Game Props", subtitle: "scoring & flow" },
  { pattern: /overtime|OT\b|extra\s*time/i, category: "Game Props", subtitle: "scoring & flow" },
  { pattern: /coin\s*toss|gatorade|anthem|color/i, category: "Novelty Props", subtitle: "fun markets" },
  { pattern: /mvp|most\s*valuable/i, category: "MVP", subtitle: "game MVP probability" },
  { pattern: /double\s*double|triple\s*double/i, category: "Player Performance", subtitle: "statistical milestones" },
  { pattern: /both\s*teams?\s*(to\s*)?score/i, category: "Game Props", subtitle: "scoring & flow" },
];

/** Unchanged fallback for rows whose label names no statistic. */
export function categorizeMarketName(name: string): { category: string; subtitle: string } {
  for (const { pattern, category, subtitle } of CATEGORY_PATTERNS) {
    if (pattern.test(name)) return { category, subtitle };
  }
  return { category: "Other Markets", subtitle: "additional markets" };
}

/**
 * A market asking who wins ONE NAMED PERIOD — `Set 1 Winner: Swiatek vs Zheng`,
 * `1st Half Winner`, `Period 2 Winner`.
 *
 * It is not the moneyline and it is in none of the maps above: the hero answers
 * the MATCH, the games map answers the TOTALS. Measured on `/events/15305580`
 * (2026-09-06 14:20Z) the payload carried `Set 1 Winner: Swiatek vs Zheng | Yes
 * = 0.735` and `Set 2 Winner: … | Yes = 0.72` — two real, properly sided
 * questions that appear nowhere else on the page.
 */
const PERIOD_SCOPED_WINNER = /\b(set|period|quarter|inning|frame|half|map|leg)\s*\d*(?:st|nd|rd|th)?\s+winner\b/i;

/** Rows already covered by the market maps / hero above this section. */
export function isRedundantWithMarketMaps(m: OtherMarketRow): boolean {
  const lower = (m.market_name || "").toLowerCase();
  const outLower = (m.outcome_name || "").toLowerCase();
  if (lower.includes("spread") || lower.includes("handicap")) return true;
  if (lower.includes("total") && (outLower.includes("over") || outLower.includes("under"))) return true;
  // `winner` was written for the moneyline. A PERIOD-scoped winner is a
  // different question with a different answer, and swallowing it is how the
  // page came to render the parent's un-sided `Set 1 Winner 74%` while hiding
  // the sided row carrying the very same number (#3575).
  if (PERIOD_SCOPED_WINNER.test(lower)) return false;
  if (lower.includes("moneyline") || lower.includes("winner") || lower.includes("match result")) return true;
  return false;
}

/** `Set 1 Winner: Swiatek vs Zheng` → scope `Set 1`, first side `Swiatek`. */
const SCOPED_WINNER_MARKET = /^(.+?)\s+winner\s*:\s*(.+?)\s+vs\.?\s+(.+?)\s*$/i;

/**
 * The label a `Yes` row on a period-winner market should carry — `Swiatek wins
 * Set 1` — or null when this row is not that.
 *
 * **Only the `Yes` side is named.** `No` on `Set 1 Winner: A vs B` is the
 * complement, and by the standing *"the blend is the product"* ruling one
 * question gets one number; rendering `A wins Set 1 — 74%` beside `A does not
 * win Set 1 — 26%` states the same fact twice. Naming `No` as `B wins Set 1`
 * would instead be a GUESS: it is only true where the period cannot be drawn,
 * which this module has no way to know. So `No` is dropped, never renamed.
 */
export function scopedWinnerLabel(
  marketName: string | null | undefined,
  outcomeName: string | null | undefined,
): string | null {
  const match = SCOPED_WINNER_MARKET.exec((marketName ?? "").trim());
  if (!match) return null;
  const [, scope, first] = match;
  if (!/^yes$/i.test((outcomeName ?? "").trim())) return null;
  if (!scope.trim() || !first.trim()) return null;
  return `${first.trim()} wins ${scope.trim()}`;
}

/**
 * Market names that are just the two-sided win probability shown in the hero.
 *
 * TWO ROWS, OR A BARE YES/NO PAIR. The row count alone was the whole test, and
 * a NAME COLLISION defeats it: on `/events/15305580` (2026-09-06 14:20Z) two
 * different `futures_markets` rows both answered to `US Open WTA: Iga Swiatek
 * vs Qinwen Zheng` — an undecomposed parent with 12 outcomes, and the match
 * market with a clean `Yes 0.795 / No 0.205`. Grouped by name that is 14
 * probabilities, never 2, so the hero's own number escaped the filter and was
 * reprinted in the rail as a bare `Yes 80%` (#3575).
 *
 * The added clause looks for the PAIR rather than counting the group, so it
 * survives a collision. It stays narrow deliberately: exactly one `Yes` and one
 * `No`, summing to one. "Some two rows here sum to 1.0" would nuke a 61-bar MLB
 * prop card on a coincidence.
 */
export function findWinProbMarkets(markets: OtherMarketRow[] | undefined | null): Set<string> {
  const byName = new Map<string, number[]>();
  const yesNo = new Map<string, { yes: number[]; no: number[] }>();
  for (const m of markets ?? []) {
    const name = m.market_name || "";
    if (!byName.has(name)) byName.set(name, []);
    if (m.probability != null) byName.get(name)!.push(m.probability);

    if (!yesNo.has(name)) yesNo.set(name, { yes: [], no: [] });
    const side = (m.outcome_name || "").trim().toLowerCase();
    if (m.probability != null && side === "yes") yesNo.get(name)!.yes.push(m.probability);
    if (m.probability != null && side === "no") yesNo.get(name)!.no.push(m.probability);
  }
  const winProb = new Set<string>();
  for (const [name, probs] of byName) {
    // Two complementary rows make a market BINARY, not the hero. `Set 1 Winner:
    // Swiatek vs Zheng` is `Yes 0.735 / No 0.265` — a perfect two-sided pair
    // about a question the hero does not answer. It was being filtered here as
    // well as by `isRedundantWithMarketMaps`, which is why the page had no
    // sided row left to fall back on.
    if (PERIOD_SCOPED_WINNER.test(name)) continue;

    if (probs.length === 2 && Math.abs(probs[0] + probs[1] - 1.0) < 0.1) {
      winProb.add(name);
      continue;
    }
    const pair = yesNo.get(name);
    if (pair && pair.yes.length === 1 && pair.no.length === 1
        && Math.abs(pair.yes[0] + pair.no[0] - 1.0) < 0.1) {
      winProb.add(name);
    }
  }
  return winProb;
}

export interface LabeledRow {
  label: string;
  probability: number | null;
  source: string | null;
  /**
   * The set this row is about, when the LABEL can no longer say so.
   *
   * `setNumberFromLabel` reads the rendered string, which works only while the
   * string still begins `Set 1 …`. A row renamed to `Swiatek wins Set 1` is the
   * same question and must still freeze when set 1 ends, so the number is
   * carried from the market title instead of re-derived from the label.
   */
  setNumber?: number | null;
}

export interface MergedOutcome {
  label: string;
  prob: number;
  source: string;
  /** How many wire rows agreed on this price. Drives the `Nx` badge. */
  sourceCount: number;
  /**
   * The question this row asks is already answered — a set that has been played
   * out — so its number is a last quote, not a chance. The renderer treats it
   * exactly as it treats a row on a finished game (#2086): no bar.
   */
  decided?: boolean;
  /** Carried from `LabeledRow`; see the note there. */
  setNumber?: number | null;
}

export interface OutcomeMergeResult {
  outcomes: MergedOutcome[];
  /** Labels withheld because their duplicates disagreed beyond tolerance. */
  withheld: number;
}

/**
 * Collapse rows sharing a label into one outcome each.
 *
 * Duplicates that AGREE collapse exactly as they always did, keeping the
 * `sourceCount` badge — that is the legitimate multi-source case the badge was
 * built for, and a single row trivially agrees with itself.
 *
 * Duplicates that DISAGREE are withheld and counted. This is the whole point of
 * the module: the old rule picked `Math.abs(p - 0.5)`-maximal, which is how a
 * 9.5% home-run prop came to render as 91%.
 */
export function mergeOutcomes(rows: LabeledRow[]): OutcomeMergeResult {
  const order: string[] = [];
  const byLabel = new Map<string, LabeledRow[]>();

  for (const row of rows) {
    const label = row.label || "Unknown";
    let bucket = byLabel.get(label);
    if (!bucket) {
      bucket = [];
      byLabel.set(label, bucket);
      order.push(label);
    }
    bucket.push(row);
  }

  const outcomes: MergedOutcome[] = [];
  let withheld = 0;

  for (const label of order) {
    const group = byLabel.get(label) as LabeledRow[];
    const probs = group.map((r) => r.probability ?? 0);
    const spread = Math.max(...probs) - Math.min(...probs);

    if (spread > AGREEMENT_TOLERANCE + TOLERANCE_EPSILON) {
      withheld += 1;
      continue;
    }

    // Set only when a row actually carries one, so an outcome's shape is
    // unchanged for every population that never needed it.
    const carried = group.find((r) => r.setNumber != null)?.setNumber;
    outcomes.push({
      label,
      prob: probs[0],
      source: group[0].source || "unknown",
      sourceCount: group.length,
      ...(carried != null ? { setNumber: carried } : {}),
    });
  }

  return { outcomes, withheld };
}

export interface MarketCard {
  name: string;
  outcomes: MergedOutcome[];
  withheld: number;
}

export interface MarketCategoryGroup {
  title: string;
  subtitle: string;
  cards: MarketCard[];
  withheld: number;
}

export interface MarketSection {
  categories: MarketCategoryGroup[];
  /** Outcome bars reachable on screen — what the header must count. */
  renderedOutcomes: number;
  /** Labels withheld across the whole section. */
  withheld: number;
}

const CATEGORY_ORDER = [
  "MVP",
  "Game Props",
  PLAYER_PROPS_CATEGORY,
  "Player Performance",
  "Novelty Props",
  "Other Markets",
];

/** The most sets a tennis match can contain — five, and only in the men's draw. */
const MAX_SETS_IN_A_MATCH = 5;

/**
 * How many sets are already over, for a tennis event, from the scores the
 * game-markets payload already carries.
 *
 * A tennis event's `home_score`/`away_score` are SETS WON (measured on the live
 * US Open match `15301138`, 09:58 PT 2026-09-04: `0` / `1` while the second set
 * was being played, with Fernandez a set up). Their sum is therefore the number
 * of completed sets, and it is the only fact this needs — not who won them,
 * which these two numbers cannot say once both sides have one.
 *
 * **It refuses rather than guesses.** A sum above five is not a set count in any
 * tennis match ever played, so a payload whose scores turn out to be games or
 * points returns 0 and nothing is marked decided. Every non-tennis sport returns
 * 0 by the same door.
 */
export function completedSetsForTennis(
  sport: string | null | undefined,
  scores: { home_score?: number | null; away_score?: number | null } | null | undefined,
): number {
  if (!/^tennis/i.test((sport ?? "").trim())) return 0;
  const home = scores?.home_score;
  const away = scores?.away_score;
  if (typeof home !== "number" || typeof away !== "number") return 0;
  if (!Number.isFinite(home) || !Number.isFinite(away) || home < 0 || away < 0) return 0;
  const total = Math.floor(home) + Math.floor(away);
  return total > MAX_SETS_IN_A_MATCH ? 0 : total;
}

export interface MarketSectionOptions {
  /**
   * Sets already played out in this match — the caller's number, never read
   * here. A tennis event's `home_score`/`away_score` ARE the sets each side has
   * won, so their sum is the count of sets that are over; every other sport
   * passes nothing and no row is ever marked decided.
   */
  completedSets?: number;
}

/**
 * Build the whole section: filter, categorise, merge, and report honest counts.
 *
 * Player-prop rows are grouped by their STATISTIC, so a live MLB game shows
 * "Home Runs" and "Strikeouts" instead of one 61-bar heap named after the
 * matchup. Everything else keeps the original `categorizeMarketName` path, so
 * NFL, golf and novelty payloads are untouched.
 */
export function buildMarketSection(
  rows: OtherMarketRow[] | undefined | null,
  options: MarketSectionOptions = {},
): MarketSection {
  const all = rows ?? [];
  const completedSets = Math.max(0, Math.floor(options.completedSets ?? 0));
  const winProb = findWinProbMarkets(all);
  const kept = all.filter(
    (m) => !isRedundantWithMarketMaps(m) && !winProb.has(m.market_name || ""),
  );

  if (kept.length < 3) return { categories: [], renderedOutcomes: 0, withheld: 0 };

  interface Draft {
    title: string;
    subtitle: string;
    cardOrder: string[];
    cards: Map<string, LabeledRow[]>;
  }
  const drafts = new Map<string, Draft>();
  const draftOrder: string[] = [];

  for (const row of kept) {
    // An undecomposed Polymarket parent (gotcha #18) lists its CHILD MARKETS in
    // the outcome slot, so `named` here is a question — `Set 1 Winner`, `Match
    // O/U 21.5` — with no side of it anywhere in the string. Printed against a
    // number it reads as an answer and cannot be one: `Set 1 Winner 74%` never
    // says for whom, `Match O/U 21.5 45%` never says over or under.
    //
    // De-prefixing (the previous ship) made those rows SHORTER; it could not
    // make them readable, because the side is not in the wire text to recover.
    // The sided rows exist — the same payload carried `Set 1 Winner: Swiatek vs
    // Zheng | Yes = 0.735` beside the parent's `… Set 1 Winner = 0.735` — so
    // the question is dropped here and answered by its real sibling below.
    //
    // Measured reach, production 2026-09-06 14:20Z, `status='open'` markets
    // linked to an event: tennis 124 parents / 1,022 rows, table_tennis 35/107,
    // basketball 5/5 (all ITF match parents), and soccer, football, baseball
    // and hockey ZERO — the MLB and NFL payloads this module was built on
    // cannot reach this branch.
    if (childTitleRemainder(row.market_name, row.outcome_name) !== null) continue;

    // De-prefix BEFORE parsing, not after. `parsePropLabel` is non-greedy on
    // its first group, so `US Open WTA: … Total Sets: O/U 2.5` parsed to
    // player `US Open WTA` — a TOUR printed in a slot headed "Player Props ·
    // by statistic". Stripping the parent title first leaves `Total Sets O/U
    // 2.5`, which correctly parses as no player prop at all.
    const named = stripCardPrefix(row.market_name, row.outcome_name);
    const parsed = parsePropLabel(named);

    // `Set 1 Winner: Swiatek vs Zheng` + `Yes` → `Swiatek wins Set 1`. The
    // complementary `No` is dropped rather than renamed: see `scopedWinnerLabel`.
    const scopedWinner = parsed ? null : scopedWinnerLabel(row.market_name, row.outcome_name);
    if (!parsed && !scopedWinner && SCOPED_WINNER_MARKET.test((row.market_name || "").trim())) continue;

    const title = parsed ? PLAYER_PROPS_CATEGORY : categorizeMarketName(row.market_name || "").category;
    const subtitle = parsed ? "by statistic" : categorizeMarketName(row.market_name || "").subtitle;
    // Every period-winner question in a match belongs on ONE card, headed with
    // the matchup. Left keyed on `market_name` they became a stack of one-row
    // cards each headed `Set 1 Winner: Swiatek vs Zheng` above a row reading
    // `Swiatek wins Set 1` — the repetition `stripCardPrefix` exists to prevent.
    const scopedWinnerCard = scopedWinner
      ? (() => {
          const m = SCOPED_WINNER_MARKET.exec((row.market_name || "").trim());
          return m ? `${m[2].trim()} vs ${m[3].trim()}` : null;
        })()
      : null;
    const cardName = parsed
      ? parsed.statistic
      : scopedWinnerCard ?? (row.market_name || "Unknown");
    // Inside a "Home Runs" card the statistic is redundant; the threshold is
    // not, because a statistic carries several (0.5 and 1.5 both occur live).
    const label = parsed
      ? `${parsed.player} O/U ${parsed.threshold}`
      : scopedWinner ?? (named || "Unknown");
    // Read from the MARKET title, which still says `Set 1` after the label has
    // been rewritten to `Swiatek wins Set 1`. Null for every other row, which
    // keeps falling back to reading its own label.
    const setNumber = scopedWinner
      ? setNumberFromLabel(SCOPED_WINNER_MARKET.exec((row.market_name || "").trim())?.[1])
      : null;

    let draft = drafts.get(title);
    if (!draft) {
      draft = { title, subtitle, cardOrder: [], cards: new Map() };
      drafts.set(title, draft);
      draftOrder.push(title);
    }

    let card = draft.cards.get(cardName);
    if (!card) {
      card = [];
      draft.cards.set(cardName, card);
      draft.cardOrder.push(cardName);
    }
    card.push({ label, probability: row.probability ?? null, source: row.source ?? null, setNumber });
  }

  let renderedOutcomes = 0;
  let withheld = 0;

  const categories: MarketCategoryGroup[] = draftOrder.map((title) => {
    const draft = drafts.get(title) as Draft;
    let categoryWithheld = 0;

    const cards: MarketCard[] = draft.cardOrder.map((name) => {
      const merged = mergeOutcomes(draft.cards.get(name) as LabeledRow[]);
      const outcomes = [...merged.outcomes]
        .map((o) => {
          // "Settled means settled" applies inside a live match too: set 1 is
          // over the moment either player has banked a set, so its row stops
          // drawing a live bar at 0% and states a last quote instead.
          // The carried number wins where it exists; everything else still
          // reads its own label, exactly as before.
          const setNumber = o.setNumber ?? setNumberFromLabel(o.label);
          return setNumber !== null && setNumber <= completedSets
            ? { ...o, decided: true }
            : o;
        })
        .sort((a, b) => b.prob - a.prob);
      renderedOutcomes += outcomes.length;
      categoryWithheld += merged.withheld;
      return { name, outcomes, withheld: merged.withheld };
    });

    withheld += categoryWithheld;
    return {
      title: draft.title,
      subtitle: draft.subtitle,
      // A card can be emptied entirely by withholding; it must not render as a
      // headed card with no bars.
      cards: cards.filter((c) => c.outcomes.length > 0),
      withheld: categoryWithheld,
    };
  });

  return {
    categories: categories
      .filter((c) => c.cards.length > 0)
      .sort((a, b) => {
        const ai = CATEGORY_ORDER.indexOf(a.title);
        const bi = CATEGORY_ORDER.indexOf(b.title);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      }),
    renderedOutcomes,
    withheld,
  };
}
