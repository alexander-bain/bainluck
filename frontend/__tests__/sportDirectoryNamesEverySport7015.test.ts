// #7015 — the `/sport` directory presents every sport the authority serves.
//
// The defect: `SPORT_META` / `SPORT_COLORS` were hand-typed with eight keys
// inside `app/sport/page.tsx` while `GET /api/sports/hierarchy` served eleven.
// Boxing, Motorsports and Esports fell through a silent `||` fallback and
// rendered as placeholders — 🏆 three times on one screen, grey cards, and
// "1 leagues" on Boxing.
//
// The load-bearing test here is `readAuthoritySportSlugs`. Asserting the three
// missing slugs by name would go green forever and catch nothing the next time
// a sport is added; reading the authority means a TWELFTH sport added to
// `backend/app/utils/sport_keys.py` turns this suite red instead of shipping a
// trophy. That is the acceptance criterion #7015 actually asked for.

import { readFileSync } from "fs";
import { join } from "path";

import {
  FALLBACK_SPORT_ICON,
  FALLBACK_SPORT_TINT,
  directorySportSlugs,
  leagueCountLabel,
  resolveSportCard,
} from "@/lib/sportDirectory";

const AUTHORITY_PATH = join(
  __dirname,
  "..",
  "..",
  "backend",
  "app",
  "utils",
  "sport_keys.py",
);

/**
 * The top-level slugs of `SPORT_HIERARCHY` — the dict `GET /api/sports/hierarchy`
 * serves verbatim (`routes/sports.py` reads it through `get_all_sport_slugs`).
 *
 * Every failure mode here THROWS rather than returning a short list. A parse
 * that silently returns `[]` would make every assertion below vacuously green,
 * which is the exact shape of bug this file exists to catch.
 */
function readAuthoritySportSlugs(): string[] {
  const src = readFileSync(AUTHORITY_PATH, "utf8");

  const marker = "SPORT_HIERARCHY: dict[str, dict] = {";
  const start = src.indexOf(marker);
  if (start === -1) {
    throw new Error(
      `Could not find "${marker}" in ${AUTHORITY_PATH}. The authority moved or ` +
        `was renamed — fix this reader, do not delete the assertion.`,
    );
  }

  // The literal ends at the first column-0 `}`. Everything inside it is
  // indented, so this cannot close early on a nested dict.
  const body = src.slice(start + marker.length);
  const end = body.search(/^\}/m);
  if (end === -1) {
    throw new Error(
      `SPORT_HIERARCHY in ${AUTHORITY_PATH} has no closing brace at column 0.`,
    );
  }

  // Top-level keys are exactly four spaces deep: `    "golf": {`.
  const slugs = [
    ...body.slice(0, end).matchAll(/^ {4}"([a-z_]+)": \{$/gm),
  ].map((match) => match[1]);

  if (slugs.length === 0) {
    throw new Error(
      `Parsed zero sports out of SPORT_HIERARCHY. The dict's formatting ` +
        `changed — fix this reader rather than letting the suite go green.`,
    );
  }
  return slugs;
}

describe("#7015 the /sport directory presents every sport the authority serves", () => {
  const authoritySlugs = readAuthoritySportSlugs();

  it("reads a plausible sport list out of the authority (anti-vacuity)", () => {
    // Eleven at the time of writing. The floor is what makes every `for` loop
    // below meaningful: a reader that degraded to one or two slugs would pass
    // them all and prove nothing.
    expect(authoritySlugs.length).toBeGreaterThanOrEqual(11);
    expect(new Set(authoritySlugs).size).toBe(authoritySlugs.length);
    // Spot-anchors on both ends of the literal, so a parse that captured only
    // the head or only the tail is caught.
    expect(authoritySlugs).toContain("golf");
    expect(authoritySlugs).toContain("esports");
  });

  it("gives every authority sport a real icon — none falls through to 🏆", () => {
    const trophied = authoritySlugs.filter(
      (slug) => resolveSportCard(slug, 1).icon === FALLBACK_SPORT_ICON,
    );
    expect(trophied).toEqual([]);
  });

  it("gives every authority sport a real tint — none falls through to grey", () => {
    const grey = authoritySlugs.filter(
      (slug) => resolveSportCard(slug, 1).tintClass === FALLBACK_SPORT_TINT,
    );
    expect(grey).toEqual([]);
  });

  it("marks no authority sport as a fallback", () => {
    const fallen = authoritySlugs.filter(
      (slug) => resolveSportCard(slug, 1).isFallback,
    );
    expect(fallen).toEqual([]);
  });

  it("covers the authority exactly — no sport unregistered, no register entry invented", () => {
    // Both directions. A missing key is the defect; a stale key is the register
    // describing a sport the site no longer has.
    expect([...directorySportSlugs()].sort()).toEqual([...authoritySlugs].sort());
  });
});

