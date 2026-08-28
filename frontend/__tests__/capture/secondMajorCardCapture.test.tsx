/**
 * UX-P151 — THE COMBINED "second major" CARD, RENDERED FOR ALEX'S EYEBALL.
 *
 * ═══ THE RULING, QUOTED ═══
 *
 * Alex, 2026-08-28 ~10:45am PT:
 *
 *   > ONE COMBINED CARD — "Who wins a second major this year?" — showing BOTH
 *   > players' probabilities (Alcaraz 2+ majors, Sinner 2+ majors, each from
 *   > its own real Kalshi market: KXGRANDSLAM-CALC26-family and
 *   > KXGRANDSLAM-JSIN26).
 *
 * It resolves two earlier notes that had been read as contradicting each
 * other. UX-P138: the two `*-second-major` cards were *"one templated question
 * with the name swapped"* — and what shipped for it deleted Alcaraz. UX-P147:
 * *"DIFFERENT PLAYERS and must both render"* and *"I'd love to"* see both —
 * and what shipped for that restored Alcaraz as a second card, bringing the
 * repetition back. Both notes are satisfied at once by dropping the assumption
 * neither of them made: that the unit is one card per market.
 *
 * ═══ WHY THIS RIG EXISTS SEPARATELY FROM THE PAGE CAPTURE ═══
 *
 * `usOpenBoardCapture` renders the whole hub, nine panels deep, and the card
 * this queue is about is one row inside the last section of it. A verdict on a
 * row should not require finding the row. This writes one short page with the
 * three states side by side.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=secondMajorCardCapture
 *
 * With no env var set it is an ordinary test that renders every state and
 * asserts the rig still works — same arrangement as the other capture rigs, so
 * a broken artifact fails CI rather than waiting to be noticed on a screen.
 *
 * ═══ WHAT IS FAITHFUL AND WHAT IS QUOTED ═══
 *
 * FAITHFUL: the shipped `TournamentProps` component, the app's own compiled
 * stylesheet from `.next/static/css`, and every probability — all four numbers
 * come from `payload-2026-08-28.json`, which `capture_tournament_payload.py`
 * produced from production through the route's own `build_props`.
 *
 * QUOTED, and captioned as such on the artifact: the BEFORE panel's two cards.
 * They are the payload the superseded register produced, reconstructed here
 * because the register no longer carries those two keys — which is the whole
 * point of a before panel. Their numbers are the same readings the combined
 * card's legs carry, because they are the same two outcomes.
 *
 * SYNTHETIC, and captioned: the LIVE treatment. Both Kalshi markets were last
 * read on 2026-07-24 and are 856 hours dark, so today the card rotates out and
 * the section renders its honest empty state — panel 3 shows exactly that, and
 * it is the true state of the page on merge. The live panel moves only the
 * server-owned liveness fields, over the real numbers, so Alex can judge the
 * card he will get rather than a description of it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentProps from "@/components/tournament/TournamentProps";
import type { PropMarket, PropOutcome } from "@/lib/tournamentProps";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const PAYLOAD_PATH = path.join(REPO, "docs", "mocks", "us-open", "payload-2026-08-28.json");

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
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

/**
 * The same card with the server-owned liveness fields set to live.
 *
 * Derived from the real card rather than hand-written, for the reason
 * `makeLiveBoard` is: a hand-authored literal keeps passing after the backend
 * changes shape underneath it, and then the artifact is a picture of a payload
 * nobody serves.
 */
function asLive(market: PropMarket): PropMarket {
  return {
    ...market,
    price_state: "live",
    age_hours: 0.4,
    freshest_age_hours: 0.4,
    stale_outcomes: [],
    outcomes: market.outcomes.map((outcome) => ({
      ...outcome,
      probability_is_live: true,
      price_state: "live" as const,
      age_hours: 0.4,
    })),
  };
}

/**
 * THE TWO CARDS AS THEY WERE — quoted from register v10, which this queue
 * superseded.
 *
 * Both were Kalshi threshold ladders (`1+ / 2+ / 3+ Grand Slam wins`), each
 * naming `2+` as its answer, and each printing that one number in the headline
 * slot. The ladder legs are carried here even though the card prints only the
 * answer, because dropping them would quietly change what `printedOutcomes`
 * and the liveness rule see and the before panel would stop being the before.
 */
