/**
 * #12307 — a bainluck.com game link can open Bain Luck's App Clip only when
 * three files agree, and the system refuses the invocation when any one drifts:
 *
 * - the website's `apple-app-site-association` lists the clip under `appclips`;
 * - the clip's entitlements claim `appclips:` for both hosts and name the app
 *   as its parent;
 * - the app's entitlements claim the same domains and name the clip.
 *
 * The clip's bundle id and team come from the project file, so renaming the
 * target or moving teams without the website fails here, in CI, which compiles
 * no Swift.
 */

import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const IOS = join(REPO_ROOT, "ios", "Bain Luck");
const read = (...parts: string[]) => readFileSync(join(...parts), "utf8");

const HOSTS = ["bainluck.com", "www.bainluck.com"];

function plistArray(xml: string, key: string): string[] {
  const block = xml.match(new RegExp(`<key>${key.replace(/\./g, "\\.")}</key>\\s*<array>([\\s\\S]*?)</array>`));
  if (!block) return [];
  return Array.from(block[1].matchAll(/<string>([^<]+)<\/string>/g), (m) => m[1]);
}

function buildSetting(entitlements: string, name: string): string[] {
  const pbx = read(IOS, "Bain Luck.xcodeproj", "project.pbxproj");
  // A target's two configurations are the ones that sign with its entitlements file.
  const configs = pbx
    .split(/\n\t\t[0-9A-F]{24} \/\* (?:Debug|Release) \*\/ = \{/)
    .filter((block) => block.includes(`CODE_SIGN_ENTITLEMENTS = "${entitlements}";`));
  return configs.map((block) => {
    const m = block.match(new RegExp(`\\n\\t+${name} = "?([^";]+)"?;`));
    return m ? m[1] : "";
  });
}

const clipBuildSetting = (name: string) => buildSetting("BainLuckClip/BainLuckClip.entitlements", name);
const appBuildSetting = (name: string) => buildSetting("Bain Luck/Bain Luck.entitlements", name);

describe("#12307 — the website, the App Clip and the app agree on the clip", () => {
  const clipIDs = clipBuildSetting("PRODUCT_BUNDLE_IDENTIFIER");
  const teams = clipBuildSetting("DEVELOPMENT_TEAM");

  test("the project builds one App Clip, in both configurations, with one bundle id and team", () => {
    expect(clipIDs).toEqual(["com.bainluck.Bain-Luck.Clip", "com.bainluck.Bain-Luck.Clip"]);
    expect(teams).toEqual(["J893F72P4R", "J893F72P4R"]);
    expect(read(IOS, "Bain Luck.xcodeproj", "project.pbxproj")).toContain(
      'productType = "com.apple.product-type.application.on-demand-install-capable";',
    );
  });

  test("the clip carries the app's version, so App Store Connect accepts the pair", () => {
    // App Store Connect refuses an upload whose App Clip version differs from the
    // app's. The clip was still 1.0.6 after #12644 moved every other target to 1.0.7.
    const appVersions = appBuildSetting("MARKETING_VERSION");
    expect(appVersions).toHaveLength(2);
    expect(new Set(appVersions).size).toBe(1);
    expect(clipBuildSetting("MARKETING_VERSION")).toEqual(appVersions);
  });

  test("the website's association file lists exactly that clip", () => {
    const aasa = JSON.parse(read(REPO_ROOT, "frontend", "public", ".well-known", "apple-app-site-association"));
    expect(aasa.appclips?.apps).toEqual([`${teams[0]}.${clipIDs[0]}`]);
    // The app's universal links are untouched by the clip.
    expect(aasa.applinks?.details?.[0]?.appID).toBe("J893F72P4R.com.bainluck.Bain-Luck");
  });

  test("the clip claims both hosts and names the app as its parent", () => {
    const clip = read(IOS, "BainLuckClip", "BainLuckClip.entitlements");
    expect(plistArray(clip, "com.apple.developer.associated-domains")).toEqual(HOSTS.map((h) => `appclips:${h}`));
    expect(plistArray(clip, "com.apple.developer.parent-application-identifiers")).toEqual([
      "$(AppIdentifierPrefix)com.bainluck.Bain-Luck",
    ]);
    expect(clip).toMatch(/<key>com\.apple\.developer\.on-demand-install-capable<\/key>\s*<true\/>/);
  });

  test("the app claims the same hosts for the clip and names it", () => {
    const app = read(IOS, "Bain Luck", "Bain Luck.entitlements");
    const domains = plistArray(app, "com.apple.developer.associated-domains");
    for (const host of HOSTS) {
      expect(domains).toContain(`appclips:${host}`);
      expect(domains).toContain(`applinks:${host}`);
    }
    expect(plistArray(app, "com.apple.developer.associated-appclip-app-identifiers")).toEqual([
      `$(AppIdentifierPrefix)${clipIDs[0]}`,
    ]);
  });
});
