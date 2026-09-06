/**
 * #3254 — a rate-limited sport/league page may not claim the sport does not exist.
 *
 * 🔴 WHAT A READER SAW. Production, 2026-09-05 ~09:50 PT, D48 LOOK pass:
 * `https://www.bainluck.com/sport/tennis/atp` rendered a near-empty page
 * reading `Sport "tennis" not found` over "Try again · Back to tennis". The
 * same URL served the full ATP page ~2 minutes later with no deploy. Tennis
 * existed the whole time and `GET /api/sports/hierarchy` had always listed it.
 * What happened was `{"detail":"Rate limit exceeded: 60/minute",
 * "retry_after":41}` — one IPv4 momentarily over the 60/min anonymous bucket,
 * which is ordinary traffic behind carrier CGNAT, office Wi-Fi or campus NAT.
 *
 * 🔴 WHY IT MATTERS MORE THAN THE WORDING. A reader told a thing does not
 * exist stops looking for it. A reader told we could not reach it reloads —
 * and reloading was literally all it took. The page also offered "Back to
 * tennis": a link to the sport it had just declared absent.
 *
 * 🔴 THE DEFECT, EXACTLY. The slug-resolution loop caught every throw with a
 * bare `catch {}` and then read `if (!h)` as absence. Gotcha #36 ("never
 * catch-all in an API client returning Optional — 429 must re-raise") and
 * gotcha #53 ("an empty read and a broken read must not render identically"),
 * on a rendered surface. Both `/sport/[sport]` and `/sport/[sport]/[league]`
 * carried it; the reported URL is the league page, but its own "Back to
 * tennis" link lands on the hub page, which printed the same false sentence.
 *
 * 🔴 WHAT THIS FILE CAN AND CANNOT PROVE. jest here runs
 * `testEnvironment: 'node'` with no jsdom, so no test in this repo can run the
 * page's `useEffect` and drive a real 429 through it. So the two halves of the
 * defect were extracted into production modules and are tested AS PRODUCTION
 * CODE — `lib/hierarchyLoadFailure.ts` decides, `components/
 * PageLoadFailureScreen.tsx` renders — rather than re-typed into a fixture
 * here, which would let the guard and the page drift apart. The bounded
 * source-region arms then prove the pages actually call them.
 *
 * Every arm below was run red against the pre-fix pages.
 */
import { renderToStaticMarkup } from "react-dom/server";
import * as fs from "fs";
import * as path from "path";
import PageLoadFailureScreen from "@/components/PageLoadFailureScreen";
import {
  classifySportResolutionFailure,
  isUnreachable,
} from "@/lib/hierarchyLoadFailure";

const read = (p: string) =>
  fs.readFileSync(path.join(process.cwd(), p), "utf8");

const LEAGUE_PAGE = read("app/sport/[sport]/[league]/page.tsx");
const HUB_PAGE = read("app/sport/[sport]/page.tsx");

/**
 * A file with its comments removed.
 *
 * Needed because the change that removed the false sentence QUOTES it in the
 * comment explaining why, so a naive substring check on the raw file fails on
 * the very documentation of the fix — and the obvious way to make it pass is
 * to delete the explanation. Strip block comments first, then line comments,
 * so a `//` inside a stripped block cannot leave a fragment.
 */
const stripComments = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

const LEAGUE_CODE = stripComments(LEAGUE_PAGE);
const HUB_CODE = stripComments(HUB_PAGE);

/**
 * A file flattened to one line, with `//` markers dropped.
 *
 * A source scan for a sentence is defeated by a LINE BREAK, and a comment
 * quoting a sentence is exactly where the wrapping falls: the league page's
 * explanation wraps as `Sport "tennis" not` / `// found`, so a raw substring
 * check reports the quote missing and the non-vacuity arm fails on a file that
 * plainly contains it.
 */
