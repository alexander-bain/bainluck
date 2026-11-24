"use client";

import React from "react";
import styles from "./formsLabPreview.module.css";
import { FormsLabCardFrame, MemberAvatar } from "./FormsLabShell";
import type { CastingRowSpec, CastingSheetBody, FormsLabCardEnvelope } from "./types_forms_lab_13551";

export function CastingSheetCard({ card }: { card: FormsLabCardEnvelope }) {
  const body = card.body as unknown as CastingSheetBody;
  const rows = body?.rows || [];

  return (
    <FormsLabCardFrame card={card}>
      <div className={styles.castingList}>
        {rows.map((row: CastingRowSpec) => (
          <div key={row.role} className={styles.castingRow}>
            <span className={styles.castingRole}>{row.role}</span>
            <div className={styles.coAvatarPair}>
              <MemberAvatar art={row.art} label={row.leader} />
              {row.co_leader && (
                <span className={styles.coAvatarSecond}>
                  <MemberAvatar art={row.co_leader.art} label={row.co_leader.name} />
                </span>
              )}
            </div>
            <div className={styles.castingLeaderWrap}>
              <div className={`${styles.castingLeaderName} ${row.is_tie ? styles.castingLeaderNameWrap : ""}`}>
                {row.co_leader ? `${row.leader} & ${row.co_leader.name}` : row.leader}
              </div>
              <span className={`${styles.castingWord} ${row.is_tie ? styles.castingWordTie : ""}`}>
                {row.certainty}
              </span>
            </div>
            <span className={styles.castingPct}>{row.pct_label}</span>
          </div>
        ))}
      </div>
    </FormsLabCardFrame>
  );
}
