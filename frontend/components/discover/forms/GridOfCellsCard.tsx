"use client";

import React from "react";
import styles from "./formsLabPreview.module.css";
import { FormsLabCardFrame, MemberAvatar } from "./FormsLabShell";
import type { FormsLabCardEnvelope, GridOfCellsBody } from "./types_forms_lab_13551";

export function GridOfCellsCard({ card }: { card: FormsLabCardEnvelope }) {
  const body = card.body as unknown as GridOfCellsBody;
  const columns = body?.columns || [];
  const rows = body?.rows || [];

  return (
    <FormsLabCardFrame card={card}>
      <table className={styles.gridTable}>
        <thead>
          <tr className={styles.gridHead}>
            <th>Contender</th>
            {columns.map((col) => (
              <th key={col.key}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className={styles.gridRow}>
              <td>
                <div className={styles.gridEntity}>
                  <MemberAvatar art={row.art} label={row.name} />
                  <span className={styles.gridEntityName}>{row.short_label || row.name}</span>
                </div>
              </td>
              {row.cells.map((cell) => {
                const peak = Boolean(cell.is_row_peak || cell.is_col_peak);
                const muted = cell.pct <= 0 || cell.pct_label === "—";
                return (
                  <td key={`${row.name}-${cell.col_key}`}>
                    <div
                      className={`${styles.gridCell} ${peak ? styles.gridCellPeak : ""} ${muted ? styles.gridCellMuted : ""}`}
                    >
                      {cell.pct_label}
                      {cell.alias_tag && <span className={styles.gridAliasSub}>{cell.alias_tag}</span>}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </FormsLabCardFrame>
  );
}
