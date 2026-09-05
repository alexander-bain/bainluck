// My Stuff — the playoff-progression vocabulary (ux/1070 item 3).
//
// WHY THIS IS A MODULE AND NOT STILL INSIDE `app/my-stuff/page.tsx`.
// The Red Sox block on My Stuff showed Division and World Series and nothing
// between them (Alex, 2026-09-04 7:00am shop). The AL pennant was NOT missing
// from the data: `American League Champion` (Kalshi market 274) carries an
// outcome `Boston` linked to team 10709 at 14.5%, and My Stuff had it in hand.
// It was missing from the LADDER because the classifier below could not read
// its name — the conference rung recognised `conference …` and `AFC/NFC`, and
// baseball does not say either word. So the market fell through to the flat
// "Other Markets" list, which is capped at ten rows, and a stage of the team's
// season simply was not on the page.
//
// A page file cannot export helpers (Next's `page.tsx` contract), so the rung
// vocabulary could not be unit-tested where it lived. It lives here now and the
// page imports it — the classifier is the thing that was wrong, so the
// classifier is the thing that gets a guard.

/** Playoff progression stages — order determines funnel display. */
export const PROGRESSION_STAGES: Record<string, { order: number; label: string }> = {
  make_playoffs: { order: 1, label: "Playoffs" },
  division_winner: { order: 2, label: "Division" },
  conference_winner: { order: 3, label: "Conf Finals" },
  championship: { order: 4, label: "Champion" },
};

/** Extract market_type from canonical_market_key (format: sport:league:type:season). */
export function extractMarketType(key: string | null | undefined): string | null {
  if (!key) return null;
  const parts = key.split(":");
  return parts.length >= 3 ? parts[2] : null;
}

/**
 * Detect market type from market name.
 * Mirrors backend _MARKET_TYPE_PATTERNS in futures_categorization.py.
 *
 * ORDER IS LOAD-BEARING. Division is tested before the pennant rung because
 * "AL East Champion" names BOTH an `al` and a `champion` — it is a division
 * title, and the division test is the specific one.
 */
export function detectMarketTypeFromName(name: string): string | null {
  const n = name.toLowerCase();
  if (/make.*playoffs|playoffs.*qualification|will make.*playoffs/i.test(n)) return "make_playoffs";
  if (/division\s*(winner|champion|title)|\b(afc|nfc|al|nl)\s+(east|west|north|south|central)\b/i.test(n)) return "division_winner";
  if (
    (/conference\s*(winner|champion|title|finals)|\b(afc|nfc)\s+(champion|winner)\b/i.test(n) ||
      // ux/1070 item 3: baseball's conference round is the PENNANT, and it never
      // says "conference". Both spellings Kalshi and Polymarket actually use —
      // "American League Champion" (274) and "MLB: 2026 American League
      // Champion" (199045) — plus the abbreviated and "pennant" forms.
      /\b(american|national)\s+league\s+(champion|championship|pennant|winner)\b/i.test(n) ||
      /\b(al|nl)\s+(champion|championship|pennant)\b/i.test(n)) &&
    !/seed|#\d|mvp/i.test(n)
  )
    return "conference_winner";
  if (
    /champion(ship)?\s*(winner|20\d{2})|win.*championship|nba\s+champion|nfl\s+champion|mlb\s+champion|nhl\s+champion|world\s+series|super\s+bowl|stanley\s+cup/i.test(n) ||
      // Kalshi's own name for the trophy market is "Pro Baseball Champion" /
      // "Pro Football Champion" — the same rung the books call "World Series
      // Winner". Without this the ladder's top rung could only ever be the
      // Polymarket/odds-api copy, and the Kalshi price beside it was invisible.
      /\bpro\s+(baseball|football|basketball|hockey|soccer)\s+champion(ship)?\b/i.test(n)
  )
    return "championship";
  return null;
}
