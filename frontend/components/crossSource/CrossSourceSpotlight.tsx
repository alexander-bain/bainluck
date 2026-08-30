/** The cross-source spotlight: the one surface that deliberately shows two
 *  sources side by side instead of the blend.
 *
 *  Lifted verbatim out of `app/politics/page.tsx` by UX-P187 (a Next.js route
 *  file may only export the reserved names, so nothing inside one can be
 *  rendered by a test) and given the outcome caption in the same move. The
 *  legacy copy, wrong in exactly the way this one is not, is banked at
 *  `frontend/__tests__/fixtures/uxp187CrossSourceCardLegacy.tsx`.
 *
 *  Moved out of `components/politics/` by UX-P194 and into a page-neutral home,
 *  because it is no longer a politics component. `/economics` and
 *  `/entertainment` build the identical payload off the identical shared
 *  `find_cross_source_markets` — measured live 2026-08-30, eight rows each —
 *  and neither had ever declared the field, let alone rendered it. There is one
 *  card, in one place, on all three pages: a second copy is how the two numbers
 *  a reader is invited to subtract start disagreeing about what they mean.
 *
 *  The STYLESHEET deliberately stays at `app/politics/politics.module.css`
 *  rather than being forked per page — the same class names on the same
 *  stylesheet, not a copy, which is the precedent UX-P187 set and wrote down in
 *  `components/politics/atoms.tsx`. Splitting it is how the three copies drift.
 */
import type { CrossSourceMatch } from "@/lib/api";
import { SourceBadge } from "@/components/politics/atoms";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { renderedPercent } from "@/lib/renderedPercent";
import s from "@/app/politics/politics.module.css";

/** Category → accent, across every vocabulary that reaches this card.
 *
 *  One map rather than a per-page prop: the card is shared, so the colour a
 *  given category draws should not depend on which page happens to host it.
 *  Politics' keys are `components/politics/atoms.tsx`'s BORDER_COLOR verbatim;
 *  the economics and entertainment keys are their routes' `_classify_theme`
 *  vocabularies. Anything unlisted — including a category a route adds later —
 *  falls to the same grey the card has always used, so a new theme degrades to
 *  a plain card instead of an absent one.
 */
export const CROSS_SOURCE_BORDER_COLOR: Record<string, string> = {
  // /politics
  presidential: "#3B82F6",
  congressional: "#8B5CF6",
  gubernatorial: "#10B981",
  policy: "#F59E0B",
  scotus: "#EF4444",
  international: "#0EA5E9",
  // /economics
  fed: "#6366F1",
  inflation: "#F59E0B",
  jobs: "#10B981",
  recession: "#EF4444",
  markets: "#3B82F6",
  energy: "#F97316",
  housing: "#8B5CF6",
  trade: "#0EA5E9",
  government: "#64748B",
  // /entertainment
  music: "#EC4899",
  movies: "#8B5CF6",
  tv_streaming: "#EF4444",
  awards: "#F59E0B",
  celebrity: "#F472B6",
  social_media: "#0EA5E9",
  viral: "#14B8A6",
  // shared fallback key
  other: "#9CA3AF",
};

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
  const borderColor = CROSS_SOURCE_BORDER_COLOR[market.category] || "#9CA3AF";

  // ── THE PRINTED PAIR (UX-P191) ─────────────────────────────────────────────
  //
  // `kalshi` and `poly` arrive as 0-100 percents at one decimal. Every other
  // market number on /politics goes through `formatProbabilityPercent` —
  // UX-P046's single home for "what percentage does this probability print" —
  // and this card did not. It printed `.toFixed(1)`, which forces a decimal
  // digit onto a number that does not have one: measured on the deployed
  // payload 2026-08-30, **6 of the 8 served matches** carry at least one whole
  // value — including three of the FOUR rows the section renders — so the card
  // printed `86.0%`, `95.0%`, `88.0%`, `16.0%`.
  //
  // Bypassing the single home also bypassed its BOUNDARY RULE, and this is the
  // one surface that selects for extremes by construction — the list is sorted
  // by delta descending, so a side pinned near 0 or 100 is precisely what
  // reaches it. A live price of 0.04% printed `0.0%` here, which is the exact
  // thing UX-P046 exists to stop a surface saying.
  //
  // ** NOT the presidential bar race, which keeps its one decimal. ** That is
  // not an oversight and not the same call: measured live the same day, its 14
  // candidates sit between 2.7% and 10.5%, and whole numbers put five
  // consecutive rows on `4%` in a table whose first column is the rank. A
  // decimal earns its place there and does not here.
  const kalshiPct = formatProbabilityPercent(market.kalshi / 100);
  const polyPct = formatProbabilityPercent(market.poly / 100);

  // Every other number on the card is DERIVED FROM THE PRINTED PAIR rather than
  // rounded on its own, so the subtraction a reader can do actually holds.
  // Rounding the served `delta` independently breaks it: `4.5 / 86.0` prints
  // `5% / 86%`, a gap of 81, while its served delta of 81.5 rounds to 82. Two
  // of the eight live cards land in that gap.
  const kalshiWhole = renderedPercent(market.kalshi / 100) ?? 0;
  const polyWhole = renderedPercent(market.poly / 100) ?? 0;
  const printedDelta = Math.abs(kalshiWhole - polyWhole);
  const printedMerged = Math.round((kalshiWhole + polyWhole) / 2);

  // The GATES stay on the served float: which cards earn a badge is a curation
  // decision, and it should be made at the server's precision rather than by a
  // display artifact. Safe against a nonsense badge because rounding each side
  // moves it by at most half a point, so `printedDelta` is never more than one
  // away from `delta` — `delta > 2` forces `printedDelta >= 2`, and
  // `delta > 5` forces `printedDelta >= 5`.
  const arbitrage = delta > 5;
  const disagree = delta > 2;

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
          <span className={s.spreadBadge}>⚠ {printedDelta}pt spread</span>
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
            {kalshiPct}
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
            {polyPct}
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
            {printedMerged}%
          </b>
        </span>
        {disagree && (
          <span>
            Disagree by{" "}
            <b className={s.probNum} style={{ color: "#B45309" }}>
              {printedDelta}pp
            </b>
          </span>
        )}
      </div>
    </div>
  );
}
