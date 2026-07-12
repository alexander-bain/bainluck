"use client";

import { useState, useMemo, useEffect } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import useSWR from "swr";
import Link from "next/link";
import { searchMovie, posterUrl, hasTMDBToken } from "@/lib/tmdb";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchEntertainment } from "@/lib/api";
import { eventPath } from "@/lib/eventKey";
import type {
  EntertainmentData,
  EntMarketRow,
  EntThresholdGroup,
  EntThemeMusic,
  EntThemeMoviesTV,
  EntThemeTechCulture,
} from "@/lib/api";
import ErrorState from "@/components/ErrorState";
import EntertainmentSkeleton from "@/components/skeletons/EntertainmentSkeleton";
import s from "./entertainment.module.css";

// ─────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────

const PALETTE = [
  ["#0F172A", "#334155"],
  ["#1E1B4B", "#4338CA"],
  ["#3F1D38", "#9D174D"],
  ["#7C2D12", "#EA580C"],
  ["#064E3B", "#10B981"],
  ["#0C4A6E", "#0EA5E9"],
  ["#3B0764", "#A855F7"],
  ["#7F1D1D", "#EF4444"],
  ["#365314", "#84CC16"],
  ["#422006", "#A16207"],
  ["#0F172A", "#64748B"],
  ["#1F2937", "#F59E0B"],
];

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  return h;
}

function tileColors(seed: string): [string, string] {
  return PALETTE[Math.abs(hash(seed)) % PALETTE.length] as [string, string];
}

const KIND_EMOJI: Record<string, string> = {
  spotify: "🎧",
  billboard: "📊",
  boxoffice: "🎬",
  rt: "🍅",
  reality: "📺",
  eurovision: "🎤",
  multi: "🌐",
  binary: "✦",
};

const KIND_LABEL: Record<string, string> = {
  spotify: "Spotify",
  billboard: "Billboard",
  boxoffice: "Box Office",
  rt: "Rotten Tomatoes",
  reality: "Reality TV",
  eurovision: "Eurovision",
  multi: "Market",
  binary: "Market",
};

// ─────────────────────────────────────────────────────────
// Shared atoms
// ─────────────────────────────────────────────────────────

function useTMDBPoster(title: string, kind?: string): string | null {
  const [poster, setPoster] = useState<string | null>(null);
  const isMovie = kind === "rt" || kind === "boxoffice";

  useEffect(() => {
    if (!isMovie || !hasTMDBToken()) return;
    let cancelled = false;
    searchMovie(title).then((result) => {
      if (!cancelled && result?.poster_path) {
        setPoster(posterUrl(result.poster_path));
      }
    });
    return () => { cancelled = true; };
  }, [title, isMovie]);

  return poster;
}

