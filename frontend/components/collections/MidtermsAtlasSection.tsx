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

function isPartyOutcomeName(label: string): boolean {
  return /^(republican(?:s| party)?|democrat(?:s|ic(?: party)?)?|gop)$/i.test(
    (label || "").trim()
  );
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
    const winnerParty = ctrl.winner ? inferParty(ctrl.winner) : null;
    const settledWinner =
      winnerParty === "R"
        ? "Republicans"
        : winnerParty === "D"
          ? "Democrats"
          : ctrl.winner ?? null;
    const gopWon =
      Boolean(settledWinner) &&
      (winnerParty === "R" || settledWinner === "Republicans");
    const demWon =
      Boolean(settledWinner) &&
      (winnerParty === "D" || settledWinner === "Democrats");
    const hasGop = typeof ctrl.gop === "number" && Number.isFinite(ctrl.gop);
    const hasDem = typeof ctrl.dem === "number" && Number.isFinite(ctrl.dem);

    return (
      <RaceCard
        key={label}
        meta={{
          marketId: ctrl.market_id,
          kicker: `CHAMBER CONTROL · ${settledWinner ? "settled" : "open"}`,
          marketTitle: `${label} Control`,
          source: ctrl.source && ctrl.source.trim() ? ctrl.source.trim() : null,
        }}
        settledWinner={settledWinner}
        contenders={[
          {
            id: `${label}-rep`,
            label: "Republicans",
            party: "R",
            probability: hasGop ? ctrl.gop / 100 : null,
            renderedPercent: hasGop ? Math.round(ctrl.gop) : null,
            isSettled: Boolean(settledWinner),
            isWinner: settledWinner ? gopWon : null,
            settledResult: settledWinner ? (gopWon ? "won" : "lost") : null,
          },
          {
            id: `${label}-dem`,
            label: "Democrats",
            party: "D",
            probability: hasDem ? ctrl.dem / 100 : null,
            renderedPercent: hasDem ? Math.round(ctrl.dem) : null,
            isSettled: Boolean(settledWinner),
            isWinner: settledWinner ? demWon : null,
            settledResult: settledWinner ? (demWon ? "won" : "lost") : null,
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
  const topOutcomes = (data.top_outcomes ?? []).filter((o) =>
    Boolean((o?.name || "").trim())
  );
  if (topOutcomes.length === 0) {
    return null;
  }
  const settledWinner =
    (data.settled_winner && data.settled_winner.trim()) ||
    topOutcomes
      .find(
        (o) =>
          (
            o as {
              is_winner?: boolean | null;
              resolution_source?: string | null;
            }
          ).is_winner === true &&
          (o as { resolution_source?: string | null }).resolution_source ===
            "venue_settlement"
      )
      ?.name?.trim() ||
    topOutcomes
      .find((o) => (o as { result?: string | null }).result === "yes")
      ?.name?.trim() ||
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
  const winnerParty = settledWinner ? inferParty(settledWinner) : null;
  const outcomes: AtlasCategoryOutcome[] = ordered.map((o, idx) => {
    const outParty = inferParty(o.name, (o as { party?: string | null }).party);
    const won =
      Boolean(winnerNorm) &&
      (o.name.trim().toLowerCase() === winnerNorm ||
        (isPartyOutcomeName(o.name) &&
          winnerParty !== null &&
          outParty === winnerParty));
    const lost = Boolean(winnerNorm) && !won;
    const hasProb =
      typeof o.probability === "number" && Number.isFinite(o.probability);
    return {
      id: `${member.key}-${idx}`,
      label: o.name,
      party: outParty,
      imageUrl: (o as { image_url?: string | null }).image_url ?? null,
      imageTitle: o.image_title,
      probability: hasProb ? o.probability : null,
      renderedPercent:
        (o as { rendered_percent?: number | null }).rendered_percent ??
        (hasProb ? Math.round(o.probability! * 100) : null),
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
    source: data.source && data.source.trim() ? data.source.trim() : null,
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
