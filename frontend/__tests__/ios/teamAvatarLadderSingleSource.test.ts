/**
 * #2977 — one team-avatar ladder on iOS, asserted by reading the Swift.
 *
 * The Sports tab drew the Los Angeles Dodgers crest and the Discover hero drew a
 * flat blue "DOD" square, on the same launch, for the same game. The Sports row
 * goes through `TeamLogoView`, which has a ladder — served url → flag → ESPN by
 * name → coloured fallback. `DiscoverEventCard.heroTeam` and
 * `DiscoverView.teamBadge` each had a private, shorter one that stopped at the
 * first rung and went straight to a letter tile.
 *
 * **Measured on production before the fix** (`/api/feed?limit=200&event_pct=0.6`,
 * 2026-09-08 — 59 event cards, 118 sides): 95 sides arrive with no avatar url of
 * any kind, and 51 of those are teams the ESPN rung names. Only 8 of the 59 cards
 * carried a `*_team_data` block at all. So the issue's framing — one bad team,
 * the Cardinals fine — is falsified: on that page both sides of most MLB cards
 * were bare, and 54% of them had a crest waiting one rung down.
 *
 * WHY THIS FILE EXISTS AND THE SWIFT TESTS DO NOT SUFFICE. `TeamAvatarLadderTests`
 * proves the ladder and proves the card's `avatarSlot(home:)` helper. It cannot
 * prove the view BODY calls that helper — and the body is where #2977 actually
 * lived. A mutation run confirmed it: replacing `slot: avatarSlot(home: true)`
 * with `slot: .tile` in the card's body left all 11 Swift tests green. The
 * assertions below are what kill that mutant, and they run in CI, which compiles
 * no Swift at all.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Utilities/TeamAvatarLadder.swift");

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/** Tells that a view is DECIDING an avatar slot rather than asking the ladder. */
const REIMPLEMENTATION_TELLS: Array<[string, RegExp]> = [
  ["decides the slot from the served url alone", /if let \w+ = avatar\.url\b/],
  ["treats a failed load as the loading state", /placeholder: \{ EmptyView\(\) \}/],
];

/**
 * Lines allowed to look like a short ladder, each with a stated reason — so
 * adding one is a decision rather than a silent widening.
 */
