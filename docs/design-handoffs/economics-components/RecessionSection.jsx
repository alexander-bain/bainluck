// GDP & Recession section

const { REC: REC_DATA } = window.ECON_DATA;

function RecessionSection() {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="GDP & recession"
        title="The big macro question"
        meta="Kalshi kxrecession* · Polymarket"
        count={22}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 14 }}>
        <Card pad={28} style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase" }}>
            Recession by end of 2026
          </div>
          <div style={{ marginTop: 16, display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 84, fontWeight: 700, color: "#22C55E", lineHeight: 1 }}>
              {REC_DATA.mainProb}<span style={{ fontSize: 40, opacity: 0.7 }}>%</span>
            </span>
          </div>
          <div style={{ marginTop: 8 }}><Delta v={REC_DATA.delta} /></div>
          <div style={{ fontSize: 13, color: "#6B7280", marginTop: 10 }}>{REC_DATA.context}</div>
          <div style={{ marginTop: 18 }}>
            <CrossSourceReveal k={21} p={25} parentProb={REC_DATA.mainProb} />
          </div>
          {REC_DATA.side.map((m, i) => (
            <div key={i} style={{ marginTop: 12, paddingTop: 10, borderTop: "1px dashed #E5E7EB", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12 }}>
              <span style={{ color: "#374151" }}>{m.q}</span>
              <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: probColor(m.prob) }}>{m.prob}%</span>
            </div>
          ))}
        </Card>
        <Card>
          <h3 style={{ fontSize: 18, fontWeight: 600, color: "#111827", margin: 0, marginBottom: 4 }}>Quarterly GDP growth</h3>
          <div style={{ fontSize: 12, color: "#6B7280", marginBottom: 16 }}>Probability bucket for each quarter · annualized</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {REC_DATA.quarters.map((q, i) => {
              const peak = q.dist.reduce((best, d, j) => (d[0] > q.dist[best][0] ? j : best), 0);
              return (
                <div key={i} style={{ border: "1px solid #E5E7EB", borderRadius: 10, padding: 12, background: q.upcoming ? "#F0FDF4" : "#fff", borderColor: q.upcoming ? "#BBF7D0" : "#E5E7EB" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>{q.q}</div>
                  <div style={{ marginTop: 8 }}>
                    <Histogram buckets={q.dist} color="#10B981" peakLabel={true} height={60} />
                  </div>
                  <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 6 }}>modal: {q.dist[peak][1]}%</div>
                </div>
              );
            })}
          </div>
          <FooterNote left="All brackets sum to 100% per quarter" right="Kalshi kxgdp*" />
        </Card>
      </div>
    </section>
  );
}

Object.assign(window, { RecessionSection });