function CoverTile({
  title,
  imageUrl,
  size = 44,
  big = false,
  kind,
}: {
  title: string;
  imageUrl?: string | null;
  size?: number;
  big?: boolean;
  kind?: string;
}) {
  const tmdbPoster = useTMDBPoster(title, kind);
  const src = imageUrl || tmdbPoster;
  const [base, tone] = tileColors(title);
  const words = (title || "").split(/\s+/).slice(0, 2);
  const initials =
    words.length === 2
      ? words.map((w) => w[0]).join("")
      : (title || "").slice(0, 4);

  return (
    <div
      className={big ? s.coverLg : s.cover}
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, ${base} 0%, ${tone} 100%)`,
      }}
    >
      {src && (
        <img src={src} alt="" className={s.coverImg} loading="lazy" />
      )}
      {initials.toUpperCase()}
    </div>
  );
}

function TagChip({ emoji, label }: { emoji?: string; label: string }) {
  return (
    <span className={s.tagChip}>
      {emoji && <span style={{ fontSize: 11 }}>{emoji}</span>}
      {label}
    </span>
  );
}

function EntSourceChip({ source }: { source: string }) {
  if (source === "kalshi") {
    return (
      <span className={s.srcKalshi}>
        <span className={s.srcDot} />
        Kalshi
      </span>
    );
  }
  return (
    <span className={s.srcPoly}>
      <span className={s.srcDot} />
      Polymarket
    </span>
  );
}

function EntDelta({ value }: { value: number | null | undefined }) {
  if (!value || Math.abs(value) < 0.1)
    return <span className={s.deltaFlat}>—</span>;
  return (
    <span className={value > 0 ? s.deltaUp : s.deltaDown}>
      {value > 0 ? "↑" : "↓"} {Math.abs(value).toFixed(1)}%
    </span>
  );
}

function MetaRow({
  src,
  volume,
  resolves,
}: {
  src: string;
  volume?: number | null;
  resolves?: string | null;
}) {
  return (
    <div className={s.metaRow}>
      <EntSourceChip source={src} />
      {volume != null && volume > 0 && (
        <span style={{ fontFamily: "var(--font-mono, monospace)", fontVariantNumeric: "tabular-nums" }}>
          Vol ${volume >= 1000 ? `${(volume / 1000).toFixed(0)}k` : volume}
        </span>
      )}
      {resolves && <span>· Resolves {formatDate(resolves)}</span>}
    </div>
  );
}

function ProbPct({ value, size = 14 }: { value: number; size?: number }) {
  return (
    <span
      className={s.probNum}
      style={{ fontSize: size, letterSpacing: size > 24 ? "-0.02em" : "-0.01em" }}
    >
      {Math.round(value)}
      <span style={{ fontSize: size * 0.65, opacity: 0.7 }}>%</span>
    </span>
  );
}

function YesNoBar({ yes, no }: { yes: number; no: number }) {
  return (
    <div className={s.ynBar}>
      <span className={s.ynYes} style={{ width: `${yes}%` }}>
        YES {Math.round(yes)}%
      </span>
      <span className={s.ynNo} style={{ width: `${no}%` }}>
        NO {Math.round(no)}%
      </span>
    </div>
  );
}

function EntProbBar({
  value,
  height = 6,
  color = "#10B981",
}: {
  value: number;
  height?: number;
  color?: string;
}) {
  return (
    <div className={s.probBar} style={{ height }}>
      <div
        className={s.probBarFill}
        style={{ width: `${Math.max(value, 1)}%`, background: color }}
      />
    </div>
  );
}

function EntHistogram({
  data,
  height = 88,
}: {
  data: { range: string; prob: number }[];
  height?: number;
}) {
  const maxV = Math.max(...data.map((d) => d.prob), 0.01);
  return (
    <div>
      <div className={s.histWrap} style={{ height }}>
        {data.map((d, i) => {
          const isPeak = d.prob === maxV;
          return (
            <div
              key={i}
              className={isPeak ? s.histBarPeak : s.histBar}
              style={{ height: `${(d.prob / maxV) * 100}%` }}
              title={`${d.range} · ${Math.round(d.prob * 100)}%`}
            >
              <span className={s.histVal}>{Math.round(d.prob * 100)}</span>
            </div>
          );
        })}
      </div>
      <div className={s.histLabels}>
        {data.map((d, i) => (
          <span key={i} className={s.histLabel}>
            {d.range}
          </span>
        ))}
      </div>
    </div>
  );
}

function TabBar<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: T; label: string }[];
  active: T;
  onChange: (k: T) => void;
}) {
  return (
    <div className={s.tabBar}>
      {tabs.map((t) => (
        <button
          key={t.key}
          className={active === t.key ? s.tabBtnActive : s.tabBtn}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Hero — editorial layout
// ─────────────────────────────────────────────────────────

function TrendingHero({ markets }: { markets: EntMarketRow[] }) {
  if (!markets || markets.length < 2) return null;
  const [lead, ...rest] = markets;

  return (
    <div className={s.heroGrid}>
      <div className={`${s.heroCardLead} ${s.heroLead}`}>
        <HeroCardContent market={lead} isLead />
      </div>
      {rest.slice(0, 4).map((m, i) => (
        <Link key={i} href={`/futures/${m.market_id}`}>
          <div className={s.heroCard} style={{ height: "100%" }}>
            <HeroCardContent market={m} />
          </div>
        </Link>
      ))}
    </div>
  );
}

function HeroCardContent({
  market,
  isLead = false,
}: {
  market: EntMarketRow;
  isLead?: boolean;
}) {
  const Wrap = isLead ? Link : "div";
  const inner = (
    <>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <CoverTile
          title={market.q}
          imageUrl={market.image_url}
          size={isLead ? 72 : 44}
          big={isLead}
          kind={market.kind}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              marginBottom: 4,
              flexWrap: "wrap",
            }}
          >
            <TagChip
              emoji={KIND_EMOJI[market.kind] || "✦"}
              label={KIND_LABEL[market.kind] || "Market"}
            />
          </div>
          <div
            style={{
              fontSize: isLead ? 18 : 14,
              fontWeight: 600,
              lineHeight: 1.25,
              letterSpacing: "-0.01em",
              color: "var(--text-primary)",
            }}
          >
            {market.q}
          </div>
          {market.hook && (
            <div
              style={{
                fontSize: isLead ? 13 : 12,
                color: "var(--text-secondary)",
                marginTop: 4,
                lineHeight: 1.4,
              }}
            >
              {market.hook}
            </div>
          )}
        </div>
      </div>

      <div style={{ flex: 1 }} />

      <CardBodyByKind market={market} isLead={isLead} />

      <MetaRow
        src={market.src}
        volume={market.volume_24h}
        resolves={market.resolution_date}
      />
    </>
  );

  if (isLead) {
    return <Link href={`/futures/${market.market_id}`}>{inner}</Link>;
  }
  return inner;
}

function CardBodyByKind({
  market,
  isLead = false,
}: {
  market: EntMarketRow;
  isLead?: boolean;
}) {
  const outcomes = market.top_outcomes;

  if (market.kind === "spotify" && outcomes.length >= 2) {
    return (
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 6,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600 }}>
            {outcomes[0].name}
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
            <ProbPct value={outcomes[0].prob} size={isLead ? 28 : 20} />
            <EntDelta value={outcomes[0].delta_24h} />
          </div>
        </div>
        <EntProbBar value={outcomes[0].prob} height={isLead ? 8 : 6} />
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginTop: 8,
          }}
        >
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
            {outcomes[1].name}
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
            <ProbPct value={outcomes[1].prob} size={13} />
            <EntDelta value={outcomes[1].delta_24h} />
          </div>
        </div>
      </div>
    );
  }

  if (
    market.kind === "reality" &&
    market.outcome_count <= 2 &&
    outcomes.length >= 2
  ) {
    const aLead = outcomes[0].prob >= outcomes[1].prob;
    return (
      <div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            marginBottom: 6,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 11,
                color: aLead ? "#111827" : "#9CA3AF",
                fontWeight: 600,
              }}
            >
              {outcomes[0].name}
            </div>
            <ProbPct value={outcomes[0].prob} size={isLead ? 24 : 18} />
          </div>
          <div style={{ textAlign: "right" }}>
            <div
              style={{
                fontSize: 11,
                color: !aLead ? "#111827" : "#9CA3AF",
                fontWeight: 600,
              }}
            >
              {outcomes[1].name}
            </div>
            <ProbPct value={outcomes[1].prob} size={isLead ? 24 : 18} />
          </div>
        </div>
        <div className={s.splitBar}>
          <span
            className={aLead ? s.splitBarLead : s.splitBarTrail}
            style={{ width: `${outcomes[0].prob}%` }}
          />
          <span
            className={!aLead ? s.splitBarLead : s.splitBarTrail}
            style={{ width: `${outcomes[1].prob}%` }}
          />
        </div>
      </div>
    );
  }

  if (
    (market.kind === "multi" ||
      market.kind === "eurovision" ||
      market.outcome_count > 2) &&
    outcomes.length >= 2
  ) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {outcomes.slice(0, isLead ? 4 : 3).map((o, i) => (
          <div
            key={i}
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr auto",
              gap: 8,
              alignItems: "center",
            }}
          >
            <span style={{ fontSize: 12, color: "var(--text-secondary)", minWidth: 0 }}>
              {o.name}
            </span>
            <EntProbBar value={o.prob} height={4} />
            <ProbPct value={o.prob} size={12} />
          </div>
        ))}
      </div>
    );
  }

  // Default: binary
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: 8,
      }}
    >
      <ProbPct value={market.prob} size={isLead ? 28 : 20} />
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
        {market.prob >= 50 ? "Yes" : "No"} likely
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Music section
// ─────────────────────────────────────────────────────────

type MusicTab = "spotify" | "billboard" | "albums" | "streaming";
const MUSIC_TABS: { key: MusicTab; label: string }[] = [
  { key: "spotify", label: "Spotify Race" },
  { key: "billboard", label: "Billboard" },
  { key: "albums", label: "Album Drops" },
  { key: "streaming", label: "Artist Streaming" },
];

function MusicSection({ data }: { data: EntThemeMusic }) {
  const [tab, setTab] = useState<MusicTab>("spotify");

  const hasSpotify = data.spotify_race.length > 0;
  const hasBillboard = data.billboard_watch.length > 0;
  const hasAlbums = data.album_drops.length > 0;
  const hasStreaming = data.artist_streaming.length > 0;
  const allMarkets = [
    ...data.spotify_race,
    ...data.billboard_watch,
    ...data.album_drops,
    ...data.artist_streaming,
    ...data.side_markets,
  ];

  if (allMarkets.length === 0) return null;

  return (
    <section id="sec-music" className={s.section}>
      <div className={s.sectionHead}>
        <div>
          <div className={s.eyebrow}>🎧 Music</div>
          <h2 className={s.sectionTitle}>Charts, drops, and streams</h2>
        </div>
        <div className={s.sectionMeta}>
          <TabBar tabs={MUSIC_TABS} active={tab} onChange={setTab} />
        </div>
      </div>

      {tab === "spotify" && (
        hasSpotify ? <SpotifyRace markets={data.spotify_race} /> : <MarketFallback markets={data.side_markets} />
      )}
      {tab === "billboard" && (
        data.billboard_groups && data.billboard_groups.length > 0
          ? <RTHeatmap groups={data.billboard_groups} />
          : hasBillboard
            ? <BillboardHeatmap markets={data.billboard_watch} />
            : <MarketFallback markets={data.side_markets} />
      )}
      {tab === "albums" && (
        hasAlbums ? <AlbumGrid markets={data.album_drops} /> : <MarketFallback markets={data.side_markets} />
      )}
      {tab === "streaming" && (
        hasStreaming ? <StreamingGrid markets={data.artist_streaming} /> : <MarketFallback markets={data.side_markets} />
      )}
    </section>
  );
}

function SpotifyRace({ markets }: { markets: EntMarketRow[] }) {
  const best = markets.reduce(
    (a, b) => (b.top_outcomes.length > a.top_outcomes.length ? b : a),
    markets[0]
  );
  if (!best) return <MarketFallback markets={markets} />;

  const contenders = best.top_outcomes;
  if (contenders.length < 2) return <MarketFallback markets={markets} />;

  return (
    <Link href={`/futures/${best.market_id}`}>
      <div className={s.card} style={{ padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
          <div>
            <div className={s.eyebrow}>🎧 Spotify Chart Race</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>{best.q}</div>
          </div>
          <EntSourceChip source={best.src} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {contenders.map((c, i) => {
            const isLeader = i === 0;
            return (
              <div key={i} className={s.raceRow}>
                <span className={isLeader ? s.raceRankLead : s.raceRank}>{i + 1}</span>
                <CoverTile title={c.name} size={36} />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {c.name}
                  </div>
                  <div style={{ marginTop: 5 }}>
                    <EntProbBar value={c.prob} height={6} color={isLeader ? "#10B981" : "rgba(16, 185, 129, 0.3)"} />
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                  <ProbPct value={c.prob} size={16} />
                  <EntDelta value={c.delta_24h} />
                </div>
                <span />
              </div>
            );
          })}
        </div>
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid #E5E7EB" }}>
          <MetaRow src={best.src} volume={best.volume_24h} resolves={best.resolution_date} />
        </div>
      </div>
    </Link>
  );
}

function AlbumGrid({ markets }: { markets: EntMarketRow[] }) {
  return (
    <div className={s.grid3}>
      {markets.map((m, i) => (
        <Link key={i} href={`/futures/${m.market_id}`}>
          <div className={s.card} style={{ padding: 16, height: "100%" }}>
            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <CoverTile title={m.q} imageUrl={m.image_url} size={56} big kind={m.kind} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 700 }}>{m.q}</div>
                {m.hook && (
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
                    {m.hook}
                  </div>
                )}
              </div>
            </div>
            {m.top_outcomes.length > 2 ? (
              <EntHistogram
                data={m.top_outcomes.map((o) => ({
                  range: o.name,
                  prob: o.prob / 100,
                }))}
              />
            ) : (
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{m.top_outcomes[0]?.name || "Yes"}</span>
                <ProbPct value={m.prob} size={20} />
              </div>
            )}
            <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid #E5E7EB" }}>
              <MetaRow src={m.src} volume={m.volume_24h} />
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}

function StreamingGrid({ markets }: { markets: EntMarketRow[] }) {
  return (
    <div className={s.card} style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid #E5E7EB", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Streaming & chart markets</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Weekly stream predictions</div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {markets.map((m, i) => {
          const qLower = m.q.toLowerCase();
          const isUp = qLower.includes("increase") || qLower.includes("above") || qLower.includes("over") || qLower.includes("up");
          const isDown = qLower.includes("decrease") || qLower.includes("below") || qLower.includes("under") || qLower.includes("down");
          const direction = isUp ? "up" : isDown ? "down" : null;
          const dirColor = direction === "up" ? "#22C55E" : direction === "down" ? "#EF4444" : "#111827";

          return (
            <Link key={i} href={`/futures/${m.market_id}`}>
              <div style={{ display: "grid", gridTemplateColumns: "32px 1fr auto", gap: 10, padding: "12px 16px", alignItems: "center", borderRight: "1px solid #E5E7EB", borderBottom: "1px solid #E5E7EB" }}>
                <CoverTile title={m.q} imageUrl={m.image_url} size={32} />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {m.top_outcomes[0]?.name || m.q}
                  </div>
                  {m.hook && <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.hook}</div>}
                </div>
                <span className={s.probNum} style={{ fontSize: 13, color: dirColor }}>
                  {direction === "up" ? "↑" : direction === "down" ? "↓" : ""} {Math.round(m.prob)}%
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Movies & TV section
// ─────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────
// Heatmap grids — RT and Billboard
// ─────────────────────────────────────────────────────────

function cellColor(p: number): string {
  const intensity = Math.min(1, p / 100);
  return `rgba(16, 185, 129, ${(intensity * 0.7 + 0.05).toFixed(2)})`;
}

function RTHeatmap({ groups }: { groups: EntThresholdGroup[] }) {
  if (groups.length === 0) return null;

  const maxThresholds = Math.max(...groups.map((g) => g.thresholds.length));
  const thresholdLabels = groups[0]?.thresholds.map((t) => t.label) || [];

  return (
    <div className={s.heatmapWrap}>
      <div style={{ display: "grid", gridTemplateColumns: `minmax(180px, 1.3fr) repeat(${maxThresholds}, minmax(48px, 1fr))`, borderBottom: "1px solid #E5E7EB" }}>
        <div className={s.heatmapHeader} style={{ justifyContent: "flex-start", borderRight: "1px solid #E5E7EB" }}>
          Movie
        </div>
        {thresholdLabels.map((label, i) => (
          <div key={i} className={s.heatmapHeader} style={{ textAlign: "center", display: "flex", alignItems: "center", justifyContent: "center", borderRight: i === maxThresholds - 1 ? "none" : "1px solid #E5E7EB", fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>
            {label.replace(/^.*?(\d+).*$/, "≥$1").slice(0, 6)}
          </div>
        ))}
      </div>
      {groups.map((group, gi) => (
        <div key={gi} style={{ display: "grid", gridTemplateColumns: `minmax(180px, 1.3fr) repeat(${maxThresholds}, minmax(48px, 1fr))` }}>
          <div style={{ padding: "10px 12px", display: "flex", alignItems: "center", gap: 10, borderRight: "1px solid #E5E7EB", borderBottom: gi === groups.length - 1 ? "none" : "1px solid #E5E7EB", cursor: "pointer" }}>
            <CoverTile title={group.title} imageUrl={group.image_url} size={32} kind="rt" />
            <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{group.title}</span>
          </div>
          {group.thresholds.map((t, ti) => (
            <Link key={ti} href={`/futures/${t.market_id}`}>
              <div className={s.heatmapCell} style={{ background: cellColor(t.prob), color: t.prob > 50 ? "#111827" : "#6B7280", borderRight: ti === maxThresholds - 1 ? "none" : undefined, borderBottom: gi === groups.length - 1 ? "none" : undefined }} title={`${group.title} ${t.label}: ${Math.round(t.prob)}%`}>
                {Math.round(t.prob)}
              </div>
            </Link>
          ))}
        </div>
      ))}
    </div>
  );
}

function BillboardHeatmap({ markets }: { markets: EntMarketRow[] }) {
  const best = markets.reduce(
    (a, b) => (b.top_outcomes.length > a.top_outcomes.length ? b : a),
    markets[0]
  );
  if (!best || best.top_outcomes.length < 2) return <MarketList markets={markets} />;

  return (
    <Link href={`/futures/${best.market_id}`}>
      <div className={s.card} style={{ padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
          <div>
            <div className={s.eyebrow}>📊 Billboard Hot 100</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>{best.q}</div>
          </div>
          <EntSourceChip source={best.src} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {best.top_outcomes.map((o, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)", minWidth: 0 }}>{o.name}</span>
              <EntProbBar value={o.prob} height={4} />
              <ProbPct value={o.prob} size={12} />
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid #E5E7EB" }}>
          <MetaRow src={best.src} volume={best.volume_24h} resolves={best.resolution_date} />
        </div>
      </div>
    </Link>
  );
}

// ─────────────────────────────────────────────────────────
// Movies & TV section
// ─────────────────────────────────────────────────────────

type MovieTab = "rt" | "boxoffice" | "reality";
const MOVIE_TABS: { key: MovieTab; label: string }[] = [
  { key: "rt", label: "Rotten Tomatoes" },
  { key: "boxoffice", label: "Box Office" },
  { key: "reality", label: "Reality TV" },
];

function MoviesTVSection({ data }: { data: EntThemeMoviesTV }) {
  const [tab, setTab] = useState<MovieTab>("rt");

  const allMarkets = [
    ...data.rt_markets,
    ...data.box_office,
    ...data.reality_tv,
    ...data.side_markets,
  ];

  if (allMarkets.length === 0) return null;

  return (
    <section id="sec-movies" className={s.section}>
      <div className={s.sectionHead}>
        <div>
          <div className={s.eyebrow}>🎬 Movies & TV</div>
          <h2 className={s.sectionTitle}>
            Critic scores, box office, and reality outcomes
          </h2>
        </div>
        <div className={s.sectionMeta}>
          {/* L2-88: entry point into the awards event-concept pages (Oscars ceremony
              — categories, marquee hero, nominations) — the awards adapter's surface. */}
          <Link
            href={eventPath("event:awards:oscars")}
            className="text-sm font-medium text-accent-brand hover:underline whitespace-nowrap"
          >
            Awards markets →
          </Link>
          <TabBar tabs={MOVIE_TABS} active={tab} onChange={setTab} />
        </div>
      </div>

      {tab === "rt" && (
        data.rt_groups && data.rt_groups.length > 0
          ? <RTHeatmap groups={data.rt_groups} />
          : data.rt_markets.length > 0
            ? <MarketList markets={data.rt_markets} />
            : <MarketFallback markets={data.side_markets} />
      )}
      {tab === "boxoffice" && (
        data.box_office.length > 0 ? <BoxOfficeCards markets={data.box_office} /> : <MarketFallback markets={data.side_markets} />
      )}
      {tab === "reality" && (
        data.reality_tv.length > 0 ? <RealityCards markets={data.reality_tv} /> : <MarketFallback markets={data.side_markets} />
      )}
    </section>
  );
}

function BoxOfficeCards({ markets }: { markets: EntMarketRow[] }) {
  return (
    <div className={s.card} style={{ padding: 18 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 14,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Box office markets</div>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {markets.map((m, i) => (
          <Link key={i} href={`/futures/${m.market_id}`}>
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                <CoverTile title={m.q} imageUrl={m.image_url} size={40} kind={m.kind} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{m.q}</div>
                  {m.hook && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {m.hook}
                    </div>
                  )}
                </div>
                <EntSourceChip source={m.src} />
              </div>
              {m.top_outcomes.length > 2 && (
                <EntHistogram
                  data={m.top_outcomes.map((o) => ({
                    range: o.name,
                    prob: o.prob / 100,
                  }))}
                  height={56}
                />
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function RealityCards({ markets }: { markets: EntMarketRow[] }) {
  return (
    <div className={s.grid3}>
      {markets.map((m, i) => {
        const isBinary = m.outcome_count <= 2;
        return (
          <Link key={i} href={`/futures/${m.market_id}`}>
            <div className={s.card} style={{ padding: 16, height: "100%" }}>
              <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
                <CoverTile title={m.q} imageUrl={m.image_url} size={44} big kind={m.kind} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{m.q}</div>
                </div>
              </div>
              {isBinary && m.top_outcomes.length >= 2 ? (
                <>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 8,
                      marginBottom: 6,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600 }}>
                        {m.top_outcomes[0].name}
                      </div>
                      <ProbPct value={m.top_outcomes[0].prob} size={20} />
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 11, fontWeight: 600 }}>
                        {m.top_outcomes[1].name}
                      </div>
                      <ProbPct value={m.top_outcomes[1].prob} size={20} />
                    </div>
                  </div>
                  <div className={s.splitBar}>
                    <span
                      className={
                        m.top_outcomes[0].prob >= m.top_outcomes[1].prob
                          ? s.splitBarLead
                          : s.splitBarTrail
                      }
                      style={{ width: `${m.top_outcomes[0].prob}%` }}
                    />
                    <span
                      className={
                        m.top_outcomes[1].prob >= m.top_outcomes[0].prob
                          ? s.splitBarLead
                          : s.splitBarTrail
                      }
                      style={{ width: `${m.top_outcomes[1].prob}%` }}
                    />
                  </div>
                </>
              ) : (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  {m.top_outcomes.map((o, j) => (
                    <div
                      key={j}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr auto",
                        gap: 8,
                        alignItems: "center",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 12, color: "var(--text-primary)" }}>
                          {o.name}
                        </div>
                        <EntProbBar value={o.prob} height={4} />
                      </div>
                      <ProbPct value={o.prob} size={13} />
                    </div>
                  ))}
                </div>
              )}
              <div
                style={{
                  marginTop: 12,
                  paddingTop: 10,
                  borderTop: "1px solid #E5E7EB",
                }}
              >
                <MetaRow src={m.src} volume={m.volume_24h} />
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Cultural moments — masonry feed
// ─────────────────────────────────────────────────────────

function CulturalMoments({ markets }: { markets: EntMarketRow[] }) {
  if (!markets || markets.length === 0) return null;

  return (
    <section className={s.section}>
      <div className={s.sectionHead}>
        <div>
          <div className={s.eyebrow}>🎭 Cultural moments</div>
          <h2 className={s.sectionTitle}>Pop culture prediction feed</h2>
          <p className={s.sectionSub}>
            One-off markets around live events, celebrity drama, and
            headline-watching
          </p>
        </div>
      </div>
      <div className={s.masonryFeed}>
        {markets.map((m, i) => (
          <MomentCard key={i} market={m} />
        ))}
      </div>
    </section>
  );
}

function MomentCard({ market }: { market: EntMarketRow }) {
  const isBinary = market.outcome_count <= 2;
  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={`${s.card} ${s.masonryCard}`} style={{ padding: 16 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
          }}
        >
          <TagChip
            emoji={KIND_EMOJI[market.kind] || "✦"}
            label={KIND_LABEL[market.kind] || "Market"}
          />
          {market.resolution_date && (
            <div
              style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-muted)" }}
            >
              Resolves {formatDate(market.resolution_date)}
            </div>
          )}
        </div>
        <div
          style={{
            fontSize: 14,
            fontWeight: 700,
            lineHeight: 1.3,
            letterSpacing: "-0.01em",
            marginBottom: 4,
            color: "var(--text-primary)",
          }}
        >
          {market.q}
        </div>
        {market.hook && (
          <div
            style={{
              fontSize: 12,
              color: "var(--text-secondary)",
              marginBottom: 12,
              lineHeight: 1.45,
            }}
          >
            {market.hook}
          </div>
        )}
        {isBinary ? (
          <YesNoBar yes={market.prob} no={100 - market.prob} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {market.top_outcomes.map((o, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  {o.name}
                </span>
                <EntProbBar value={o.prob} height={4} />
                <ProbPct value={o.prob} size={12} />
              </div>
            ))}
          </div>
        )}
        <div
          style={{
            marginTop: 12,
            paddingTop: 10,
            borderTop: "1px solid #E5E7EB",
          }}
        >
          <MetaRow src={market.src} volume={market.volume_24h} />
        </div>
      </div>
    </Link>
  );
}

// ─────────────────────────────────────────────────────────
// Tech & Culture sidebar
// ─────────────────────────────────────────────────────────

function TechCultureSidebar({ data }: { data: EntThemeTechCulture }) {
  if (!data.markets || data.markets.length === 0) return null;

  return (
    <aside className={s.sidebar}>
      <div className={s.sidebarCard}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 8,
          }}
        >
          <h3 className={s.sidebarTitle}>Tech & Culture</h3>
          <span
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
              fontWeight: 600,
            }}
          >
            {data.count} markets
          </span>
        </div>
        <p className={s.sidebarSub}>
          Net worth, social media, and platform bets
        </p>
      </div>

      {data.markets.map((m, i) => (
        <Link key={i} href={`/futures/${m.market_id}`}>
          <div className={s.sidebarCard}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
              {m.q}
            </div>
            {m.hook && (
              <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 8 }}>
                {m.hook}
              </div>
            )}
            {m.outcome_count <= 2 ? (
              <YesNoBar yes={m.prob} no={100 - m.prob} />
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                {m.top_outcomes.map((o, j) => (
                  <div
                    key={j}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr auto",
                      gap: 8,
                      alignItems: "center",
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--text-primary)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {o.name}
                      </div>
                      <EntProbBar value={o.prob} height={3} />
                    </div>
                    <ProbPct value={o.prob} size={11} />
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 8 }}>
              <EntSourceChip source={m.src} />
            </div>
          </div>
        </Link>
      ))}
    </aside>
  );
}

// ─────────────────────────────────────────────────────────
// Fallback components
// ─────────────────────────────────────────────────────────

function MarketList({ markets }: { markets: EntMarketRow[] }) {
  if (!markets || markets.length === 0)
    return (
      <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
        No markets in this category yet
      </div>
    );
  return (
    <div className={s.gridAuto}>
      {markets.map((m, i) => (
        <GenericMarketCard key={i} market={m} />
      ))}
    </div>
  );
}

function MarketFallback({ markets }: { markets: EntMarketRow[] }) {
  if (!markets || markets.length === 0)
    return (
      <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
        No markets in this category yet
      </div>
    );
  return <MarketList markets={markets} />;
}

function GenericMarketCard({ market }: { market: EntMarketRow }) {
  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.card} style={{ padding: 14, height: "100%", display: "flex", flexDirection: "column", gap: 10 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: 11,
            color: "var(--text-muted)",
          }}
        >
          <EntSourceChip source={market.src} />
          {market.outcome_count > 3 && (
            <span
              style={{
                marginLeft: "auto",
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 10,
              }}
            >
              +{market.outcome_count - 3} more
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
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginTop: "auto",
          }}
        >
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {market.top_outcomes[0]?.name || "Yes"}
          </span>
          <ProbPct value={market.prob} size={20} />
        </div>
        <EntProbBar value={market.prob} height={4} />
      </div>
    </Link>
  );
}

// ─────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────

type FilterKey = "all" | "music" | "movies" | "tv" | "internet" | "live";
const FILTERS: { key: FilterKey; label: string; emoji: string }[] = [
  { key: "all", label: "All", emoji: "✦" },
  { key: "music", label: "Music", emoji: "🎧" },
  { key: "movies", label: "Movies", emoji: "🎬" },
  { key: "tv", label: "TV", emoji: "📺" },
  { key: "internet", label: "Internet", emoji: "🌐" },
  { key: "live", label: "Live Events", emoji: "🎤" },
];

export default function EntertainmentPage() {
  usePageTracking({ pageType: "entertainment", pageTitle: "Entertainment & Culture" });
  useScrollDepth({ pageType: "entertainment" });
  useEngagementTime({ pageType: "entertainment" });

  const [filter, setFilter] = useState<FilterKey>("all");
  const { data, error } = useSWR("entertainment-data-v2", fetchEntertainment, {
    refreshInterval: 60000,
  });

  if (error) {
    return (
      <div className={s.page}>
        <ErrorState message="Failed to load entertainment data" onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={s.page}>
        <EntertainmentSkeleton />
      </div>
    );
  }

  const show = (key: FilterKey) => filter === "all" || filter === key;

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className={`${s.page} -mx-3 md:-mx-6 -mt-4`}>
      {/* Page header */}
      <div className={s.pageHead}>
        <div className={s.eyebrow}>🎤 Entertainment & Culture</div>
        <h1 className={s.pageTitle}>
          What the markets are betting on in pop culture
        </h1>
        <p className={s.pageSub}>
          Live probabilities on charts, box office, reality TV, and the
          moments breaking the internet.
        </p>
        <div className={s.pageMeta}>
          <span>
            <b className={s.metaNum}>
              {data.total_markets.toLocaleString()}
            </b>{" "}
            active markets
          </span>
          <span>·</span>
          <span>
            Updated{" "}
            <b className={s.metaNum}>{formatTimeAgo(data.updated_at)}</b>
          </span>
        </div>
      </div>

      {/* Filter chips */}
      <div className={s.filterRow}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={
              filter === f.key ? s.filterChipActive : s.filterChip
            }
            onClick={() => setFilter(f.key)}
          >
            <span style={{ fontSize: 14 }}>{f.emoji}</span>
            {f.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className={s.pageContent}>
        {/* Trending hero */}
        {data.trending && data.trending.length > 0 && (
          <TrendingHero markets={data.trending} />
        )}

        {/* Main + sidebar grid */}
        <div className={s.mainSidebar}>
          <div className={s.main}>
            {show("music") && data.themes.music && (
              <MusicSection data={data.themes.music} />
            )}
            {(show("movies") || show("tv")) && data.themes.movies_tv && (
              <MoviesTVSection data={data.themes.movies_tv} />
            )}
            {data.cultural_moments && data.cultural_moments.length > 0 && (
              <CulturalMoments markets={data.cultural_moments} />
            )}
          </div>
          {show("internet") && data.themes.tech_culture && (
            <TechCultureSidebar data={data.themes.tech_culture} />
          )}
        </div>

        {/* Footer */}
        <div className={s.footer}>
          <span>
            Probabilities update on a 30-second cadence. Bain Luck is a
            discovery platform — we never accept bets.
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)" }}>
            {data.total_markets.toLocaleString()} entertainment ·{" "}
            {new Date().toLocaleDateString()}
          </span>
        </div>
      </div>
    </div>
    </ErrorBoundary>
  );
}

// ─────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}
