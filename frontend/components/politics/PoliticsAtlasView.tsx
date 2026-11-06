"use client";

import React, { useState } from "react";
import type {
  ChamberControl,
  PoliticsData,
  PoliticsMarketRow,
  PoliticsThemeSimple,
} from "@/lib/api";
import { formatAtlasTimestampPT } from "@/components/atlas/atlasStateCopy";
import {
  BinaryRow,
  BucketDistribution,
  FieldBoard,
  RaceCard,
  ThresholdLadderCard,
  type AtlasCategoryOutcome,
  type AtlasJourneySeries,
  type AtlasMarketMeta,
} from "@/components/atlas/CategoryAtlasComponents";

const THEMES = [
  { key: "presidential", label: "Presidential 2028" },
  { key: "congressional", label: "Congressional" },
  { key: "gubernatorial", label: "Gubernatorial" },
  { key: "policy", label: "Policy & Legislation" },
  { key: "scotus", label: "Supreme Court" },
  { key: "international", label: "International" },
  { key: "other", label: "Other" },
] as const;

type ExtendedChamberControl = ChamberControl & {
  source?: string;
  winner?: string | null;
  status?: string | null;
};

type ExtendedPoliticsMarketRow = PoliticsMarketRow & {
  status?: string | null;
  settled_winner?: string | null;
};

