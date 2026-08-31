/**
 * UX-P209 — THE HUB STATUS PILL HAS ONE HOME, AND THIS IS THE TRIPWIRE.
 *
 * ── THE FAILURE THIS EXISTS TO CATCH, WHICH IS ALREADY WRITTEN AND WAITING ───
 *
 * The pill lived inside `app/hub/[competition]/page.tsx`. `program/ux-148`
 * extracts the same markup — including the catch-all that CERT-519 blocked —
 * into `components/hub/UpcomingCard.tsx`, a DIFFERENT file. Measured
 * 2026-08-31: `git merge-tree` reports the two branches' production code
 * auto-merging with zero conflicts.
 *
 * So this is the silent case. Whichever order the two land in, git is happy,
 * every existing test is green, and the render path that ships is whichever
 * copy of the pill survived — which is the one with the false Upcoming in it.
 * No conflict marker, no red suite, and the repair simply is not there any
 * more. "Disjoint files still collide semantically", with the diff to prove it.
 *
 * A rendered test cannot catch that: it imports the good copy by name and
 * passes while the page renders the other one. Only a statement about the
 * REPOSITORY can. Hence a source scan, deliberately.
 *
 * ── WHAT IT POLICES, AND WHAT IT DELIBERATELY DOES NOT ───────────────────────
 *
 * The claim is narrow and it is the claim the header makes: WITHIN THE HUB
 * SURFACE, one component decides what phase label a card shows. The scan is
 * scoped to `app/hub/**` and `components/hub/**`, which is where the collision
 * is (ux-148's file lands in the second one).
 *
 * It is NOT a site-wide ban on the shape. An unscoped first draft of this file
 * reported two more matches and both were measured 2026-08-31:
 *   · `app/sport/[sport]/[league]/page.tsx` — a false positive. Its "Upcoming"
 *     is an `<h2>` section heading; there is no pill.
 *   · `app/playoffs/[sport]/page.tsx:384` — a REAL instance of the same shape:
 *     `tournament.status === "live" ? "In Progress" : "Upcoming"`, a two-way
 *     ternary where anything not live reads Upcoming. It is fed by the
 *     championship-grid payload, not by a hub lister, so no `unknown` reaches
 *     it today and it is not a live defect. Widening this ship to cover it
 *     would be scope the cert did not ask for; it is parked as UX-P209-1
 *     instead. Do not silence it by widening the allowlist here — give it its
 *     own ship.
 *
 * WHEN THIS GOES RED after a merge, the fix is not to widen the allowlist. It
 * is to make the new component import `StatusPill` from the single home and
 * delete its copy — which is also all `UpcomingCard.tsx` needs.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "..");
const SCANNED_DIRS = [path.join("app", "hub"), path.join("components", "hub")];
const HOME = path.join("components", "hub", "HubStatusPill.tsx");
/** UX-P210: the rail — the single home of the HEADING's phase decision. */
const RAIL = path.join("components", "hub", "HubUpcomingRail.tsx");

