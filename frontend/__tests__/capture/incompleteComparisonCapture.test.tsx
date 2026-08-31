/**
 * UX-P156 — A COMPARISON WITH A MISSING LEG, RENDERED FOR ALEX'S EYEBALL.
 *
 * ═══ WHY THIS EXISTS ═══
 *
 * CERT-430 withheld the token on this branch, finding 1 first:
 *
 *   > A missing price turns the two-player comparison into a live one-player
 *   > answer. […] with Alcaraz unpriced and Sinner fresh at .555, `build_props`
 *   > returns the `second-major` card as `price_state='live'`, with Alcaraz
 *   > `(None, false)` and Sinner `(.555, true)`. Rendering that exact shape
 *   > produces one `prop-field-row`, containing Sinner and no Alcaraz, beneath
 *   > **"Who wins a second major this year?"**
 *
 * The repair is a rule, and a rule is a claim about what a reader sees — so it
 * gets a render, not a description. Three panels, all from the SHIPPED
 * `TournamentProps` with the same two real Kalshi readings:
 *
 *   1. WHAT THE CERT EXECUTED — reproduced by defeating the fix, so the panel
 *      shows the actual defect rather than a drawing of it.
 *   2. WHAT IT DOES NOW — both men, the missing one named, the card muted.
 *   3. THE CONTROL — both legs quoted, and the card is live and says nothing.
 *      A repair that darkened every comparison would pass panel 2 and destroy
 *      the section, so the healthy case is on the same page.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=incompleteComparisonCapture
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig works — same arrangement as the other capture rigs.
 *
 * FAITHFUL: the shipped component, the app's own compiled stylesheet, and both
 * probabilities (Alcaraz .25 / Sinner .555, from `payload-2026-08-28.json`,
 * which `capture_tournament_payload.py` read from production through the
 * route's own `build_props`).
 *
 * SYNTHETIC, and captioned as such: the LIVENESS. Both legs were last read on
 * 2026-07-24, so on today's data the card renders quiet — which is panel 4 of
 * the UX-P154 artifact and is not what this one is about. The panels below move
 * the server-owned freshness fields only, over the real numbers, so the rule
 * under review is the thing on screen.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentProps from "@/components/tournament/TournamentProps";
import { propIsPresentedAsLive, type PropMarket } from "@/lib/tournamentProps";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const PAYLOAD_PATH = path.join(REPO, "docs", "mocks", "us-open", "payload-2026-08-28.json");

function loadCombined(): PropMarket {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
  const card = (payload.props ?? []).find((p) => p.key === "second-major");
  if (!card) throw new Error("payload no longer carries the combined card");
  return card as PropMarket;
}

function appStylesheet(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

/** The real card, with the two declared legs and both readings current. */
function healthy(): PropMarket {
  const card = loadCombined();
  return {
    ...card,
    legs: 2,
    unpriced_legs: [],
    price_state: "live",
    age_hours: 0.4,
    freshest_age_hours: 0.4,
    stale_outcomes: [],
    outcomes: card.outcomes.map((o) => ({
      ...o,
      probability_is_live: true,
      price_state: "live" as const,
      age_hours: 0.4,
    })),
  };
}

/** The same card with the Alcaraz leg's reading absent — the cert's specimen. */
function missingLeg(): PropMarket {
  const card = healthy();
  return {
    ...card,
    unpriced_legs: ["KXGRANDSLAM-CALC26"],
    outcomes: card.outcomes.map((o) =>
      o.display_name === "Carlos Alcaraz"
        ? {
            ...o,
            probability: null,
            probability_is_live: false,
            observed_at: null,
            age_hours: null,
            price_state: "dark" as const,
          }
        : o
    ),
  };
}

/**
 * The same data with the fix DEFEATED, for the before panel.
 *
 * `legs` is what tells the page this card is a comparison; without it the card
 * is an ordinary field, the unpriced row is dropped from the ranking for having
 * nothing to rank it by, and one man renders under a two-man question. That is
 * precisely the state the cert executed, so the before panel is the real defect
 * rather than a reconstruction of it.
 */
function asItShipped(): PropMarket {
  const { legs: _legs, unpriced_legs: _unpriced, ...rest } = missingLeg();
  return { ...rest, price_state: "live" };
}

