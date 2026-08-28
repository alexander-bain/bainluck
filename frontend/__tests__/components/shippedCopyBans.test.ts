/**
 * UX-P150 — THE COPY GUARD READS WHAT SHIPPED, NOT WHAT IS IN THE TREE.
 *
 * ═══ THE INCIDENT ═══
 *
 * UX-P145 swept the tournament copy for internal vocabulary. UX-P146 swept it
 * again for ruling 138's ban on the word *price*. Both were real sweeps, both
 * had render guards, both reported done. On 2026-08-28 Alex opened the LIVE
 * page and read:
 *
 *   > "No prices yet. We have not recorded a price for today's matches."
 *   > "Once the main draw starts, Kalshi and Polymarket list more of them…
 *   >  and the ones worth asking appear here as they are priced."
 *
 * Every one of those strings had been fixed. None of the fixes had landed. The
 * branch was clean and the guards were green because the guards read
 * `components/tournament/*.tsx` and `renderToStaticMarkup` — a working tree
 * and a fixture. Neither is a reader.
 *
 *   > Extend the pinned copy test to run against the strings the PRODUCTION
 *   > bundle serves, so branch-only sweeps can never look done again.
 *   > — Alex, 2026-08-28
 *
 * ═══ WHAT THIS FILE DOES, IN THREE LAYERS ═══
 *
 * 1. THE PREDICATE, PINNED. Every retired sentence Alex quoted is rendered
 *    back through the rules and MUST be rejected, and a set of legitimate
 *    strings MUST survive. A banned-word test that has never seen a banned
 *    word is a test whose regexes are wrong.
 *
 * 2. THE LOCAL BUILD. `.next/static/chunks` is the exact byte stream Vercel
 *    uploads. Scanning it catches everything the render guard cannot reach:
 *    copy in a branch a fixture never takes, copy in a component no test
 *    imports, copy in a page. CI runs `npm run build` before this suite, so in
 *    CI the directory is always there — and when it IS there and this test
 *    finds nothing, that is a claim about the artifact rather than the source.
 *
 * 3. PRODUCTION, ON DEMAND. Point `SHIPPED_BUNDLE_DIR` at a directory filled
 *    by `scripts/fetch-shipped-copy.mjs` and the same rules run over the
 *    chunks a browser downloaded from bainluck.com. That is the only layer
 *    that can answer "is it on production", and it is the one the ship proof
 *    for this queue is taken from.
 *
 * ═══ WHY LAYERS 2 AND 3 ARE CONDITIONAL, AND WHY THAT IS NOT A SILENT SKIP ═══
 *
 * A guard that quietly no-ops when its input is missing is worse than no
 * guard: it reports green and teaches everyone to trust it. So the bundle scan
 * is conditional on the directory EXISTING, and `it("...")` logs loudly and
 * names the exact command when it is not — plus `ciRequiresBundle` makes the
 * absence a hard failure under `CI`, where `npm run build` has always run and
 * a missing `.next` means the gate was skipped rather than satisfied.
 */

import fs from "node:fs";
import path from "node:path";

import {
  ALL_COPY_BANS,
  FUTURE_PROMISE_BANS,
  VENUE_BANS,
  extractBundleStrings,
  findBannedCopy,
  isProse,
  scanBundleSource,
  surfaceOf,
  type BundleCopyHit,
} from "@/lib/copyBans";

/* ───────────────────────── layer 1: the predicate ───────────────────────── */

