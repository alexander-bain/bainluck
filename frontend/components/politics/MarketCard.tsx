"use client";

import Link from "next/link";
import type { PoliticsMarketRow } from "@/lib/api";
import { twoLegCardPair } from "@/lib/twoLegCardPair";
import { renderedOutcomeRowPercents } from "@/lib/renderedPercent";
import { BORDER_COLOR, SourceBadge } from "./atoms";
import s from "@/app/politics/politics.module.css";

export default function MarketCard({
  market,
  theme,
  forceField = false,
  forceDuel = false,
}: {
  market: PoliticsMarketRow;
  theme: string;
  forceField?: boolean;
  forceDuel?: boolean;
}) {
  const borderColor = BORDER_COLOR[theme] || "#9CA3AF";
  // #6766 — TWO LEGS IS NOT THE SAME FACT AS TWO SIDES OF ONE QUESTION.
  //
  // `outcome_count <= 2` was the whole test, and `BinaryCard` is built on the two
  // legs being complements: it prints one number, derives the other, and draws
  // them as the two ends of one full bar. A two-RUNG market satisfies the arity
  // and denies the premise — "Before Nov 3, 2026" 2.5% beside "Before Oct 1,
  // 2026" 1.0% are nested rungs summing to 3.5, and the card printed 98% under
  // the second name. `twoLegCardPair` decides it on the prices, and a pair that
  // is not one question is rendered by `MultiCard`, which is this page's own
  // render for independent rungs — leader, its bar, then each runner-up with its
  // OWN served price. No new markup, and nothing that draws a partition the
  // prices deny.
  const pair = twoLegCardPair(market);
  const isBinary = !forceField && ((forceDuel && market.top_outcomes.length >= 2) || (market.outcome_count <= 2 && pair.oneQuestion));

  if (isBinary) {
    return <BinaryCard market={market} borderColor={borderColor} />;
  }
  return <MultiCard market={market} borderColor={borderColor} showAll={forceField} />;
}

function BinaryCard({
  market,
  borderColor,
}: {
  market: PoliticsMarketRow;
  borderColor: string;
}) {
  // #6766: the second number is the SERVED leg wherever the payload carries one.
  // `MarketCard` above only routes a complement pair here, so `second` is
  // non-null and the two round through the pair contract (#2831) rather than
  // independently — which is also why `94.5 / 5.5` stops printing `95% vs 6%`.
  const { first, second } = twoLegCardPair(market);
  const yesProb = first.prob;
  const noProb = second?.prob ?? 100 - yesProb;
  const [yesPct, noPct] = renderedOutcomeRowPercents([yesProb / 100, noProb / 100]);
  const yesLeads = yesProb >= 50;

  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.marketCard} style={{ borderTop: `2px solid ${borderColor}` }}>
        <div className={s.marketCardInner}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
            <SourceBadge source={market.src} />
          </div>

          <h3
            style={{
              margin: 0,
              fontSize: 14,
              fontWeight: 500,
              lineHeight: 1.35,
              color: "var(--text-primary)",
            }}
          >
            {market.q}
          </h3>

          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span
              className={s.probNum}
              style={{ fontSize: 24, color: yesLeads ? "#16A34A" : "#111827" }}
            >
              {yesPct ?? Math.round(yesProb)}%
            </span>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {first.name}
            </span>
            <span
              style={{
                marginLeft: "auto",
                fontSize: 11,
                color: "var(--text-muted)",
              }}
            >
              vs{" "}
              <span className={s.probNum}>{noPct ?? Math.round(noProb)}%</span>{" "}
              {second?.name || "No"}
            </span>
          </div>

          {twoLegCardPair(market).oneQuestion && <div className={s.binaryBar}>
            <div style={{ width: `${yesProb}%`, background: "#16A34A" }} />
            <div style={{ width: `${noProb}%`, background: "#94A3B8" }} />
          </div>}
        </div>
      </div>
    </Link>
  );
}

function MultiCard({
  market,
  borderColor,
  showAll = false,
}: {
  market: PoliticsMarketRow;
  borderColor: string;
  showAll?: boolean;
}) {
  const leader = market.top_outcomes?.[0];
  if (!leader) return null;
  // #9109: the server counts the rungs the page behind this card shows and the
  // card does not. `outcome_count - 3` counted passed deadlines the page drops
  // ("+9 more" over two rows); it is only the fallback for an older payload.
  const moreCount = showAll ? Math.max(0, market.outcome_count - market.top_outcomes.length) : market.more_count ?? market.outcome_count - 3;
  // #9474: "Leader" is a claim that the rows compete for one win. On a ladder
  // ("Before Jan 3, 2027" ⊃ "Before Dec 12, 2026"; "At least 1" ⊃ "At least 2")
  // the top row is the loosest rung by construction, and on a pick-several
  // list every row can come true — 57 of 68 cards on 2026-09-28 were one of
  // those and all 57 said "Leader". The word goes; the row stays.
  const namesALeader = market.mutually_exclusive !== false;

  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.marketCard} style={{ borderTop: `2px solid ${borderColor}` }}>
        <div className={s.marketCardInner}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
            <SourceBadge source={market.src} />
            {moreCount > 0 && (
              <span
                style={{
                  marginLeft: "auto",
                  fontFamily: "var(--font-mono, monospace)",
                  fontSize: 10,
                }}
              >
                +{moreCount} more
              </span>
            )}
          </div>

          <h3
            style={{
              margin: 0,
              fontSize: 14,
              fontWeight: 500,
              lineHeight: 1.35,
              color: "var(--text-primary)",
            }}
          >
            {market.q}
          </h3>

          {/* #9474 follow-up: a pick-several row's name can be a whole case
              caption ("Bird v. Iowa Migrant Movement for Justice"); with no gap
              it ran into the number as "…for Justice39%". The name wraps, the
              number keeps its width. */}
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
              {namesALeader && (
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    fontWeight: 600,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  Leader
                </span>
              )}
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  marginTop: namesALeader ? 2 : 0,
                }}
              >
                {leader.name}
              </span>
            </div>
            <span
              className={s.probNum}
              style={{ fontSize: 28, color: "var(--text-primary)", flexShrink: 0 }}
            >
              {Math.round(leader.prob)}%
            </span>
          </div>

          <div
            style={{
              height: 4,
              background: "#E5E7EB",
              borderRadius: 9999,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.max(leader.prob, 2)}%`,
                height: "100%",
                background: "#8B5CF6",
                opacity: 0.7,
              }}
            />
          </div>

          {/* Runner-up outcomes */}
          {market.top_outcomes.length > 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 2 }}>
              {market.top_outcomes.slice(1, showAll ? undefined : 3).map((o, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "var(--text-secondary)" }}>{o.name}</span>
                  <span className={s.probNum} style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {Math.round(o.prob)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

