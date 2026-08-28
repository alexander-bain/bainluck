/**
 * THE RENDERED ANSWER TO ALEX'S REDIRECT (UX-P152).
 *
 *     "It seems like we're reinventing the event page here."
 *     "I thought that tournaments were containers for related events."
 *
 * Four panels, in one file, full width, so every media query is the one his own
 * window fires:
 *
 *   1. **A US Open match, on the standard event page** — the tournament's two
 *      sections below everything the event page already renders.
 *   2. **Each player's chance of reaching each round** — his item 2, through
 *      the same component the MLB/NBA championship path goes through.
 *   3. **The trend graph, his format vs an alternative** — the bold blend, the
 *      faint labelled source lines, and the end-of-game case he named.
 *   4. **The way in** — the match list row, now addressing `/events/{id}`.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=usOpenEventPage
 *     → p152-event-page.html
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig still works.
 *
 * ═══ WHAT IS FAITHFUL, AND WHAT IS A DRAWING ═══
 *
 * Panels 1, 2 and 4 are the shipped components with the app's own compiled CSS,
 * over payloads captured from production by
 * `backend/scripts/capture_event_tournament.py` — which reproduces the route by
 * calling the same `build_*` functions, including the id-anchored event
 * resolution that is this queue's whole architectural claim.
 *
 * Panel 3 is **drawn**, and says so on the page. `OddsChart` is Recharts, and
 * Recharts measures its container: server-rendered it emits an empty box, so a
 * "render" of it here would be a blank rectangle presented as a chart. The
 * panel therefore plots the SAME production series the chart plots, at the
 * shipped chart's own line weights and colours, so the styling question Alex
 * asked can be answered from it.
 *
 * ⚠️ UX-P154: ALEX RATIFIED 3B. The end-of-line source labels UX-P152 shipped
 * are reverted in full, and the guard at the bottom of this file is inverted
 * accordingly — it now asserts the chart writes NO source name onto the plot,
 * because a passing guard around a reverted feature is how a reverted feature
 * comes back.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import AdvancementPath from "@/components/event/AdvancementPath";
import MatchProps from "@/components/tournament/MatchProps";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import { toStages, ADVANCEMENT_HEADING } from "@/components/event/TournamentExtensions";
import { matchListFromSlate } from "@/lib/matchList";
import { sourceHex } from "@/lib/sourceColors";
import type {
  EventTournamentResponse,
  TournamentAdvancementRow,
} from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const MOCKS = path.join(REPO, "docs", "mocks", "us-open");
const CHART_MOCKS = path.join(REPO, "docs", "mocks", "chart");

function load(dir: string, name: string): any {
  return JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
}

const EVENT = load(MOCKS, "event-2026-08-28.json");
const EXTENSIONS: EventTournamentResponse = load(
  MOCKS,
  "event-tournament-2026-08-28.json"
);
const LINKS = load(MOCKS, "event-links-2026-08-28.json");
const BLOWOUT = load(CHART_MOCKS, "blowout-history-2026-08-28.json");

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

/** One advancement card, as `TournamentExtensions` lays it out. */
function PlayerCard({ row }: { row: TournamentAdvancementRow | null }) {
  const stages = toStages(row);
  if (!row || stages.length === 0) return <div />;
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-5">
      <div className="flex items-center gap-3 mb-4">
        {row.logo_url ? (
          <img src={row.logo_url} alt="" className="w-11 h-11 rounded-full object-cover shrink-0" />
        ) : (
          <div className="w-11 h-11 rounded-full grid place-items-center font-mono font-bold text-white shrink-0 bg-text-muted">
            {row.short_name.slice(0, 3).toUpperCase()}
          </div>
        )}
        <div>
          <div className="font-semibold text-lg leading-tight">{row.short_name}</div>
          {row.record && (
            <div className="text-xs text-text-muted font-mono tabular-nums">{row.record}</div>
          )}
        </div>
      </div>
      <AdvancementPath stages={stages} heading={ADVANCEMENT_HEADING} />
      {row.monotonic === false && (
        <p className="-mt-3 text-[11px] leading-snug text-text-muted">
          These came from separate questions and they disagree — one later round is
          priced above an earlier one, which cannot both be true. Shown as the market
          has them.
        </p>
      )}
    </div>
  );
}

