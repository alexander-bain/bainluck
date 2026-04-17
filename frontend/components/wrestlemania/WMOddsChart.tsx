"use client";

import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { format, parseISO } from "date-fns";
import type { WMOutcome } from "@/lib/types";

const OUTCOME_COLORS = ["#FF2E93", "#00E5FF", "#FFD700", "#9B59B6", "#2ECC71", "#E67E22"];

interface WMOddsChartProps {
  outcomes: WMOutcome[];
  height?: number;
}

export default function WMOddsChart({ outcomes, height = 220 }: WMOddsChartProps) {
  const chartData = useMemo(() => {
    const timeMap = new Map<string, Record<string, number>>();

    outcomes.forEach((outcome, idx) => {
      for (const point of outcome.history) {
        const key = point.t;
        if (!timeMap.has(key)) timeMap.set(key, { time: new Date(point.t).getTime() } as Record<string, number>);
        const entry = timeMap.get(key)!;
        entry[`o${idx}`] = Math.round(point.p * 100);
      }
    });

    return Array.from(timeMap.values()).sort((a, b) => (a.time as number) - (b.time as number));
  }, [outcomes]);

  const hasData = chartData.length >= 2;

  if (!hasData) {
    return (
      <div style={{
        height,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--wm-text-muted)",
        fontSize: "0.8rem",
        border: "1px dashed var(--wm-card-border)",
        borderRadius: 6,
      }}>
        Chart data will appear once odds start moving
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="time"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(val) => format(new Date(val), "h:mm a")}
            tick={{ fill: "#606080", fontSize: 10 }}
            stroke="rgba(255,255,255,0.1)"
            tickCount={5}
          />
          <YAxis
            domain={[0, 100]}
            tickFormatter={(val) => `${val}%`}
            tick={{ fill: "#606080", fontSize: 10 }}
            stroke="rgba(255,255,255,0.1)"
            width={40}
          />
          <ReferenceLine y={50} stroke="rgba(255,255,255,0.1)" strokeDasharray="4 4" />
          <Tooltip
            contentStyle={{
              background: "#111128",
              border: "1px solid #1a1a3a",
              borderRadius: 6,
              fontSize: "0.75rem",
              fontFamily: "'Space Mono', monospace",
            }}
            labelFormatter={(val) => format(new Date(val as number), "MMM d, h:mm a")}
            formatter={(value: number, name: string) => {
              const idx = parseInt(name.replace("o", ""));
              return [`${value}%`, outcomes[idx]?.name ?? name];
            }}
          />
          {outcomes.map((outcome, idx) => (
            <Line
              key={outcome.id}
              type="monotone"
              dataKey={`o${idx}`}
              stroke={OUTCOME_COLORS[idx % OUTCOME_COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              name={`o${idx}`}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {/* Legend */}
      <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginTop: "0.25rem" }}>
        {outcomes.map((outcome, idx) => (
          <div key={outcome.id} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.65rem", color: "var(--wm-text-secondary)" }}>
            <div style={{ width: 10, height: 3, background: OUTCOME_COLORS[idx % OUTCOME_COLORS.length], borderRadius: 1 }} />
            {outcome.name}
          </div>
        ))}
      </div>
    </div>
  );
}
