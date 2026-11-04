"use client";

import Link from "next/link";
import type { FeedFuturesData } from "@/lib/types";
import { twoLegCardPair } from "@/lib/twoLegCardPair";
import { renderedOutcomeRowPercents } from "@/lib/renderedPercent";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { MIDTERMS_PARTY_COLOR, midtermsBalanceParties, midtermsOutcomeParty, type MidtermsParty } from "@/lib/midtermsParty";
import MarketCard from "@/components/politics/MarketCard";
import { SourceBadge } from "@/components/politics/atoms";
import EntityImage from "@/components/EntityImage";
import { cleanPersonOutcomeName, isPersonOutcomeName } from "@/lib/eventConceptDisplay";

const partyName = (party: MidtermsParty) => party === "D" ? "Democratic" : "Republican";
const colour = (party: MidtermsParty | null) => party ? MIDTERMS_PARTY_COLOR[party] : "var(--text-primary)";
const focus = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-brand";

// Only the collection's already-priced, ungraded branch reaches this renderer.
// The caller retains its settled/unpriced handling, including #11872's count.
export default function MidtermsMarketCard({ market, presentation }: { market: FeedFuturesData; presentation: string }) {
  const row = {
    q: market.name, market_id: market.id, src: market.source ?? "",
    prob: market.top_outcomes[0].probability! * 100, outcome_count: market.outcome_count,
    top_outcomes: market.top_outcomes.map(outcome => ({ name: outcome.name, prob: outcome.probability! * 100 })),
  };
  const balance = market.id === 108619 && presentation === "field"
    ? market.top_outcomes.map(outcome => ({ outcome, parties: midtermsBalanceParties(outcome.name) })) : [];
  if (balance.length === 4 && balance.every(cell => cell.parties)) {
    // Fixed chamber positions, never a price-ranked shuffle of the board.
    balance.sort((a, b) => (a.parties!.senate === "R" ? 2 : 0) + (a.parties!.house === "R" ? 1 : 0)
      - (b.parties!.senate === "R" ? 2 : 0) - (b.parties!.house === "R" ? 1 : 0));
    return <Link href={`/futures/${market.id}`} data-midterms-card="balance" className={`block rounded-card border border-surface-border bg-surface-card p-4 ${focus}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-text-primary">{market.name}</h3>
        <SourceBadge source={row.src} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {balance.map(({ outcome, parties }) => {
          const { house, senate } = parties!;
          return <div key={outcome.id ?? outcome.name} data-balance-outcome={outcome.name} data-balance-parties={`${house}${senate}`} className="rounded-lg border-y border-x-2 border-surface-border bg-surface-elevated p-3" style={{ borderLeftColor: colour(house), borderRightColor: colour(senate) }}>
            <div className="mb-2 flex flex-wrap gap-x-2 text-[10px] font-semibold">
              <span style={{ color: colour(house) }} aria-label={`${partyName(house)} House`}>House {house}</span>
              <span style={{ color: colour(senate) }} aria-label={`${partyName(senate)} Senate`}>Senate {senate}</span>
            </div>
            <p className="font-mono text-[28px] font-semibold leading-none tabular-nums" style={{ color: house === senate ? colour(house) : "var(--text-primary)" }}>{formatProbabilityPercent(outcome.probability!)}</p>
            <p className="mt-2 text-xs leading-snug text-text-secondary">{outcome.name}</p>
          </div>;
        })}
      </div>
      <p className="mt-3 flex gap-4 text-[10px] font-semibold"><span style={{ color: colour("D") }}>D · Democratic</span><span style={{ color: colour("R") }}>R · Republican</span></p>
    </Link>;
  }

  const pair = twoLegCardPair(row);
  if (presentation === "field" || !pair.second) return <MarketCard market={{ ...row, top_outcomes: row.top_outcomes.slice(0, 5) }} theme="congressional" forceField={presentation === "field"} forceDuel={presentation === "duel"} showLeaderHeadshot />;
  const percentages = renderedOutcomeRowPercents([pair.first.prob / 100, pair.second.prob / 100]);
  const legs = [pair.first, pair.second].map((leg, index) => {
    const source = market.top_outcomes.find(outcome => outcome.name === leg.name);
    return { ...leg, party: midtermsOutcomeParty(market.id, source ?? { name: leg.name }),
      label: formatProbabilityPercent(leg.prob / 100, { rendered: percentages[index] }) };
  });
  if (legs[0].party === "R" && legs[1].party === "D") legs.reverse();
  const compact = presentation === "duel";
  return <Link href={`/futures/${market.id}`} data-midterms-card={compact ? "race" : "governor"} className={`block p-4 hover:bg-surface-elevated ${compact ? "" : "rounded-card border border-surface-border bg-surface-card"} ${focus}`}>
    <div className="mb-3 flex items-start justify-between gap-3">
      <h3 className="text-sm font-semibold leading-snug text-text-primary">{market.name}</h3>
      <SourceBadge source={row.src} />
    </div>
    <div className="grid grid-cols-2 gap-4">
      {legs.map((leg, index) => <div key={leg.name} data-party={leg.party ?? "unknown"} className={`min-w-0 ${index ? "text-right" : ""}`}>
        <p className={`font-mono font-semibold leading-none tabular-nums ${compact ? "text-2xl" : "text-3xl"}`} style={{ color: colour(leg.party) }}>{leg.label}</p>
        <p className={`mt-1.5 flex items-center gap-1.5 text-xs leading-snug text-text-secondary ${index ? "justify-end" : ""}`}>
          {leg.name === pair.first.name && isPersonOutcomeName(leg.name) && (
            <EntityImage type="wikipedia" name={cleanPersonOutcomeName(leg.name)} size={20} showFallback={false} />
          )}
          <span>{leg.name}{leg.party && <span className="ml-1 font-semibold" style={{ color: colour(leg.party) }} aria-label={partyName(leg.party)}>({leg.party})</span>}</span>
        </p>
      </div>)}
    </div>
    {pair.oneQuestion && <div aria-hidden className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-surface-elevated">
      {legs.map(leg => <span key={leg.name} data-party-bar={leg.party ?? "unknown"} style={{ width: `${leg.prob}%`, backgroundColor: leg.party ? colour(leg.party) : "var(--text-muted)" }} />)}
    </div>}
  </Link>;
}
