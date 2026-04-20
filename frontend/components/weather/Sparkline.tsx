"use client";

import { useId } from "react";

interface SparklineProps {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
  stroke?: number;
}

export default function Sparkline({
  data,
  color = "#10B981",
  width = 96,
  height = 28,
  stroke = 1.5,
}: SparklineProps) {
  const gradientId = useId();

  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const pad = 3;
  const plotW = width - pad * 2;
  const plotH = height - pad * 2;

  const points = data.map((v, i) => ({
    x: pad + (i / (data.length - 1)) * plotW,
    y: pad + plotH - ((v - min) / range) * plotH,
  }));

  // Build smooth cubic bezier path
  const pathParts: string[] = [`M${points[0].x},${points[0].y}`];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    pathParts.push(`C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`);
  }
  const linePath = pathParts.join(" ");

  const last = points[points.length - 1];

  // Area path: line path + close to bottom
  const areaPath = `${linePath} L${last.x},${height} L${points[0].x},${height} Z`;

  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <style>{`
        .spark-line {
          stroke-dasharray: 400;
          stroke-dashoffset: 400;
          animation: spark-draw 1.2s ease-out forwards;
        }
        @keyframes spark-draw {
          to { stroke-dashoffset: 0; }
        }
      `}</style>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <path
        d={linePath}
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        className={prefersReducedMotion ? undefined : "spark-line"}
      />
      <circle cx={last.x} cy={last.y} r={2.2} fill={color} />
    </svg>
  );
}
