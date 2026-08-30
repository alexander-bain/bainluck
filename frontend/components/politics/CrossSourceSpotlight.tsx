/** The cross-source spotlight: the one surface on /politics that deliberately
 *  shows two sources side by side instead of the blend.
 *
 *  Lifted verbatim out of `app/politics/page.tsx` by UX-P187 (a Next.js route
 *  file may only export the reserved names, so nothing inside one can be
 *  rendered by a test) and given the outcome caption in the same move. The
 *  legacy copy, wrong in exactly the way this one is not, is banked at
 *  `frontend/__tests__/fixtures/uxp187CrossSourceCardLegacy.tsx`.
 */
import type { CrossSourceMatch } from "@/lib/api";
import { BORDER_COLOR, SourceBadge } from "@/components/politics/atoms";
import s from "@/app/politics/politics.module.css";

export function CrossSourceSpotlight({ matches }: { matches: CrossSourceMatch[] }) {
  if (!matches || matches.length === 0) return null;

  return (
    <div className={s.section}>
      <div className={s.sectionHead}>
        <h2 className={s.sectionTitle}>
          <span className={s.sectionEmoji}>⇄</span>
          Cross-source spotlight
          <span className={s.sectionCount}>
            Markets where sources disagree
          </span>
        </h2>
      </div>
      <div className={s.grid}>
        {matches.slice(0, 4).map((m, i) => (
          <CrossSourceCard key={i} market={m} />
        ))}
      </div>
    </div>
  );
}

export function CrossSourceCard({ market }: { market: CrossSourceMatch }) {
  const delta = market.delta;
  const merged = (market.kalshi + market.poly) / 2;
  const arbitrage = delta > 5;
  const disagree = delta > 2;
  const borderColor = BORDER_COLOR[market.category] || "#9CA3AF";

  return (
    <div className={s.crossCard} style={{ borderTop: `2px solid ${borderColor}` }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        <SourceBadge source="both" />
        {arbitrage && (
          <span className={s.spreadBadge}>⚠ {delta.toFixed(1)}pt spread</span>
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

      {/* WHICH outcome the two numbers price. Under "Kraków mayoral election
          winner?" a bare "Kalshi 65.5% / Polymarket 33.5%" does not say what
          either side is 65.5% about, and the spread below it is only a spread
          because both are Łukasz Gibała. Unlike the weather page's leader
          caption this is named even when it reads "Yes": the defect this card
          used to have was comparing one source's Yes against the other's No,
          so on a comparison surface "Yes" is the load-bearing word, not a
          restatement of the question. Absent only on a pre-deploy cached
          payload. */}
      {market.outcome ? (
        <p
          style={{
            margin: 0,
            marginTop: -6,
            fontSize: 12,
            fontWeight: 600,
            color: "var(--text-secondary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={market.outcome}
        >
          {market.outcome}
        </p>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
          marginTop: 2,
        }}
      >
        <div className={s.sourceCellKalshi}>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "#22C55E",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Kalshi
          </span>
          <span
            className={s.probNum}
            style={{
              fontSize: 22,
              color: market.kalshi >= market.poly ? "#111827" : "#6B7280",
            }}
          >
            {market.kalshi.toFixed(1)}%
          </span>
        </div>
        <div className={s.sourceCellPoly}>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "#3B82F6",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Polymarket
          </span>
          <span
            className={s.probNum}
            style={{
              fontSize: 22,
              color: market.poly >= market.kalshi ? "#111827" : "#6B7280",
            }}
          >
            {market.poly.toFixed(1)}%
          </span>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 11,
          color: "var(--text-muted)",
          marginTop: 2,
        }}
      >
        <span>
          Merged:{" "}
          <b className={s.probNum} style={{ color: "var(--text-primary)" }}>
            {merged.toFixed(1)}%
          </b>
        </span>
        {disagree && (
          <span>
            Disagree by{" "}
            <b className={s.probNum} style={{ color: "#B45309" }}>
              {delta.toFixed(1)}pp
            </b>
          </span>
        )}
      </div>
    </div>
  );
}
