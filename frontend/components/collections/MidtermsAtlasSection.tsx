"use client";

import React from "react";
import type { CollectionMember } from "@/lib/collections";
import type { FeedFuturesData } from "@/lib/types";
import {
  BucketDistribution,
  RaceCard,
  ThresholdLadderCard,
  type AtlasCategoryOutcome,
} from "@/components/atlas/CategoryAtlasComponents";

type ControlInfo = {
  market_id: number;
  gop: number;
  dem: number;
  source?: string;
  winner?: string;
} | null;

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

function inferParty(
  name: string,
  explicitParty?: string | null
): "R" | "D" | "I" | null {
  if (explicitParty === "R" || explicitParty === "D" || explicitParty === "I") {
    return explicitParty;
  }
  if (/\(R\)|\bRepublican(?:s| Party)?\b|\bGOP\b/i.test(name)) return "R";
  if (/\(D\)|\bDemocrat(?:s|ic(?: Party)?)?\b/i.test(name)) return "D";
  if (/\(I\)|\bIndependent\b/i.test(name)) return "I";
  return null;
}

export function MidtermsAtlasChamberControl({
  senate,
  house,
}: {
  senate: ControlInfo;
  house: ControlInfo;
}) {
  const renderChamber = (label: string, ctrl: ControlInfo) => {
    if (!ctrl) return null;
    const gopWon = ctrl.winner === "Republicans" || ctrl.gop >= 99.5;
    const demWon = ctrl.winner === "Democrats" || ctrl.dem >= 99.5;
    const settledWinner =
      ctrl.winner ?? (gopWon ? "Republicans" : demWon ? "Democrats" : null);

    return (
      <RaceCard
        key={label}
        meta={{
          marketId: ctrl.market_id,
          kicker: `CHAMBER CONTROL · ${settledWinner ? "settled" : "open"}`,
          marketTitle: `${label} Control`,
          source: ctrl.source ?? null,
        }}
        settledWinner={settledWinner}
        contenders={[
          {
            id: `${label}-rep`,
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
            id: `${label}-dem`,
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
        ]}
      />
    );
  };

  return (
    <div
      data-testid="midterms-atlas-party-control"
      className="grid grid-cols-1 md:grid-cols-2 gap-4"
    >
      {renderChamber("Senate", senate)}
      {renderChamber("House", house)}
    </div>
  );
}

export function MidtermsAtlasMemberCard({
  member,
  sectionTitle,
}: {
  member: CollectionMember;
  sectionTitle?: string;
}) {
  const data = member.item.data as FeedFuturesData & {
    settled_winner?: string | null;
    status?: string | null;
  };
  const topOutcomes = data.top_outcomes ?? [];
  const settledWinner =
    data.settled_winner ??
    topOutcomes.find(
      (o) =>
        (o as { result?: string | null }).result === "yes" ||
        ((data.status === "settled" || data.status === "resolved") &&
          (o.probability ?? 0) >= 0.995)
    )?.name ??
    null;

  const numericItems = topOutcomes.map((o, idx) => ({
    o,
    idx,
    num: parseLeadingNumber(o.name),
  }));
  const isNumericMarket =
    numericItems.length >= 2 &&
    numericItems.filter((x) => x.num !== null).length === numericItems.length;

  const ordered = isNumericMarket
    ? [...numericItems]
        .sort((a, b) => (a.num ?? 0) - (b.num ?? 0))
        .map((x) => x.o)
    : topOutcomes;

  const winnerNorm = (settledWinner || "").trim().toLowerCase();
  const outcomes: AtlasCategoryOutcome[] = ordered.map((o, idx) => {
    const won =
      Boolean(winnerNorm) && o.name.trim().toLowerCase() === winnerNorm;
    const lost = Boolean(winnerNorm) && !won;
    return {
      id: `${member.key}-${idx}`,
      label: o.name,
      party: inferParty(o.name, (o as { party?: string | null }).party),
      imageUrl: (o as { image_url?: string | null }).image_url ?? null,
      probability: o.probability,
      renderedPercent:
        (o as { rendered_percent?: number | null }).rendered_percent ??
        Math.round((o.probability ?? 0) * 100),
      openingProbability:
        (o as { opening_probability?: number | null }).opening_probability ??
        null,
      isSettled: Boolean(winnerNorm),
      isWinner: won ? true : lost ? false : null,
      settledResult: won ? "won" : lost ? "lost" : null,
    };
  });

  const meta = {
    marketId: member.id,
    kicker: sectionTitle ? sectionTitle.toUpperCase() : "MIDTERMS 2026",
    marketTitle: data.name,
    source: data.source ?? null,
    resolutionDate: data.resolution_date ?? null,
  };

  const thresholdCount = ordered.filter((o) => isThresholdLabel(o.name)).length;
  if (thresholdCount >= 2) {
    return <ThresholdLadderCard meta={meta} rungs={outcomes} />;
  }

  if (isNumericMarket) {
    return <BucketDistribution meta={meta} buckets={outcomes} />;
  }

  return (
    <RaceCard
      meta={meta}
      contenders={outcomes}
      settledWinner={settledWinner}
    />
  );
}
