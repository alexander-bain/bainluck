/**
 * Static golf tournament metadata for the golf landing page.
 */

export const MAJOR_TOURNAMENTS = new Set([
  "masters",
  "pga_championship",
  "us_open",
  "the_open",
]);

export const TOURNAMENT_ORDER: string[] = [
  "masters",
  "pga_championship",
  "us_open",
  "the_open",
  "players",
  "ryder_cup",
  "presidents_cup",
  "liv",
  "other",
];

export const TOURNAMENT_DISPLAY_NAMES: Record<string, string> = {
  masters: "The Masters",
  pga_championship: "PGA Championship",
  us_open: "U.S. Open",
  the_open: "The Open Championship",
  players: "The Players Championship",
  ryder_cup: "Ryder Cup",
  presidents_cup: "Presidents Cup",
  liv: "LIV Golf",
  other: "Other Tournaments",
};

export const TOURNAMENT_VENUES: Record<string, string> = {
  masters: "Augusta National Golf Club",
  pga_championship: "Quail Hollow Club",
  us_open: "Shinnecock Hills Golf Club",
  the_open: "Royal Portrush Golf Club",
};

export const TOURNAMENT_EMOJI: Record<string, string> = {
  masters: "\u26F3",       // golf flag
  pga_championship: "\uD83C\uDFC6",  // trophy
  us_open: "\uD83C\uDDFA\uD83C\uDDF8",  // US flag
  the_open: "\uD83C\uDDEC\uD83C\uDDE7",  // GB flag
  players: "\u2B50",       // star
  ryder_cup: "\uD83C\uDDEA\uD83C\uDDFA",  // EU flag
  presidents_cup: "\uD83C\uDF0D", // globe
  liv: "\uD83D\uDCB0",    // money bag
  other: "\uD83C\uDFCC\uFE0F",  // golfer
};
