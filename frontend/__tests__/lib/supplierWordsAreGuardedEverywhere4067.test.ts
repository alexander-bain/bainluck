// #4067 REPAIR (CERT-2290) — `4067-ALL-READER-SURFACES-USE-SPORTSBOOKS`.
//
// ── WHAT THE FIRST SHIP GOT WRONG ────────────────────────────────────────────
//
// Standing notice 33 (Alex, 2026-09-08 2:00pm PT, on D92 — *"we wouldn't EVER
// want to reference 'bookmakers'"*): the words `books`, `bookmaker`,
// `bookmakers`, `per-bookmaker` never appear on the site or in the app, in any
// label, row, caption, tooltip, alt text or API string the clients print. The
// approved word is `sportsbooks`.
//
// `b0e54ac3` swept for that and left four reader-facing strings behind, on
// three surfaces. CERT-2290 found them in one pass:
//
//   1. `/calibration` — "vig-removed consensus closing odds across 20+
//      bookmakers", unconditional page copy.
//   2. `lib/calibrationProviders.ts` — `odds_api_bookmaker: "Per-Bookmaker
//      (Odds API)"`.
//   3. `lib/sourceColors.ts` — the same label, a second time, in the shared
//      colour registry.
//   4. `/about` — "the whole market's honest opinion, not one book's" — the
//      SINGULAR, which the ship's own pattern already rejected.
//
// ── WHY THE GUARD DID NOT SEE ANY OF THEM ────────────────────────────────────
//
// 🔴 **THE SCOPE OF THE RULE AND THE SCOPE OF THE GUARD WERE DIFFERENT SCOPES.**
// The ban is product-wide by its own words; the guard lived in
// `SUPPLIER_PROSE_BANS`, which is fenced to the tournament surfaces under D86's
// staged rollout. So the sweep fixed every string somebody thought to look at
// and the guard could only ever confirm the places already looked at. That is
// not a weaker guard — it is a guard that cannot fail for the reason you need
// it to.
//
// `sportsbook` genuinely is staged: it is the approved word IN A MARK and the
// banned word IN A CAPTION, so its fence encodes a product distinction. `books`
// and `bookmakers` encode nothing — they are banned wherever they sit — so
// `SUPPLIER_WORD_BANS` now rides in `ALL_COPY_BANS` and the shipped-bundle scan
// in `shippedCopyBans.test.ts` enforces them over every chunk the site serves.
//
// ── AND ITEMS 2 AND 3 ARE A DIFFERENT BUG FROM ITEMS 1 AND 4 ─────────────────
//
// The backend label was already correct — `b0e54ac3` changed
// `calibration_source_labels.py` to "Per-sportsbook (Odds API)" — and the page
// went on printing the old one, because `makeSourceLabeller` gives the LOCAL
// map precedence over the server's `label` field by design (CAL-P1025 / #3357).
// That precedence is right and is not touched here. What it means is that
// **fixing a label on the server does not fix it on the page**, and the two
// local overrides have to be found by name. They are pinned below.

import { readFileSync } from "fs";
import { join } from "path";

import {
  ALL_COPY_BANS,
  findBannedCopy,
  SUPPLIER_PROSE_BANS,
  SUPPLIER_WORD_BANS,
} from "@/lib/copyBans";
// Two registries, two `sourceLabel`s, and CERT-2290's point is that both carried
// the banned word. Imported side by side under names that say which is which.
import { sourceLabel as calibrationSourceLabel } from "@/lib/calibrationProviders";
import { sourceLabel as registrySourceLabel } from "@/lib/sourceColors";
import { STORY_BLEND } from "@/lib/story-content";
import { describeCohort } from "@/lib/calibrationCohort";

/* ─────────── the four strings the cert named, each pinned by value ─────────── */

