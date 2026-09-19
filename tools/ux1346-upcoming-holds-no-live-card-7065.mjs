/**
 * #7065 AFTER-CHECK — does a card reading `● LIVE` still sit under `📅 Upcoming`?
 *
 * The defect is a DISAGREEMENT between two things on one screen, so the probe
 * reads both out of the live DOM and compares them. It does not ask whether the
 * bucketer is "correct" in the abstract — it asks the reader's question: is
 * there a card claiming to be live inside a section headed Upcoming.
 *
 * ── THE THREE TRAPS THIS IS BUILT AROUND ─────────────────────────────────────
 *
 * 1. SUBJECT DETECTION IS NOT KEYED ON THE DEFECT. If it were — "find a LIVE
 *    badge under Upcoming, and if there is none report subject-missing" — then
 *    a working fix and an empty page would be indistinguishable, and the probe
 *    would call a shipped fix an absent subject. So the subject is "a tournament
 *    card whose badge says LIVE, ANYWHERE on the page". After the fix that card
 *    still exists; it is under Live Now. No such card at all ⇒ exit 4, because
 *    golf tournaments come and go and a Tuesday has none.
 *
 * 2. ANCESTRY, NOT A PREFIX. Production serves the MERGE COMMIT, so comparing
 *    the deployed commit to a BRANCH sha with `startsWith` can only ever say
 *    NOT-LIVE. "Does the deployed tree contain this commit" is a git question.
 *
 * 3. THE SECTION IS READ FROM THE HEADING DOWN, not from a class name. The
 *    heading text is what the reader sees and what the issue photographed; a
 *    probe keyed on internal markup reports "subject missing" the day someone
 *    renames a wrapper.
 *
 * Usage:
 *   SHA=<branch sha> node tools/ux1346-upcoming-holds-no-live-card-7065.mjs
 *   node tools/ux1346-upcoming-holds-no-live-card-7065.mjs --no-deploy-gate   # read it now
 *
 * Exit 0  every LIVE card is under a live heading — paid.
 * Exit 3  a LIVE card is still under Upcoming — the defect is on production.
 * Exit 4  NOT PAYABLE: not deployed, or no tournament is live right now. NOT a pass.
 * Exit 5  the probe could not read the page at all (no sections found).
 */
import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";
import { execFileSync } from "child_process";

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return process.cwd() + "/";
}
const { chromium } = createRequire(findPlaywright())("playwright");

const SITE = process.env.SITE || "https://bainluck.com";
const SHA = process.env.SHA || "";
const noGate = process.argv.includes("--no-deploy-gate");

// ── The deployment must carry the sha under test (trap 2) ────────────────────
if (SHA && !noGate) {
  let deployed = "";
  try {
    const r = await fetch(`${SITE}/api/frontend-build`);
    deployed = (await r.json()).commit || "";
  } catch (e) {
    console.error(`could not read ${SITE}/api/frontend-build: ${e.message}`);
    process.exit(4);
  }
  let carries = false;
  try {
    execFileSync("git", ["merge-base", "--is-ancestor", SHA, deployed], { stdio: "ignore" });
    carries = true;
  } catch {
    carries = false;
  }
  if (!carries) {
    console.log(JSON.stringify({ verdict: "NOT-LIVE", deployed, expected: SHA }, null, 2));
    console.error(`\nDeployment is on ${deployed}, which does not contain ${SHA}. Nothing graded.`);
    process.exit(4);
  }
  console.error(`deployment ${deployed} contains ${SHA} — payable`);
}

const args = ["--single-process", "--no-sandbox"];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>");

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  extraHTTPHeaders: { "x-bainluck-origin": "ux" },
});