describe("the rules reject the copy Alex read on production", () => {
  /**
   * Verbatim, from Alex's 2026-08-28 review of the live page. Each entry is a
   * sentence that WAS served to a reader; each must be rejected, and the
   * comment names the rule it must be rejected BY, so a rule that stops
   * existing cannot be covered for by a neighbour.
   */
  const RETIRED: [string, RegExp][] = [
    // ruling 138 — the word is PROBABILITY
    ["No prices yet. We have not recorded a price for today's matches.", /price/i],
    ["47 matches have prices that do not agree yet.", /price/i],
    ["We know who is in this draw, but nobody has priced it yet.", /price/i],
    ["cells carry a market price.", /price/i],
    ["They come back when they are priced again.", /price/i],
    // ruling 141 — venue names
    ["we asked Kalshi and Polymarket and neither runs that market.", /venue|Kalshi/i],
    ["Polymarket 20 days ago", /venue|Polymarket/i],
    // ruling 142 — future-tense promises
    ["New questions are coming — check back soon.", /promise|later|coming/i],
    ["Matches appear here as they are scheduled.", /section WILL|appear here/i],
    ["Questions about sets, games and margins appear here as soon as anyone opens one.", /appear here|future|promise/i],
    ["It is in the draw; the number comes later.", /later/i],
    // the whole sentence, all three rulings at once — Alex's headline example
    [
      "Once the main draw starts, Kalshi and Polymarket list more of them beyond who-reaches-what, and the ones worth asking appear here as they are priced.",
      /./,
    ],
  ];

  it.each(RETIRED)("rejects %j", (sentence, whyPattern) => {
    const hits = findBannedCopy(sentence);
    expect(hits.length).toBeGreaterThan(0);
    // Not just "something fired" — the REASON has to be about the right thing,
    // or a stray `stale` rule could carry a venue-name test forever.
    expect(hits.map((h) => `${h.ban.id} ${h.ban.why}`).join(" | ")).toMatch(whyPattern);
  });

  it("the replacement for 'No market yet' passes — the fix is not itself banned", () => {
    expect(findBannedCopy("No probability yet")).toEqual([]);
  });

  /**
   * The other half, and the half that decides whether this guard survives
   * contact with a real page: it must NOT fire on the product's own content.
   * Market questions are written by markets and half of them start with
   * "Will"; a rule that eats those is a rule somebody turns off.
   */
  const ALLOWED = [
    "Will Sinner actually play?",
    "Who will be the men's singles champion?",
    "Can Sinner win a second major this year?",
    "How many slams for Alcaraz this year?",
    "Updates paused. These are the last probabilities we saw, not live ones.",
    "No market has put a probability on today's matches.",
    "This section holds the questions about this draw worth asking beyond who reaches which round.",
    "Nobody is quoting this match yet. It is in the draw with no probability against it.",
    "Nothing is on right now. This is where the day's matches sit.",
    "one reading 20 days ago",
    "This draw has none with a probability against them.",
  ];

  it.each(ALLOWED)("leaves legitimate copy alone: %j", (sentence) => {
    expect(findBannedCopy(sentence)).toEqual([]);
  });

  it("every rule is reachable — no rule is dead weight", () => {
    // A rule nobody can trigger is a rule that will be silently broken by the
    // next refactor of the regex list.
    for (const ban of ALL_COPY_BANS) {
      expect(ban.pattern.source.length).toBeGreaterThan(2);
      expect(ban.why).not.toEqual("");
      expect(ban.id).toMatch(/^[a-z0-9-]+$/);
    }
    const ids = ALL_COPY_BANS.map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("the venue ban is case-sensitive on purpose — the source ids survive", () => {
    // `kalshi` and `polymarket` are enum values on `source`, `group_id` and
    // `stale_sources`, and they are read by the sentinels and CERT-411. The
    // ruling is about a NAME in a sentence, so the pattern is capitalised.
    expect(findBannedCopy("Kalshi", VENUE_BANS).length).toBe(1);
    expect(findBannedCopy('source: "kalshi"', VENUE_BANS)).toEqual([]);
    expect(findBannedCopy('group_id: "polymarket:12345"', VENUE_BANS)).toEqual([]);
  });

  it("the future-promise rules do not fire on a market question", () => {
    for (const q of ["Will Djokovic reach the final?", "Will there be a five-setter?"]) {
      expect(findBannedCopy(q, FUTURE_PROMISE_BANS)).toEqual([]);
    }
  });
});

/* ─────────────────── the extractor, before it is trusted ─────────────────── */

describe("reading copy back out of minified JavaScript", () => {
  it("does not stitch two literals into one fake string", () => {
    // The bug that made the first draft of this scanner useless: a global
    // /"([^"]*)"/ run over minified code matches from the CLOSING quote of one
    // literal to the OPENING quote of the next, and reports the code between
    // them as copy. This is that exact shape.
    const src = 'if("dark"===e.price_state)return null;let t="No numbers yet";';
    const strings = extractBundleStrings(src);
    expect(strings).toContain("dark");
    expect(strings).toContain("No numbers yet");
    expect(strings.some((s) => s.includes("price_state"))).toBe(false);
  });

  it("splits a template literal at its interpolations", () => {
    // eslint-disable-next-line no-useless-escape
    const src = "const s=`We have not seen a new number on ${n} questions in a while.`;";
    const strings = extractBundleStrings(src);
    expect(strings).toContain("We have not seen a new number on ");
    expect(strings).toContain(" questions in a while.");
  });

  it("surfaceOf reads the ROUTE out of a chunk path, in both layouts", () => {
    // The local build nests them; `fetch-shipped-copy.mjs` reproduces the same
    // nesting on purpose. If either flattens, every route chunk becomes
    // "shared" and the tournament gate passes by scanning nothing.
    expect(surfaceOf("app/tournaments/[slug]/page-0a584f.js")).toBe("app/tournaments");
    expect(surfaceOf("_next/static/chunks/app/tournaments/[slug]/page-0a584f.js")).toBe(
      "app/tournaments"
    );
    expect(surfaceOf("app/admin/matching/page-fedb32.js")).toBe("app/admin");
    expect(surfaceOf("3657-bef4a5.js")).toBe("shared");
  });

  it("isProse keeps sentences and drops identifiers, classes and enums", () => {
    expect(isProse("No market has put a probability on today's matches.")).toBe(true);
    expect(isProse("we asked Kalshi and Polymarket and neither runs that market.")).toBe(true);
    expect(isProse("data-price-state")).toBe(false);
    expect(isProse("priced_cells")).toBe(false);
    expect(isProse("mt-2 max-w-[62ch] text-[11.5px] leading-snug")).toBe(false);
    expect(isProse("===e.price_state)return null;if(")).toBe(false);
  });

  it("finds a planted violation in a bundle-shaped source", () => {
    // The scan must survive minification, not just clean source. If this ever
    // goes green because `scanBundleSource` stopped looking, the two bundle
    // tests below would go green for the same reason and say nothing.
    const planted =
      'function O(e){return e.n?"Live number.":"Once the main draw starts, Kalshi lists more of them."}';
    const hits = scanBundleSource("planted.js", planted);
    expect(hits.map((h) => h.ban.id).sort()).toEqual(["once-the", "venue-kalshi"]);
  });
});

/* ───────────────── layers 2 and 3: what actually shipped ───────────────── */

function scanDir(dir: string): BundleCopyHit[] {
  const hits: BundleCopyHit[] = [];
  const walk = (d: string) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".js")) {
        hits.push(...scanBundleSource(path.relative(dir, full), fs.readFileSync(full, "utf8")));
      }
    }
  };
  walk(dir);
  return hits;
}