describe("CERT-2290's four findings, each fixed at its own source", () => {
  it("the calibration page's methodology answer counts sportsbooks", () => {
    // Read off the page rather than restated, so a reworded paragraph that
    // re-introduces the word fails here instead of shipping.
    const page = readFileSync(
      join(process.cwd(), "app/calibration/page.tsx"),
      "utf8"
    );
    expect(page).toContain("consensus closing odds across 20+ sportsbooks");
    expect(findBannedCopy(page, ALL_COPY_BANS).map((h) => h.ban.id)).not.toContain(
      "supplier-bookmaker"
    );
  });

  it("the per-source calibration label is the server's word, not the old local one", () => {
    expect(calibrationSourceLabel("odds_api_bookmaker")).toBe("Per-sportsbook (Odds API)");
  });

  it("the shared colour registry spells it the same way", () => {
    // Two registries, one source. #2442's rule is that they cannot disagree;
    // CERT-2290's finding is that agreeing on a BANNED word is not compliance.
    expect(registrySourceLabel("odds_api_bookmaker")).toBe("Per-sportsbook (Odds API)");
    expect(registrySourceLabel("odds_api_bookmaker")).toBe(
      calibrationSourceLabel("odds_api_bookmaker")
    );
  });

  it("the /about blend story does not end on the singular", () => {
    expect(STORY_BLEND.body).toContain("not one sportsbook's");
    // Scoped to the two words this repair is about. The wider list carries
    // ruling 138's `price` family and the venue names, and `/about` has its own
    // standing entries for those in `shippedCopyBans.test.ts`'s OWED map — a
    // guard that quietly asserts a neighbouring debt is paid fails for the
    // wrong reason and gets the wrong fix.
    expect(findBannedCopy(STORY_BLEND.body, SUPPLIER_WORD_BANS)).toEqual([]);
  });

  it("the calibration partition note does not either", () => {
    // The one the cert did not name and the product-wide switch-on found. It
    // is generated, not literal, so it is asserted through the generator.
    const note = describeCohort(
      { movedN: 349310, unchangedN: 263022, notApplicableN: 40075 },
      652407,
      true
    ).partitionNote;
    expect(note).toContain("a sportsbook moves its line with money");
    // Same scoping, same reason: this note legitimately says "price-moved",
    // which is `/calibration`'s recorded ruling-138 debt and not this ship's.
    expect(findBannedCopy(note ?? "", SUPPLIER_WORD_BANS)).toEqual([]);
  });
});

/* ─────────────────── the scope fix, which is the real ship ─────────────────── */

describe("the two absolute words are guarded everywhere, not behind a fence", () => {
  it("they ride in ALL_COPY_BANS, so the shipped-bundle scan reads them", () => {
    const ids = ALL_COPY_BANS.map((b) => b.id);
    expect(ids).toContain("supplier-books");
    expect(ids).toContain("supplier-bookmaker");
  });

  it("`sportsbook` stays fenced — its scope is a product distinction, not a sweep record", () => {
    // D91 protects the word in a mark: "Kalshi · Polymarket · 7 sportsbooks".
    // Promoting it with the other two would fail the gate on copy the ruling
    // explicitly keeps, which is this file's oldest recorded failure mode.
    expect(ALL_COPY_BANS.map((b) => b.id)).not.toContain("supplier-sportsbook");
    expect(SUPPLIER_PROSE_BANS.map((b) => b.id)).toEqual(["supplier-sportsbook"]);
  });

  const BANNED = [
    "aggregated across multiple bookmakers by The Odds API",
    "Per-Bookmaker (Odds API)",
    "the whole market's honest opinion, not one book's",
    "a book moves its line with money",
    "the books disagree by four points",
    "20+ bookmakers",
    "one book's number",
  ];

  it.each(BANNED)("rejected anywhere on the site: %j", (sentence) => {
    expect(findBannedCopy(sentence, ALL_COPY_BANS).length).toBeGreaterThan(0);
  });
});

/* ────────── `book` is also an ordinary noun, and must stay writable ────────── */

describe("the carve-out: a compound that is not a supplier", () => {
  it("/privacy may still say what it does not read", () => {
    // Verbatim from the live page. Measured 2026-09-08: switching the two words
    // on product-wide produced exactly two hits over `.next/static/chunks` —
    // the calibration singular, fixed above, and this. If the pattern had been
    // shipped without the carve-out, a clean build would have failed a copy
    // gate on a true sentence about contact permissions, and the fix somebody
    // reached for would have been to switch the rule back off.
    expect(
      findBannedCopy("we never access your address book or contact list", ALL_COPY_BANS)
    ).toEqual([]);
  });

  const ORDINARY = [
    "we never access your address book or contact list",
    "He is in the record books after that run.",
    "The rule book says the clock stops.",
    "A phone book is not a data source.",
  ];

  it.each(ORDINARY)("ordinary English survives: %j", (sentence) => {
    expect(findBannedCopy(sentence, ALL_COPY_BANS)).toEqual([]);
  });

  it("the carve-out is a compound rule, not a hole", () => {
    // 🔴 THE MUTATION THAT WOULD MAKE THIS GUARD USELESS: widening the
    // lookbehind until "the book" itself walks through it. The exemption is for
    // a noun that PRECEDES `book` and changes what it means; a bare supplier
    // reference has no such noun, and neither does one wearing an article.
    for (const s of ["the book", "a book", "the books", "our books", "one book's"]) {
      expect(findBannedCopy(s, ALL_COPY_BANS).map((h) => h.ban.id)).toContain(
        "supplier-books"
      );
    }
  });

  it("no word boundary, no rule — `notebook` was never in scope", () => {
    // Recorded so nobody adds an arm for it and then believes the arm is
    // load-bearing. `\bbook\b` cannot match inside a compound written solid.
    expect(findBannedCopy("Open the notebook and check Facebook.", ALL_COPY_BANS)).toEqual(
      []
    );
  });
});
