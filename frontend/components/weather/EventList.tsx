import { type EventMarket, probColor } from "./data";
import { SourceBadge } from "./SourceBadge";

interface EventListProps {
  title: string;
  sub: string;
  icon: string;
  items: EventMarket[];
  accent: string;
}

export default function EventList({ title, sub, icon, items, accent }: EventListProps) {
  return (
    <div
      style={{
        backgroundColor: "#fff",
        borderRadius: 16,
        padding: 22,
      }}
    >
      {/* Header */}
      <div className="flex items-center" style={{ gap: 10, marginBottom: 16 }}>
        <div
          className="flex items-center justify-center"
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            backgroundColor: `${accent}14`,
            fontSize: 15,
            color: accent,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>
        <div>
          <h3
            style={{
              fontSize: 18,
              fontWeight: 600,
              color: "#111827",
              margin: 0,
              lineHeight: 1.2,
            }}
          >
            {title}
          </h3>
          <span style={{ fontSize: 12.5, color: "#6B7280" }}>{sub}</span>
        </div>
      </div>

      {/* Item rows */}
      <div className="flex flex-col" style={{ gap: 0 }}>
        {items.map((item, i) => (
          <div
            key={i}
            style={{
              borderTop: i > 0 ? "1px solid #F3F4F6" : undefined,
              padding: "10px 0",
            }}
          >
            <div className="flex items-center justify-between" style={{ gap: 10 }}>
              <div className="flex-1" style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, color: "#111827", marginBottom: 4 }}>
                  {item.q}
                </div>
                <div className="flex items-center" style={{ gap: 6 }}>
                  <SourceBadge src={item.src} />
                  <span
                    className="font-mono"
                    style={{ fontSize: 11, color: "#9CA3AF" }}
                  >
                    {item.closes}
                  </span>
                </div>
              </div>

              <div className="flex items-center" style={{ gap: 8, flexShrink: 0 }}>
                <div
                  style={{
                    width: 56,
                    height: 4,
                    backgroundColor: "#F3F4F6",
                    borderRadius: 2,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${item.prob}%`,
                      height: "100%",
                      backgroundColor: probColor(item.prob),
                      borderRadius: 2,
                    }}
                  />
                </div>
                <span
                  className="font-mono"
                  style={{
                    fontSize: 18,
                    fontWeight: 600,
                    color: probColor(item.prob),
                    minWidth: 40,
                    textAlign: "right",
                  }}
                >
                  {item.prob}%
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
