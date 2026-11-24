"use client";

import React from "react";
import styles from "./formsLabPreview.module.css";
import type { FallbackRowSpec, FormsLabCardEnvelope, MemberArtSpec } from "./types_forms_lab_13551";

export function MemberAvatar({
  art,
  label,
  small = false,
}: {
  art: MemberArtSpec | null | undefined;
  label: string;
  small?: boolean;
}) {
  if (!art?.url) {
    return (
      <span className={styles.monogram} aria-label={label}>
        {art?.initials || label.slice(0, 2).toUpperCase()}
      </span>
    );
  }
  const pres = art.presentation || "portrait";
  if (pres === "logo") {
    return (
      <span className={`${styles.avatarLogo} ${small ? styles.avatarLogoSm : ""}`}>
        <img src={art.url} alt={label} className={styles.avatarLogoImg} loading="eager" />
      </span>
    );
  }
  if (pres === "poster") {
    return (
      <span className={styles.avatarPoster}>
        <img src={art.url} alt={label} className={styles.avatarCoverImg} loading="eager" />
      </span>
    );
  }
  return (
    <span className={styles.avatarPortrait}>
      <img src={art.url} alt={label} className={styles.avatarCoverImg} loading="eager" />
    </span>
  );
}

export function FallbackRowsView({ card }: { card: FormsLabCardEnvelope }) {
  return (
    <div>
      {card.refusal_reasons.length > 0 && (
        <div className={styles.refusalBanner} data-testid={`refusal-${card.card_id}`}>
          <strong>Truth check refused specialized form:</strong> {card.refusal_reasons.join("; ")}
        </div>
      )}
      <div className={styles.fallbackList}>
        {card.fallback_rows.map((r: FallbackRowSpec, idx: number) => (
          <div key={`${card.card_id}-fb-${idx}`} className={styles.fallbackRow}>
            <MemberAvatar art={r.art} label={r.label} />
            <span className={styles.fallbackLabel}>{r.label}</span>
            <span className={styles.fallbackPct}>{r.pct_label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function FormsLabCardFrame({
  card,
  children,
}: {
  card: FormsLabCardEnvelope;
  children: React.ReactNode;
}) {
  return (
    <article
      className={styles.card}
      data-card-id={card.card_id}
      data-form-variant={card.form_variant}
      data-status={card.status}
    >
      <div className={styles.cardTop}>
        <span className={styles.topicTag}>{card.topic}</span>
        <span className={styles.variantTag}>
          {card.status === "refused_fallback_rows" ? "Fallback rows" : card.form_variant.replace(/_/g, " ")}
        </span>
      </div>
      <h3 className={styles.title}>{card.title}</h3>
      <p className={styles.subtitle}>{card.subtitle}</p>
      {card.status === "refused_fallback_rows" ? <FallbackRowsView card={card} /> : children}
      <div className={styles.footnote}>
        <span>{card.footnote}</span>
        <span className={styles.sourceChip}>{card.source_label}</span>
      </div>
    </article>
  );
}