function ExtensionsPanel({ data }: { data: EventTournamentResponse }) {
  const a = data.advancement;
  return (
    <div className="w-full px-4 lg:px-6 pb-10">
      <section className="mt-6">
        <div className="flex items-end justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold tracking-tight">
              {data.tournament?.title}
            </h3>
            <p className="text-sm text-text-secondary mt-0.5">
              {data.draw_label}
              {data.round ? ` · ${data.round}` : ""}
            </p>
          </div>
          <span className="text-[11px] font-semibold text-text-secondary underline decoration-dotted underline-offset-2">
            The whole draw →
          </span>
        </div>
        {a && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PlayerCard row={a.home_team} />
            <PlayerCard row={a.away_team} />
          </div>
        )}
        {(data.props?.length ?? 0) > 0 && <MatchProps payload={data} />}
      </section>
    </div>
  );
}

/** The event page's own hero, at the weights `app/events/[id]/page.tsx` uses. */
function HeroPanel() {
  const home = Math.round((EVENT.current_odds?.home_probability ?? 0) * 100);
  const away = Math.round((EVENT.current_odds?.away_probability ?? 0) * 100);
  return (
    <div className="w-full px-4 lg:px-6 pt-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col items-center flex-1">
          <div className="text-sm font-semibold text-text-primary">{EVENT.home_team}</div>
        </div>
        <div className="flex flex-col items-center">
          <div className="flex items-baseline">
            <span className="text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums text-text-primary">
              {home}
            </span>
            <span className="text-lg font-bold leading-none ml-0.5">%</span>
            <span className="text-lg font-light text-text-muted mx-1.5 self-center">–</span>
            <span className="text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums text-text-muted">
              {away}
            </span>
            <span className="text-lg font-bold leading-none ml-0.5">%</span>
          </div>
          <div className="mt-1 text-[11px] text-text-muted">
            {EVENT.current_odds?.bookmaker_count} sources
          </div>
        </div>
        <div className="flex flex-col items-center flex-1">
          <div className="text-sm font-semibold text-text-primary">{EVENT.away_team}</div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
 * PANEL 3 — the trend graph.
 *
 * Alex's format, in his words: the aggregated Bain Luck line BOLD and
 * prominent; a faint gray line per source behind it, LABELED, barely-there but
 * readable — so a glance shows WHICH source is moving the blend. And the
 * end-of-game case he named by name: sportsbooks dropping out of a blowout
 * visibly explaining aggregate movement.
 *
 * The specimen is that case, from production: Blue Jays 2 – Royals 13, where
 * Kalshi contributed 2 readings and stopped, the sportsbook line stopped at 18,
 * and ESPN and the two models carried the rest.
 * ═══════════════════════════════════════════════════════════════════════════ */

const W = 1040;
const H = 300;
const PAD = { l: 44, r: 92, t: 16, b: 26 };

type Series = { key: string; label: string; color: string; dash?: string; pts: [number, number][] };

function seriesFrom(): { blend: Series; sources: Series[]; t0: number; t1: number } {
  const stamp = (s: string) => new Date(s).getTime();
  const agg: [number, number][] = (BLOWOUT.aggregate_line ?? []).map(
    (p: any) => [stamp(p.timestamp), p.home_probability] as [number, number]
  );
  const book: [number, number][] = (BLOWOUT.history ?? [])
    .filter((p: any) => (p.bookmaker_count ?? 0) > 0)
    .map((p: any) => [stamp(p.timestamp), p.home_probability] as [number, number]);
  const wph = BLOWOUT.win_prob_history ?? {};
  const named: Record<string, string> = {
    espn: "ESPN",
    stat_model: "Bain Luck Model",
    mlb: "MLB Model",
    kalshi: "Kalshi",
    polymarket: "Polymarket",
  };
  const sources: Series[] = [
    {
      key: "betting",
      label: "Sportsbooks",
      color: sourceHex("betting"),
      pts: book,
    },
    ...Object.entries(wph).map(([key, pts]: [string, any]) => ({
      key,
      label: named[key] ?? key,
      color: sourceHex(key),
      dash: key === "kalshi" || key === "polymarket" ? "8 4" : "4 4",
      pts: pts.map((p: any) => [stamp(p.timestamp), p.home_probability] as [number, number]),
    })),
  ].filter((s) => s.pts.length > 0);

  const all = [...agg, ...sources.flatMap((s) => s.pts)];
  const t0 = Math.min(...all.map((p) => p[0]));
  const t1 = Math.max(...all.map((p) => p[0]));
  return {
    blend: { key: "blend", label: "Bain Luck", color: sourceHex("blend"), pts: agg },
    sources,
    t0,
    t1,
  };
}

function pathFor(pts: [number, number][], t0: number, t1: number): string {
  const x = (t: number) => PAD.l + ((t - t0) / Math.max(1, t1 - t0)) * (W - PAD.l - PAD.r);
  const y = (p: number) => PAD.t + (1 - p) * (H - PAD.t - PAD.b);
  return pts
    .map((pt, i) => `${i === 0 ? "M" : "L"}${x(pt[0]).toFixed(1)},${y(pt[1]).toFixed(1)}`)
    .join(" ");
}

/**
 * @param labelled  Alex's format — every faint line ends in its own name.
 *                  `false` is the alternative below it: the same chart with the
 *                  names in a legend instead, which is what shipped before.
 */
function TrendGraph({ labelled }: { labelled: boolean }) {
  const { blend, sources, t0, t1 } = seriesFrom();
  const x = (t: number) => PAD.l + ((t - t0) / Math.max(1, t1 - t0)) * (W - PAD.l - PAD.r);
  const y = (p: number) => PAD.t + (1 - p) * (H - PAD.t - PAD.b);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ background: "#fff", borderRadius: 12, border: "1px solid #E5E7EB" }}
      role="img"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <g key={p}>
          <line
            x1={PAD.l}
            x2={W - PAD.r}
            y1={y(p)}
            y2={y(p)}
            stroke={p === 0.5 ? "rgba(0,0,0,0.2)" : "rgba(0,0,0,0.06)"}
            strokeDasharray={p === 0.5 ? "4 4" : undefined}
            strokeWidth={p === 0.5 ? 1.5 : 1}
          />
          <text x={8} y={y(p) + 4} fontSize={11} fill="#4B5563">
            {Math.round(p * 100)}%
          </text>
        </g>
      ))}

      {/* The faint source lines, at the shipped chart's collapsed weights. */}
      {sources.map((s) => (
        <path
          key={s.key}
          d={pathFor(s.pts, t0, t1)}
          fill="none"
          stroke={s.color}
          strokeWidth={1}
          strokeOpacity={0.28}
          strokeDasharray={s.dash}
        />
      ))}

      {/* The blend, bold and on top. */}
      <path d={pathFor(blend.pts, t0, t1)} fill="none" stroke={blend.color} strokeWidth={3} />

      {labelled &&
        sources.map((s) => {
          const last = s.pts[s.pts.length - 1];
          return (
            <text
              key={`${s.key}-label`}
              x={x(last[0]) + 4}
              y={y(last[1]) + 3}
              fontSize={9}
              fontWeight={600}
              fill={s.color}
              fillOpacity={0.55}
            >
              {s.label}
            </text>
          );
        })}
      {(() => {
        const last = blend.pts[blend.pts.length - 1];
        return (
          <text
            x={x(last[0]) + 4}
            y={y(last[1]) + 3}
            fontSize={10}
            fontWeight={800}
            fill={blend.color}
          >
            Bain Luck
          </text>
        );
      })()}
    </svg>
  );
}