const flatten = (src: string) => src.replace(/\/\//g, " ").replace(/\s+/g, " ");

/** The `ApiError` shape `apiFetch` throws for a throttled read. */
const throttle = { status: 429, message: "Rate limit exceeded: 60/minute" };
/** A genuine "this slug is not a sport" answer. */
const absent = { status: 404, message: "Sport not found" };

describe("which candidate-slug failures mean the sport is absent", () => {
  it("treats a 404 as the alias mechanism working, not as a failure to ask", () => {
    // `/sport/icehockey/nhl` tries `icehockey` (404) before `hockey` (200), so
    // a 404 is expected traffic on the happy path and must stay silent.
    expect(isUnreachable(absent)).toBe(false);
  });

  it("treats a throttle, a server error and an offline device as unreachable", () => {
    expect(isUnreachable(throttle)).toBe(true);
    expect(isUnreachable({ status: 500, message: "boom" })).toBe(true);
    // No status at all is how `apiFetch` throws a timeout/abort/DNS failure.
    expect(isUnreachable(new Error("Network request failed"))).toBe(true);
    expect(isUnreachable(undefined)).toBe(true);
  });
});

describe("the failure a page names when the hierarchy would not resolve", () => {
  it("names the throttle, and never says the sport is missing", () => {
    const f = classifySportResolutionFailure(throttle, "tennis");

    expect(f.title).toBe("Too many requests");
    // The server's own line is the evidence under the heading; the heading is
    // the reader's answer. Publishing the message alone would print a bare
    // "Rate limit exceeded: 60/minute" with nothing naming it.
    expect(f.message).toBe("Rate limit exceeded: 60/minute");
    // The sentence the issue was filed on, in the state it was filed in.
    expect(f.title).not.toContain("not found");
    expect(f.message).not.toContain("not found");
    expect(f.sportAbsent).toBe(false);
    expect(f.status).toBe(429);
  });

  it("still offers a retry for a throttle, because it clears on its own", () => {
    expect(classifySportResolutionFailure(throttle, "tennis").retryable).toBe(true);
  });

  it("does say not-found when every candidate really did 404", () => {
    // The fix must not overshoot into never claiming absence — a wrong slug is
    // a real state and the page has to be able to say so.
    const f = classifySportResolutionFailure(null, "quidditch");

    expect(f.title).toBe('Sport "quidditch" not found');
    expect(f.sportAbsent).toBe(true);
    // A 404 answers a reload with the same 404; the button cannot help.
    expect(f.retryable).toBe(false);
  });

  it("one unreachable candidate outranks a later clean 404", () => {
    // The asymmetry that makes this more than a status check. Run the real
    // predicate over the real loop shape: if `icehockey` is throttled and the
    // aliased `hockey` then 404s, we still never got a verdict on the sport,
    // so the page may not claim absence.
    let unreachable: unknown = null;
    for (const outcome of [throttle, absent]) {
      if (isUnreachable(outcome)) unreachable = outcome;
    }

    const f = classifySportResolutionFailure(
      unreachable as typeof throttle,
      "hockey",
    );
    expect(f.sportAbsent).toBe(false);
    expect(f.title).toBe("Too many requests");
  });
});

describe("what the reader actually sees", () => {
  it("shows the throttle, a retry, and keeps the sport as an escape", () => {
    const f = classifySportResolutionFailure(throttle, "tennis");
    const html = renderToStaticMarkup(
      <PageLoadFailureScreen
        failure={f}
        status={f.status}
        escape={{ href: "/sport/tennis", label: "Back to Tennis" }}
      />,
    );

    expect(html).toContain("Too many requests");
    expect(html).toContain("Rate limit exceeded: 60/minute");
    expect(html).toContain("Try again");
    expect(html).toContain("Back to Tennis");
    // The whole point: the screen the reader got must no longer say this.
    expect(html).not.toContain("not found");
  });

  it("withholds the retry and the sport link once absence IS established", () => {
    const f = classifySportResolutionFailure(null, "quidditch");
    const html = renderToStaticMarkup(
      <PageLoadFailureScreen
        failure={f}
        status={f.status}
        escape={{ href: "/sports", label: "Browse all sports" }}
      />,
    );

    // `&quot;` because this is rendered markup, not the raw string — asserting
    // the unescaped form here passes only if the page stops rendering it.
    expect(html).toContain("Sport &quot;quidditch&quot; not found");
    // Both halves of the issue's second complaint: no button that cannot help,
    // and no offer to navigate to the sport we just said is not there.
    expect(html).not.toContain("Try again");
    expect(html).not.toContain("Back to");
    expect(html).toContain("Browse all sports");
  });

  it("draws the escape as the primary action when there is no retry beside it", () => {
    // Caught by the LOOK pass, not by a unit test: with the retry correctly
    // withheld on a real 404, the muted "Browse all sports" was the ONLY thing
    // a reader could do and it was drawn in the same grey as inert text.
    const html = (retryable: boolean) =>
      renderToStaticMarkup(
        <PageLoadFailureScreen
          failure={{ title: "t", message: "m", retryable }}
          escape={{ href: "/sports", label: "Browse all sports" }}
        />,
      );

    // Alone: accented, like the "Try again" it replaced.
    expect(html(false)).toContain("text-accent-brand");
    // Beside a retry: stays secondary, so the two do not compete.
    const beside = html(true);
    expect(beside).toContain("Try again");
    expect(beside).toContain("text-text-muted");
  });

  it("publishes the status as an attribute, never as copy", () => {
    // #3297's lesson: a screenshot of this screen looks identical whether the
    // cause is our own throttling or a real regression, so every lane running
    // a LOOK pass can file a bug that does not exist.
    const f = classifySportResolutionFailure(throttle, "tennis");
    const html = renderToStaticMarkup(
      <PageLoadFailureScreen
        failure={f}
        status={f.status}
        escape={{ href: "/sport/tennis", label: "Back to Tennis" }}
      />,
    );

    expect(html).toContain('data-error-status="429"');
    // As an attribute means NOT in the prose the reader reads.
    expect(html).not.toContain(">429<");
  });
});

describe("the pages actually route through it", () => {
  /**
   * The league page's slug-resolution loop, bounded.
   *
   * Bounded rather than whole-file because this page legitimately contains
   * other `catch` blocks — the golf and grid fetches are supplementary and
   * swallow their own failures on purpose. A blanket ban would be false.
   */
  const loop = LEAGUE_CODE.slice(
    LEAGUE_CODE.indexOf("for (const candidate of hierarchySlugCandidates"),
    LEAGUE_CODE.indexOf("if (cancelled) return;", LEAGUE_CODE.indexOf("for (const candidate")),
  );

  it("bounds the region it is asserting on — the slice is the loop", () => {
    // A region-bounded scan that silently sliced to "" would pass every arm
    // below. Pin that the slice is real and is the code it claims to be.
    expect(loop.length).toBeGreaterThan(80);
    expect(loop).toContain("fetchSportHierarchyDetail(candidate)");
  });

  it("classifies the caught error instead of discarding it", () => {
    expect(loop).toContain("isUnreachable(err)");
    // The bare parameterless catch IS the defect.
    expect(loop).not.toContain("catch {");
  });

  it("neither page still builds the false sentence in code", () => {
    for (const code of [LEAGUE_CODE, HUB_CODE]) {
      expect(code).not.toContain('${sportSlug}" not found');
    }
    expect(LEAGUE_CODE).toContain("classifySportResolutionFailure");
    expect(HUB_CODE).toContain("describeLoadFailure");
  });

  it("that source check is not vacuous — the sentence IS still in both files", () => {
    // A stripped-source assertion can pass because the strip ate everything.
    // Each page's comment quotes the old sentence, so the raw file must still
    // contain it while the code must not: that pair proves the strip removed
    // comments and not the page.
    for (const [raw, code] of [
      [LEAGUE_PAGE, LEAGUE_CODE],
      [HUB_PAGE, HUB_CODE],
    ]) {
      expect(flatten(raw)).toContain('Sport "tennis" not found');
      expect(code.length).toBeGreaterThan(raw.length * 0.5);
    }
  });
});
