/**
 * THE PICTURE A PASTED LINK UNFURLS WITH (#5888).
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * `/tournaments/[slug]` and `/event/[domain]/[slug]` got their WORDS right in
 * #5813 and #5833 — "US Open 2026: Alexander Zverev 57%, Elena Rybakina 99%",
 * "2026 Midterm Elections: Xavier Becerra 96%, Steve Hilton 4%" — and then sat
 * that specific sentence next to the site's house card. Measured with a crawler
 * UA on 2026-09-13 at 10:13:53Z, three unrelated links named ONE picture:
 *
 *   /tournaments/us-open                              -> /opengraph-image
 *   /event/election/2026-midterms                     -> /opengraph-image
 *   /event/ufc/contender-series-hunt-vs-perea-26sep15 -> /opengraph-image
 *
 * `GET /opengraph-image` answered `200 image/png`, md5
 * `99618661539802337202ef69dc6595bc`, on every read. `/events/[id]` and
 * `/futures/[id]` already served their own card, so the mechanism was built and
 * proven; these two routes were the ones it had never been extended to.
 *
 * ═══ WHY ONE COMPONENT AND NOT A THIRD COPY ═══
 *
 * `/events/[id]` and `/futures/[id]` each hold a standalone ~190-line image
 * route with its own inlined palette. Adding two more copies would put four
 * hand-maintained colour tables in the tree and make "the cards look like one
 * family" a thing nobody can check. Both new routes render THIS, and differ only
 * in the facts they hand it.
 *
 * The two existing routes are deliberately NOT migrated here: they are live,
 * certed and shipping correct pictures, and rewriting them is a change with no
 * reader on the other end. Named residue, not an oversight.
 *
 * ═══ WHY IT TAKES FORMATTED STRINGS ═══
 *
 * `probability` arrives as `"57%"`, already through `formatShareProbability` —
 * the same function the title used. The alternative is handing this component a
 * number and letting it format, which is how a card ends up rounding one way
 * while the sentence under it rounds the other. It draws; it does not decide.
 *
 * ⚠️ Satori (what `ImageResponse` renders with) is not a browser. Any element
 * with more than one child needs an explicit `display: "flex"`, CSS variables do
 * not resolve, and there is no cascade — so every colour here is a literal and
 * that is intentional, not a design-system violation. This file is also why
 * there is no `"use client"`: it runs on the edge at request time.
 */

export interface UnfurlCardRow {
  /** The competitor, candidate or contender. */
  name: string;
  /** Already formatted by `formatShareProbability`, e.g. `"57%"`. */
  probability: string;
  /** 0..1, for the bar. Drawn from the same value the string was made from. */
  fraction: number;
  /** The draw or contest this row belongs to ("Men's Singles"), when it has one. */
  sublabel?: string | null;
}

export interface UnfurlCardProps {
  /** The pill in the top right: "Tennis", "UFC", "Election". */
  eyebrow: string;
  /** The subject — the tournament or event's own name. */
  title: string;
  /** Venue, location, or the contest label. Rendered under the title. */
  subtitle?: string | null;
  /** Front-runners, best first. Empty draws the quiet card. */
  rows: UnfurlCardRow[];
  /**
   * The bottom-left line: "2 draws tracked", "25 candidates".
   *
   * Kept to a counted fact. Notice 34 — no diagnostic prose on a reader's
   * screen, and a share card is the most public screen we have.
   */
  note?: string | null;
  /**
   * The line that replaces the numbers when there is nothing honest to print:
   * a settled result, or a link that names nothing. Suppresses `rows`.
   */
  verdict?: string | null;
  accent: string;
}

const COLOR_WHITE = "#ffffff";
const COLOR_PRIMARY = "#111827";
const COLOR_SECONDARY = "#374151";
const COLOR_MUTED = "#6b7280";
const COLOR_SUBTLE = "#94a3b8";
const COLOR_BAR_BG = "#f1f5f9";

export const DEFAULT_ACCENT = "#10B981";

/**
 * Accent per category, copied in value (not imported) from
 * `/futures/[id]/opengraph-image.tsx` so the family reads as one set.
 *
 * Keyed on the concept route's own `domain` segment as well as the sport names,
 * because that segment is the one signal available before the payload is
 * fetched — and it is still available when the fetch fails.
 */
const CATEGORY_ACCENT: Record<string, string> = {
  basketball: "#c24005",
  football: "#0d803d",
  baseball: "#ba1c1c",
  hockey: "#2663eb",
  soccer: "#049966",
  golf: "#176633",
  tennis: "#7c9a1f",
  mma: "#991c1c",
  ufc: "#991c1c",
  boxing: "#9a3412",
  economics: "#7c3aed",
  politics: "#4338ca",
  election: "#4338ca",
  tech: "#0891b2",
  culture: "#db2777",
  weather: "#0284c7",
  entertainment: "#bf26d6",
  awards: "#bf26d6",
  cricket: "#14b8a6",
  olympics: "#d97706",
  f1: "#dc2626",
  esports: "#6d28d9",
};

export function accentFor(category: string | null | undefined): string {
  if (!category) return DEFAULT_ACCENT;
  return CATEGORY_ACCENT[category.toLowerCase()] || DEFAULT_ACCENT;
}

/**
 * Satori does not wrap-and-ellipsize the way a browser does, so long text is
 * cut here. The limits are per-slot rather than one constant: a title has two
 * lines to live in and a row name has half a line beside its percentage.
 */
