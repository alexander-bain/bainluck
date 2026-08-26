/**
 * INT-131 guard: the US Open props section stays OFF until its fix certs.
 *
 * CERT-411 BLOCK is scoped to `TournamentProps` — a fresh leader beside a stale
 * runner renders `data-live=true` against a server `data-price-state=dark`. The
 * boards shipped; the props section did not. This guard is what stops it
 * shipping by accident.
 *
 * Two assertions, deliberately, because either alone is weak:
 *
 *  1. The flag's SEMANTICS — unset/empty/garbage must all be OFF. A flag that
 *     fails open is not a flag.
 *  2. The flag's CALL SITE — the page must not render `<TournamentProps>`
 *     unconditionally. A value-only test stays green the day someone deletes
 *     the conditional and leaves the constant behind, which is exactly the
 *     failure this guard exists to catch.
 */
import fs from "fs";
import path from "path";

const PAGE = path.join(
  __dirname,
  "..",
  "..",
  "app",
  "tournaments",
  "[slug]",
  "page.tsx",
);

describe("tournament props feature flag (INT-131 / CERT-411)", () => {
  const original = process.env.NEXT_PUBLIC_TOURNAMENT_PROPS;

  afterEach(() => {
    if (original === undefined) delete process.env.NEXT_PUBLIC_TOURNAMENT_PROPS;
    else process.env.NEXT_PUBLIC_TOURNAMENT_PROPS = original;
    jest.resetModules();
  });

  function load() {
    let value = false;
    jest.isolateModules(() => {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      value = require("@/lib/tournamentFlags").TOURNAMENT_PROPS_ENABLED;
    });
    return value;
  }

  it.each([
    ["unset", undefined],
    ["empty", ""],
    ["0", "0"],
    ["false", "false"],
    ["true", "true"],
    ["yes", "yes"],
  ])("is OFF when the env var is %s", (_label, raw) => {
    if (raw === undefined) delete process.env.NEXT_PUBLIC_TOURNAMENT_PROPS;
    else process.env.NEXT_PUBLIC_TOURNAMENT_PROPS = raw;
    expect(load()).toBe(false);
  });

  it("is ON only for the exact string \"1\"", () => {
    process.env.NEXT_PUBLIC_TOURNAMENT_PROPS = "1";
    expect(load()).toBe(true);
  });

  it("the page never renders <TournamentProps> outside the flag", () => {
    const src = fs.readFileSync(PAGE, "utf8");

    // It is imported and it is used — if the whole section were deleted this
    // guard would be vacuous, so assert the section still exists.
    expect(src).toContain("TournamentProps");
    expect(src).toContain("TOURNAMENT_PROPS_ENABLED");

    // Every JSX render of the component must sit behind the flag.
    const renders = src.match(/<TournamentProps\b/g) ?? [];
    expect(renders.length).toBeGreaterThan(0);

    const guarded =
      src.match(/TOURNAMENT_PROPS_ENABLED\s*&&\s*\(\s*<TournamentProps\b/g) ??
      [];
    expect(guarded.length).toBe(renders.length);
  });
});
