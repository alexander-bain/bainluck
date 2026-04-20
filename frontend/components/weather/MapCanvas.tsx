"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { SOURCES, tempColorC, toC } from "./data";
import type { CityData } from "./data";

interface MapCanvasProps {
  cities: CityData[];
  selected: string;
  hover: string | null;
  onHover: (id: string | null) => void;
  onSelect: (id: string) => void;
}

type ResolvedCity = CityData & { rx: number; ry: number };

function resolveCollisions(cities: CityData[], minDist: number): ResolvedCity[] {
  const pins = cities.map(c => ({ ...c, rx: c.preferredX, ry: c.preferredY }));
  const ITERATIONS = 40;
  for (let it = 0; it < ITERATIONS; it++) {
    let moved = false;
    for (let i = 0; i < pins.length; i++) {
      for (let j = i + 1; j < pins.length; j++) {
        const a = pins[i], b = pins[j];
        const dx = b.rx - a.rx, dy = b.ry - a.ry;
        const d = Math.hypot(dx, dy);
        if (d < minDist && d > 0.01) {
          const push = (minDist - d) / 2;
          const ux = dx / d, uy = dy / d;
          a.rx -= ux * push; a.ry -= uy * push;
          b.rx += ux * push; b.ry += uy * push;
          moved = true;
        } else if (d <= 0.01) {
          b.rx += 0.5; b.ry += 0.5;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  pins.forEach(p => {
    p.rx = Math.max(2, Math.min(98, p.rx));
    p.ry = Math.max(4, Math.min(94, p.ry));
  });
  return pins;
}

export default function MapCanvas({ cities, selected, hover, onHover, onSelect }: MapCanvasProps) {
  const crossSourceCount = useMemo(() => cities.filter(c => c.srcs.length > 1).length, [cities]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isNarrow, setIsNarrow] = useState(false);

  useEffect(() => {
    const check = () => {
      if (containerRef.current) {
        setIsNarrow(containerRef.current.offsetWidth < 700);
      }
    };
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const minDist = isNarrow ? 3.2 : 2.4;
  const resolvedCities = useMemo(() => resolveCollisions(cities, minDist), [cities, minDist]);

  return (
    <div
      ref={containerRef}
      className="bg-white border border-surface-border overflow-hidden"
      style={{ borderRadius: 16 }}
    >
      {/* Toolbar */}
      <div
        className="flex items-center justify-between flex-wrap gap-3"
        style={{ padding: "14px 18px", borderBottom: "1px solid var(--surface-border)" }}
      >
        <TempLegend />
        <span className="font-mono" style={{ fontSize: 11, color: "#9CA3AF" }}>
          HIGH &middot; APR 20, 2026
        </span>
      </div>

      {/* Map plane — 1.55:1 aspect, min 560px tall */}
      <div
        className="relative"
        style={{
          aspectRatio: "1.8 / 1",
          minHeight: 420,
          background: "linear-gradient(180deg, #FAFAFB 0%, #F5F5F7 100%)",
        }}
      >
        {/* Grid pattern */}
        <svg
          viewBox="0 0 2000 1000"
          preserveAspectRatio="none"
          className="absolute inset-0 w-full h-full"
        >
          <defs>
            <pattern id="worldDots" x="0" y="0" width="24" height="24" patternUnits="userSpaceOnUse">
              <circle cx="1.8" cy="1.8" r="1.8" fill="#E5E7EB" />
            </pattern>
          </defs>
          <rect width="2000" height="1000" fill="url(#worldDots)" opacity="0.7" />

          {/* Continent outlines */}
          {/* North America */}
          <path
            className="continent-outline"
            d="M280,120 L350,100 L480,110 L580,130 L640,160 L680,220 L700,300 L680,380 L640,420 L580,480 L520,520 L460,540 L400,530 L360,500 L320,440 L300,380 L280,320 L260,260 L250,200 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />
          {/* South America */}
          <path
            className="continent-outline"
            d="M520,560 L580,550 L640,570 L680,620 L700,680 L690,740 L660,800 L620,850 L570,880 L530,870 L500,830 L480,770 L470,710 L480,650 L500,600 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />
          {/* Europe */}
          <path
            className="continent-outline"
            d="M900,200 L920,170 L960,150 L1000,160 L1040,150 L1080,170 L1120,160 L1160,180 L1200,200 L1180,240 L1200,280 L1180,320 L1140,350 L1100,380 L1060,400 L1020,420 L980,400 L940,380 L920,340 L900,300 L880,260 L890,220 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />
          {/* Africa */}
          <path
            className="continent-outline"
            d="M960,420 L1000,410 L1040,420 L1080,430 L1120,420 L1160,440 L1180,480 L1200,540 L1190,600 L1170,660 L1140,720 L1100,770 L1060,790 L1020,780 L990,740 L970,680 L960,620 L950,560 L940,500 L950,460 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />
          {/* Asia */}
          <path
            className="continent-outline"
            d="M1200,180 L1280,150 L1360,130 L1440,120 L1520,140 L1600,160 L1680,200 L1740,250 L1780,300 L1760,360 L1720,400 L1680,440 L1620,480 L1560,520 L1500,540 L1440,560 L1380,540 L1320,500 L1280,450 L1240,400 L1220,340 L1200,280 L1190,230 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />
          {/* Southeast Asia / Indonesia */}
          <path
            className="continent-outline"
            d="M1560,520 L1600,510 L1660,530 L1720,540 L1780,560 L1820,580 L1800,610 L1750,620 L1700,610 L1640,590 L1580,570 L1550,550 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />
          {/* Australia */}
          <path
            className="continent-outline"
            d="M1620,680 L1680,660 L1750,670 L1820,690 L1870,720 L1890,770 L1870,820 L1830,850 L1770,860 L1710,840 L1660,810 L1630,770 L1610,730 Z"
            fill="none"
            stroke="#E2E5E9"
            strokeWidth="1.5"
            opacity="0.5"
          />

          {[200, 400, 600, 800].map(y => (
            <line key={`lat-${y}`} x1="0" y1={y} x2="2000" y2={y} stroke="#E5E7EB" strokeWidth="1" strokeDasharray="8 6" />
          ))}
          {[500, 1000, 1500].map(x => (
            <line key={`lng-${x}`} x1={x} y1="0" x2={x} y2="1000" stroke="#E5E7EB" strokeWidth="1" strokeDasharray="8 6" />
          ))}
          <line x1="0" y1="500" x2="2000" y2="500" stroke="#D1D5DB" strokeWidth="1.5" strokeDasharray="12 4" />
        </svg>

        {/* Region labels */}
        {[
          { label: "AMERICAS", left: "18%" },
          { label: "EUROPE / AFRICA", left: "48%" },
          { label: "ASIA / OCEANIA", left: "78%" },
        ].map(r => (
          <span
            key={r.label}
            className="absolute font-mono pointer-events-none select-none"
            style={{ left: r.left, top: 16, fontSize: 10, color: "#D1D5DB", letterSpacing: "0.08em" }}
          >
            {r.label}
          </span>
        ))}

        {/* City pins */}
        {resolvedCities.map(city => {
          const isSelected = city.id === selected;
          const isHovered = city.id === hover;
          const color = tempColorC(toC(city));
          const isCrossSource = city.srcs.length > 1;
          const size = isSelected ? 28 : isHovered ? 22 : 14;

          return (
            <div
              key={city.id}
              className="absolute"
              style={{
                left: `${city.rx}%`,
                top: `${city.ry}%`,
                transform: "translate(-50%, -50%)",
                zIndex: isSelected ? 30 : isHovered ? 20 : 10,
              }}
            >
              <button
                onClick={() => onSelect(city.id)}
                onMouseEnter={() => onHover(city.id)}
                onMouseLeave={() => onHover(null)}
                className="p-0 border-0"
                style={{
                  width: size,
                  height: size,
                  borderRadius: 9999,
                  backgroundColor: color,
                  cursor: "pointer",
                  transition: "all 180ms ease",
                  boxShadow: isSelected
                    ? `0 0 0 3px white, 0 0 0 6px ${color}, 0 8px 20px -6px ${color}aa`
                    : `0 0 0 1.5px white, 0 2px 6px rgba(0,0,0,0.15)`,
                  position: "relative",
                }}
                aria-label={`${city.name} ${Math.round(city.high.mode)}°${city.high.unit}`}
              >
                {isCrossSource && (
                  <span
                    style={{
                      position: "absolute",
                      top: -2,
                      right: -2,
                      width: 7,
                      height: 7,
                      borderRadius: 9999,
                      background: `linear-gradient(135deg, ${SOURCES.polymarket.color} 50%, ${SOURCES.kalshi.color} 50%)`,
                      border: "1px solid white",
                    }}
                  />
                )}
              </button>

              {(isSelected || isHovered) && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    top: "100%",
                    left: "50%",
                    transform: "translateX(-50%)",
                    marginTop: 4,
                    whiteSpace: "nowrap",
                    background: "white",
                    borderRadius: 9999,
                    padding: "2px 8px",
                    boxShadow: "0 1px 6px rgba(0,0,0,0.12)",
                    fontSize: 10,
                    color: "#374151",
                    zIndex: 40,
                  }}
                >
                  <span className="font-medium">{city.name}</span>{" "}
                  <span className="font-mono" style={{ color, fontWeight: 600 }}>
                    {Math.round(city.high.mode)}&deg;
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between font-mono"
        style={{ padding: "10px 18px", borderTop: "1px solid #F3F4F6", fontSize: 11, color: "#9CA3AF" }}
      >
        <span>{cities.length} cities shown &middot; tap a pin for distribution</span>
        <span>{crossSourceCount} cross-source</span>
      </div>
    </div>
  );
}

function TempLegend() {
  const stops = [-5, 5, 15, 22, 30, 40].map(t => tempColorC(t));
  return (
    <div className="flex items-center gap-2.5">
      <div
        style={{
          width: 160,
          height: 8,
          borderRadius: 9999,
          background: `linear-gradient(90deg, ${stops.join(",")})`,
        }}
      />
      <span className="font-mono" style={{ fontSize: 11, color: "#6B7280" }}>
        23°F &nbsp;→&nbsp; 104°F
      </span>
    </div>
  );
}