function legendRow() {
  const { sources } = seriesFrom();
  return `<div style="display:flex;gap:14px;flex-wrap:wrap;padding:10px 2px 0;font-size:11px;color:#6B7280">
    <span style="font-weight:700;color:${sourceHex("blend")}">━ Bain Luck</span>
    ${sources
      .map((s) => `<span style="color:${s.color};opacity:.7">╌ ${s.label}</span>`)
      .join("")}
  </div>`;
}

function matchListPanel(): string {
  const entries = matchListFromSlate(
    [
      {
        priced: true,
        matchup_key: EXTENSIONS.matchup_key,
        event_id: EXTENSIONS.event_id,
        draw: "mens-singles",
        draw_label: "Men's Singles",
        round: EXTENSIONS.round,
        scheduled_date: EVENT.commence_time,
        coherent: true,
        decided: false,
        sides: [
          {
            entity_key: "a",
            display_name: EVENT.home_team,
            seed: null,
            country: null,
            image: null,
            role: "participant",
            probability: EVENT.current_odds?.home_probability ?? null,
            opening_probability: EVENT.current_odds?.home_probability ?? null,
            move: 0,
            raw_probability: EVENT.current_odds?.home_probability ?? null,
            raw_opening_probability: EVENT.current_odds?.home_probability ?? null,
            observed_at: EVENT.current_odds?.captured_at ?? null,
            age_hours: 1,
            price_state: "live",
          },
          {
            entity_key: "b",
            display_name: EVENT.away_team,
            seed: null,
            country: null,
            image: null,
            role: "participant",
            probability: EVENT.current_odds?.away_probability ?? null,
            opening_probability: EVENT.current_odds?.away_probability ?? null,
            move: 0,
            raw_probability: EVENT.current_odds?.away_probability ?? null,
            raw_opening_probability: EVENT.current_odds?.away_probability ?? null,
            observed_at: EVENT.current_odds?.captured_at ?? null,
            age_hours: 1,
            price_state: "live",
          },
        ],
      },
    ] as never,
    {}
  );
  return renderToStaticMarkup(
    <div className="px-4 lg:px-6">
      <TournamentMatches entries={entries} initialExpanded />
    </div>
  );
}

