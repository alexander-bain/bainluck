"use client";

import React from "react";
import styles from "./formsLabPreview.module.css";
import { FormsLabCardFrame, MemberAvatar } from "./FormsLabShell";
import type {
  BubbleAndCutBody,
  BubbleTeamSpec,
  ConferenceCutSpec,
  FormsLabCardEnvelope,
} from "./types_forms_lab_13551";

interface PlacedBubble {
  team: BubbleTeamSpec;
  leftPct: number;
  topPct: number;
  isFocus: boolean;
}

function layoutBubbles(teams: BubbleTeamSpec[], focusCodes: Set<string>): PlacedBubble[] {
  const tracksY = [27, 42, 57, 72, 87];
  const lastXByTrack = [-99, -99, -99, -99, -99];
  const sorted = [...teams].sort((a, b) => a.pct - b.pct);
  const placed: PlacedBubble[] = [];

  for (const team of sorted) {
    const leftPct = Math.min(93, Math.max(7, 7 + (team.pct / 100) * 86));
    let chosenTrack = 0;
    let bestSpacing = -1;
    for (let idx = 0; idx < tracksY.length; idx++) {
      const gap = leftPct - lastXByTrack[idx];
      if (gap >= 8.5) {
        chosenTrack = idx;
        break;
      }
      if (gap > bestSpacing) {
        bestSpacing = gap;
        chosenTrack = idx;
      }
    }
    lastXByTrack[chosenTrack] = leftPct;
    placed.push({
      team,
      leftPct,
      topPct: tracksY[chosenTrack],
      isFocus: focusCodes.has(team.code) || (team.pct >= 40 && team.pct <= 60),
    });
  }
  return placed;
}

function bandClass(band?: string): string {
  if (band === "safe") return styles.cutSafe;
  if (band === "bubble") return styles.cutBubble;
  if (band === "chase") return styles.cutChase;
  return styles.cutLong;
}

function renderBubbleLine(body: BubbleAndCutBody) {
  const low = body.bubble_low ?? 40;
  const high = body.bubble_high ?? 60;
  const focusCodes = new Set((body.focus_teams || []).map((t) => t.code));
  const placed = layoutBubbles(body.teams || [], focusCodes);
  const zoneLeft = 6 + (low / 100) * 88;
  const zoneWidth = ((high - low) / 100) * 88;

  return (
    <div>
      <div className={styles.bubbleBox}>
        <div
          className={styles.bubbleZone}
          style={{ left: `${zoneLeft}%`, width: `${zoneWidth}%` }}
        >
          <span className={styles.bubbleZoneLabel}>
            Bubble {low}%–{high}%
          </span>
        </div>
        {placed.map(({ team, leftPct, topPct }) => {
          const inDoubt = team.pct >= low && team.pct <= high;
          return (
            <div
              key={team.name}
              title={`${team.name}: ${team.pct_label}`}
              className={`${styles.bubbleDot} ${inDoubt ? styles.bubbleDotDoubt : ""}`}
              style={{ left: `${leftPct}%`, top: `${topPct}%` }}
            >
              {team.art.url ? (
                <img src={team.art.url} alt={team.name} className={styles.avatarLogoImg} />
              ) : (
                <span>{team.code}</span>
              )}
            </div>
          );
        })}
      </div>
      <div className={styles.axisTickRow}>
        <span>0%</span>
        <span>25%</span>
        <span>40%–60% bubble</span>
        <span>75%</span>
        <span>100%</span>
      </div>
      <div className={styles.bubbleFocusStrip}>
        {(body.teams || [])
          .filter((t) => t.pct >= low && t.pct <= high)
          .map((t) => (
            <span key={`doubt-${t.code}`} className={styles.bubbleFocusPill}>
              {t.code} {t.pct_label}
            </span>
          ))}
      </div>
    </div>
  );
}

function renderTheCut(body: BubbleAndCutBody) {
  const conferences = body.conferences || [];
  return (
    <div className={styles.cutGrid}>
      {conferences.map((conf: ConferenceCutSpec) => {
        const above = conf.teams.slice(0, conf.places);
        const below = conf.teams.slice(conf.places);
        return (
          <div key={conf.conference}>
            <h4 className={styles.cutColTitle}>
              <span>{conf.conference}</span>
              <span>
                {conf.total_teams} → {conf.places}
              </span>
            </h4>
            {above.map((t) => (
              <div
                key={t.name}
                className={`${styles.cutRow} ${bandClass(t.likelihood_band)}`}
                title={`${t.name}: ${t.pct_label}`}
              >
                <span className={styles.cutRank}>{t.rank}</span>
                <MemberAvatar art={t.art} label={t.name} small />
                <span className={styles.cutName}>{t.code}</span>
                <span className={styles.cutPct}>{t.pct_label}</span>
              </div>
            ))}
            <div className={styles.cutLine}>
              <span className={styles.cutLineBadge}>
                {conf.has_cut_tie ? `${conf.cut_label} · 38% tie` : conf.cut_label}
              </span>
            </div>
            {below.map((t) => (
              <div
                key={t.name}
                className={`${styles.cutRow} ${bandClass(t.likelihood_band)}`}
                title={`${t.name}: ${t.pct_label}`}
              >
                <span className={styles.cutRank}>{t.rank}</span>
                <MemberAvatar art={t.art} label={t.name} small />
                <span className={styles.cutName}>{t.code}</span>
                <span className={styles.cutPct}>{t.pct_label}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export function BubbleAndCutCard({ card }: { card: FormsLabCardEnvelope }) {
  const body = card.body as unknown as BubbleAndCutBody;
  return (
    <FormsLabCardFrame card={card}>
      {card.form_variant === "bubble_line" ? renderBubbleLine(body) : renderTheCut(body)}
    </FormsLabCardFrame>
  );
}