await page.goto(`${SITE}/sports`, { waitUntil: "networkidle", timeout: 60000 });
await page.waitForTimeout(3000);
// The feed pages in; walk the whole thing so later sections exist in the DOM.
await page.evaluate(async () => {
  for (let y = 0; y < 12; y++) {
    window.scrollBy(0, window.innerHeight);
    await new Promise((r) => setTimeout(r, 350));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(1500);

const read = await page.evaluate(() => {
  // The reader's own anchors: the section headings, by their visible text.
  const headings = [...document.querySelectorAll("h2, h3")]
    .map((h) => ({ el: h, text: (h.textContent || "").replace(/\s+/g, " ").trim() }))
    .filter((h) => /Live Now|Upcoming|Just Happened|Top Markets/i.test(h.text));
  if (headings.length === 0) return { readable: false };

  // A section owns every card between its heading and the next one. Walking the
  // flat document order is deliberate: it does not care how the wrappers nest,
  // which is what the reader's eye does too.
  const all = [...document.querySelectorAll("*")];
  const indexOf = (el) => all.indexOf(el);
  const bounds = headings.map((h, i) => ({
    text: h.text,
    from: indexOf(h.el),
    to: i + 1 < headings.length ? indexOf(headings[i + 1].el) : all.length,
  }));

  // A tournament card: the golf/tour label the card prints for itself.
  const TOUR = /PGA Tour|Korn Ferry|LPGA|DP World|European Tour|Champions Tour|Ryder Cup|Presidents Cup/i;

  /**
   * The card a node belongs to: the nearest ancestor that is a link or article.
   * Walking UP from the badge is what fixed the first cut of this probe — a
   * top-down scan over `a, article, div` with a containment dedup found ONE of
   * the two live tournament cards a screenshot of the same page showed. An
   * under-counting probe is safe on a RED verdict and dangerous on a GREEN one:
   * it would have reported PAID while a second card was still misfiled.
   */
  const cardOf = (node) => {
    let el = node;
    for (let i = 0; i < 12 && el; i++) {
      if (el.matches && el.matches("a[href], article")) return el;
      el = el.parentElement;
    }
    return node.parentElement || node;
  };

  const sectionOf = (el) => {
    const i = indexOf(el);
    const sec = bounds.find((b) => i > b.from && i < b.to);
    return sec ? sec.text : "(no section)";
  };

  // Every live badge on the page — the pulsing dot IS the card's claim to be
  // live. Keyed on the claim, not on the defect, so the subject survives the fix.
  const badges = [...document.querySelectorAll(".animate-pulse")].map((dot) => {
    const card = cardOf(dot);
    const text = (card.textContent || "").replace(/\s+/g, " ").trim();
    return { section: sectionOf(card), text: text.slice(0, 160), tournament: TOUR.test(text) };
  });

  // Every tournament card, live or not — the denominator, so the output says
  // how much of the page the probe actually saw.
  const seen = [];
  for (const node of document.querySelectorAll("a[href], article")) {
    const t = (node.textContent || "").replace(/\s+/g, " ").trim();
    if (!t || t.length > 600 || !TOUR.test(t)) continue;
    if (seen.some((s) => s.el.contains(node) || node.contains(s.el))) continue;
    seen.push({ el: node, text: t });
  }

  return {
    readable: true,
    sections: bounds.map((b) => b.text),
    badges,
    tournamentCards: seen.map((s) => ({
      section: sectionOf(s.el),
      text: s.text.slice(0, 120),
      live: !!s.el.querySelector(".animate-pulse"),
    })),
  };
});

await browser.close();

if (!read.readable) {
  console.error("no feed section headings on /sports — the probe read nothing.");
  process.exit(5);
}

const liveTournaments = read.badges.filter((b) => b.tournament);
const misfiled = liveTournaments.filter((b) => /Upcoming/i.test(b.section));
// Not this ship (tournaments are), but a LIVE game under Upcoming is CERT-786's
// class and the probe is already holding the answer — so it reports rather than
// discards it.
const misfiledGames = read.badges.filter((b) => !b.tournament && /Upcoming/i.test(b.section));

console.log(
  JSON.stringify(
    {
      sections: read.sections,
      tournamentCardsSeen: read.tournamentCards.length,
      liveBadges: read.badges.length,
      liveTournamentBadges: liveTournaments.length,
      misfiled: misfiled.map((b) => ({ section: b.section, text: b.text })),
      placements: liveTournaments.map((b) => ({ section: b.section, text: b.text })),
      tournamentCards: read.tournamentCards,
      alsoNoted_liveNonTournamentUnderUpcoming: misfiledGames.map((b) => b.text),
    },
    null,
    2,
  ),
);

// Subject (trap 1): a LIVE tournament card must exist SOMEWHERE, or there is
// nothing to grade tonight. This is exit 4, never a pass.
if (liveTournaments.length === 0) {
  console.error(
    `\nNOT PAYABLE: ${read.tournamentCards.length} tournament card(s) on /sports and none claims ` +
      `to be live right now. No specimen — re-run during a tournament.`,
  );
  process.exit(4);
}

if (misfiled.length > 0) {
  console.error(
    `\n✖ DEFECT STILL ON PRODUCTION: ${misfiled.length} tournament card(s) reading LIVE under an Upcoming heading:`,
  );
  for (const m of misfiled) console.error(`   [${m.section}] ${m.text}`);
  process.exit(3);
}

console.error(
  `\n✓ PAID: ${liveTournaments.length} live tournament card(s), every one under a live heading ` +
    `(${[...new Set(liveTournaments.map((b) => b.section))].join(", ")}).`,
);
if (misfiledGames.length > 0) {
  console.error(
    `  (noted, not this ship: ${misfiledGames.length} live NON-tournament card(s) under Upcoming.)`,
  );
}
process.exit(0);