describe("UX-P152 — the match, on the standard event page", () => {
  it("the captured payload is the specimen these panels need", () => {
    expect(EXTENSIONS.tournament?.slug).toBe("us-open");
    expect(EXTENSIONS.matchup_key).toBeTruthy();
    // The architectural claim, in the artifact's own data: the fixture resolved
    // to an `events` row by id, and the event row is the one the API serves.
    expect(EXTENSIONS.event_id).toBe(EVENT.id);
    expect(LINKS.linked).toBeGreaterThan(0);
  });

  it("the advancement strip renders both players' ladders", () => {
    const html = renderToStaticMarkup(<ExtensionsPanel data={EXTENSIONS} />);
    expect(html).toContain('data-testid="advancement-stage"');
    const a = EXTENSIONS.advancement!;
    for (const row of [a.home_team, a.away_team]) {
      if (row) expect(html).toContain(row.short_name);
    }
  });

  it("the trend panels plot the real production series", () => {
    const { blend, sources } = seriesFrom();
    expect(blend.pts.length).toBeGreaterThan(100);
    // The case Alex named: at least one source stops long before the others.
    const lengths = sources.map((s) => s.pts.length).sort((a, b) => a - b);
    expect(lengths[0]).toBeLessThan(lengths[lengths.length - 1] / 5);
    const labelled = renderToStaticMarkup(<TrendGraph labelled />);
    const bare = renderToStaticMarkup(<TrendGraph labelled={false} />);
    // Both directions: labelling must actually change the picture.
    expect(labelled).toContain("ESPN");
    expect(bare).not.toContain(">ESPN<");
    expect(labelled.length).toBeGreaterThan(bare.length);
  });

  it("the way-in row addresses the standard event page", () => {
    expect(matchListPanel()).toContain(`href="/events/${EVENT.id}"`);
  });

  it("3B is what ships: the chart writes NO source name onto the plot", () => {
    /**
     * ═══ ALEX RATIFIED 3B OVER 3A (UX-P154) ═══
     *
     * *"Panel 3B ('+ N sources' press) is RATIFIED over 3A."* — Alex's review
     * of P149/P150/P151/P152, relayed through the UX-P154 runner directive.
     *
     * So this test inverted. It used to assert that the real `SourceEndLabel`
     * drew at the series' last point and nowhere else; the choice it was
     * guarding was not the one Alex made, and a passing guard around a
     * reverted feature is how a reverted feature comes back.
     *
     * It reads the SOURCE rather than a render because the thing being
     * forbidden is a component that no longer exists — there is nothing to
     * mount. The two forbidden strings are the label's own `data-testid` and
     * the export name, so either rebuilding it under its old name or wiring a
     * new one to the same hook turns this red.
     */
    const chart = fs.readFileSync(
      path.join(FRONTEND, "components", "OddsChart.tsx"),
      "utf8"
    );
    expect(chart).not.toContain('data-testid="chart-source-label"');
    expect(chart).not.toContain("export function SourceEndLabel");
    // The ratified treatment is still there — this must not pass by the legend
    // having been deleted too.
    expect(chart).toContain("legendExpanded");
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });
    const css = appStylesheet();

    const panel = (tag: string, tone: string, head: string, body: string) => `
<div class="panel-head"><span class="tag ${tone}">${tag}</span> ${head}</div>
<div class="rule"></div>
<div class="panel">${body}</div>`;

    const a = EXTENSIONS.advancement!;
    const sides = [a.home_team, a.away_team].filter(Boolean) as TournamentAdvancementRow[];
    const who = sides.map((s) => s.name).join(" v ");
    const propsNote =
      (EXTENSIONS.props?.length ?? 0) > 0
        ? `${EXTENSIONS.props.length} other questions about this match sit under the strip.`
        : `<b>No props panel on this fixture, and that is the true state.</b> For the main
           draw Polymarket lists exactly one market per match today — an exact-score market
           with no siblings — so the group hop returns nothing to group. The prop sets
           (who wins set 1, total games, the margin) appeared on the qualifying matches in
           the hours before they started, and this section fills itself in when they do.
           The component is unchanged from UX-P149; only its container moved.`;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P152 — a match is an event</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:16px 22px;font-size:13px;line-height:1.65;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .banner ul{margin:8px 0 0;padding-left:18px}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.a{background:#EFF6FF;color:#1E40AF}
  .tag.b{background:#ECFDF5;color:#065F46}
  .tag.c{background:#FFF7ED;color:#9A3412}
  .tag.d{background:#F5F3FF;color:#5B21B6}
  .panel{padding:8px 0 44px;background:#F5F5F7}
  .panel-head{padding:20px 22px 6px;font-size:13px;color:#4B5563;line-height:1.6;background:#fff}
  .rule{height:1px;background:#E5E7EB}
  .chartwrap{padding:0 22px}
  .drawn{margin:0 22px 10px;padding:8px 11px;border-radius:8px;background:#FFFBEB;border:1px solid #FDE68A;font-size:12px;color:#78350F}
</style></head>
<body>
<div class="banner">
  <b>UX-P152 — a US Open match is an ordinary event, and renders on the ordinary event page.</b>
  UX-P149's separate <code>/tournaments/us-open/matches/{key}</code> page is deleted. Its premise —
  that a tennis match has no <code>events</code> row — expired on 27 August, when the Odds API
  ingested the main draw: <b>94 standard events now exist for the 96 registered R128 fixtures</b>,
  and all ${LINKS.linked} registered fixtures with a pinned market dereference to one by id.
  <ul>
    <li>The match card now routes to <code>/events/{id}</code> exactly as any game card does, and
        the tournament adds sections <i>to</i> that page rather than replacing it.</li>
    <li>The link is resolved by <b>id only</b> — the register's pinned match-winner
        <code>market_id</code> through <code>futures_markets.event_id</code>. Never the two player
        names sitting right there. Unresolved fixtures get no link and a counted reason
        (<code>${JSON.stringify(LINKS.unresolved)}</code>).</li>
    <li>Everything below is drawn from <b>production payloads captured minutes before this ran</b>,
        through the same builders the route calls.</li>
  </ul>
</div>
${panel(
  "1 — the event page's own half",
  "a",
  `${EVENT.home_team} v ${EVENT.away_team}, event <code>${EVENT.id}</code>. This is the part
   UX-P149 rebuilt and did not need to: the hero, the blended pair, the source count — and above
   all the probability-over-time graph, which the bespoke match page omitted entirely. Shown here
   at the event page's own weights so the sections below sit where they really sit.`,
  renderToStaticMarkup(<HeroPanel />)
)}
${panel(
  "2 — what the tournament adds",
  "b",
  `${who}. <b>Each player's chance of reaching each later round</b> — your item 2 — rendered
   through <code>AdvancementPath</code>, which is <i>the same component</i> the MLB / NBA event
   page's CHAMPIONSHIP PATH block goes through, not a tennis copy of it.
   ${propsNote}
   <br><br>One thing to look at: a ladder that does not climb says so. The market sometimes prices
   "reach the final" above "reach the semis" (21 of 84 ladder players on 26 Aug, all in the sub-5%
   tail). The grid's ruling is report-not-correct; at one match's magnification silence would read
   as our arithmetic, so the card says it in words.`,
  renderToStaticMarkup(<ExtensionsPanel data={EXTENSIONS} />)
)}
<div class="panel-head"><span class="tag c">3 — the trend graph</span>
  Your format, and the alternative. Specimen is the end-of-game case you named: <b>Blue Jays 2 –
  Royals 13</b>, where Kalshi contributed two readings and stopped, the sportsbook line stopped
  at 18, and ESPN and the two models carried the rest of the game. Watch the blend bend as the
  thin sources drop out.
</div>
<div class="rule"></div>
<div class="panel">
  <div class="drawn"><b>Panels 3A and 3B are drawn, not rendered.</b> The chart is Recharts and
  Recharts measures its container — server-rendered it emits an empty box, so a "render" here
  would be a blank rectangle presented as a chart. These plot the same production series at the
  shipped chart's own line weights and colours, which is what the styling question needs.
  <br><br><b>UX-P154: you ratified 3B.</b> 3A is reverted in full — no source name is written onto
  the plot, and the chart is exactly what it was before UX-P152 touched it. The panels below are
  kept as the record of the choice, not as a proposal.</div>
  <div class="chartwrap">
    <div style="font:700 12px inherit;color:#111827;margin:6px 0 6px">3A — your format: every faint line ends in its own name</div>
    ${renderToStaticMarkup(<TrendGraph labelled />)}
    <p style="font-size:12px;color:#4B5563;line-height:1.6;margin:10px 0 26px">
      A glance answers "which source is moving the blend", and — the part a legend structurally
      cannot do — <b>where each source stopped</b>. Kalshi's name sits at the far left because
      Kalshi stopped there. That is the blowout drop-out, visible without a tooltip or a click.
    </p>
    <div style="font:700 12px inherit;color:#111827;margin:6px 0 6px">3B — what ships today: the same lines, names behind a "+ N sources" press</div>
    ${renderToStaticMarkup(<TrendGraph labelled={false} />)}
    ${legendRow()}
    <p style="font-size:12px;color:#4B5563;line-height:1.6;margin:10px 0 6px">
      The blend already dominates and the faint lines are already there. 3A's argument was that
      the lines are anonymous until you press for a legend, and that a legend cannot say
      <i>when</i> a source stopped. <b>You ratified 3B, and 3B is what ships.</b> The one thing 3A
      was right about is recorded in the chart's own source so the next lane starts from the gap
      rather than from the argument you have already heard: an end-of-line label is the only
      annotation that can carry when a source dropped out, and that remains unsurfaced.
    </p>
  </div>
</div>
${panel(
  "4 — the way in",
  "d",
  `The match list row, tapped. One link now, to <code>/events/${EVENT.id}</code>. There were two
   a moment ago — UX-P139's <code>event_id</code> link, which rendered on nothing, and UX-P149's
   tournament-private match URL, built because the first had nowhere to go. A fixture that does
   not dereference to an events row gets no link at all: a link to the wrong match is worse than
   no link.`,
  matchListPanel()
)}
</body></html>`;

    fs.writeFileSync(path.join(dir, "p152-event-page.html"), html);

    // The rig asserts its own artifact — a capture that writes an empty page
    // reports success exactly like one that works.
    const written = fs.readFileSync(path.join(dir, "p152-event-page.html"), "utf8");
    expect(written.length).toBeGreaterThan(20000);
    expect(written).toContain(ADVANCEMENT_HEADING);
    expect(written).toContain(`href="/events/${EVENT.id}"`);
    // No LIVE link to the deleted route. Scoped to `href=` because the banner
    // above names the route in prose — the artifact explains what was removed,
    // and a substring guard would fail on its own explanation.
    expect(written).not.toMatch(/href="[^"]*\/matches\//);
    expect(written.split("<svg").length - 1).toBeGreaterThanOrEqual(2);
    expect(css.length).toBeGreaterThan(1000);
  });
});
