/**
 * UX-P159 — THE CARD THAT DID NOT ADD UP NOW SAYS WHY, for Alex's eyeball.
 *
 * ═══ WHAT THIS IS ═══
 *
 * UX-P113 (#2060) fixed the two-outcome card that SHOULD total 100 — Alex's
 * 08-20 gold card printed `93% + 8% = 101%` and now prints 93 / 7. INT-104 then
 * measured that queue's own deploy check in production and got **17 of 18**, and
 * filed #2088 about the one that missed: `Bilardo vs Gschwendtner`, served
 * `57 / 40`, with nothing on the card saying why.
 *
 * That card is not a bug. `is_complement_pair` refused it correctly, because
 * forcing 0.97 to 1.00 would invent three points of probability rather than
 * round one. The defect is that the reader cannot tell it apart from the bug we
 * had just fixed — **an unexplained non-100 is the defect; a labelled one is a
 * fact.**
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * Every card here is the SHIPPED `LabelingCard` component with the app's own
 * compiled stylesheet, and every number comes from
 * `tests/fixtures/labeling_card_trio_20260821.json` — the LIVE output of
 * `GET /api/admin/ranking-judgments/candidates?limit=100`, captured against
 * production `ec636bae`. Nothing on this page is drawn by hand.
 *
 *   • Panel 1 — the card as it renders today, from the fixture's own row.
 *   • Panel 2 — the same row with the served reason, which is what deploys.
 *   • Panel 3 — the WHOLE two-outcome pool, so the density of the change is
 *     visible rather than asserted: how many cards gain a line, and how many
 *     deliberately do not.
 *
 * The one thing the fixture cannot supply is an unpriced side (every captured
 * row is fully priced), so that card is marked SYNTHETIC on the page rather than
 * quietly mixed in — the discipline UX-P158's rig had to learn the hard way.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=cardSumReasonCapture
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig works, same as the other capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import LabelingCard, {
  type LabelingCardData,
} from "@/components/admin/LabelingCard";
import { CARD_SUM_EXPLANATION } from "@/lib/cardSum";
import {
  SUM_INDEPENDENT_PRICES,
  SUM_UNPRICED_OUTCOME,
  cardSum,
  cardSumReason,
  renderedCardPercents,
} from "@/lib/renderedPercent";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const POOL_PATH = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "labeling_card_trio_20260821.json"
);

/** The card #2088 names. */
const FILED_EXEMPLAR_ID = 59194098;

interface PoolOutcome {
  name: string | null;
  probability: number | null;
}
interface PoolRow {
  id: number;
  name: string;
  category?: string;
  source?: string;
  top_outcomes: PoolOutcome[];
}

function pool(): PoolRow[] {
  return JSON.parse(fs.readFileSync(POOL_PATH, "utf8")).items as PoolRow[];
}

function twoOutcome(): PoolRow[] {
  return pool().filter((r) => r.top_outcomes.length === 2);
}

/** A pool row → the card the surface actually serves, with the reason attached. */
function cardFor(row: PoolRow): LabelingCardData {
  const probabilities = row.top_outcomes.map((o) => o.probability);
  const percents = renderedCardPercents(probabilities);
  return {
    name: row.name,
    source: row.source ?? "kalshi",
    category: row.category ?? "—",
    image_url: null,
    hook_description: null,
    rendered_probability: probabilities[0],
    commence_time: null,
    resolution_date: null,
    top_outcomes: row.top_outcomes.map((o, i) => ({
      name: o.name,
      probability: o.probability,
      rendered_percent: percents[i],
    })),
    card_sum_reason: cardSumReason(probabilities),
  };
}

/**
 * The card as the PREVIOUS build drew it.
 *
 * It cannot be produced by handing this component a card — an absent
 * `card_sum_reason` makes it DERIVE the reason (that fallback is deliberate, so a
 * tab holding a pre-deploy payload still explains itself), and a `null` would be
 * a lie, since null now means "the server checked and these total 100".
 *
 * So BEFORE is reconstructed by removing the one element this queue added, which
 * is a faithful reconstruction precisely because that element IS the whole
 * change to the component. The caller asserts that exactly one was removed —
 * a strip that silently matched nothing would render an identical "before" and
 * turn the comparison into theatre.
 */
function stripExplanation(markup: string): string {
  const stripped = markup.replace(
    /<p class="[^"]*" data-testid="card-sum-explanation">.*?<\/p>/g,
    ""
  );
  if (stripped === markup) throw new Error("nothing stripped — BEFORE is not a before");
  return stripped;
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

