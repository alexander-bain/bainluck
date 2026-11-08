/**
 * #12304 — the App Store rating prompt has ONE caller.
 *
 * `ReviewPromptModifier12304` asks only when `ReviewPromptPolicy12304` says yes
 * (never in a reader's first days, never twice in 120 days or for one version,
 * only after a good moment, never in a run that showed trouble). A second
 * `requestReview` call anywhere else would skip every one of those rules, and
 * nothing at runtime would notice: Apple shows the sheet at most three times a
 * year and says nothing when it declines. So the rule is held at the source.
 */
import { existsSync, readdirSync, readFileSync } from "fs";
import { join, relative } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck");
const MODIFIER = join(IOS_ROOT, "Bain Luck/Utilities/ReviewPromptModifier12304.swift");

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

/** The calls that show Apple's rating sheet: the SwiftUI action and UIKit's API. */
const ASKS = /\brequestReview\s*\(|SKStoreReviewController\s*\.\s*requestReview|AppStore\s*\.\s*requestReview/;

function askers(files: Array<[string, string]>): string[] {
  return files.filter(([, src]) => ASKS.test(stripComments(src))).map(([path]) => path);
}

const present = existsSync(IOS_ROOT);
const t = present ? describe : describe.skip;

t("#12304 — the rating prompt has one caller", () => {
  it("only the modifier asks for a rating, in every target", () => {
    const files = swiftFiles(IOS_ROOT).map((p): [string, string] => [p, readFileSync(p, "utf8")]);
    expect(askers(files).map((p) => relative(IOS_ROOT, p))).toEqual([
      relative(IOS_ROOT, MODIFIER),
    ]);
  });

  it("the modifier still asks through the policy", () => {
    const src = stripComments(readFileSync(MODIFIER, "utf8"));
    expect(src).toMatch(/ReviewPromptPolicy12304\(\)\.shouldAsk\(/);
    expect(src).toMatch(/requestReview\(\)/);
  });

  it("the scan can actually fail", () => {
    const stray: Array<[string, string]> = [
      ["Views/Stray.swift", "func done() { requestReview() }"],
      ["Views/Old.swift", "SKStoreReviewController.requestReview(in: scene)"],
      ["Views/Commented.swift", "// requestReview() is not called here"],
    ];
    expect(askers(stray)).toEqual(["Views/Stray.swift", "Views/Old.swift"]);
  });
});
