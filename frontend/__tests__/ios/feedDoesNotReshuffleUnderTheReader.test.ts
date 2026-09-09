/**
 * #4110 — once a card has a position, nothing but the reader moves it.
 *
 * Alex, reading Discover in the app Tue 2026-09-08 3:30–3:42pm PT: *"the feed
 * re-rendered several times during load and a card he was reading disappeared."*
 *
 * `DiscoverViewModel` had three writers that each assigned the WHOLE `items` array
 * through `FeedInterleave.byCategory`: the boot seed from the last-good cache, the
 * fresh network fetch, and the pagination merge. The interleave is deterministic for
 * a given input, but the cached response and the fresh response are DIFFERENT inputs,
 * so they interleave to different orders — the boot paint was not a prefix of the
 * fresh paint. No race is needed to reproduce it; it is what the code did on a normal
 * successful load.
 *
 * ═══ WHY THIS FILE EXISTS AND NOT ONLY THE XCTESTS ═══
 *
 * CI COMPILES NO SWIFT. `DiscoverFeedReconcileTests` proves the four branches and the
 * merge, and runs on a laptop. It structurally CANNOT prove the thing that actually
 * regressed here, which is not a function's behaviour but a CALL SITE: whether the
 * network publish still goes through the decision at all. Deleting the switch and
 * restoring `items = Self.interleave(renderable)` leaves every Swift test in the repo
 * green — the pure functions still pass, nothing reaches them. discover/001 named this
 * trap in the contract before the build started; these assertions are the answer to it.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * The acceptance criterion — "open Discover cold on a phone, on a slow connection, and
 * watch one card" — is a device observation and nothing here can make it. It is carried
 * by the paired screenshots on the PR. What is asserted here is narrower and checkable:
 * no writer re-derives the order behind the reader's back.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const VIEW_MODEL = join(IOS_ROOT, "ViewModels/DiscoverViewModel.swift");
const RECONCILE = join(IOS_ROOT, "Utilities/DiscoverFeedReconcile.swift");
const FEED_MODELS = join(IOS_ROOT, "Models/FeedModels.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass — the unrunnable-check failure
// mode a source scan is most prone to.
const present = [VIEW_MODEL, RECONCILE, FEED_MODELS].every(existsSync);
const d = present ? describe : describe.skip;

d("#4110 — the feed does not reshuffle under the reader", () => {
  const viewModel = () => stripComments(readFileSync(VIEW_MODEL, "utf8"));

  /**
   * Slice one function's body, and PROVE the slice.
   *
   * A scoping regex that silently matches nothing turns every assertion under it
   * into a vacuous pass, which is the exact failure #4134 shipped last night: a
   * guard that exercised a helper nothing called. So each slice is checked for a
   * landmark that only the right function contains.
   */
  function functionBody(declaration: string, endMarker: string): string {
    const source = viewModel();
    const start = source.indexOf(declaration);
    expect([declaration, start > -1]).toEqual([declaration, true]);
    const end = source.indexOf(endMarker, start + declaration.length);
    expect([endMarker, end > start]).toEqual([endMarker, true]);
    return source.slice(start, end);
  }

  describe("the interleave call sites are an exact, accounted-for set", () => {
    it("there are exactly three, and each is the one this ship intends", () => {
      // Discovered, not listed: a FOURTH writer added later is red by default,
      // which is the property that outlives the three sites named in the issue.
      const sites = viewModel()
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l.includes("Self.interleave("));

      expect(sites).toEqual([
        // Boot seed — the FIRST paint. Nothing on screen to protect, so the full
        // interleave is correct here and stays.
        "items = Self.interleave(renderable)",
        // Network publish — now the `.repaint` ARM of the decision, not the
        // unconditional assignment it used to be. Guarded below.
        "items = Self.interleave(renderable)",
        // Pagination — interleaves the NEW PAGE among itself and appends. The
        // painted prefix is not an input, so it cannot move.
        "items = items + Self.interleave(fresh)",
      ]);
    });

    it("THE MUTANT: pagination cannot go back to re-deriving the whole list", () => {
      // `items = Self.interleave(items + fresh)` re-derived the order of every
      // already-painted card on every scroll — the same wholesale-reorder defect
      // as the network path, triggered by the reader instead of by the clock.
      expect(viewModel()).not.toContain("Self.interleave(items + fresh)");
    });
  });

  describe("the network publish goes through the decision", () => {
    const publish = () => functionBody("func load(", "private func scheduleColdStartRecovery");

    it("the slice is the load path and not something else", () => {
      const body = publish();
      expect(body).toContain("loadLastGoodFeed");
      expect(body).toContain("reportSuppressedEnvelopes");
      expect(body.length).toBeGreaterThan(2000);
    });

    it("it asks DiscoverFeedReconcile before it may reorder", () => {
      const body = publish();
      expect(body).toContain("DiscoverFeedReconcile.decision(");
      expect(body).toContain("DiscoverFeedReconcile.merge(");
      expect(body).toMatch(/case \.repaint:/);
      expect(body).toMatch(/case \.reconcile:/);
    });

    it("THE MUTANT: the repaint is not reachable without the decision", () => {
      // Deleting the switch and restoring the unconditional assignment is the
      // whole regression, it is three lines, and it leaves every Swift test green.
      // So: within the load path, every `Self.interleave(renderable)` that is NOT
      // the boot seed must sit under a `case .repaint:`.
      const body = publish();
      const repaintArm = body.indexOf("case .repaint:");
      expect(repaintArm).toBeGreaterThan(-1);
      const afterArm = body.slice(repaintArm, repaintArm + 200);
      expect(afterArm).toContain("items = Self.interleave(renderable)");

      // And the pre-fix shape — verbatim from origin/master `3b9a420a` — is
      // detectable, so this assertion is not merely describing today's text.
      const prefix = body.replace(
        /switch DiscoverFeedReconcile\.decision\([\s\S]*?case \.reconcile:[\s\S]*?\n                }/,
        "items = Self.interleave(renderable)"
      );
      expect(prefix).not.toContain("DiscoverFeedReconcile.decision(");
    });
  });

  describe("the painted edition is recorded wherever the list is painted", () => {
    it("every paint site sets it, and the reset clears it", () => {
      const source = viewModel();
      // A paint that forgets to record its edition makes the NEXT response
      // compare against a stale token — which either reconciles two different
      // lists together or repaints one that never changed.
      expect(source).toContain("paintedEdition = cached.response.edition");
      expect(source).toContain("paintedEdition = response.edition");
      expect(source).toContain("paintedEdition = nil");
    });

    it("the identity rebind clears it, so one account cannot inherit another's ordering", () => {
      const body = functionBody("func rebindForIdentityChange(", "static func isRenderable");
      expect(body).toContain("items = []");
      expect(body).toContain("paintedEdition = nil");
    });
  });

  describe("pagination refuses a page from a different edition", () => {
    const paginate = () => functionBody("func loadMoreIfNeeded(", "private static func pageBoundary");

    it("the slice is the pagination path", () => {
      const body = paginate();
      expect(body).toContain("loadedIds");
      expect(body).toContain("hasMore = response.hasMore");
    });

    it("a page whose token does not match the painted list is not spliced", () => {
      expect(paginate()).toMatch(
        /if let pageEdition = response\.edition, pageEdition != paintedEdition \{\s*fresh = \[\]/
      );
    });
  });

  describe("the token reaches the client at all", () => {
    it("FeedResponse decodes it, tolerantly, and declares its key", () => {
      // `FeedResponse` has BOTH a custom `init(from:)` and an explicit
      // `CodingKeys` — the contract note said it had neither, and a field added
      // to the struct alone would silently decode as nil forever.
      const models = stripComments(readFileSync(FEED_MODELS, "utf8"));
      expect(models).toMatch(/let edition: String\?/);
      expect(models).toMatch(/case edition/);
      expect(models).toMatch(
        /edition = try\? c\.decodeIfPresent\(String\.self, forKey: \.edition\)/
      );
    });

    it("the four branches are declared where they can be read", () => {
      const reconcile = stripComments(readFileSync(RECONCILE, "utf8"));
      expect(reconcile).toMatch(/if paintedCount == 0 \{ return \.repaint \}/);
      expect(reconcile).toMatch(/guard let incomingEdition else \{ return \.reconcile \}/);
      expect(reconcile).toMatch(
        /return paintedEdition == incomingEdition \? \.reconcile : \.repaint/
      );
    });
  });
});
