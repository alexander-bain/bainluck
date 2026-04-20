"use client";

import { probColor } from "./data";

interface ProbabilityNumberProps {
  value: number;
  size?: number;
  forceColor?: string;
}

export default function ProbabilityNumber({
  value,
  size = 36,
  forceColor,
}: ProbabilityNumberProps) {
  const color = forceColor ?? probColor(value);
  const pctSize = size * 0.42;

  return (
    <span
      className="font-mono"
      style={{
        fontSize: size,
        fontWeight: 600,
        letterSpacing: "-0.02em",
        color,
        lineHeight: 1,
      }}
    >
      {Math.round(value)}
      <span style={{ fontSize: pctSize, opacity: 0.7 }}>%</span>
    </span>
  );
}
