import { ImageResponse } from "next/og";
import { NextRequest } from "next/server";

export const runtime = "edge";

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;

  const accuracy = searchParams.get("accuracy") || "0";
  const total = searchParams.get("total") || "0";
  const correct = searchParams.get("correct") || "0";
  const streak = searchParams.get("streak") || "0";
  const bestStreak = searchParams.get("best") || "0";

  const accuracyNum = Math.min(100, Math.max(0, parseInt(accuracy) || 0));
  const totalNum = parseInt(total) || 0;
  const correctNum = parseInt(correct) || 0;
  const streakNum = parseInt(streak) || 0;
  const bestStreakNum = parseInt(bestStreak) || 0;

  return new ImageResponse(
    (
      <div
        style={{
          width: "1200px",
          height: "630px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #F5F5F7 0%, #FFFFFF 50%, #F0FDF4 100%)",
          fontFamily: "system-ui, -apple-system, sans-serif",
          position: "relative",
        }}
      >
        {/* Top bar accent */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "6px",
            background: "linear-gradient(90deg, #10B981, #059669)",
            display: "flex",
          }}
        />

        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            marginBottom: "16px",
          }}
        >
          <div
            style={{
              fontSize: "22px",
              fontWeight: 800,
              color: "#6B7280",
              letterSpacing: "-0.02em",
              textTransform: "uppercase",
            }}
          >
            Prediction Scorecard
          </div>
        </div>

        {/* Main accuracy circle */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            marginBottom: "40px",
          }}
        >
          <div
            style={{
              width: "200px",
              height: "200px",
              borderRadius: "100px",
              background: "#FFFFFF",
              border: "8px solid #10B981",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 4px 24px rgba(16, 185, 129, 0.15)",
            }}
          >
            <div
              style={{
                fontSize: "72px",
                fontWeight: 900,
                color: "#111827",
                lineHeight: 1,
                letterSpacing: "-0.03em",
              }}
            >
              {accuracyNum}%
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 600,
                color: "#6B7280",
                marginTop: "4px",
              }}
            >
              accuracy
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div
          style={{
            display: "flex",
            gap: "48px",
            alignItems: "center",
          }}
        >
          <StatBox label="Predictions" value={totalNum.toString()} />
          <StatBox label="Correct" value={correctNum.toString()} />
          <StatBox
            label="Streak"
            value={streakNum > 0 ? streakNum.toString() : bestStreakNum.toString()}
            suffix={streakNum > 0 ? " active" : " best"}
            highlight={streakNum > 0}
          />
        </div>

        {/* Footer branding */}
        <div
          style={{
            position: "absolute",
            bottom: "28px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <div
            style={{
              fontSize: "18px",
              fontWeight: 800,
              color: "#9CA3AF",
              letterSpacing: "-0.01em",
            }}
          >
            bainluck.com/discover
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    }
  );
}

function StatBox({
  label,
  value,
  suffix,
  highlight,
}: {
  label: string;
  value: string;
  suffix?: string;
  highlight?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        minWidth: "140px",
        padding: "20px 24px",
        borderRadius: "16px",
        background: "#FFFFFF",
        border: "1px solid #E5E7EB",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "4px",
        }}
      >
        <div
          style={{
            fontSize: "36px",
            fontWeight: 900,
            color: highlight ? "#10B981" : "#111827",
            letterSpacing: "-0.02em",
          }}
        >
          {value}
        </div>
        {suffix && (
          <div
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "#9CA3AF",
            }}
          >
            {suffix}
          </div>
        )}
      </div>
      <div
        style={{
          fontSize: "14px",
          fontWeight: 600,
          color: "#6B7280",
          marginTop: "4px",
        }}
      >
        {label}
      </div>
    </div>
  );
}