const LADDER_AGE_HOURS = 856.1;
const LADDER_OBSERVED = "2026-07-24T02:50:56.699511+00:00";

function ladderOutcome(
  key: string,
  name: string,
  probability: number,
  isAnswer: boolean
): PropOutcome {
  return {
    entity_key: `${key}:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    display_name: name,
    probability,
    probability_is_live: false,
    observed_at: LADDER_OBSERVED,
    age_hours: LADDER_AGE_HOURS,
    price_state: "dark",
    is_answer: isAnswer,
  };
}

function ladderCard(
  key: string,
  title: string,
  hook: string,
  rungs: [string, number][],
  answer: string
): PropMarket {
  const outcomes = rungs.map(([name, p]) => ladderOutcome(key, name, p, name === answer));
  return {
    key,
    title,
    hook,
    draw: "mens-singles",
    source: "kalshi",
    outcomes,
    answer_entity_key: outcomes.find((o) => o.is_answer)!.entity_key,
    price_state: "dark",
    observed_at: LADDER_OBSERVED,
    age_hours: LADDER_AGE_HOURS,
    freshest_observed_at: LADDER_OBSERVED,
    freshest_age_hours: LADDER_AGE_HOURS,
    stale_outcomes: outcomes.map((o) => o.entity_key),
    mixed_freshness: false,
  };
}

function supersededCards(): PropMarket[] {
  return [
    ladderCard(
      "alcaraz-second-major",
      "Can Alcaraz win a second major this year?",
      "The other half of the men's duopoly, chasing the same thing.",
      [
        ["2+ Grand Slam wins", 0.25],
        ["3+ Grand Slam wins", 0.01],
        ["All 4 Grand Slam wins", 0.01],
      ],
      "2+ Grand Slam wins"
    ),
    ladderCard(
      "sinner-second-major",
      "Can Sinner win a second major this year?",
      "He already has one in 2026. The next chance is this fortnight.",
      [
        ["1+ Grand Slam wins", 0.99],
        ["2+ Grand Slam wins", 0.555],
        ["3+ Grand Slam wins", 0.01],
      ],
      "2+ Grand Slam wins"
    ),
  ];
}

describe("UX-P151 — the combined second-major card", () => {
  const payload = loadPayload();
  const props = (payload.props ?? []) as PropMarket[];
  const combined = props.find((market) => market.key === "second-major");

  it("the payload carries the combined card, with both men on it", () => {
    // The rig is worthless on a stale payload — the whole lesson of
    // `capture_tournament_payload.py`. These are the facts the panels are FOR.
    expect(combined).toBeDefined();
    expect(combined!.title).toBe("Who wins a second major this year?");
    expect(combined!.outcomes.map((o) => o.display_name)).toEqual(["Alcaraz", "Sinner"]);
    expect(combined!.outcomes.map((o) => o.probability)).toEqual([0.25, 0.555]);
    // A comparison has no single answer, so the card ranks rather than leading.
    expect(combined!.answer_entity_key).toBeNull();
  });

  it("the register no longer carries the two cards the BEFORE panel shows", () => {
    // If they came back, the before and after panels would stop being before
    // and after and the artifact would silently stop making its point.
    expect(props.filter((p) => p.key.endsWith("-second-major"))).toHaveLength(0);
  });

  it("BEFORE: two cards, the same question twice, one number each", () => {
    const html = renderToStaticMarkup(
      <TournamentProps markets={supersededCards().map(asLive)} draw="mens-singles" />
    );
    // The repetition Alex objected to, on screen: two cards, and the only
    // difference between their questions is the name inside them.
    expect(html).toContain("Can Alcaraz win a second major this year?");
    expect(html).toContain("Can Sinner win a second major this year?");
    expect(
      (html.match(/data-testid="prop-market"/g) ?? []).length
    ).toBe(2);
    // Each led with one number, and the row under it said `2+ Grand Slam
    // wins` — the market's own words, in a threshold ladder's vocabulary.
    expect(html).toContain("2+ Grand Slam wins");
    expect((html.match(/data-shape="answer"/g) ?? []).length).toBe(2);
  });

  it("AFTER: one card, two players, no headline number", () => {
    const html = renderToStaticMarkup(
      <TournamentProps markets={[asLive(combined!)]} draw="mens-singles" />
    );
    expect((html.match(/data-testid="prop-market"/g) ?? []).length).toBe(1);
    expect(html).toContain('data-shape="field"');
    expect(html).toContain("Who wins a second major this year?");
    // Two names, two numbers, ranked — Sinner's 56% above Alcaraz's 25%.
    expect((html.match(/data-testid="prop-field-row"/g) ?? []).length).toBe(2);
    expect(html).toContain("Sinner");
    expect(html).toContain("Alcaraz");
    expect(html).toContain("56%");
    expect(html).toContain("25%");
    // NOT normalised to 100. Four majors a year and each man needs two of
    // them, so both can resolve Yes; a card that made them add up would be
    // asserting an exclusivity the two markets do not have.
    expect(html).not.toContain("69%");
    expect(html).not.toContain("31%");
    // And "2+ Grand Slam wins" is gone from the reader's view: the rows are
    // named after the men, which is what the question compares.
    expect(html).not.toContain("Grand Slam wins");
  });

  it("TODAY: on the real readings the card is dark and the section says so", () => {
    // The honest half, and the reason the report cannot claim a visible ship.
    // Both legs were last read 2026-07-24. `propIsDark` rotates the card out
    // and the section renders its empty state with the count and the reason.
    const html = renderToStaticMarkup(<TournamentProps markets={props} draw="mens-singles" />);
    expect(html).toContain('data-testid="props-empty"');
    expect(html).toContain("have not seen a new number on");
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
      <TournamentProps markets={supersededCards().map(asLive)} draw="mens-singles" />
    );
    const after = renderToStaticMarkup(
      <TournamentProps markets={[asLive(combined!)]} draw="mens-singles" />
    );
    const today = renderToStaticMarkup(
      <TournamentProps markets={props} draw="mens-singles" />
    );

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P151 — Who wins a second major this year?</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.before{background:#FEF2F2;color:#991B1B}
  .tag.after{background:#ECFDF5;color:#065F46}
  .tag.today{background:#FFFBEB;color:#92400E}
  .panel{padding:8px 0 40px}
  .panel-head{padding:16px 22px 4px;font-size:13px;color:#4B5563;line-height:1.6}
  .rule{height:1px;background:#E5E7EB;margin:8px 0 0}
</style></head>
<body>
<div class="banner">
  <span class="tag after">UX-P151</span> <b>One combined card, both men on it.</b>
  Your ruling this morning: <i>"ONE COMBINED CARD — 'Who wins a second major this year?' —
  showing BOTH players' probabilities."</i> Every number below is real: Alcaraz's
  <b>2+ Grand Slam wins</b> at 25% and Sinner's at 55.5%, read from production through the page's
  own <code>build_props</code>.
  <br><br>
  <b>The two markets are independent.</b> There are four majors a year and each man needs two of
  them, not the same two — so both can resolve Yes, the numbers do not add to 100, and the card
  does not make them. That is what the sentence under the card is for; the title on its own reads
  as a race.
  <br><br>
  <b>What you will actually see on merge is panel 3.</b> Both Kalshi markets were last read on
  <b>2026-07-24</b>, 856 hours ago, so the card is too old to show and the section keeps its empty
  state. Panel 2 is the same card with only the freshness fields moved — the shape you are ruling
  on, over today's real numbers. It becomes panel 2 for real the day these two markets are read
  again.
</div>
${panel(
  "before",
  "Two cards — the same question with the name swapped.",
  "Quoted from register v10, which this queue supersedes. Shipped component, real numbers.",
  before
)}
${panel(
  "after",
  "One card, two players, ranked. No headline number.",
  "Shipped component, unmodified. Real numbers; freshness set live so the treatment is visible.",
  after
)}
${panel(
  "today",
  "The section as it renders on merge.",
  "Nothing moved. Both legs are 856 hours old, so the card rotates out and the section says why.",
  today
)}
</body></html>`;

    const file = path.join(dir, "p151-second-major-card.html");
    fs.writeFileSync(file, html);

    const written = fs.readFileSync(file, "utf8");
    expect(written.length).toBeGreaterThan(20_000);
    expect(written).toContain('class="tag before"');
    expect(written).toContain('class="tag after"');
    expect(written).toContain("Who wins a second major this year?");
    expect(written).toContain("Can Alcaraz win a second major this year?");
  });
});
