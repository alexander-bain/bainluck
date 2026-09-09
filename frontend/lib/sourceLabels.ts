/**
 * The one place the web turns a backend source key into a word a reader sees.
 *
 * 🔴 WHY THIS IS A MODULE AND NOT A NINTH COPY OF THE SAME OBJECT LITERAL (#4284).
 * `BookmakerTable` rendered `{odds.bookmaker}` raw, so every event page printed
 * the Odds API's own keys where the brand belongs — measured on production
 * 2026-09-09, all 17 rows of `/events/15308043`: `betrivers`, `williamhill_us`,
 * `mybookieag`, `betonlineag`, `ballybet`, `betparx`. `SourceAggregationBlock`
 * two sections up had a 23-entry map and never lent it out, and its own unknown
 * branch title-cased (`betanysports` → "Betanysports", `williamhill_us` →
 * "Williamhill_us"), which reads like a brand and is not one.
 *
 * ✅ SO THE UNKNOWN-KEY BRANCH FAILS QUIET, as the iOS half already does
 * (`SourceLabels.swift`, #4135/#4284): `sourceLabel()` returns null for a key we
 * cannot name and every call site draws nothing rather than the raw or
 * title-cased string. The defect that outlives any one key is the passthrough
 * itself — whatever key the provider adds next reaches the screen unaided, and
 * under standing notice 33 a `books` key would print "Books" with no code change.
 * A key we cannot name is a key we do not print.
 *
 * Measured census behind the entries below (production `odds_snapshots`, distinct
 * `bookmaker`, 24h to 2026-09-09): 18 keys, all named here. `caesars` is NOT among
 * them — production emits `williamhill_us` for that brand and never both — so the
 * two keys mapping to one name collide with nothing today.
 */
const SOURCE_LABELS: Record<string, string> = {
  draftkings: "DraftKings",
  fanduel: "FanDuel",
  betmgm: "BetMGM",
  bovada: "Bovada",
  pointsbet: "PointsBet",
  williamhill: "William Hill",
  // The Odds API still keys Caesars' US book `williamhill_us` — the brand behind
  // the key was renamed, the key was not. Mapping it to "William Hill" would name
  // a sportsbook that no longer takes the bet; the iOS map says "Caesars" too.
  williamhill_us: "Caesars",
  caesars: "Caesars",
  bet365: "Bet365",
  unibet: "Unibet",
  barstool: "Barstool",
  betrivers: "BetRivers",
  mybookieag: "MyBookie",
  superbook: "SuperBook",
  lowvig: "LowVig",
  betonlineag: "BetOnline",
  betus: "BetUS",
  wynnbet: "WynnBet",
  // #4311 — the brand styles itself `ESPN BET`, and the iOS map already said so
  // while this one said "ESPN Bet". Two halves of one product spelling one
  // sportsbook two ways, on a key with 1,467 rows in `odds_snapshots` over the
  // 24h to 2026-09-09, so both spellings were on real screens. The web moved
  // rather than iOS because the brand's own styling is the all-caps one.
  // `clientsSpellOneBrandOneWay4311` now compares the two maps directly, so the
  // next brand added to one client cannot drift from the other the same way.
  espnbet: "ESPN BET",
  fanatics: "Fanatics",
  fliff: "Fliff",
  hardrockbet: "Hard Rock",
  ballybet: "Bally Bet",
  betanysports: "BetAnySports",
  betparx: "betPARX",
  rebet: "Rebet",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};

/**
 * The reader-facing name for a source key, or null when we cannot name it.
 * Callers drop the row; they never fall back to the raw key or to title case.
 */
export function sourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  return SOURCE_LABELS[source] ?? null;
}

/** Whether a source key is one this app can put on a screen. */
export function isNamedSource(source: string | null | undefined): boolean {
  return sourceLabel(source) !== null;
}
