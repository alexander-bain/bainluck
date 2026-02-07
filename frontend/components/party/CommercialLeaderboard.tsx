"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import useSWR from "swr";
import { fetchSuperBowlCommercials } from "@/lib/api";
import type { Commercial } from "@/lib/types";

// ─── Individual commercial row ─────────────────────────────────────────

function CommercialRow({
  commercial,
  isTop3,
}: {
  commercial: Commercial;
  isTop3: boolean;
}) {
  const rankColors = ["#FFD700", "#C0C0C0", "#CD7F32"]; // gold, silver, bronze

  return (
    <div className="flex items-center gap-[0.6vw] py-[0.4vh] px-[0.4vw] rounded bg-white/5">
      {/* Rank */}
      <span
        className="font-bold font-mono text-[1.8vh] tabular-nums shrink-0 w-[2vw] text-center"
        style={isTop3 ? { color: rankColors[commercial.rank - 1] } : undefined}
      >
        {commercial.rank}
      </span>

      {/* Thumbnail */}
      <img
        src={commercial.thumbnail}
        alt=""
        className="rounded shrink-0 object-cover"
        style={{ width: "5vw", height: "3vh", minWidth: "60px", minHeight: "34px" }}
      />

      {/* Title + Brand */}
      <div className="flex-1 min-w-0">
        <span className="text-white font-medium text-[1.3vh] truncate block leading-tight">
          {commercial.title}
        </span>
        <span className="text-white/40 text-[1vh] truncate block">
          {commercial.brand}
        </span>
      </div>

      {/* View count */}
      <div className="shrink-0 text-right">
        <span className="text-emerald-400 font-bold font-mono text-[1.5vh] tabular-nums">
          {commercial.view_count_display}
        </span>
        <span className="text-white/30 text-[0.9vh] block">views</span>
      </div>
    </div>
  );
}

// ─── Auto-scrolling leaderboard ────────────────────────────────────────

function ScrollingLeaderboard({
  commercials,
  pixelsPerSecond = 18,
}: {
  commercials: Commercial[];
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
      scrollerRef.current.style.transform = "translateY(0)";
      offsetRef.current = 0;
      setNeedsScroll(false);
      return;
    }

    setNeedsScroll(true);

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
  }, [commercials, pixelsPerSecond]);

  const handleMouseEnter = useCallback(() => {
    pausedRef.current = true;
  }, []);

  const handleMouseLeave = useCallback(() => {
    pausedRef.current = false;
    lastTimeRef.current = 0;
  }, []);

  const renderItems = (prefix: string) => (
    <div className="space-y-[0.3vh]">
      {commercials.map((c) => (
        <CommercialRow
          key={`${prefix}-${c.video_id}`}
          commercial={c}
          isTop3={c.rank <= 3}
        />
      ))}
    </div>
  );

  return (
    <div
      className="flex-1 overflow-hidden relative"
      ref={viewportRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
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
      <div ref={scrollerRef} className="px-[0.3vw]">
        <div ref={singleCopyRef} className="py-[0.4vh]">
          {renderItems("a")}
        </div>
        <div className="py-[0.4vh]">{renderItems("b")}</div>
      </div>
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────

export default function CommercialLeaderboard() {
  const { data, error, isLoading } = useSWR(
    "superbowl-commercials",
    () => fetchSuperBowlCommercials(),
    { refreshInterval: 300000 } // Refresh every 5 minutes
  );

  return (
    <div className="bg-[#111118] rounded-2xl border border-white/5 overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div className="px-[0.8vw] pt-[0.6vh] pb-[0.4vh] border-b border-white/5 flex items-center justify-between shrink-0">
        <h3 className="text-white font-semibold text-[1.5vh] uppercase tracking-wider flex items-center gap-[0.4vw]">
          <span style={{ fontSize: "2vh" }}>{"\uD83C\uDFC6"}</span>
          Ad Leaderboard
        </h3>
        <span className="text-white/30 text-[1.1vh]">
          {data ? `${data.total} ads` : "YouTube views"}
        </span>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center text-white/40 text-[1.3vh]">
          Loading commercials...
        </div>
      ) : error || !data || data.commercials.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-white/30 text-[1.3vh] text-center px-[1vw]">
          {error
            ? "Could not load commercials"
            : "No Super Bowl ads found yet — check back on game day!"}
        </div>
      ) : (
        <ScrollingLeaderboard commercials={data.commercials} />
      )}
    </div>
  );
}