describe("UX-P156 — a comparison is complete or it is not presented as one", () => {
  it("BEFORE: the cert's specimen renders one player under a two-player question", () => {
    const html = renderToStaticMarkup(
      <TournamentProps markets={[asItShipped()]} draw="mens-singles" />
    );
    // The defect, on screen: one row, Sinner only, and the card calls itself
    // live. This assertion is the one that must FLIP in the after panel.
    expect((html.match(/data-testid="prop-field-row"/g) ?? []).length).toBe(1);
    expect(html).toContain("Jannik Sinner");
    expect(html).not.toContain("Carlos Alcaraz");
    expect(html).toContain('data-live="true"');
  });

  it("AFTER: both men, the missing one named, and the card is not live", () => {
    const card = missingLeg();
    expect(propIsPresentedAsLive(card)).toBe(false);

    const html = renderToStaticMarkup(
      <TournamentProps markets={[card]} draw="mens-singles" />
    );
    expect((html.match(/data-testid="prop-field-row"/g) ?? []).length).toBe(2);
    expect(html).toContain("Carlos Alcaraz");
    expect(html).toContain("Jannik Sinner");
    expect(html).toContain("56%");
    expect(html).toContain("No number yet");
    // UX-P212 (CERT-537) moved this off the present perfect. "No number HAS
    // reached us … yet" is a claim about all of history, and `observed_at` —
    // the newest `captured_at` WHERE `probability IS NOT NULL` — can disprove it
    // on this exact row shape. The sentence now reports what we HAVE.
    expect(html).toContain(
      "We have no number for Carlos Alcaraz yet, so this comparison is not complete."
    );
    expect(html).toContain('data-live="false"');
    expect(html).toContain('data-incomplete="true"');
  });

  it("CONTROL: with both legs quoted the card is live and apologises for nothing", () => {
    const html = renderToStaticMarkup(
      <TournamentProps markets={[healthy()]} draw="mens-singles" />
    );
    expect(html).toContain('data-live="true"');
    expect(html).toContain('data-incomplete="false"');
    expect(html).not.toContain('data-testid="prop-incomplete"');
    expect(html).toContain("56%");
    expect(html).toContain("25%");
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const css = appStylesheet();
    const framed = (markup: string) =>
      `<div class="max-w-content mx-auto px-3 md:px-6 py-4"><div class="w-full"><div class="px-4 lg:px-6">${markup}</div></div></div>`;
    const panel = (kind: string, label: string, note: string, markup: string) =>
      `<div class="panel"><div class="panel-head"><span class="tag ${kind}">${kind}</span> <b>${label}</b> ${note}</div>${framed(markup)}<div class="rule"></div></div>`;

    const before = renderToStaticMarkup(
      <TournamentProps markets={[asItShipped()]} draw="mens-singles" />
    );
    const after = renderToStaticMarkup(
      <TournamentProps markets={[missingLeg()]} draw="mens-singles" />
    );
    const control = renderToStaticMarkup(
      <TournamentProps markets={[healthy()]} draw="mens-singles" />
    );

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P156 — a comparison with a leg missing</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.before{background:#FEF2F2;color:#991B1B}
  .tag.after{background:#ECFDF5;color:#065F46}
  .tag.control{background:#EEF2FF;color:#3730A3}
  .panel{padding:8px 0 40px}
  .panel-head{padding:16px 22px 4px;font-size:13px;color:#4B5563;line-height:1.6}
  .rule{height:1px;background:#E5E7EB;margin:8px 0 0}
</style></head>
<body>
<div class="banner">
  <span class="tag after">UX-P156</span> <b>A two-name question can no longer answer with one name.</b>
  <br><br>
  The cert found it and ran it: with Alcaraz's market unquoted and Sinner's fresh at 55.5%,
  the combined card called itself <b>live</b> and printed <b>one player</b> under
  <i>"Who wins a second major this year?"</i>. Every step was locally reasonable — an unpriced
  row has nothing to rank it by, so the ranking dropped it, and only priced rows voted on
  whether the card was current.
  <br><br>
  <b>The rule now:</b> a card built from several declared markets prints <b>every declared
  subject</b>, is never presented as current while one of them has no number, and says which one
  is missing. It is <b>not hidden</b> — that would break the other half of the ruling
  (<i>illiquid questions render with honest freshness indication, never hidden</i>) and would
  throw away Sinner's real number as well.
  <br><br>
  Both probabilities below are real, read from production. Freshness is set current in all three
  panels so the rule under review is what you are looking at.
</div>
${panel(
  "before",
  "1 — What the cert executed.",
  "One row, one man, in the confident type. Reproduced by removing the one field that tells the page this card is a comparison — this is the defect, not a drawing of it.",
  before
)}
${panel(
  "after",
  "2 — The same data, today's page.",
  "Both men. Sinner's real 56%. Alcaraz's row says <b>No number yet</b> instead of vanishing, the card is muted, and the sentence underneath names him.",
  after
)}
${panel(
  "control",
  "3 — The healthy card, unchanged.",
  "Both legs quoted: live type, no age chip, no apology. A repair that muted every comparison would have passed panel 2 and cost the section its best card.",
  control
)}
</body></html>`;

    const file = path.join(dir, "p156-incomplete-comparison.html");
    fs.writeFileSync(file, html);

    const written = fs.readFileSync(file, "utf8");
    expect(written.length).toBeGreaterThan(20_000);
    expect(written).toContain('class="tag before"');
    expect(written).toContain('class="tag after"');
    expect(written).toContain('class="tag control"');
    // The artifact must contain the FIX, not three copies of the same panel.
    expect(written).toContain("We have no number for Carlos Alcaraz");
    expect(written).toContain('data-incomplete="true"');
    expect(written).toContain('data-incomplete="false"');
  });
});