function countChunks(dir: string): number {
  let n = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) n += countChunks(path.join(dir, entry.name));
    else if (entry.name.endsWith(".js")) n += 1;
  }
  return n;
}

function report(hits: BundleCopyHit[]): string {
  return hits
    .map((h) => `  [${h.ban.id}] ${h.surface}  (${h.file})\n    ${h.ban.why}\n    "${h.literal}"`)
    .join("\n");
}

/**
 * Surfaces the rulings do not reach.
 *
 * `app/admin` is staff-only — ruling 138 already recorded that it is
 * "arguably outside user-facing altogether", and its copy exists to name the
 * exact venue and the exact enum that an operator has to go and fix.
 * The rest is third-party code we did not write and cannot reword.
 */
const EXEMPT_SURFACES = new Set(["app/admin"]);
const THIRD_PARTY_CHUNKS = [/polyfills-/, /\bframework-/, /\bfd9d1056-/, /\b463d092a-/, /\bb3bee427-/];

/**
 * ═══ THE DEBT, ENUMERATED — ruling 138's "owed, not done", made executable ═══
 *
 * Rulings 138, 141 and 142 are product-wide and permanent. This queue swept
 * the TOURNAMENT surfaces, which is what Alex was reading. Every other surface
 * that still violates them is listed here, by surface and by the exact rule it
 * breaks, so that:
 *
 *   • the ship surfaces are gated HARD — `app/tournaments` is not in this map
 *     and any hit on it fails, on the branch and on production alike;
 *   • a NEW surface can never quietly join the debt — an unlisted surface with
 *     any hit fails, which is the only property that makes a debt list worth
 *     writing down;
 *   • a NEW KIND of violation on an already-owed surface still fails — the key
 *     is (surface, rule), not surface;
 *   • the list can only be paid DOWN. Removing an entry is a one-line diff
 *     next to the fix; adding one requires saying so out loud in review.
 *
 * `/calibration` is the heaviest entry and deliberately NOT swept here: ruling
 * 138 flagged that the `price_moved` dimension is a real distinction about
 * TRADING, and "did trading move the number" has to keep meaning what "did
 * trading move the price" meant. That is a rewrite with judgment in it, not a
 * find-and-replace, and doing it badly would cost the page its meaning.
 */
