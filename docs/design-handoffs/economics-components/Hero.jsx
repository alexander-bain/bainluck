// Hero: ticker strip + calendar of upcoming releases

const { TICKER, CALENDAR, SOURCES: HERO_SOURCES, probColor: heroProbColor } = window.ECON_DATA;

function Ticker() {
  // Duplicate items for seamless loop
  const items = [...TICKER, ...TICKER];
  return (
    <div style={{
      position: "relative",
      background: "#0F172A",
      color: "#F8FAFC",
      borderRadius: 14,
      overflow: "hidden",
      marginBottom: 14,
    }}>
      <style>{`
        @keyframes econ-ticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }
      `}</style>
      <div style={{
        display: "flex", gap: 0,
        animation: "econ-ticker 60s linear infinite",
        width: "max-content",
      }}>
        {items.map((it, i) => {
          const s = HERO_SOURCES[it.src] || HERO_SOURCES.kalshi;
          const up = (it.delta || 0) > 0;
          const down = (it.delta || 0) < 0;
          const deltaCol = up ? "#4ADE80" : down ? "#F87171" : "#94A3B8";
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "14px 24px",
              borderRight: "1px solid rgba(255,255,255,0.08)",
              whiteSpace: "nowrap",
            }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: "#94A3B8", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>
                {it.q}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 700 }}>{it.val}</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600, color: deltaCol }}>
                {up ? "▲" : down ? "▼" : "—"} {Math.abs(it.delta || 0)}{it.unit ? "" : it.delta === 0 ? "" : "pp"}
              </span>
            </div>
          );
        })}
      </div>
      {/* Fades */}
      <div style={{ position: "absolute", top: 0, left: 0, width: 80, height: "100%", background: "linear-gradient(90deg, #0F172A, transparent)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", top: 0, right: 0, width: 80, height: "100%", background: "linear-gradient(270deg, #0F172A, transparent)", pointerEvents: "none" }} />
      {/* Live label */}
      <div style={{ position: "absolute", top: 10, right: 14, display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "#4ADE80", textTransform: "uppercase" }}>
        <span className="econ-live-dot" />
        Live
      </div>
    </div>
  );
}

function CalendarRow() {
  return (
    <div style={{
      background: "#fff", border: "1px solid #E5E7EB",
      borderRadius: 14, padding: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#059669", textTransform: "uppercase" }}>
            Data calendar
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "#111827", marginTop: 2 }}>
            Next 3 weeks of economic releases
          </div>
        </div>
        <span style={{ fontSize: 11, color: "#9CA3AF", fontFamily: "var(--mono)" }}>
          Market-implied expectations →
        </span>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: `repeat(${CALENDAR.length}, minmax(140px, 1fr))`,
        gap: 8, overflowX: "auto",
      }}>
        {CALENDAR.map((c, i) => {
          const col = heroProbColor(c.prob);
          return (
            <div key={i} style={{
              border: "1px solid #E5E7EB",
              borderRadius: 10,
              padding: "12px 12px 14px",
              background: i === 2 ? "#F0FDF4" : "#fff",
              borderColor: i === 2 ? "#BBF7D0" : "#E5E7EB",
              position: "relative",
            }}>
              {i === 2 && (
                <div style={{
                  position: "absolute", top: -8, left: 10,
                  background: "#22C55E", color: "#fff",
                  fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
                  padding: "2px 6px", borderRadius: 4,
                }}>
                  NEXT
                </div>
              )}
              <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 6 }}>
                <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: "#111827" }}>{c.date}</span>
                <span style={{ fontSize: 10, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.08em" }}>{c.day}</span>
              </div>
              <div style={{ fontSize: 12, color: "#374151", fontWeight: 500, lineHeight: 1.3, marginBottom: 10, minHeight: 32 }}>
                {c.release}
              </div>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "#6B7280" }}>{c.note}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 700, color: col, marginTop: 2 }}>{c.prob}%</div>
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "#9CA3AF", textAlign: "right" }}>
                  cons.<br/>{c.est}
                </div>
              </div>
              <div style={{ height: 3, background: "#F3F4F6", borderRadius: 999, overflow: "hidden", marginTop: 10 }}>
                <div style={{ width: `${c.prob}%`, height: "100%", background: col, borderRadius: 999 }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Hero({ variant = "both" }) {
  return (
    <section style={{ marginBottom: 40 }}>
      {/* Pill + headline */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 7,
          padding: "4px 11px", borderRadius: 999,
          background: "#ECFDF5", color: "#047857",
          fontSize: 12, fontWeight: 600, letterSpacing: "0.02em",
        }}>
          <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8 }}>
            <span className="econ-ping" style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#4ADE80", opacity: 0.6 }} />
            <span style={{ position: "relative", width: 8, height: 8, borderRadius: "50%", background: "#22C55E" }} />
          </span>
          Economics markets · Live
        </span>
        <span style={{ fontSize: 11, color: "#9CA3AF", fontFamily: "var(--mono)" }}>
          1,284 active · updated 18s ago
        </span>
      </div>

      <h1 style={{
        fontSize: 48, fontWeight: 600, color: "#111827",
        letterSpacing: "-0.028em", lineHeight: 1.08,
        marginBottom: 10, maxWidth: 900,
      }}>
        What do markets think about <span style={{ color: "#10B981" }}>the economy</span>?
      </h1>
      <p style={{ fontSize: 17, color: "#6B7280", maxWidth: 640, marginBottom: 22, lineHeight: 1.45 }}>
        1,284 economic prediction markets from Kalshi and Polymarket translated into plain probabilities.
        Rates, inflation, jobs, GDP — no odds, just percentages.
      </p>

      {(variant === "ticker" || variant === "both") && <Ticker />}
      {(variant === "calendar" || variant === "both") && <CalendarRow />}
    </section>
  );
}

Object.assign(window, { Ticker, CalendarRow, Hero });