export function clampText(value: string, maxLength: number): string {
  const trimmed = value.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

/** How many rows fit above the footer without the card becoming a table. */
const MAX_ROWS = 3;

export function UnfurlCard({
  eyebrow,
  title,
  subtitle,
  rows,
  note,
  verdict,
  accent,
}: UnfurlCardProps) {
  const visible = verdict ? [] : rows.slice(0, MAX_ROWS);
  // One row gets the hero treatment `/futures/[id]` uses; two or three share the
  // space evenly. The percentage is the largest thing on the card either way,
  // because it is the thing the reader stopped scrolling for.
  const hero = visible.length === 1;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: COLOR_WHITE,
        color: COLOR_PRIMARY,
        fontFamily: "Inter, Arial, sans-serif",
      }}
    >
      <div style={{ height: 6, background: accent, width: "100%", display: "flex" }} />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          flex: 1,
          padding: "44px 64px 48px",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          {/*
            A typographic wordmark, and NOT the 🍀 the other four cards use.

            Satori resolves an emoji through `loadAdditionalAsset`, which fetches
            the glyph from a third-party CDN at render time. Measured here: with
            the clover in this header the route does not degrade to a missing
            character, it fails outright — `next start` answered every
            `opengraph-image` request with "failed to pipe response / fetch
            failed … loadAdditionalAsset", HTTP 000 to the client, on all seven
            branches. On Vercel that fetch succeeds (`/opengraph-image`,
            `/events/15304875/opengraph-image` and `/futures/109952/opengraph-image`
            all answered `200 image/png` in 0.6–1.2s while this was written), so
            the four existing cards are not broken and this is not a bug report
            about them.

            It is still a dependency the most public surface we have does not
            need: one third-party round trip per unfurl, on a path where failure
            is total rather than cosmetic. Dropping it also makes this component
            renderable in the sandbox and in CI, which is the only reason the
            before/after for #5888 could be shot at all.

            Named residue: the same swap in `app/opengraph-image.tsx`,
            `app/about/opengraph-image.tsx`, `/events/[id]` and `/futures/[id]`.
          */}
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ fontSize: 28, fontWeight: 800, letterSpacing: -0.5 }}>
              Bain Luck
            </span>
          </div>
          <div
            style={{
              display: "flex",
              border: `2px solid ${accent}`,
              borderRadius: 999,
              padding: "8px 20px",
              fontSize: 19,
              fontWeight: 700,
              color: accent,
            }}
          >
            {clampText(eyebrow, 28)}
          </div>
        </div>

        {/* Body */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
          <div
            style={{
              fontSize: hero || verdict ? 46 : 40,
              fontWeight: 800,
              lineHeight: 1.15,
              color: COLOR_PRIMARY,
              maxWidth: 1020,
            }}
          >
            {clampText(title, 72)}
          </div>

          {subtitle ? (
            <div style={{ fontSize: 24, color: COLOR_MUTED, lineHeight: 1.3, maxWidth: 960 }}>
              {clampText(subtitle, 90)}
            </div>
          ) : null}

          {verdict ? (
            <div
              style={{
                display: "flex",
                marginTop: 14,
                fontSize: 40,
                fontWeight: 800,
                color: COLOR_SECONDARY,
              }}
            >
              {clampText(verdict, 60)}
            </div>
          ) : null}

          {visible.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: hero ? 6 : 18, marginTop: 12 }}>
              {visible.map((row) => (
                <div
                  key={`${row.name}-${row.sublabel ?? ""}`}
                  style={{ display: "flex", flexDirection: "column", gap: 8 }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      justifyContent: "space-between",
                      gap: 24,
                    }}
                  >
                    <span
                      style={{
                        fontSize: hero ? 44 : 32,
                        fontWeight: 800,
                        color: COLOR_PRIMARY,
                      }}
                    >
                      {clampText(row.name, hero ? 34 : 30)}
                    </span>
                    <span
                      style={{
                        fontSize: hero ? 92 : 44,
                        fontWeight: 900,
                        letterSpacing: hero ? -2 : -1,
                        lineHeight: 1,
                        color: COLOR_PRIMARY,
                      }}
                    >
                      {row.probability}
                    </span>
                  </div>

                  <div
                    style={{
                      width: "100%",
                      height: hero ? 22 : 14,
                      borderRadius: 999,
                      background: COLOR_BAR_BG,
                      overflow: "hidden",
                      display: "flex",
                    }}
                  >
                    <div
                      style={{
                        width: `${barWidth(row.fraction)}%`,
                        height: "100%",
                        borderRadius: 999,
                        background: accent,
                        display: "flex",
                      }}
                    />
                  </div>

                  {row.sublabel ? (
                    <div style={{ display: "flex", fontSize: 20, color: COLOR_SUBTLE }}>
                      {clampText(row.sublabel, 48)}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            color: COLOR_SUBTLE,
            fontSize: 20,
          }}
        >
          <span>{note ? clampText(note, 52) : ""}</span>
          <span style={{ fontWeight: 600 }}>bainluck.com</span>
        </div>
      </div>
    </div>
  );
}

/**
 * The bar never reads as empty or as full.
 *
 * A 99.5% favourite and a certainty are different claims, and a 0.4% longshot
 * that draws a zero-width bar looks like a rendering fault rather than a small
 * number. `/futures/[id]` clamps to the same 3..97 for the same reason.
 */
export function barWidth(fraction: number): number {
  if (!Number.isFinite(fraction)) return 3;
  return Math.max(3, Math.min(97, Math.round(fraction * 100)));
}