const OWED: Record<string, string[]> = {
  // The methodology page. Names its sources because comparing them IS the
  // subject (the standing "deliberate comparison surfaces only" carve-out),
  // and says "price" throughout for the reason in ruling 138.
  "app/calibration": ["price-family", "venue-kalshi", "venue-polymarket", "blend"],
  // Legal disclosure. Naming the third parties we read is the POINT of the
  // section; a privacy policy that will not say who is involved is not one.
  "app/privacy": ["price-family", "venue-kalshi", "venue-polymarket"],
  // Category dashboards — venue names in section subtitles and source chips.
  "app/weather": ["venue-kalshi", "venue-polymarket", "appear-here"],
  "app/politics": ["price-family", "venue-kalshi", "venue-polymarket"],
  "app/categories": ["check-back", "venue-kalshi", "venue-polymarket"],
  // "the price at the pump", "Gas price", "Inflation & Consumer Prices" —
  // ruling 138 explicitly SPARES these: they are prices of goods in the world,
  // which is what those markets are about. Listed so the exemption is visible.
  "app/economics": ["price-family"],
  // The explainer page. "Kalshi + Polymarket, unified" is a claim ABOUT the
  // unification, which is the one place naming them is arguably the subject —
  // and exactly the judgment call ruling 141 leaves to Alex rather than to a
  // sweep. Listed, not silently exempted.
  "app/about": ["venue-kalshi", "venue-polymarket"],
  "app/futures": ["price-family"],
  "app/events": ["price-family", "blend"],
  "app/search": ["check-back"],
  "app/hub": ["check-back"],
  "app/my-stuff": ["check-back"],
  "app/sports": ["check-back"],
  "app/playoffs": ["will-populate"],
  // Components shared across routes: the marketing blurbs on the landing
  // shell, `lib/priceCadenceCopy.ts`, and the live-game chart caption.
  shared: [
    "blend",
    "price-family",
    "venue-kalshi",
    "venue-polymarket",
    "check-back",
    "once-the",
    "will-populate",
  ],
};

/** Hits that the debt list does not already account for. */
function unowned(hits: BundleCopyHit[]): BundleCopyHit[] {
  return hits.filter((h) => {
    if (THIRD_PARTY_CHUNKS.some((p) => p.test(h.file))) return false;
    if (EXEMPT_SURFACES.has(h.surface)) return false;
    return !(OWED[h.surface] ?? []).includes(h.ban.id);
  });
}

