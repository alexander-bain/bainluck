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

/**
 * The same two superseded cards with their TOPICS pulled apart, so the render-
 * time combiner leaves them alone.
 *
 * Needed only for the "what it used to look like" panel, and captioned as a
 * reconstruction on the artifact. Since UX-P154 there is no data that produces
 * two same-topic cards on this page — which is the change — so the only way to
 * photograph the old repetition is to defeat the thing that ended it.
 */
function unfamilied(cards: PropMarket[]): PropMarket[] {
  return cards.map((card, index) =>
    index === 0 ? { ...card, key: `${card.key}-a` } : { ...card, key: `${card.key}-b` }
  );
}

describe("UX-P154 — the combined card, and who builds it", () => {
  const payload = loadPayload();
  const props = (payload.props ?? []) as PropMarket[];
  const combined = props.find((market) => market.key === "second-major");

  it("the payload carries the combined card, with both men on it", () => {
    // The rig is worthless on a stale payload — the whole lesson of
    // `capture_tournament_payload.py`. These are the facts the panels are FOR.
    expect(combined).toBeDefined();
    expect(combined!.title).toBe("Who wins a second major this year?");
    // UX-P154: the rows are the SOURCE's own words, derived from each market's
    // title by `prop_template_family.subject_display`. UX-P151 hand-wrote
    // "Alcaraz" and "Sinner", which nothing downstream could check.
    expect(combined!.outcomes.map((o) => o.display_name)).toEqual([
      "Carlos Alcaraz",
      "Jannik Sinner",
    ]);
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
      <TournamentProps markets={unfamilied(supersededCards()).map(asLive)} draw="mens-singles" />
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

  it("THE ANSWER TO ALEX'S QUESTION: the OLD data now combines itself", () => {
    /* ═══ ITEM 1, ON SCREEN ═══
     *
     * *"Was this a bespoke solution? I thought we'd built tools to identify
     * groups and surface them as groups. Why didn't any of them trigger?"*
     *
     * It was bespoke. This is the same superseded register-v10 payload, with
     * its ORIGINAL keys, rendered by today's page — and it comes out as one
     * card. Nothing in the data says to combine it; `combinePropFamilies` sees
     * one topic and two subjects and merges them, and the question is named
     * from the two titles' own shared words.
     *
     * This is the strongest form of the claim, because the input is the exact
     * thing that produced the repetition Alex objected to.
     */
    const html = renderToStaticMarkup(
      <TournamentProps markets={supersededCards().map(asLive)} draw="mens-singles" />
    );
    expect((html.match(/data-testid="prop-market"/g) ?? []).length).toBe(1);
    expect(html).toContain("Can … win a second major this year?");
    expect((html.match(/data-testid="prop-field-row"/g) ?? []).length).toBe(2);
    expect(html).toContain("Alcaraz");
    expect(html).toContain("Sinner");
    // Nobody was deleted. That is the difference between combining and the
    // collapse ruling 139 forbids.
    expect(html).toContain('data-testid="props-combined"');
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
    expect(html).toContain("Jannik Sinner");
    expect(html).toContain("Carlos Alcaraz");
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

  it("TODAY: on the real readings the card RENDERS, and says how old it is", () => {
    /* ═══ ITEM 4, ON THE REAL PAYLOAD ═══
     *
     * This assertion is inverted from UX-P151's, and the inversion is the ship.
     * Both legs were last read 2026-07-24, 856 hours ago. Until now that
     * emptied the section, and the P151 report's honest half was that "what
     * ships today is the SHAPE".
     *
     * Alex, item 4: illiquid props render with honest freshness indication,
     * never hidden — *"that's part of the value of the product."* So the card
     * is on the page, 35 days old, saying so, and never in the confident type.
     */
    const html = renderToStaticMarkup(<TournamentProps markets={props} draw="mens-singles" />);
    expect(html).not.toContain('data-testid="props-empty"');
    expect(html).toContain("Who wins a second major this year?");
    expect(html).toContain('data-live="false"');
    expect(html).toContain("Last number 35 days ago");
    expect(html).toContain("not when it was created");
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
      <TournamentProps
        markets={unfamilied(supersededCards()).map(asLive)}
        draw="mens-singles"
      />
    );
    const systemic = renderToStaticMarkup(
      <TournamentProps markets={supersededCards().map(asLive)} draw="mens-singles" />
    );
    const after = renderToStaticMarkup(
      <TournamentProps markets={[asLive(combined!)]} draw="mens-singles" />
    );
    const today = renderToStaticMarkup(
      <TournamentProps markets={props} draw="mens-singles" />
    );
    const variants = (["labelled", "sentence", "dot"] as const).map((variant) =>
      renderToStaticMarkup(
        <TournamentProps markets={props} draw="mens-singles" variant={variant} />
      )
    );

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P154 — grouping by the system, and how a quiet question shows its age</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.before{background:#FEF2F2;color:#991B1B}
  .tag.after{background:#ECFDF5;color:#065F46}
  .tag.today{background:#FFFBEB;color:#92400E}
  .tag.riff{background:#EEF2FF;color:#3730A3}
  .panel{padding:8px 0 40px}
  .panel-head{padding:16px 22px 4px;font-size:13px;color:#4B5563;line-height:1.6}
  .rule{height:1px;background:#E5E7EB;margin:8px 0 0}
  .ask{padding:14px 22px;background:#FFFBEB;border-top:1px solid #FDE68A;border-bottom:1px solid #FDE68A;font-size:13px;line-height:1.6;color:#78350F}
</style></head>
<body>
<div class="banner">
  <span class="tag after">UX-P154</span> <b>The grouping is systemic now, and no question is
  hidden for being old.</b>
  <br><br>
  <b>Your question:</b> <i>"Was this a bespoke solution? I thought we'd built tools to identify
  groups and surface them as groups. Why didn't any of them trigger?"</i>
  <br>
  <b>It was bespoke</b> — a human wrote down two tickers, the outcome to pull from each, and the
  label each row should print. Nothing was detected. Two things could have fired and neither
  could: the props renderer's family rule was a <i>cap</i>, whose only outputs were two cards or
  one card and a deletion — and since UX-P147 keyed it on the whole register key, and register
  keys are unique, it had been <b>structurally unreachable</b>. The real grouper
  (<code>prop_families.py</code>) is not wired to this pass and returns nothing for
  <i>"Carlos Alcaraz: Grand Slam wins in 2026"</i> anyway.
  <br><br>
  <b>Panel 2 is the answer.</b> It is the OLD two-card data, with its original keys, rendered by
  today's page — and it comes out as one card. Nothing in the data says to combine it.
  <br><br>
  <b>And every number below is real:</b> Alcaraz's <b>2+ Grand Slam wins</b> at 25% and Sinner's at
  55.5%, read from production. The two markets are independent — four majors a year and each man
  needs two of them, not the same two — so both can resolve Yes, the numbers do not add to 100,
  and the card does not make them.
</div>
${panel(
  "before",
  "1 — What it looked like: the same question with the name swapped.",
  "Register v10's two cards. Reconstructed: their keys are pulled apart so today's combiner leaves them alone, because there is no longer any data that produces this.",
  before
)}
${panel(
  "after",
  "2 — The same old data, rendered by today's page.",
  "Original keys, nothing else changed. One card, both men, and the question named from the two titles' own shared words. This is what &ldquo;by the system&rdquo; means.",
  systemic
)}
${panel(
  "after",
  "3 — What the register now holds, built by the detector.",
  "The rows say <b>Carlos Alcaraz</b> and <b>Jannik Sinner</b> because that is what the markets call them — derived, not curated. A third player's ladder joins this card with no edit anywhere. Freshness set live so the treatment is visible.",
  after
)}
${panel(
  "today",
  "4 — The section as it renders on merge. THIS IS THE SHIP.",
  "Nothing moved. Both legs are 856 hours old — and the card is on the page, saying so, instead of being deleted. Until today this section was EMPTY every day it existed.",
  today
)}
<div class="ask">
  <span class="tag riff">Your eyeball</span> <b>Three ways a quiet question can show its age.</b>
  You said the <i>"32 hours ago"</i> ambiguity is real — created? updated? last traded? — and that
  this is <i>"an open riff, not a settled design."</i>
  <br><br>
  <b>What the timestamp actually means,</b> traced to the query: it is
  <code>MAX(futures_odds_snapshots.captured_at)</code>, and every refresh writes a snapshot whether
  or not the number moved. So it is <b>the last time a probability for that question reached us</b>
  — not created, not last updated by the venue, not last traded. And it cannot tell you which of
  two causes it has: the market may be quoted and untraded, or our reader may not be covering it.
  Both are &ldquo;no new number reached us&rdquo;, so that is what the copy says rather than
  claiming to know the market went quiet.
  <br><br>
  All three below are the SHIPPED component with the same real data — not drawings.
  <b>A is the default.</b>
</div>
${panel(
  "riff",
  "A — labelled chip (shipped default).",
  "Carries the noun on every card without spending a line on it. The one that answers &ldquo;32 hours since what&rdquo; inline.",
  variants[0]
)}
${panel(
  "riff",
  "B — plain sentence.",
  "Least ambiguous, most vertical space. Reads well at two cards; would drown a section of eight.",
  variants[1]
)}
${panel(
  "riff",
  "C — dot and compact age.",
  "Densest. The meaning lives once in the section footnote instead of on each card. The one to try if this section grows.",
  variants[2]
)}
</body></html>`;

    const file = path.join(dir, "p154-props-and-grouping.html");
    fs.writeFileSync(file, html);

    const written = fs.readFileSync(file, "utf8");
    expect(written.length).toBeGreaterThan(20_000);
    expect(written).toContain('class="tag before"');
    expect(written).toContain('class="tag after"');
    expect(written).toContain('class="tag riff"');
    expect(written).toContain("Who wins a second major this year?");
    expect(written).toContain("Can Alcaraz win a second major this year?");
    // All three riff variants really rendered — a panel that fell back to the
    // default would look plausible and prove nothing.
    for (const variant of ["labelled", "sentence", "dot"]) {
      expect(written).toContain(`data-variant="${variant}"`);
    }
  });
});