function parseLeadingNumber(label: string): number | null {
  const cleaned = (label || "").replace(/,/g, "");
  const m = /(-?\d+(?:\.\d+)?)/.exec(cleaned);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

function isThresholdLabel(label: string): boolean {
  const trimmed = (label || "").trim();
  return (
    /^(above|over|at least|under|below|more than|less than|before)\b/i.test(trimmed) ||
    /\+$/.test(trimmed)
  );
}

function inferPartyFromLabel(label: string): "R" | "D" | "I" | null {
  const s = (label || "").trim();
  if (/\(R\)|\bRepublican(?:s| Party)?\b|\bGOP\b/i.test(s)) return "R";
  if (/\(D\)|\bDemocrat(?:s|ic(?: Party)?)?\b/i.test(s)) return "D";
  if (/\(I\)|\bIndependent\b/i.test(s)) return "I";
  return null;
}

function toOrderedOutcomes(
  outcomes: { name: string; prob: number; rendered_percent?: number | null }[],
  orderNumeric: boolean,
  settledWinner?: string | null
): AtlasCategoryOutcome[] {
  const items = outcomes.map((o, idx) => ({
    o,
    idx,
    num: parseLeadingNumber(o.name),
  }));
  const sorted =
    orderNumeric && items.filter((x) => x.num !== null).length >= 2
      ? [...items].sort((a, b) => {
          if (a.num !== null && b.num !== null && a.num !== b.num) {
            return a.num - b.num;
          }
          if (a.num !== null && b.num === null) return -1;
          if (a.num === null && b.num !== null) return 1;
          return a.idx - b.idx;
        })
      : items;

  const winnerNorm = (settledWinner || "").trim().toLowerCase();
  return sorted.map(({ o }, idx) => {
    const won =
      Boolean(winnerNorm) && o.name.trim().toLowerCase() === winnerNorm;
    const lost = Boolean(winnerNorm) && !won;
    return {
      id: `${o.name}-${idx}`,
      label: o.name,
      probability: o.prob / 100,
      renderedPercent: o.rendered_percent ?? Math.round(o.prob),
      party: inferPartyFromLabel(o.name),
      isSettled: Boolean(winnerNorm),
      isWinner: won ? true : lost ? false : null,
      settledResult: won ? "won" : lost ? "lost" : null,
    };
  });
}

function renderChamberRaceCard(
  chamberName: "Senate" | "House",
  ctrl: ExtendedChamberControl | null | undefined
) {
  if (!ctrl) return null;
  const gopSettled = ctrl.winner === "Republicans" || ctrl.gop >= 99.5;
  const demSettled = ctrl.winner === "Democrats" || ctrl.dem >= 99.5;
  const settledWinner =
    ctrl.winner ??
    (gopSettled ? "Republicans" : demSettled ? "Democrats" : null);

  const contenders: AtlasCategoryOutcome[] = [
    {
      id: `${chamberName}-rep`,
      label: "Republicans",
      party: "R",
      probability: ctrl.gop / 100,
      renderedPercent: Math.round(ctrl.gop),
      isSettled: Boolean(settledWinner),
      isWinner: settledWinner ? settledWinner === "Republicans" : null,
      settledResult: settledWinner
        ? settledWinner === "Republicans"
          ? "won"
          : "lost"
        : null,
    },
    {
      id: `${chamberName}-dem`,
      label: "Democrats",
      party: "D",
      probability: ctrl.dem / 100,
      renderedPercent: Math.round(ctrl.dem),
      isSettled: Boolean(settledWinner),
      isWinner: settledWinner ? settledWinner === "Democrats" : null,
      settledResult: settledWinner
        ? settledWinner === "Democrats"
          ? "won"
          : "lost"
        : null,
    },
  ];

  return (
    <RaceCard
      key={chamberName}
      meta={{
        marketId: ctrl.market_id,
        kicker: `CHAMBER CONTROL · ${settledWinner ? "settled" : "open"}`,
        marketTitle: `${chamberName} Control`,
        source: ctrl.source ?? null,
      }}
      contenders={contenders}
      settledWinner={settledWinner}
    />
  );
}

function renderPoliticsMarketByShape(
  row: ExtendedPoliticsMarketRow,
  themeKey: string
) {
  const outcomes = row.top_outcomes ?? [];
  const meta: AtlasMarketMeta = {
    marketId: row.market_id,
    marketTitle: row.q,
    kicker: themeKey.toUpperCase(),
    source: row.src,
  };
  const settledWinner = row.settled_winner ?? null;

  if (outcomes.length <= 1) {
    const lead = outcomes[0];
    const prob = lead ? lead.prob : row.prob;
    const won =
      Boolean(settledWinner) &&
      (settledWinner?.toLowerCase() === "yes" ||
        settledWinner?.toLowerCase() === lead?.name?.toLowerCase());
    const lost = Boolean(settledWinner) && !won;
    return (
      <BinaryRow
        key={row.market_id}
        meta={meta}
        outcome={{
          id: row.market_id,
          label: lead?.name && !/^(yes|no)$/i.test(lead.name) ? lead.name : row.q,
          probability: prob / 100,
          renderedPercent: lead?.rendered_percent ?? Math.round(prob),
          isSettled: Boolean(settledWinner),
          isWinner: won ? true : lost ? false : null,
          settledResult: won ? "won" : lost ? "lost" : null,
        }}
      />
    );
  }

  const thresholdCount = outcomes.filter((o) => isThresholdLabel(o.name)).length;
  if (row.mutually_exclusive === false || thresholdCount >= 2) {
    return (
      <ThresholdLadderCard
        key={row.market_id}
        meta={meta}
        rungs={toOrderedOutcomes(outcomes, true, settledWinner)}
      />
    );
  }

  const numericCount = outcomes.filter((o) => parseLeadingNumber(o.name) !== null).length;
  if (numericCount >= 2 && numericCount === outcomes.length) {
    return (
      <BucketDistribution
        key={row.market_id}
        meta={meta}
        buckets={toOrderedOutcomes(outcomes, true, settledWinner)}
      />
    );
  }

  if (
    themeKey === "congressional" ||
    themeKey === "gubernatorial" ||
    outcomes.some((o) => inferPartyFromLabel(o.name) !== null)
  ) {
    return (
      <RaceCard
        key={row.market_id}
        meta={meta}
        contenders={toOrderedOutcomes(outcomes, false, settledWinner)}
        settledWinner={settledWinner}
      />
    );
  }

  return (
    <FieldBoard
      key={row.market_id}
      meta={meta}
      outcomes={toOrderedOutcomes(outcomes, false, settledWinner)}
      showPartyPills
    />
  );
}

export default function PoliticsAtlasView({ data }: { data: PoliticsData }) {
  const [activeTheme, setActiveTheme] = useState<string | null>(null);
  const t = data.themes;
  const updatedPT = formatAtlasTimestampPT(data.updated_at);

  const showTheme = (key: string) => !activeTheme || activeTheme === key;

  const pres = t.presidential;
  const presCandidates = pres?.candidates ?? [];
  const sortedPres = [...presCandidates].sort((a, b) => b.merged - a.merged);
  const presOutcomes: AtlasCategoryOutcome[] = sortedPres.map((c, idx) => ({
    id: `${c.name}-${idx}`,
    label: c.name,
    party: c.party || null,
    probability: c.merged / 100,
    renderedPercent: Math.round(c.merged),
    openingProbability:
      c.history && c.history.length > 0 ? c.history[0].p / 100 : null,
    openingObservedAt:
      c.history && c.history.length > 0 ? c.history[0].t : null,
    observedAt:
      c.history && c.history.length > 0
        ? c.history[c.history.length - 1].t
        : data.updated_at,
  }));

  const presJourneySeries: AtlasJourneySeries[] = sortedPres
    .slice(0, 4)
    .filter((c) => Array.isArray(c.history) && c.history.length >= 2)
    .map((c) => ({
      label: c.name,
      party: c.party || null,
      points: (c.history ?? []).map((pt) => ({
        observedAt: pt.t,
        probability: pt.p / 100,
      })),
    }));

  const renderSimpleThemeSection = (
    themeKey: string,
    title: string,
    sectionData: PoliticsThemeSimple | undefined
  ) => {
    if (!showTheme(themeKey) || !sectionData?.markets?.length) return null;
    return (
      <section
        key={themeKey}
        id={`sec-${themeKey}`}
        data-section={themeKey.toUpperCase()}
        className="space-y-4"
      >
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            {title.toUpperCase()}
          </p>
          <h2 className="text-xl font-semibold text-text-primary mt-0.5">
            {title}
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sectionData.markets.map((m) =>
            renderPoliticsMarketByShape(m as ExtendedPoliticsMarketRow, themeKey)
          )}
        </div>
      </section>
    );
  };

  return (
    <div
      data-testid="politics-atlas-view"
      className="max-w-[1120px] mx-auto px-4 md:px-6 py-8 space-y-10"
    >
      {/* Header */}
      <section data-section="HERO" className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          POLITICS · PROBABILITY FIRST
        </p>
        <h1 className="text-3xl md:text-4xl font-semibold text-text-primary tracking-tight">
          Politics
        </h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Live probabilities for elections, chambers, legislation, and
          international affairs — one calibrated reading per market.
        </p>
        {updatedPT && (
          <p className="font-mono text-xs text-text-muted">
            Last reading {updatedPT}
          </p>
        )}
      </section>

      {/* Theme Jump Pills (no raw market counts) */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setActiveTheme(null)}
          className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
            !activeTheme
              ? "bg-text-primary text-surface-card border-text-primary"
              : "bg-surface-card text-text-secondary border-surface-border hover:text-text-primary"
          }`}
        >
          All
        </button>
        {THEMES.map((th) => (
          <button
            key={th.key}
            type="button"
            onClick={() => setActiveTheme(th.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              activeTheme === th.key
                ? "bg-text-primary text-surface-card border-text-primary"
                : "bg-surface-card text-text-secondary border-surface-border hover:text-text-primary"
            }`}
          >
            {th.label}
          </button>
        ))}
      </div>

      {/* Presidential 2028 */}
      {showTheme("presidential") && presOutcomes.length > 0 && (
        <section
          id="sec-presidential"
          data-section="PRESIDENTIAL"
          className="space-y-4"
        >
          <FieldBoard
            meta={{
              marketId: pres?.kalshi_market_id ?? pres?.poly_market_id ?? null,
              kicker: "PRESIDENTIAL 2028",
              marketTitle:
                pres?.headline_q || "Who wins the 2028 presidential election?",
              observedAt: data.updated_at,
              sourceCount: pres?.has_dual_source ? 2 : 1,
            }}
            outcomes={presOutcomes}
            journeySeries={presJourneySeries}
            previewCount={6}
            showPartyPills
          />

          {pres?.side_markets && pres.side_markets.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {pres.side_markets.slice(0, 6).map((m) =>
                renderPoliticsMarketByShape(
                  m as ExtendedPoliticsMarketRow,
                  "presidential"
                )
              )}
            </div>
          )}
        </section>
      )}

      {/* Congressional */}
      {showTheme("congressional") &&
        t.congressional &&
        t.congressional.count > 0 && (
          <section
            id="sec-congressional"
            data-section="CONGRESSIONAL"
            className="space-y-4"
          >
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                CONGRESSIONAL
              </p>
              <h2 className="text-xl font-semibold text-text-primary mt-0.5">
                Chamber control &amp; races
              </h2>
            </div>

            {(t.congressional.chamber_control?.senate ||
              t.congressional.chamber_control?.house) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {renderChamberRaceCard(
                  "Senate",
                  t.congressional.chamber_control?.senate as ExtendedChamberControl
                )}
                {renderChamberRaceCard(
                  "House",
                  t.congressional.chamber_control?.house as ExtendedChamberControl
                )}
              </div>
            )}

            {t.congressional.markets && t.congressional.markets.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {t.congressional.markets.map((m) =>
                  renderPoliticsMarketByShape(
                    m as ExtendedPoliticsMarketRow,
                    "congressional"
                  )
                )}
              </div>
            )}
          </section>
        )}

      {/* Remaining theme sections (CrossSourceSpotlight retired per S-A) */}
      {renderSimpleThemeSection(
        "gubernatorial",
        "Gubernatorial Races",
        t.gubernatorial
      )}
      {renderSimpleThemeSection(
        "policy",
        "Policy & Legislation",
        t.policy
      )}
      {renderSimpleThemeSection("scotus", "Supreme Court", t.scotus)}
      {renderSimpleThemeSection(
        "international",
        "International",
        t.international
      )}
      {renderSimpleThemeSection("other", "Other Political Markets", t.other)}
    </div>
  );
}