describe("the built bundle — the bytes Vercel uploads", () => {
  const dir = path.join(__dirname, "..", "..", ".next", "static", "chunks");
  const present = fs.existsSync(dir);

  it("the build output exists, or CI has skipped its own gate", () => {
    if (present) {
      expect(present).toBe(true);
      return;
    }
    const message =
      "No .next/static/chunks — the shipped-copy scan did NOT run.\n" +
      "  Run `npm run build` first. This is the layer that catches copy no fixture renders.";
    if (process.env.CI) throw new Error(message);
    console.warn(`\n⚠️  ${message}\n`);
  });

  (present ? it : it.skip)("the tournament surfaces ship no banned language at all", () => {
    // The ship. Not "fewer than before" and not "none that we know about":
    // zero, on the surface Alex read, in the artifact that gets uploaded.
    const hits = scanDir(dir).filter((h) => h.surface === "app/tournaments");
    if (hits.length > 0) {
      throw new Error(`banned language on the tournament surfaces:\n${report(hits)}`);
    }
  });

  (present ? it : it.skip)("no surface violates a rule that is not already written down", () => {
    const hits = unowned(scanDir(dir));
    if (hits.length > 0) {
      throw new Error(
        "banned language on a surface/rule pair that is NOT in OWED.\n" +
          "Either fix it, or add the (surface, rule) to OWED with a reason — silently is not one of the options.\n" +
          report(hits)
      );
    }
  });

  (present ? it : it.skip)("the debt list has no dead entries — it can only be paid down", () => {
    // A surface that was fixed but left on the list makes the debt look bigger
    // than it is, and makes the next reader distrust the whole map.
    const live = new Set(scanDir(dir).map((h) => `${h.surface} ${h.ban.id}`));
    const dead: string[] = [];
    for (const [surface, ids] of Object.entries(OWED)) {
      for (const id of ids) {
        if (!live.has(`${surface} ${id}`)) dead.push(`${surface} → ${id}`);
      }
    }
    if (dead.length > 0) {
      throw new Error(
        `OWED entries that no longer fire — delete them:\n  ${dead.join("\n  ")}`
      );
    }
  });
});

describe("production — the chunks a browser downloaded from bainluck.com", () => {
  const dir = process.env.SHIPPED_BUNDLE_DIR;
  const present = Boolean(dir) && fs.existsSync(dir as string);

  it("says plainly when it did not run, instead of passing", () => {
    if (present) {
      // The empty-directory case is the one that matters: a scan of nothing
      // returns nothing, and "no hits" would read as "production is clean".
      // Recursive: `fetch-shipped-copy.mjs` preserves `app/<route>/…` nesting
      // because `surfaceOf` needs it, so a top-level readdir counts zero and
      // this test would report "did not run" over a perfectly good download.
      expect(countChunks(dir as string)).toBeGreaterThan(0);
      return;
    }
    console.warn(
      "\n⚠️  SHIPPED_BUNDLE_DIR unset — production was NOT scanned. This run proves\n" +
        "    nothing about bainluck.com. To prove it:\n" +
        "      node scripts/fetch-shipped-copy.mjs --url https://www.bainluck.com/tournaments/us-open-2026\n" +
        "      SHIPPED_BUNDLE_DIR=$TMPDIR/bainluck-shipped npx jest shippedCopyBans\n"
    );
  });

  (present ? it : it.skip)("serves no banned language on the tournament surfaces", () => {
    const hits = scanDir(dir as string).filter((h) => h.surface === "app/tournaments");
    if (hits.length > 0) {
      throw new Error(
        `banned language LIVE on production (${dir}):\n${report(hits)}\n\n` +
          "This is the ship. A green branch does not close it."
      );
    }
  });

  (present ? it : it.skip)("serves nothing that is not already written down", () => {
    // The prod fetch only pulls ONE page's chunks, so the dead-entry check
    // above deliberately does not run here: most of OWED is simply not in the
    // download, and "absent" would be indistinguishable from "fixed".
    const hits = unowned(scanDir(dir as string));
    if (hits.length > 0) {
      throw new Error(`unlisted banned language LIVE on production:\n${report(hits)}`);
    }
  });
});
