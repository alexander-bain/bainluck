// Markets & Indices section

const { MKTS: MKTS_DATA } = window.ECON_DATA;

function MarketsSection() {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Markets & indices"
        title="Resolves daily. Highest-velocity section."
        meta="Kalshi + Polymarket · Daily close + weekly range"
        count={184}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr", gap: 14 }}>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 600, color: "#111827", margin: 0 }}>Today's close</h3>
              <div style={{ fontSize: 12, color: "#6B7280", marginTop: 2 }}>Direction vs yesterday's close</div>
            </div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#059669", letterSpacing: "0.08em" }}>LIVE · 3:42PM ET</span>
          </div>
          {MKTS_DATA.today.map((m, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "90px 1fr 60px", alignItems: "center", gap: 10, padding: "10px 0", borderTop: i > 0 ? "1px solid #F3F4F6" : "none" }}>
              <span style={{ fontWeight: 600, color: "#111827", fontSize: 13 }}>{m.sym}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: m.dir === "up" ? "#22C55E" : "#EF4444", fontWeight: 600 }}>
                  {m.dir === "up" ? "▲" : "▼"}
                </span>
                <span style={{ fontSize: 12, color: "#6B7280" }}>{m.range}</span>
              </div>
              <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: probColor(m.prob), textAlign: "right" }}>
                {m.prob}%
              </span>
            </div>
          ))}
          <FooterNote left={`Yesterday: ${MKTS_DATA.resolved.sym} · priced ${MKTS_DATA.resolved.expected} → ${MKTS_DATA.resolved.actual} ✓`} right="Polymarket" />
        </Card>

        <Card>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: "#111827", margin: 0, marginBottom: 6 }}>Single stocks · daily</h3>
          <div style={{ fontSize: 12, color: "#6B7280", marginBottom: 12 }}>Probability up today</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {MKTS_DATA.stocks.map((s, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 10px", background: "#F9FAFB", borderRadius: 8 }}>
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color: "#111827" }}>{s.sym}</div>
                  <Delta v={s.delta} />
                </div>
                <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: probColor(s.prob) }}>{s.prob}%</span>
              </div>
            ))}
          </div>
          <FooterNote left="6 of 180+ stock markets" right="Polymarket" />
        </Card>

        <Card>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: "#111827", margin: 0, marginBottom: 4 }}>QQQ weekly range</h3>
          <div style={{ fontSize: 12, color: "#6B7280", marginBottom: 12 }}>
            Close Friday · Current: <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>${MKTS_DATA.weekly.current}</span>
          </div>
          <Histogram buckets={MKTS_DATA.weekly.buckets} color="#3B82F6" height={80} />
          <FooterNote left="Modal: 485-490" right="Kalshi" />
        </Card>
      </div>
    </section>
  );
}

Object.assign(window, { MarketsSection });