/** The pill's discriminator: the line every copy of it has to contain. */
const DISCRIMINATOR = /status\s*===\s*["']live["']/;
/** The label the blocked build produced for everything it did not recognise. */
const AFFIRMATIVE_LABEL = />\s*Upcoming\s*</;

/** Does this source decide a hub card's phase label on its own? */
function isPillCopy(source: string): boolean {
  return DISCRIMINATOR.test(source) && AFFIRMATIVE_LABEL.test(source);
}

function walk(dir: string, out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      walk(full, out);
    } else if (/\.tsx?$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

const FILES = SCANNED_DIRS.flatMap((d) => walk(path.join(ROOT, d))).map((f) =>
  path.relative(ROOT, f),
);

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/**
 * `program/ux-148`'s `components/hub/UpcomingCard.tsx`, verbatim from
 * `git show origin/program/ux-148-us-open-start-date-and-marquee:...` on
 * 2026-08-31. Kept here as a FIXTURE, not as code: it is the exact text this
 * tripwire has to recognise on the day that branch merges, and asserting
 * against a description of it would prove nothing. `__tests__` is outside the
 * scanned dirs, so this copy cannot itself trip the scan.
 */
const UX148_PILL = `
export function StatusPill({ status }: { status: string }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent-live">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
        Live
      </span>
    );
  }
  if (status === "settled") {
    return <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Final</span>;
  }
  return <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-brand">Upcoming</span>;
}
`;

describe("the scan is looking at the right files", () => {
  it("found a real, populated hub surface", () => {
    // A walk that silently returned nothing would make every assertion below
    // pass. Both scanned directories must exist and the home must be in them.
    expect(FILES.length).toBeGreaterThan(1);
    expect(FILES).toContain(HOME);
    expect(FILES).toContain(RAIL);
    expect(FILES).toContain(path.join("app", "hub", "[competition]", "page.tsx"));
  });

  it("can report a positive — the home itself is recognised", () => {
    // PROVE THE SWEEP CAN SEE ITS TARGET before trusting it to report absence.
    expect(isPillCopy(read(HOME))).toBe(true);
  });

  it("recognises ux-148's copy, which is the whole point of the file", () => {
    // The bite, proved against the real bytes rather than predicted.
    expect(isPillCopy(UX148_PILL)).toBe(true);
  });

  it("does not fire on a file that merely mentions a live status", () => {
    // The other direction: a detector that returns true for everything would
    // pass the two assertions above and be useless.
    expect(isPillCopy(`const t = games.some((g) => g.status === "live");`)).toBe(false);
    expect(isPillCopy(`<h2>Upcoming</h2>`)).toBe(false);
  });
});

describe("no second copy of the hub status pill", () => {
  it("routes every hub-card phase decision through the single home", () => {
    const copies = FILES.filter((f) => f !== HOME && isPillCopy(read(f)));
    expect(copies).toEqual([]);
  });

  it("keeps the component that renders the rail on the shared import", () => {
    /**
     * The converse, and it is not redundant: the check above passes trivially
     * if nothing renders a pill at all. This names the consumer, so an
     * extraction that moves the usage elsewhere without carrying the import
     * lands here rather than in production.
     *
     * UX-P210 moved that consumer. The rail — heading and cards together — is
     * now `components/hub/HubUpcomingRail.tsx`, because CERT-525's finding was
     * about what SURROUNDS the card and a route file cannot be rendered by a
     * guard. The page keeps the section, so both links are checked: page →
     * rail → pill. Breaking either one is what this catches.
     */
    const rail = read(RAIL);
    expect(rail).toContain("@/components/hub/HubStatusPill");
    expect(rail).toContain("<StatusPill status={card.status} />");

    const page = read(path.join("app", "hub", "[competition]", "page.tsx"));
    expect(page).toContain("@/components/hub/HubUpcomingRail");
    expect(page).toContain("<HubUpcomingRail");
  });
});

/**
 * UX-P210 (CERT-525) — THE RAIL HEADING HAS ONE HOME FOR THE SAME REASON.
 *
 * The pill's collision story applies unchanged to the heading: it is the second
 * place on this surface that states a phase, `program/ux-148` is already
 * rewriting this rail in a different file, and two branches editing disjoint
 * files merge silently with the wrong copy surviving. A rendered guard imports
 * the good one by name and passes while the page renders the other.
 *
 * The phase RULE (`hubUpcomingHeading`) is what must have one home — not the
 * `<h2>`, which is markup. So the scan looks for a source that prints the
 * served `upcoming_label` without routing through the rule.
 */
describe("no second decision about what the rail heading claims", () => {
  /** Reading the served affirmative label — the input to the decision. */
  const READS_SERVED_LABEL = /upcoming_label\b/;
  /** The one function allowed to turn that into a heading. */
  const ROUTES_THROUGH_THE_RULE = /hubUpcomingHeading/;
  /** Handing the label to the rail, which is not a decision — it is the wiring. */
  const DELEGATES_TO_THE_RAIL = /<HubUpcomingRail/;

  /**
   * Deciding, rather than forwarding. The page reads `data.upcoming_label` and
   * must keep doing so — it is where the payload arrives — so a rule of "reads
   * the label" alone would fire on the correct file. The unscoped first draft of
   * this check did exactly that (UX-P205-4 again: a grep for the expression is
   * not a census of the defect). What is banned is holding the label and
   * turning it into a heading yourself.
   */
  function decidesTheHeadingAlone(src: string): boolean {
    if (!READS_SERVED_LABEL.test(src)) return false;
    return !ROUTES_THROUGH_THE_RULE.test(src) && !DELEGATES_TO_THE_RAIL.test(src);
  }

  it("can report a positive — a hand-rolled heading is recognised", () => {
    // PROVE THE SWEEP CAN SEE ITS TARGET (UX-P204) before trusting its silence.
    // This is the shape CERT-525 blocked, as it stood in `page.tsx`.
    expect(
      decidesTheHeadingAlone(`<h2>{data.upcoming_label || "Upcoming"}</h2>`),
    ).toBe(true);
    // And the two legitimate shapes are not confused with it.
    expect(decidesTheHeadingAlone(read(RAIL))).toBe(false);
    expect(
      decidesTheHeadingAlone(`<HubUpcomingRail label={data.upcoming_label} />`),
    ).toBe(false);
  });

  it("has a rail that really does route its heading through the rule", () => {
    /**
     * The other half of the control: the rail's exemption has to be earned, and
     * it is earned by CALLING the rule, not by being named `RAIL`. It never
     * reads `upcoming_label` itself — the page hands it down as a `label` prop —
     * which is why the rogue predicate's first clause already lets it past, and
     * why this second assertion is the one doing the work.
     */
    const rail = read(RAIL);
    expect(READS_SERVED_LABEL.test(rail)).toBe(false);
    expect(ROUTES_THROUGH_THE_RULE.test(rail)).toBe(true);
  });

  it("keeps the page delegating rather than deciding", () => {
    // Names the wiring, so an "improvement" that inlines the heading back into
    // the route file — where no guard can render it — lands here.
    const page = read(path.join("app", "hub", "[competition]", "page.tsx"));
    expect(READS_SERVED_LABEL.test(page)).toBe(true);
    expect(DELEGATES_TO_THE_RAIL.test(page)).toBe(true);
  });

  /**
   * ── THE SECOND CLAUSE, AND ux-148's REAL BYTES ARE WHY IT EXISTS ───────────
   *
   * The clause above keys on the served label, and that is not the only way to
   * make the claim. `git show
   * origin/program/ux-148-us-open-start-date-and-marquee:.../page.tsx` on
   * 2026-08-31 renders the heading as a STRING LITERAL — `<h2 …>Upcoming
   * Cards</h2>` — reading no payload field at all. (Its base predates UX-P167,
   * so it would also print combat vocabulary over the tennis rail; that half is
   * UX-P167's guard to catch, not this one's.) A detector for the label
   * expression is blind to it, which is UX-P205-4 in the other direction: the
   * defect is the CLAIM, and the expression was only one of its spellings.
   *
   * So a hub heading may not contain a phase word as literal text. The rail's
   * own `<h2>` renders `{heading}` — an expression — and every section heading
   * renders `sectionLabel(...)`, so nothing legitimate here spells one out. The
   * pill is not a heading and is untouched by this.
   */
  const HEADING_BLOCK = /<h2\b[^>]*>([\s\S]*?)<\/h2>/g;
  const PHASE_WORD_LITERAL = /\b(upcoming|live|final|settled)\b/i;

  function headingLiteralsClaimingAPhase(src: string): string[] {
    return Array.from(src.matchAll(HEADING_BLOCK))
      .map((m) => m[1])
      // Strip interpolations and comments — only text a reader would see.
      .map((inner) => inner.replace(/\{[\s\S]*?\}/g, " ").replace(/\s+/g, " ").trim())
      .filter((text) => PHASE_WORD_LITERAL.test(text));
  }

  it("can report a positive — ux-148's hard-coded heading is recognised", () => {
    // Verbatim from that branch, kept as a FIXTURE so the bite is proved
    // against the bytes rather than against a description of them.
    const UX148_HEADING = `
            <h2 className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3">
              Upcoming Cards
            </h2>`;
    expect(headingLiteralsClaimingAPhase(UX148_HEADING)).toEqual(["Upcoming Cards"]);
    // And the shapes that are fine stay fine.
    expect(headingLiteralsClaimingAPhase(`<h2>{heading}</h2>`)).toEqual([]);
    expect(headingLiteralsClaimingAPhase(`<h2>{sectionLabel(key)}</h2>`)).toEqual([]);
    expect(headingLiteralsClaimingAPhase(`<h2>Something went wrong</h2>`)).toEqual([]);
  });

  it("spells no phase word into a hub heading", () => {
    const spelled = FILES.flatMap((f) =>
      headingLiteralsClaimingAPhase(read(f)).map((t) => `${f}: ${t}`),
    );
    expect(spelled).toEqual([]);
  });

  it("lets no hub source print the served label on its own authority", () => {
    const rogue = FILES.filter((f) => f !== RAIL && decidesTheHeadingAlone(read(f)));
    /**
     * WHEN THIS GOES RED, the fix is not to add the file to an allowlist. It is
     * to render `<HubUpcomingRail>` instead of hand-rolling a heading, or — if
     * the surface genuinely is not this rail — to call `hubUpcomingHeading` and
     * honour a `null` by printing nothing.
     */
    expect(rogue).toEqual([]);
  });
});
