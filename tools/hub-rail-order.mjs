#!/usr/bin/env node
/**
 * hub-rail-order.mjs — measure the ORDER of /hub/tennis's matches rail.
 *
 * ux/1093, for the ordering ship ux/1092 named and deliberately left unfiled.
 *
 * THE QUESTION IT ANSWERS. During the US Open the rail sorts live-first then
 * soonest-first with no tournament weighting, so a Challenger starting sooner
 * outranks a Slam — and nothing on a card names its tournament, so the two are
 * indistinguishable to a reader. That is two separable claims and this prints
 * evidence for both:
 *
 *   1. WHERE the first US Open card sits among priced cards (rank, not vibes)
 *   2. WHETHER any card names its own tournament at all
 *
 * WHY IT READS THE API AND NOT THE DOM. The rail's order is decided server-side
 * in `build_linked_matches`; scraping rendered cards would re-measure the
 * browser's ability to lay them out, and a fullPage LOOK of this page is
 * 63,366px tall. Read the payload the page reads.
 *
 * MEASURE IT ONLY AFTER #3455 IS ON PRODUCTION. That change adds the whole
 * women's draw to this exact rail, so a run against a deploy without it
 * describes a population that no longer exists. Check first:
 *   curl -s $BAINLUCK_API/api/health | python3 -c 'import sys,json;print(json.load(sys.stdin)["commit"])'
 * and confirm that commit contains 56e8fff3.
 *
 * Usage:  node tools/hub-rail-order.mjs [apiBase]
 *         (defaults to $BAINLUCK_API, else https://api.bainluck.com)
 */

const API = process.argv[2] || process.env.BAINLUCK_API || "https://api.bainluck.com";

/** Does this card's own text name the tournament it belongs to? */
function namesTournament(text) {
  return /US Open|Wimbledon|Roland ?Garros|French Open|Australian Open|Masters|ATP \d|WTA \d|Challenger|ITF/i.test(
    text || "",
  );
}

/** Best-effort: is this row a US Open match? */
function isUSOpen(row) {
  const hay = [row.name, row.external_id].filter(Boolean).join(" ");
  return /US ?Open|USOPEN|KXUSOPEN/i.test(hay);
}

/** Is this a women's-draw row? The #3455 ship, countable. */
function isWomens(row) {
  const hay = [row.name, row.external_id].filter(Boolean).join(" ");
  return /WTA|Women/i.test(hay);
}

// NOT `fetch`. Node's fetch is EPERM-blocked by the agent sandbox's egress rules
// while `curl` is allowed, and the failure is a stack trace rather than an HTTP
// error, so it reads as a broken script instead of a blocked one. Shell out.
import { execFileSync } from "node:child_process";
let data;
try {
  const body = execFileSync(
    "curl",
    ["-sS", "--max-time", "60", "-H", "accept: application/json", `${API}/api/hub/tennis`],
    { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
  );
  data = JSON.parse(body);
} catch (e) {
  console.error(`GET /api/hub/tennis failed: ${e.message}`);
  process.exit(1);
}

// `sections` is an OBJECT keyed by section name, not a list — the rail is
// `sections.matches`, and each row carries `top_outcomes[].probability`
// (not `outcomes[].current_probability`; that is the league-futures shape).
const rail = data?.sections?.matches;
if (!Array.isArray(rail)) {
  console.error("could not locate sections.matches; section keys:",
    Object.keys(data?.sections || {}));
  process.exit(2);
}

const priced = rail.filter((r) =>
  (r.top_outcomes || []).some((o) => o.probability != null),
);

const usOpenIdx = priced.findIndex(isUSOpen);
const womensIdx = priced.findIndex(isWomens);

console.log(JSON.stringify({
  api: API,
  rail_total: rail.length,
  priced_cards: priced.length,
  section_counts_matches: data.section_counts?.matches ?? null,

  // (1) ORDER — where the first US Open card sits among priced cards.
  first_us_open_rank: usOpenIdx === -1 ? null : usOpenIdx + 1,
  us_open_priced_cards: priced.filter(isUSOpen).length,

  // The #3455 ship, countable on the same rail.
  first_womens_rank: womensIdx === -1 ? null : womensIdx + 1,
  womens_priced_cards: priced.filter(isWomens).length,

  // (2) NAMING — note this counts the PAYLOAD's `name`, which on this API does
  // carry a "US Open ATP (Doubles): …" prefix. If the rendered card still reads
  // as anonymous, the loss is in the frontend's truncation/stripping, NOT in the
  // data — check the card before repeating "nothing names its tournament".
  payload_names_naming_their_tournament: priced.filter((r) => namesTournament(r.name)).length,

  leading_cards: priced.slice(0, 10).map((r, i) => ({
    rank: i + 1,
    name: r.name,
    us_open: isUSOpen(r),
    womens: isWomens(r),
  })),
}, null, 1));