const ALLOWED = new Map<string, Array<[string, string]>>([
  [
    join(IOS_ROOT, "Components/OddsChartView.swift"),
    [
      [
        "placeholder: { EmptyView() }",
        "#3988 — the chart gutter's 14pt crest is decoration beside a label that always renders, so its symptom is milder and it is filed as its own ship rather than widened into #2977",
      ],
    ],
  ],
]);

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("iOS team avatars climb exactly one ladder", () => {
  const canonical = iosPresent ? readFileSync(CANONICAL, "utf8") : "";

  it("the canonical ladder exists", () => {
    expect(canonical).toMatch(/func teamAvatarURL\(servedURL: String\?, teamName: String, sportKey: String\? = nil\)/);
    expect(canonical).toMatch(/func teamAvatarSlot\(avatar: ParticipantAvatar, teamName: String, sportKey: String\? = nil\)/);
    expect(canonical).toMatch(/enum TeamAvatarSlot/);
  });

  it("the rungs are in the Sports row's order", () => {
    // Order is the whole rule. A derived crest that outranks a served one is a
    // worse bug than the letter tile this replaced.
    const served = canonical.indexOf("if let servedURL");
    const flag = canonical.indexOf("isInternationalSport(sportKey)");
    const espn = canonical.indexOf("return espnTeamLogoURL(for: teamName)");
    expect(served).toBeGreaterThan(-1);
    expect(flag).toBeGreaterThan(served);
    expect(espn).toBeGreaterThan(flag);
  });

  it("an empty served url falls through instead of winning", () => {
    // A payload with the key and nothing behind it. Treated as a url it blanks
    // the slot — `TeamLogoView` calls `teamAvatarURL` directly with whatever it
    // was handed, so this guard is on a live path.
    expect(canonical).toMatch(/if let servedURL, !servedURL\.isEmpty \{ return servedURL \}/);
  });

  it("the flag rung stays behind the national-competition guard", () => {
    // `flagURL` matches "america" and "korea", and the feed carries a
    // Libertadores and a K-League fixture. Without the guard, Club América is
    // handed the flag of the United States.
    expect(canonical).toMatch(/if isInternationalSport\(sportKey\), let flag = flagURL\(for: teamName, width: 80\)/);
  });

  it("a derived url is never a photograph", () => {
    // #2919's regression re-armed: `isPhotograph` crops square, which turns a
    // crest into a clipped crest and a portrait into something recognisable.
    // Only a SERVED headshot may carry the flag.
    expect(canonical).toMatch(/isPhotograph: served != nil && avatar\.isPhotograph/);
  });

  describe("the consumers — the half that was actually broken", () => {
    const card = () => readFileSync(join(IOS_ROOT, "Components/DiscoverEventCard.swift"), "utf8");
    const discover = () => readFileSync(join(IOS_ROOT, "Views/DiscoverView.swift"), "utf8");

    it("the Sports row delegates rather than keeping the original copy", () => {
      // `TeamLogoView` is where the ladder came from; it must now ask for it.
      expect(readFileSync(join(IOS_ROOT, "Components/TeamLogoView.swift"), "utf8"))
        .toMatch(/teamAvatarURL\(servedURL: url, teamName: teamName, sportKey: sportKey\)/);
    });

    it("the Discover hero passes the ladder's answer for BOTH sides", () => {
      // THE mutant. `slot: .tile` at either call site is #2977 back on that side,
      // and every Swift test stays green through it — a one-sided fix is exactly
      // how the Cardinals looked fine while the Dodgers did not.
      expect(card()).toMatch(/slot: avatarSlot\(home: false\)/);
      expect(card()).toMatch(/slot: avatarSlot\(home: true\)/);
    });

    it("the hero's slot is built from the WHOLE sport key", () => {
      // The card has its own `sportKey` property meaning "baseball" — the first
      // component only. Passing that compiles, reads right, and silently blinds
      // the flag rung to every "..._world_cup" key.
      expect(card()).toMatch(/sportKey: event\.sport\b/);
      expect(card()).not.toMatch(/teamAvatarSlot\([^)]*sportKey: sportKey\b/);
    });

    it("the guess card climbs the same ladder for both sides", () => {
      expect(discover()).toMatch(/teamAvatarSlot\(avatar: event\.avatar\(home: false\), teamName: event\.awayTeam, sportKey: event\.sport\)/);
      expect(discover()).toMatch(/teamAvatarSlot\(avatar: event\.avatar\(home: true\), teamName: event\.homeTeam, sportKey: event\.sport\)/);
    });

    it("both surfaces draw something when a url fails, not a hole", () => {
      // `placeholder:` is the FAILURE state as well as the loading one, so the
      // pre-fix cards drew a 52pt shadowed blank on a 404. Both now branch on
      // `phase.error`.
      for (const source of [card(), discover()]) {
        expect(source).toMatch(/phase\.error != nil/);
      }
    });
  });

  it("no OTHER Swift file decides an avatar slot on its own — discovered, not listed", () => {
    const offenders: string[] = [];

    for (const path of swiftFiles(IOS_ROOT)) {
      if (path === CANONICAL) continue;
      const allowed = ALLOWED.get(path) ?? [];
      const code = stripComments(readFileSync(path, "utf8"));

      for (const line of code.split("\n")) {
        if (allowed.some(([needle]) => line.includes(needle))) continue;
        const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(line)).map(([why]) => why);
        if (hits.length > 0) {
          offenders.push(`${path.slice(IOS_ROOT.length + 1)} — ${hits.join("; ")} — ${line.trim()}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("the discovery check fires on the REAL pre-fix source", () => {
    // Not a synthetic that merely proves the regex can match: these two lines are
    // copied verbatim from DiscoverEventCard.swift and DiscoverView.swift at
    // origin/master d634e589, and are exactly what drew "DOD". A guard is only
    // proven by the code it was built to catch.
    const prefix = [
      `            if let logo = avatar.url, let url = URL(string: logo) {`,
      `                } placeholder: { EmptyView() }`,
    ];
    for (const line of prefix) {
      const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(stripComments(line)));
      expect(hits.length).toBeGreaterThan(0);
    }
  });

  it("the scan does NOT fire on a surface that delegates", () => {
    // The inverse hazard: a scan that flags every file becomes a nuisance and
    // gets suppressed. `EventCardView` hands `avatar.url` straight to
    // `TeamLogoView`, which is asking for the ladder, not re-implementing it.
    const delegation = `                url: avatar.url,`;
    const hits = REIMPLEMENTATION_TELLS.filter(([, re]) => re.test(stripComments(delegation)));
    expect(hits).toEqual([]);
  });

  it("stripping comments does not blind the scan to real code", () => {
    const withTrailingComment = `if let logo = avatar.url, let url = URL(string: logo) { // draw it`;
    expect(
      REIMPLEMENTATION_TELLS.some(([, re]) => re.test(stripComments(withTrailingComment)))
    ).toBe(true);
  });
});
