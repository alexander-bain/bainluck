import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { FuturesMarketDetailResponse, FuturesOutcomeHistory } from "@/lib/types";
import Prototype from "../Prototype";
import { CASES, type RelatedMarket } from "../_model";
import duel from "../_data/109085.json";
import field from "../_data/108629.json";
import quantity from "../_data/65536371.json";
import participation from "../_data/227.json";
import oneLeg from "../_data/109918.json";
import settled from "../_data/108645.json";
import midterms from "../_data/midterms.json";
import cfp from "../_data/cfp.json";
import weather from "../_data/weather.json";
import manifest from "../_data/manifest.json";

export const metadata: Metadata = {
  title: "Futures design preview",
  robots: { index: false, follow: false },
};

const snapshots: Record<string, unknown> = {
  "109085": duel, "108629": field, "65536371": quantity,
  "227": participation, "109918": oneLeg, "108645": settled,
};

interface Card {
  id: number; name: string; source?: string; sources?: string[]; status?: string;
  top_outcomes?: FuturesMarketDetailResponse["outcomes"];
}
function collectionCards(collection: unknown): Card[] {
  const data = collection as { sections: { members: { card?: Card }[] }[] };
  return data.sections.flatMap((section) => section.members.flatMap((member) => member.card ? [member.card] : []));
}
function relatedCard(card: Card): RelatedMarket {
  const rows = card.top_outcomes ?? [];
  const lead = rows[0];
  return {
    id: card.id, name: card.name, lead: lead?.name ?? "",
    probability: lead?.probability ?? null,
    verdict: null, outcomes: rows, status: card.status,
    sources: card.sources ?? (card.source ? [card.source] : []),
  };
}

export default function FuturesPrototypePage({ params, searchParams }: { params: { id: string }; searchParams?: { state?: string } }) {
  if (!snapshots[params.id]) notFound();
  const raw = snapshots[params.id] as {
    detail: FuturesMarketDetailResponse; history: { outcomes: FuturesOutcomeHistory[] };
  };
  const detail = { ...raw.detail, outcomes: raw.detail.outcomes.map((row) => ({ ...row })) };
  let sources = [detail.source ?? ""];
  const politicsCards = collectionCards(midterms);
  if (detail.id === 109085) {
    // This is the production container's registered-twin blend, by outcome ID.
    // No local weighting, name matching, or same-canonical-key union.
    const blended = politicsCards.find((card) => card.id === detail.id)!;
    const byId = new Map(blended.top_outcomes!.map((outcome) => [outcome.id, outcome]));
    detail.outcomes = detail.outcomes.map((outcome) => ({ ...outcome, probability: byId.get(outcome.id)?.probability ?? null }));
    sources = blended.sources ?? [];
  }
  let related = politicsCards.filter((card) => card.id !== detail.id).slice(0, 3).map(relatedCard);
  if (detail.id === 227) related = collectionCards(cfp).filter((card) => card.id !== detail.id).map(relatedCard);
  if (detail.id === 65536371) related = weather.slice(0, 3).map((card) => ({
    id: card.market_id, name: card.q, lead: card.leader,
    probability: card.probability, verdict: null, sources: [card.src],
  }));

  const study = searchParams?.state === "open" || searchParams?.state === "settled" ? searchParams.state : "payload";
  return <Prototype key={`${detail.id}-${study}`} initialStudy={study} data={{
    detail, history: raw.history.outcomes, sources, related,
    capturedAt: manifest.captured_at,
    settledAt: detail.id === 108645 ? manifest.settled_today.settled_at : null,
    historyNote: detail.id === 109085
      ? "The current number is blended. The recorded path covers one venue; a registered-twin blended history is not served yet."
      : detail.id === 65536371
        ? "Five isolated readings are served across these thresholds. None has enough history to draw a path."
        : null,
  }} />;
}

export function generateStaticParams() {
  return CASES.map(({ id }) => ({ id: String(id) }));
}
