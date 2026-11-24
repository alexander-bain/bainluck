"use client";

import React from "react";
import styles from "./formsLabPreview.module.css";
import { FormsLabCardFrame, MemberAvatar } from "./FormsLabShell";
import type { CalendarStripBody, CalendarTileSpec, FormsLabCardEnvelope } from "./types_forms_lab_13551";

function tileBackgroundVar(intensity: number): string {
  if (intensity >= 0.85) return "var(--fl-cal-4)";
  if (intensity >= 0.45) return "var(--fl-cal-3)";
  if (intensity >= 0.15) return "var(--fl-cal-2)";
  if (intensity >= 0.06) return "var(--fl-cal-1)";
  return "var(--fl-cal-0)";
}

export function CalendarStripCard({ card }: { card: FormsLabCardEnvelope }) {
  const body = card.body as unknown as CalendarStripBody;
  const tiles = body?.tiles || [];
  const allowDailyNumbers = Boolean(body?.decision_367_daily_numbers_enabled);

  return (
    <FormsLabCardFrame card={card}>
      <div>
        <div className={styles.calHeaderRow}>
          <MemberAvatar art={body?.art} label="Spotify" />
          <span className={styles.gridEntityName}>{body?.peak_summary || "Peak window"}</span>
        </div>
        <div className={styles.calGrid} data-decision-367={allowDailyNumbers ? "numbers-on" : "shaded-only"}>
          {tiles.map((t: CalendarTileSpec) => (
            <div
              key={t.date_label}
              className={`${styles.calTile} ${t.is_peak ? styles.calTilePeak : ""}`}
              style={{ background: tileBackgroundVar(t.intensity) }}
              title={t.date_label}
            >
              <span className={styles.calTileMonth}>{t.month}</span>
              <span className={styles.calTileDay}>{t.day_num}</span>
              {allowDailyNumbers && t.daily_number_label && (
                <span className={styles.gridAliasSub}>{t.daily_number_label}</span>
              )}
            </div>
          ))}
        </div>
        <div className={styles.calEnds}>
          <span>{body?.earlier_label}</span>
          <span>{body?.later_label}</span>
        </div>
      </div>
    </FormsLabCardFrame>
  );
}
