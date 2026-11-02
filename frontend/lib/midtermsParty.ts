import type { FeedFuturesOutcome } from "./types";

export type MidtermsParty = "D" | "R";
export const MIDTERMS_PARTY_COLOR = {
  D: "var(--party-democratic)",
  R: "var(--party-republican)",
} as const;

// #11873: identity hints for this curated edition, not a surname classifier.
// Verified Nov 2 against each Kalshi event's -D/-R market and yes_sub_title:
// https://api.elections.kalshi.com/trade-api/v2/events/{event_ticker}.
// Both the served outcome id AND name must still agree. New/replaced candidates
// stay neutral until evidenced; never turn an unknown into a party claim.
const CANDIDATES: Record<number, { market: number; name: string; party: MidtermsParty }> = {
  1595212: { market: 109085, name: "Adam Hamilton", party: "D" }, // SENATEKS-26-D
  1595211: { market: 109085, name: "Roger Marshall", party: "R" }, // SENATEKS-26-R
  1595218: { market: 109088, name: "Josh Turek", party: "D" }, // SENATEIA-26-D
  1595217: { market: 109088, name: "Ashley Hinson", party: "R" }, // SENATEIA-26-R
  1595205: { market: 109082, name: "Troy Jackson", party: "D" }, // SENATEME-26-D
  1595206: { market: 109082, name: "Susan Collins", party: "R" }, // SENATEME-26-R
  1595232: { market: 109095, name: "Democratic party", party: "D" }, // SENATEAK-26-D
  1595231: { market: 109095, name: "Republican party", party: "R" }, // SENATEAK-26-R
  1595170: { market: 109065, name: "James Talarico", party: "D" }, // SENATETX-26-D
  1595169: { market: 109065, name: "Ken Paxton", party: "R" }, // SENATETX-26-R
  1595184: { market: 109072, name: "Sherrod Brown", party: "D" }, // SENATEOHS-26-D
  1595183: { market: 109072, name: "Jon Husted", party: "R" }, // SENATEOHS-26-R
  1595175: { market: 109068, name: "Darline Graham", party: "R" }, // SENATESC-26-R
  1595176: { market: 109068, name: "Annie Andrews", party: "D" }, // SENATESC-26-D
  1595203: { market: 109081, name: "Abdul El-Sayed", party: "D" }, // SENATEMI-26-D
  1595204: { market: 109081, name: "Mike Rogers", party: "R" }, // SENATEMI-26-R
  1594121: { market: 108645, name: "Keisha Lance Bottoms", party: "D" }, // GOVPARTYGA-26-D
  1594122: { market: 108645, name: "Rick Jackson", party: "R" }, // GOVPARTYGA-26-R
};

export function midtermsOutcomeParty(marketId: number, outcome: Pick<FeedFuturesOutcome, "name"> & { id?: number }): MidtermsParty | null {
  if (/^democrat(?:s|ic(?: party)?)?$/i.test(outcome.name) || /\(D\)$/i.test(outcome.name)) return "D";
  if (/^republican(?:s| party)?$|^gop$/i.test(outcome.name) || /\(R\)$/i.test(outcome.name)) return "R";
  const candidate = outcome.id == null ? null : CANDIDATES[outcome.id];
  if (candidate?.market === marketId && candidate.name === outcome.name) return candidate.party;
  if (marketId === 108619) {
    const parties = midtermsBalanceParties(outcome.name);
    if (parties && parties.house === parties.senate) return parties.house;
  }
  // Yes means a Democratic sweep in this explicit market. No is NOT a
  // Republican sweep and must not inherit Republican red.
  return marketId === 109918 && outcome.name === "Yes" ? "D" : null;
}

export function midtermsBalanceParties(name: string): { house: MidtermsParty; senate: MidtermsParty } | null {
  if (/^democrats? sweep$/i.test(name)) return { house: "D", senate: "D" };
  if (/^republicans? sweep$/i.test(name)) return { house: "R", senate: "R" };
  const chambers: Partial<Record<"house" | "senate", MidtermsParty>> = {};
  for (const match of name.matchAll(/\b(democrat(?:ic|s)?|republicans?|[dr])\b[\s-]+(house|senate)\b/gi)) {
    chambers[match[2].toLowerCase() as "house" | "senate"] = match[1].toLowerCase().startsWith("d") ? "D" : "R";
  }
  return chambers.house && chambers.senate ? { house: chambers.house, senate: chambers.senate } : null;
}
