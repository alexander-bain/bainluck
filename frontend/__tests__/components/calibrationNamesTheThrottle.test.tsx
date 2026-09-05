/**
 * CAL-P1023 (#3297) — the calibration page may not call our throttling
 * "Failed to load calibration data".
 *
 * Production, 2026-09-05: `tools/look.sh https://bainluck.com/calibration`
 * rendered that one sentence and nothing else. The curve was fine — the same
 * endpoint answered 200 twelve times in a row one rate-limit window later. What
 * had happened was a 429: this network was momentarily over the 60/min
 * anonymous bucket, which is not an exotic state (carrier CGNAT, office Wi-Fi
 * and university NAT all put many readers behind one IPv4 and one bucket).
 *
 * The sentence is the defect. A reader told the calibration data failed
 * concludes the page is broken and leaves; a reader told we were throttled
 * waits ten seconds. `lib/loadFailure.ts` already draws that distinction
 * correctly for the event page (#2783), so this is a reuse, not a new
 * vocabulary (ruling 025 clause 2).
 *
 * Rendered rather than source-scanned wherever a render can prove it: the
 * question here is what a reader SEES, and a substring in a file is not that.
 */
import { renderToStaticMarkup } from "react-dom/server";
import * as fs from "fs";
import * as path from "path";
import ErrorState from "@/components/ErrorState";
import { describeLoadFailure } from "@/lib/loadFailure";

const PAGE = fs.readFileSync(
  path.join(process.cwd(), "app/calibration/page.tsx"),
  "utf8",
);

/**
 * The page with its comments removed.
 *
 * Needed because the change that removed the false sentence from the RENDER
 * quotes it in the comment explaining why — so a naive substring check on the
 * raw file fails on the very documentation of the fix, and the obvious way to
 * make it pass is to delete the explanation. Strip block comments first, then
 * line comments, so a `//` inside a stripped block cannot leave a fragment.
 */
const PAGE_CODE = PAGE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

/** The `ApiError` shape `apiFetch` throws for a throttled read. */
const throttle = { status: 429, message: "Rate limit exceeded: 60/minute" };

describe("the failure the calibration page names", () => {
  it("renders WHICH failure it was, above the server's own sentence", () => {
    const failure = describeLoadFailure(throttle, "calibration data");
    const html = renderToStaticMarkup(
      <ErrorState title={failure.title} message={failure.message} onRetry={() => {}} />,
    );

    // The heading is the reader's answer; the server's line is the evidence
    // under it. Rendering the message alone would publish a bare
    // "Rate limit exceeded: 60/minute" with nothing naming it — which is why
    // `loadFailure.ts` says the title is "only ever a heading over it".
    expect(html).toContain("Too many requests");
    expect(html).toContain("Rate limit exceeded: 60/minute");
    // And it must not say the thing that is false.
    expect(html).not.toContain("Failed to load calibration data");
  });

  it("still offers a retry, because a throttle clears on its own", () => {
    expect(describeLoadFailure(throttle, "calibration data").retryable).toBe(true);
  });

  it("renders exactly as before when no title is given — every other caller", () => {
    // The prop is additive. An existing call site that passes only a message
    // must produce the same markup it produced before this change, or this
    // touched far more of the site than it claims to.
    const before = renderToStaticMarkup(<ErrorState message="Something broke" />);
    expect(before).not.toContain("<p class=\"text-text-primary");
    expect(before).toContain("Something broke");
  });

  it("the page no longer hard-codes the sentence that was false", () => {
    // The one thing a render of a component cannot prove: that the PAGE stopped
    // printing it. A short, exact literal is the robust form of a source check.
    expect(PAGE_CODE).not.toContain("Failed to load calibration data");
    expect(PAGE_CODE).toContain("describeLoadFailure");
  });

  it("that source check is not vacuous — the sentence IS still findable in the file", () => {
    // A stripped-source assertion can pass because the strip ate everything.
    // The comment explaining the fix quotes the old sentence, so the raw file
    // must still contain it while the code must not: that pair proves the strip
    // removed comments and not the page.
    expect(PAGE).toContain("Failed to load calibration data");
    expect(PAGE_CODE.length).toBeGreaterThan(PAGE.length * 0.5);
  });

  it("the page publishes the status as evidence, so a LOOK pass can tell ours from theirs", () => {
    // #3297's other half: a screenshot of this failure looks identical whether
    // the cause is our own throttling or a real regression, so every lane
    // following the LOOK RULE can file a bug that does not exist. The status is
    // an attribute, never copy.
    expect(PAGE).toContain("data-error-status=");
    expect(PAGE).toContain("errorStatus={(error as ApiError).status}");
  });
});
