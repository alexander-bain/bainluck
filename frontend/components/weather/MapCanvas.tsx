"use client";

import { CITIES, SOURCES, tempColorC, toC } from "./data";

interface MapCanvasProps {
  selected: string;
  hover: string | null;
  onHover: (id: string | null) => void;
  onSelect: (id: string) => void;
}

const CROSS_SOURCE_COUNT = CITIES.filter((c) => c.srcs.length > 1).length;

export default function MapCanvas({
  selected,
  hover,
  onHover,
  onSelect,
}: MapCanvasProps) {
  return (
    <div className="bg-white rounded-2xl overflow-hidden">
      {/* Toolbar */}
      <div
        className="flex items-center justify-between"
        style={{ padding: "14px 18px", borderBottom: "1px solid #E5E7EB" }}
      >
        {/* Temperature gradient legend */}
        <div
          style={{
            width: 160,
            height: 8,
            borderRadius: 9999,
            background:
              "linear-gradient(to right, rgb(37,99,235), rgb(56,189,248), rgb(148,163,184), rgb(245,158,11), rgb(239,68,68), rgb(159,18,57))",
          }}
        />
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 11,
            color: "#9CA3AF",
            letterSpacing: "0.04em",
          }}
        >
          HIGH &middot; APR 20, 2026
        </span>
      </div>

      {/* Map plane */}
      <div
        className="relative"
        style={{
          aspectRatio: "2/1",
          minHeight: 360,
          background: "linear-gradient(180deg, #F9FAFB 0%, #F3F4F6 100%)",
        }}
      >
        {/* SVG dotted grid + lines */}
        <svg
          viewBox="0 0 2000 1000"
          preserveAspectRatio="none"
          className="absolute inset-0 w-full h-full"
          style={{ pointerEvents: "none" }}
        >
          <defs>
            <pattern
              id="dot-grid"
              width="24"
              height="24"
              patternUnits="userSpaceOnUse"
            >
              <circle cx="12" cy="12" r="1.8" fill="#E5E7EB" />
            </pattern>
          </defs>
          <rect width="2000" height="1000" fill="url(#dot-grid)" />

          {/* Latitude lines */}
          {[200, 400, 600, 800].map((y) => (
            <line
              key={`lat-${y}`}
              x1="0"
              y1={y}
              x2="2000"
              y2={y}
              stroke="#E5E7EB"
              strokeWidth="1"
              strokeDasharray="8 6"
            />
          ))}

          {/* Longitude lines */}
          {[500, 1000, 1500].map((x) => (
            <line
              key={`lng-${x}`}
              x1={x}
              y1="0"
              x2={x}
              y2="1000"
              stroke="#E5E7EB"
              strokeWidth="1"
              strokeDasharray="8 6"
            />
          ))}

          {/* Equator */}
          <line
            x1="0"
            y1="500"
            x2="2000"
            y2="500"
            stroke="#D1D5DB"
            strokeWidth="1.5"
            strokeDasharray="12 4"
          />
        </svg>

        {/* Region labels */}
        {[
          { label: "AMERICAS", left: "18%" },
          { label: "EUROPE / AFRICA", left: "48%" },
          { label: "ASIA / OCEANIA", left: "78%" },
        ].map((r) => (
          <span
            key={r.label}
            className="absolute"
            style={{
              left: r.left,
              top: 16,
              transform: "translateX(-50%)",
              fontFamily: "monospace",
              fontSize: 10,
              color: "#D1D5DB",
              letterSpacing: "0.08em",
              pointerEvents: "none",
              userSelect: "none",
            }}
          >
            {r.label}
          </span>
        ))}

        {/* City pins */}
        {CITIES.map((city) => {
          const isSelected = city.id === selected;
          const isHovered = city.id === hover;
          const color = tempColorC(toC(city));
          const tempC = toC(city);
          const displayTemp =
            city.high.unit === "F"
              ? `${Math.round(city.high.mode)}°F`
              : `${Math.round(city.high.mode)}°C`;

          const size = isSelected ? 34 : isHovered ? 30 : 22;
          const isCrossSource = city.srcs.length > 1;

          return (
            <div
              key={city.id}
              className="absolute"
              style={{
                left: `${city.x}%`,
                top: `${city.y}%`,
                transform: "translate(-50%, -50%)",
                zIndex: isSelected ? 30 : isHovered ? 20 : 10,
              }}
            >
              <button
                onClick={() => onSelect(city.id)}
                onMouseEnter={() => onHover(city.id)}
                onMouseLeave={() => onHover(null)}
                style={{
                  width: size,
                  height: size,
                  borderRadius: 9999,
                  backgroundColor: color,
                  border: "none",
                  cursor: "pointer",
                  transition: "transform 180ms ease, width 180ms ease, height 180ms ease",
                  boxShadow: isSelected
                    ? `0 0 0 3px white, 0 0 0 5px ${color}, 0 4px 16px rgba(0,0,0,0.25)`
                    : `0 0 0 2px white, 0 2px 6px rgba(0,0,0,0.15)`,
                  position: "relative",
                }}
                aria-label={`${city.name} ${displayTemp}`}
              >
                {/* Cross-source indicator dot */}
                {isCrossSource && (
                  <span
                    style={{
                      position: "absolute",
                      top: -2,
                      right: -2,
                      width: 10,
                      height: 10,
                      borderRadius: 9999,
                      background: `linear-gradient(135deg, ${SOURCES.polymarket.color} 50%, ${SOURCES.kalshi.color} 50%)`,
                      border: "1.5px solid white",
                    }}
                  />
                )}
              </button>

              {/* City label pill */}
              {(isSelected || isHovered) && (
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: "50%",
                    transform: "translateX(-50%)",
                    marginTop: 6,
                    whiteSpace: "nowrap",
                    background: "white",
                    borderRadius: 9999,
                    padding: "3px 10px",
                    boxShadow: "0 1px 6px rgba(0,0,0,0.12)",
                    fontFamily: "monospace",
                    fontSize: 11,
                    color: "#374151",
                    pointerEvents: "none",
                    zIndex: 40,
                  }}
                >
                  {city.name}{" "}
                  <span style={{ color, fontWeight: 600 }}>
                    {Math.round(
                      city.high.unit === "C" ? city.high.mode : tempC
                    )}
                    &deg;
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between"
        style={{
          padding: "10px 18px",
          borderTop: "1px solid #F3F4F6",
        }}
      >
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 11,
            color: "#9CA3AF",
          }}
        >
          {CITIES.length} cities shown &middot; tap a pin for distribution
        </span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 11,
            color: "#9CA3AF",
          }}
        >
          {CROSS_SOURCE_COUNT} cross-source
        </span>
      </div>
    </div>
  );
}