describe("#7015 the directory tells its sports apart", () => {
  it("never shows one icon on two sports", () => {
    const icons = directorySportSlugs().map(
      (slug) => resolveSportCard(slug, 1).icon,
    );
    const duplicated = icons.filter(
      (icon, i) => icons.indexOf(icon) !== i,
    );
    expect(duplicated).toEqual([]);
  });

  it("does not stack two boxing gloves — MMA and Boxing are adjacent at 390px", () => {
    // The pre-fix page rendered MMA 🥊 directly above Boxing 🏆. Handing Boxing
    // the glove without moving MMA would have traded three trophies for two
    // identical gloves on touching cards — the same defect, quieter.
    const mma = resolveSportCard("mma", 1).icon;
    const boxing = resolveSportCard("boxing", 1).icon;
    expect(boxing).toBe("🥊");
    expect(mma).not.toBe(boxing);
  });

  it("never shows one tint on two sports", () => {
    const tints = directorySportSlugs().map(
      (slug) => resolveSportCard(slug, 1).tintClass,
    );
    expect(new Set(tints).size).toBe(tints.length);
  });
});

describe("#7015 the subtitle", () => {
  it("pluralizes — the Boxing card said \"1 leagues\"", () => {
    expect(leagueCountLabel(1)).toBe("1 league");
    expect(leagueCountLabel(0)).toBe("0 leagues");
    expect(leagueCountLabel(2)).toBe("2 leagues");
    expect(leagueCountLabel(11)).toBe("11 leagues");
  });

  it("never renders a bare league count for a sport the register knows", () => {
    // The placeholder tell was a subtitle that only restated the chips below
    // it. A known sport gets a sentence; only an unknown one gets a count.
    for (const slug of directorySportSlugs()) {
      const subtitle = resolveSportCard(slug, 3).subtitle;
      expect(subtitle).not.toBe(leagueCountLabel(3));
      expect(subtitle.length).toBeGreaterThan(0);
    }
  });

  it("names the three sports that were placeholders", () => {
    expect(resolveSportCard("boxing", 1).subtitle).toBe(
      "Title fights & marquee bouts",
    );
    expect(resolveSportCard("motorsports", 2).subtitle).toBe("Formula 1, NASCAR");
    expect(resolveSportCard("esports", 3).subtitle).toBe(
      "League of Legends, Counter-Strike 2, Valorant",
    );
  });
});

describe("#7015 the fallback still exists and still fails open", () => {
  // Deleting the fallback would be a worse bug than the one being fixed: an
  // unknown sport must still render a usable card. The register's job is that
  // no sport the authority serves ever REACHES it.
  it("gives an unknown sport a card rather than a blank or a crash", () => {
    const card = resolveSportCard("kabaddi", 4);
    expect(card.isFallback).toBe(true);
    expect(card.icon).toBe(FALLBACK_SPORT_ICON);
    expect(card.tintClass).toBe(FALLBACK_SPORT_TINT);
    expect(card.subtitle).toBe("4 leagues");
  });

  it("pluralizes the fallback subtitle too", () => {
    expect(resolveSportCard("kabaddi", 1).subtitle).toBe("1 league");
  });
});
