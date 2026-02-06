"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import useSWR from "swr";
import { fetchEventProps } from "@/lib/api";
import type { PropBet, PropCategory } from "@/lib/types";

interface PropBetsProps {
  eventId: number;
}

// Categories that go in the "Stats" panel; everything else goes to "Scoring"
const STAT_CATEGORIES = new Set(["Passing", "Rushing", "Receiving", "Kicking"]);

const CATEGORY_ICONS: Record<string, string> = {
  Passing: "\uD83C\uDFC8",
  Rushing: "\uD83C\uDFC3",
  Receiving: "\uD83D\uDC50",
  Scoring: "\uD83C\uDFAF",
  Kicking: "\uD83E\uDDB6",
};

// ─── Individual prop row ───────────────────────────────────────────────

function PropRow({ prop }: { prop: PropBet }) {
  // Over/Under props (passing yards, rushing yards, etc.)
  if (prop.over_probability != null) {
    const overPct = Math.round(prop.over_probability * 100);
    const isOverFavored = overPct >= 50;

    return (
      <div className="flex items-center justify-between py-[0.5vh] px-[0.6vw] rounded-lg bg-white/5">
        <div className="flex-1 min-w-0">
          <span className="text-white font-medium text-[1.5vh] truncate block">
            {prop.player}
          </span>
          <span className="text-white/50 text-[1.2vh]">
            {prop.type} {prop.line != null ? `O/U ${prop.line}` : ""}
          </span>
        </div>
        <div className="flex items-center gap-[0.8vw] ml-[0.6vw]">
          <div
            className={`text-right ${
              isOverFavored ? "text-emerald-400" : "text-white/60"
            }`}
          >
            <div className="font-bold font-mono" style={{ fontSize: "2vh" }}>{overPct}%</div>
            <div className="text-[1vh] uppercase tracking-wide opacity-60">
              Over
            </div>
          </div>
          <div className="w-px bg-white/20" style={{ height: "3vh" }} />
          <div
            className={`text-right ${
              !isOverFavored ? "text-emerald-400" : "text-white/60"
            }`}
          >
            <div className="font-bold font-mono" style={{ fontSize: "2vh" }}>
              {100 - overPct}%
            </div>
            <div className="text-[1vh] uppercase tracking-wide opacity-60">
              Under
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Yes/No props (anytime TD, first TD)
  if (prop.probability != null) {
    const pct = Math.round(prop.probability * 100);
    return (
      <div className="flex items-center justify-between py-[0.5vh] px-[0.6vw] rounded-lg bg-white/5">
        <div className="flex-1 min-w-0">
          <span className="text-white font-medium text-[1.5vh] truncate block">
            {prop.player}
          </span>
          <span className="text-white/50 text-[1.2vh]">{prop.type}</span>
        </div>
        <div className="text-emerald-400 font-bold font-mono ml-[0.6vw]" style={{ fontSize: "2vh" }}>
          {pct}%
        </div>
      </div>
    );
  }

  return null;
}

// ─── Renders a flat list of category headers + prop rows ───────────────

function PropList({
  categories,
  keyPrefix,
}: {
  categories: PropCategory[];
  keyPrefix: string;
}) {
  return (
    <>
      {categories.map((cat) => (
        <div key={`${keyPrefix}-${cat.category}`}>
          <div className="text-white/70 text-[1.3vh] font-semibold uppercase tracking-widest py-[0.5vh] flex items-center gap-[0.4vw]">
            <span>{CATEGORY_ICONS[cat.category] || "\u26BD"}</span>
            {cat.category}
            <span className="text-white/30">({cat.props.length})</span>
          </div>
          <div className="space-y-[0.3vh]">
            {cat.props.map((prop, i) => (
              <PropRow
                key={`${keyPrefix}-${prop.player}-${prop.type}-${prop.line}-${i}`}
                prop={prop}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

// ─── Auto-scrolling panel ──────────────────────────────────────────────

function ScrollingPanel({
  title,
  icon,
  categories,
  pixelsPerSecond = 22,
}: {
  title: string;
  icon: string;
  categories: PropCategory[];
  pixelsPerSecond?: number;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const singleCopyRef = useRef<HTMLDivElement>(null);
  const offsetRef = useRef(0);
  const animRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const pausedRef = useRef(false);
  const [needsScroll, setNeedsScroll] = useState(false);

  const totalProps = categories.reduce(
    (sum, c) => sum + c.props.length,
    0
  );

  // Measure content & start/stop animation
  useEffect(() => {
    if (
      !singleCopyRef.current ||
      !viewportRef.current ||
      !scrollerRef.current
    )
      return;

    const contentH = singleCopyRef.current.offsetHeight;
    const viewportH = viewportRef.current.clientHeight;

    if (contentH <= viewportH || contentH <= 0) {
      // Content fits — no scrolling needed
      scrollerRef.current.style.transform = "translateY(0)";
      offsetRef.current = 0;
      setNeedsScroll(false);
      return;
    }

    setNeedsScroll(true);

    // Keep current offset if it's valid for the new content height
    if (offsetRef.current >= contentH) {
      offsetRef.current = offsetRef.current % contentH;
    }
    lastTimeRef.current = 0;

    const animate = (time: number) => {
      if (lastTimeRef.current && !pausedRef.current) {
        const dt = (time - lastTimeRef.current) / 1000;
        offsetRef.current += pixelsPerSecond * dt;
        if (offsetRef.current >= contentH) {
          offsetRef.current -= contentH;
        }
        if (scrollerRef.current) {
          scrollerRef.current.style.transform = `translateY(-${offsetRef.current}px)`;
        }
      }
      lastTimeRef.current = time;
      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animRef.current);
      lastTimeRef.current = 0;
    };
  }, [categories, pixelsPerSecond]);

  const handleMouseEnter = useCallback(() => {
    pausedRef.current = true;
  }, []);

  const handleMouseLeave = useCallback(() => {
    pausedRef.current = false;
    lastTimeRef.current = 0; // avoid jump after pause
  }, []);

  if (totalProps === 0) {
    return (
      <div className="flex-1 bg-[#111118] rounded-2xl border border-white/5 flex items-center justify-center">
        <span className="text-white/20 text-[1.4vh]">
          No {title.toLowerCase()} available
        </span>
      </div>
    );
  }

  return (
    <div
      className="flex-1 bg-[#111118] rounded-2xl border border-white/5 overflow-hidden flex flex-col"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Panel header */}
      <div className="px-[0.8vw] pt-[0.6vh] pb-[0.4vh] border-b border-white/5 flex items-center justify-between shrink-0">
        <h3 className="text-white font-semibold text-[1.5vh] uppercase tracking-wider flex items-center gap-[0.4vw]">
          <span style={{ fontSize: "2vh" }}>{icon}</span>
          {title}
        </h3>
        <span className="text-white/30 text-[1.2vh]">{totalProps} props</span>
      </div>

      {/* Scrolling viewport */}
      <div
        ref={viewportRef}
        className="flex-1 overflow-hidden relative"
        style={
          needsScroll
            ? {
                maskImage:
                  "linear-gradient(to bottom, transparent 0%, black 4%, black 96%, transparent 100%)",
                WebkitMaskImage:
                  "linear-gradient(to bottom, transparent 0%, black 4%, black 96%, transparent 100%)",
              }
            : undefined
        }
      >
        <div ref={scrollerRef} className="px-[0.5vw]">
          {/* First copy (measured for scroll distance) */}
          <div ref={singleCopyRef} className="space-y-[0.4vh] py-[0.6vh]">
            <PropList categories={categories} keyPrefix="a" />
          </div>
          {/* Duplicate for seamless infinite scroll */}
          <div className="space-y-[0.4vh] py-[0.6vh]">
            <PropList categories={categories} keyPrefix="b" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────

export default function PropBets({ eventId }: PropBetsProps) {
  const { data, error, isLoading } = useSWR(
    ["props", eventId],
    () => fetchEventProps(eventId),
    { refreshInterval: 120000 } // Refresh every 2 minutes
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-white/40 text-[1.4vh]">
        Loading props...
      </div>
    );
  }

  if (error || !data || data.total_props === 0) {
    return (
      <div className="flex items-center justify-center h-full text-white/30 text-[1.4vh]">
        {error ? "Props unavailable" : "No props available for this event"}
      </div>
    );
  }

  // Split categories: stat-based (O/U) vs scoring (TD probabilities)
  const statCategories = data.categories.filter((c) =>
    STAT_CATEGORIES.has(c.category)
  );
  const scoringCategories = data.categories.filter(
    (c) => !STAT_CATEGORIES.has(c.category)
  );

  return (
    <div className="flex gap-4 h-full">
      <ScrollingPanel
        title="Player Stats"
        icon="\uD83D\uDCCA"
        categories={statCategories}
        pixelsPerSecond={20}
      />
      <ScrollingPanel
        title="Touchdown & Scoring"
        icon="\uD83C\uDFAF"
        categories={scoringCategories}
        pixelsPerSecond={20}
      />
    </div>
  );
}
