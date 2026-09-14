// #5914 — the embed predicate, at its edges.
//
// `isEmbeddedAbout` decides whether the site's chrome is drawn. Getting it
// wrong in one direction leaves the native About screen wearing a website
// header, a bottom tab bar that fights the native one, and a consent banner for
// tracking the app never asked for. Getting it wrong in the OTHER direction
// blanks the chrome on a real page of the website, which is worse, because it
// happens to everybody.
//
// It is a pure function of two strings precisely so both directions can be
// enumerated here without mounting React.

import { EMBED_PARAM, EMBED_PATH, EMBED_VALUE, isEmbeddedAbout } from "@/lib/embed";

describe("the embed contract's constants are the ones native built against", () => {
  // native/168 holds the other half as a literal URL. If either side edits its
  // string alone the contract silently becomes "no embed, ever" — the chrome
  // comes back and nothing goes red. `git grep embed=1` finds both halves.
  test("the parameter, value and path are exactly ?embed=1 on /about", () => {
    expect(EMBED_PARAM).toBe("embed");
    expect(EMBED_VALUE).toBe("1");
    expect(EMBED_PATH).toBe("/about");
    expect(`${EMBED_PATH}?${EMBED_PARAM}=${EMBED_VALUE}`).toBe("/about?embed=1");
  });
});

describe("isEmbeddedAbout", () => {
  test("the contract URL is an embed", () => {
    expect(isEmbeddedAbout("/about", "1")).toBe(true);
  });

  // THE PATH IS PART OF THE PREDICATE. If the flag were honoured site-wide, one
  // tap out of About would leave a chromeless Discover under a native title bar
  // still reading "About". A stray ?embed=1 anywhere else must be inert.
  test.each([
    ["the home page", "/"],
    ["discover", "/discover"],
    ["calibration", "/calibration"],
    ["privacy", "/privacy"],
    ["a nested route", "/sport/football/nfl"],
    ["a path merely containing /about", "/company/about"],
    ["a child of /about", "/about/team"],
    ["a trailing slash", "/about/"],
    ["different case", "/About"],
  ])("?embed=1 is INERT on %s", (_name, pathname) => {
    expect(isEmbeddedAbout(pathname, "1")).toBe(false);
  });

  // Only the agreed value counts. A truthy-looking one is not the contract.
  test.each([
    ["absent", null],
    ["undefined", undefined],
    ["empty", ""],
    ["zero", "0"],
    ["true", "true"],
    ["yes", "yes"],
    ["a whitespace-padded 1", " 1"],
    ["1 with a suffix", "1x"],
  ])("/about with embed=%s is not an embed", (_name, value) => {
    expect(isEmbeddedAbout("/about", value)).toBe(false);
  });

  // Both React sources are nullable and a client component can render before
  // either resolves. "Not yet known" must read as NOT an embed, or the site's
  // chrome blanks for a frame on every page load.
  test.each([
    ["both null", null, null],
    ["pathname null", null, "1"],
    ["pathname undefined", undefined, "1"],
  ])("%s is not an embed", (_name, pathname, value) => {
    expect(isEmbeddedAbout(pathname, value)).toBe(false);
  });

  test("it is a pure predicate — same inputs, same answer, no state", () => {
    for (let i = 0; i < 3; i++) {
      expect(isEmbeddedAbout("/about", "1")).toBe(true);
      expect(isEmbeddedAbout("/", "1")).toBe(false);
    }
  });
});
