// #4646 after-check — the "Bigger Picture" rail does not re-answer the hero's question.
//
//   node tools/ux1349-own-moneyline-not-related-4646.mjs [eventId]
//   default: 15314525   (Zhao–Ma, the frame in artifacts/ux-1349)
//
// Exit 0 = PAID · 3 = the defect is still on production · 4 = UNPAID, this event's payload
// carries no bare-matchup market so there was nothing to check (NOT a pass) · 5 = could not
// read the page.
//
// 🔴 SUBJECT DETECTION IS KEYED ON THE PAYLOAD, NEVER ON THE DEFECT'S MARKUP. The subject is
// "this event's own moneyline exists in `related-futures`", which is a property of the
// backend and is TRUE on both sides of the fix. A probe that looked for the offending CARD
// to decide whether the page was in scope would report every repaired page as "no subject"
// and print green on a page it never examined.
//
// 🔴 THE OFFENDER IS IDENTIFIED BY MARKET ID, NOT BY LABEL OR PRICE. Every rail tile links
// to `/futures/{market_id}`, so the reading is an id join against the payload's own rows.
// Labels are ellipsised at display width and prices move between the probe's read and the
// page's, and both of those would make a text/price match flap. On 15314529 two different
// surviving markets print "Nika Radisic" within one point of the dropped leg's price.
//
// 🔴 THE PREDICATE IS RESTATED HERE ON PURPOSE. Importing `isEventOwnMoneylineMarket` would
// make the probe agree with the code under test by construction; this is a second, simpler
// reading of the same question (both sides named, different sides).
//
// 🪤 SPECIMENS ROTATE. Qualifying draws re-price and finish within hours. Exit 4 is the
// common outcome on a stale id — find a live one with:
//
//   curl -s "$BAINLUCK_API/api/events?sport=tennis_wta&limit=40" | python3 -c "..."
//   (any league works; NHL and EPL carried 2–3 legs per event on 2026-09-19)
//
// 🪤 Node's global `fetch` has no egress in a lane shell, and neither does `page.request`.
// The payload read therefore happens INSIDE the page context, from the site's own origin.

import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";

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

const eventId = process.argv[2] || "15314525";
const url = `https://bainluck.com/events/${eventId}`;
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
const args = ["--single-process"];
if (proxy) args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>");

const browser = await chromium.launch({ args });
let code = 5;
try {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  // NOT `networkidle` — a live event page polls forever.
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(4000);

  const read = await page.evaluate(async (id) => {
    const payload = await fetch(`https://api.bainluck.com/api/events/${id}/related-futures`).then(
      (r) => r.json(),
    );

    const fold = (v) =>
      (v ?? "")
        .toLowerCase()
        .replace(/[.,]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    const namesSide = (label, team) => {
      const l = fold(label);
      const t = fold(team);
      if (!l || !t) return false;
      return l === t || t.startsWith(l + " ") || t.endsWith(" " + l);
    };
    const isOwn = (name) => {
      const m = (name ?? "").trim().match(/^(.+?)\s+(?:vs\.?|v\.?|at|@)\s+(.+)$/i);
      if (!m) return false;
      const [, a, b] = m;
      return (
        (namesSide(a, payload.away_team) && namesSide(b, payload.home_team)) ||
        (namesSide(a, payload.home_team) && namesSide(b, payload.away_team))
      );
    };

    const rows = [
      ...(payload.home_team_futures ?? []),
      ...(payload.away_team_futures ?? []),
    ];
    const own = rows
      .filter((r) => r.display_category === "game_prop" && isOwn(r.market_name))
      .map((r) => ({
        market_id: r.market_id,
        market_name: r.market_name,
        outcome_name: r.outcome_name,
        pct: r.probability == null ? null : Math.round(r.probability * 100),
      }));

    // The rail, located by its own heading rather than by a class that could be restyled.
    const heading = [...document.querySelectorAll("h3")].find(
      (h) => (h.textContent || "").trim() === "Bigger Picture",
    );
    const rail = heading ? heading.closest("div").parentElement.parentElement : null;
    const tiles = rail
      ? [...rail.querySelectorAll('a[href^="/futures/"]')].map((a) => ({
          marketId: Number(a.getAttribute("href").split("/").pop()),
          text: (a.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60),
        }))
      : [];

    const hero = (document.body.textContent || "")
      .replace(/\s+/g, " ")
      .match(/(\d+)\s*%\s*[–-]\s*(\d+)\s*%/);

    return {
      home: payload.home_team,
      away: payload.away_team,
      totalRows: rows.length,
      own,
      railDrew: !!rail,
      tiles,
      hero: hero ? `${hero[1]}% – ${hero[2]}%` : null,
    };
  }, eventId);

  console.log(`url=${url} width=390`);
  console.log(`  ${read.away} @ ${read.home}   hero: ${read.hero ?? "(not read)"}`);
  console.log(`  related-futures rows: ${read.totalRows}   this event's own moneyline legs: ${read.own.length}`);
  for (const r of read.own) {
    console.log(`      own leg  market ${r.market_id}  "${r.market_name}" — ${r.outcome_name} ${r.pct}%`);
  }
  console.log(`  rail drew: ${read.railDrew}   tiles in it: ${read.tiles.length}`);

  if (read.own.length === 0) {
    console.log(
      "\nUNPAID — this event's payload carries no bare-matchup market, so nothing was\n" +
        "checked. Specimens rotate within hours; find a scheduled fixture on any league and\n" +
        "re-run. This is NOT a pass.",
    );
    code = 4;
  } else {
    const ownIds = new Set(read.own.map((r) => r.market_id));
    const offenders = read.tiles.filter((t) => ownIds.has(t.marketId));
    if (offenders.length > 0) {
      console.log(`\n🔴 STILL ON PRODUCTION — ${offenders.length} rail tile(s) are this event's own question:`);
      for (const o of offenders) console.log(`      /futures/${o.marketId}  ${o.text}`);
      code = 3;
    } else {
      console.log(
        `\n✅ PAID — the payload offers ${read.own.length} leg(s) of this event's own market and the\n` +
          `rail prints none of them. Hero answers the question once.`,
      );
      code = 0;
    }
  }
} catch (err) {
  console.log(`could not read the page: ${err.message}`);
  code = 5;
} finally {
  await browser.close();
}
process.exit(code);