const html = (data: LabelingCardData) =>
  renderToStaticMarkup(<LabelingCard card={data} />);

/** How many of these cards print an explanation. */
function explained(rows: PoolRow[]): number {
  return rows.filter((r) =>
    html(cardFor(r)).includes('data-testid="card-sum-explanation"')
  ).length;
}

describe("UX-P159 — the non-100 card explains itself", () => {
  it("the fixture still contains the card the issue was filed about", () => {
    // If this stops holding, every panel below is rendering something else.
    const rows = twoOutcome();
    expect(rows.length).toBe(17);
    const exemplar = rows.find((r) => r.id === FILED_EXEMPLAR_ID);
    expect(exemplar).toBeDefined();
    const probabilities = exemplar!.top_outcomes.map((o) => o.probability);
    expect(renderedCardPercents(probabilities)).toEqual([57, 40]);
    expect(cardSum(probabilities)).toBe(97);
    expect(cardSumReason(probabilities)).toBe(SUM_INDEPENDENT_PRICES);
  });

  it("BEFORE prints the numbers and no reason; AFTER prints both", () => {
    const exemplar = twoOutcome().find((r) => r.id === FILED_EXEMPLAR_ID)!;
    const after = html(cardFor(exemplar));
    const before = stripExplanation(after);

    // The numbers are IDENTICAL. This queue explains the card; it does not
    // normalize it, and a rig that quietly fixed the numbers would be selling a
    // different change from the one that ships.
    const nums = (markup: string) =>
      [...markup.matchAll(/>(\d+)%</g)].map((m) => Number(m[1]));
    expect(nums(before)).toEqual(nums(after));
    expect(nums(after).slice(1).reduce((a, b) => a + b, 0)).toBe(97);

    expect(before).not.toContain('data-testid="card-sum-explanation"');
    expect(after).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("exactly ONE of the 17 pool cards gains a line — the change is not wallpaper", () => {
    // The density question, answered against the real capture rather than
    // guessed. Alex already has an open taste call about how loud the
    // illiquidity mark is on a grid; this one had better not be loud at all.
    const rows = twoOutcome();
    expect(rows.length).toBe(17);
    expect(explained(rows)).toBe(1);
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) return;

    const css = appStylesheet();
    const rows = twoOutcome();
    const exemplar = rows.find((r) => r.id === FILED_EXEMPLAR_ID)!;

    const synthetic: LabelingCardData = {
      name: "A question with only one side quoted",
      source: "polymarket",
      category: "tennis",
      image_url: null,
      hook_description: null,
      rendered_probability: 0.57,
      commence_time: null,
      resolution_date: null,
      top_outcomes: [
        { name: "Yes", probability: 0.57, rendered_percent: 57 },
        { name: "No", probability: null, rendered_percent: null },
      ],
      card_sum_reason: SUM_UNPRICED_OUTCOME,
    };

    const poolRow = (row: PoolRow) => {
      const probabilities = row.top_outcomes.map((o) => o.probability);
      const total = cardSum(probabilities);
      const reason = cardSumReason(probabilities);
      return `<tr class="${reason ? "hit" : ""}">
        <td class="mono">${row.id}</td>
        <td>${row.name}</td>
        <td class="mono num">${renderedCardPercents(probabilities).join(" / ")}</td>
        <td class="mono num"><b>${total}</b></td>
        <td>${reason ? CARD_SUM_EXPLANATION[reason as keyof typeof CARD_SUM_EXPLANATION] : "<span class='q'>— totals 100, nothing to say</span>"}</td>
      </tr>`;
    };

    const page = `<!doctype html><html><head><meta charset="utf-8">
<title>UX-P159 — a card that does not add up says why (#2088)</title>
<style>${css}</style>
<style>
  body { font: 14px/1.5 ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 32px; background: #fafafa; color: #111; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: #666; margin: 0 0 28px; max-width: 70ch; }
  .panel { margin: 0 0 34px; }
  .ph { font: 600 12px/1 ui-monospace, monospace; letter-spacing: .08em; color: #444; text-transform: uppercase; margin: 0 0 10px; }
  .pn { color: #666; margin: 0 0 12px; max-width: 76ch; font-size: 13px; }
  .cards { display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-start; }
  .cw { width: 340px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }
  th, td { border-bottom: 1px solid #e6e6e6; padding: 7px 9px; text-align: left; vertical-align: top; }
  th { background: #f2f2f2; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #555; }
  .mono { font-family: ui-monospace, monospace; }
  .num { text-align: right; white-space: nowrap; }
  tr.hit td { background: #fff8e6; }
  .q { color: #999; }
  .syn { border-left: 3px solid #d0a000; padding-left: 10px; color: #7a5c00; background: #fffbeb; font-size: 13px; margin: 0 0 12px; }
  .banner { border-top: 2px solid #111; padding-top: 12px; margin-top: 30px; font-size: 13px; max-width: 86ch; }
</style></head><body>
<h1>A two-outcome card that does not add up to 100 now says why</h1>
<p class="sub">#2088. Every card below is the shipped <code>LabelingCard</code> component with the app's own
compiled stylesheet, and every number comes from the live capture of
<code>/api/admin/ranking-judgments/candidates?limit=100</code> taken against production <code>ec636bae</code>.
Nothing here is drawn by hand.</p>

<div class="panel">
  <div class="ph">1 · What the card shows right now</div>
  <p class="pn">Market ${FILED_EXEMPLAR_ID}, the card #2088 was filed about. It prints 57 and 40. They add to 97,
  and the card says nothing about it — which looks exactly like the <b>93 + 8 = 101</b> bug UX-P113 had just fixed.
  A reader cannot tell the two apart, and that is the whole defect.
  <br><i>Reconstructed by removing the one element this queue adds — which is the whole change to the component —
  and the rig fails if that removal matches nothing.</i></p>
  <div class="cards"><div class="cw">${stripExplanation(html(cardFor(exemplar)))}</div></div>
</div>

<div class="panel">
  <div class="ph">2 · What it shows once this deploys</div>
  <p class="pn">The same card, the same two numbers — <b>unchanged, deliberately</b>. Forcing 0.97 up to 1.00 would
  invent three points of probability rather than round one, so the numbers stay and the card explains itself instead.</p>
  <div class="cards"><div class="cw">${html(cardFor(exemplar))}</div></div>
</div>

<div class="panel">
  <div class="ph">3 · The other reason, and it is a different fact</div>
  <p class="syn"><b>SYNTHETIC:</b> every card in the live capture is fully quoted, so this one is made up to show the
  second sentence. The numbers on it are not measured; the sentence is the shipped one.</p>
  <p class="pn">A card with one side missing is not a card whose two sides disagree. Folding them into one sentence
  would tell the reader "these two do not add up" about a card carrying a single number.</p>
  <div class="cards"><div class="cw">${html(synthetic)}</div></div>
</div>

<div class="panel">
  <div class="ph">4 · How loud this is, across the whole captured pool</div>
  <p class="pn">All <b>${rows.length}</b> two-outcome cards in the capture. <b>One</b> gains a line; the other
  ${rows.length - 1} total 100 already and stay silent. That ratio is the answer to "does this become wallpaper" —
  an explanation on a correct card would be worse than the unexplained card this removes.</p>
  <table>
    <thead><tr><th>market</th><th>question</th><th class="num">renders</th><th class="num">total</th><th>what the card says</th></tr></thead>
    <tbody>${rows.map(poolRow).join("")}</tbody>
  </table>
</div>

<div class="banner"><b>What did not change:</b> not one number on any card. #2060's complement rule still forces the
two sides of one question to 100, and this queue does not touch it. The only thing added is a sentence on the cards
whose numbers genuinely do not add up — and, on the payload, a machine-readable reason so the count of
<i>unexplained</i> non-100 cards can be asserted at zero.</div>
</body></html>`;

    const out = path.join(dir, "p159-card-sum-reason.html");
    fs.writeFileSync(out, page, "utf8");

    // THE RIG ASSERTS ITS OWN ARTIFACT. A capture that wrote an empty file, or
    // one whose panels silently lost the thing they exist to show, would look
    // like a pass and read like a ship (UX-P157's lesson).
    const written = fs.readFileSync(out, "utf8");
    expect(written.length).toBeGreaterThan(15_000);
    expect(written).toContain("1 · What the card shows right now");
    expect(written).toContain("2 · What it shows once this deploys");
    expect(written).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    expect(written).toContain(CARD_SUM_EXPLANATION[SUM_UNPRICED_OUTCOME]);
    // The stylesheet is the app's, not a hand-rolled approximation.
    expect(css.length).toBeGreaterThan(1_000);
    // Panel 1 must genuinely lack the sentence, or the before/after is theatre.
    const panel1 = written.split("2 · What it shows once this deploys")[0];
    expect(panel1).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    // And the pool table must carry every row, with exactly one highlighted.
    expect((written.match(/<tr class="hit">/g) ?? []).length).toBe(1);
  });
});
