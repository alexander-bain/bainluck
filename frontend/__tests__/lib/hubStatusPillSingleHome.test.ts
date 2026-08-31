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

  it("keeps the page that renders the rail on the shared import", () => {
    /**
     * The converse, and it is not redundant: the check above passes trivially
     * if the page stops rendering a pill at all. This names the consumer, so
     * an extraction that moves the usage elsewhere without carrying the import
     * lands here rather than in production.
     */
    const page = read(path.join("app", "hub", "[competition]", "page.tsx"));
    expect(page).toContain("@/components/hub/HubStatusPill");
    expect(page).toContain("<StatusPill status={card.status} />");
  });
});
