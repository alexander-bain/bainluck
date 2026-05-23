// Inflation section — calendar + bucket stack variants

const { CPI_CAL, INFL_SIDE } = window.ECON_DATA;

function CPICalendarViz() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${CPI_CAL.length}, 1fr)`, gap: 8 }}>
      {CPI_CAL.map((m, i) => {
        const peak = m.released ? m.peakWas : m.peakIs;
        const peakBucket = m.brackets[peak];
        const prob = peakBucket[0];
        const col = m.released ? "#9CA3AF" : probColor(prob);
        return (
          <div key={i} style={{
            border: "1px solid #E5E7EB",
            borderRadius: 10, padding: "12px 10px 14px",
            background: m.upcoming ? "#F0FDF4" : "#fff",
            borderColor: m.upcoming ? "#BBF7D0" : "#E5E7EB",
            opacity: m.released ? 0.75 : 1,
            position: "relative",
          }}>
            {m.upcoming && (
              <div style={{ position: "absolute", top: -8, left: 10, background: "#22C55E", color: "#fff", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", padding: "2px 6px", borderRadius: 4 }}>
                NEXT
              </div>
            )}
            <div style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>{m.mo}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "#9CA3AF", marginBottom: 10 }}>{m.date}</div>

            {/* Mini histogram */}
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 46, marginBottom: 6 }}>
              {m.brackets.map((b, bi) => {
                const max = Math.max(...m.brackets.map((x) => x[0]));
                const h = (b[0] / max) * 100;
                const isPeak = bi === peak;
                return (
                  <div key={bi} style={{
                    flex: 1, height: `${h}%`, minHeight: 2,
                    background: col,
                    opacity: isPeak ? 1 : 0.3,
                    borderRadius: "2px 2px 0 0",
                  }} />
                );
              })}
            </div>
            <div style={{ fontSize: 10, color: "#6B7280", marginBottom: 4 }}>{peakBucket[1]}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 700, color: col }}>
              {prob}%
            </div>
            {m.released ? (
              <div style={{ marginTop: 8 }}>
                <ResolvedBadge actual={`${m.actual}%`} expected={`${m.est}%`} correct={Math.abs(m.actual - m.est) < 0.2} />
              </div>
            ) : (
              <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 6 }}>modal bucket</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CPIStackedViz() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {CPI_CAL.map((m, i) => {
        const total = m.brackets.reduce((s, b) => s + b[0], 0);
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "100px 1fr 80px", gap: 12, alignItems: "center", opacity: m.released ? 0.6 : 1 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>{m.mo}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "#9CA3AF" }}>{m.date}</div>
            </div>
            <div style={{ display: "flex", height: 28, borderRadius: 6, overflow: "hidden", border: "1px solid #F3F4F6" }}>
              {m.brackets.map((b, bi) => {
                const w = (b[0] / total) * 100;
                const colors = ["#10B981", "#6EE7B7", "#FDE68A", "#FCA5A5", "#F87171"];
                return (
                  <div key={bi} title={`${b[1]}: ${b[0]}%`} style={{
                    width: `${w}%`, background: colors[bi], display: "flex",
                    alignItems: "center", justifyContent: "center",
                    fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600,
                    color: bi < 2 ? "#064E3B" : "#7C2D12",
                  }}>
                    {b[0] >= 12 ? `${b[0]}` : ""}
                  </div>
                );
              })}
            </div>
            <div style={{ textAlign: "right" }}>
              {m.released ? (
                <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "#111827" }}>
                  <span style={{ textDecoration: "line-through", color: "#9CA3AF" }}>{m.est}%</span> {m.actual}%
                </span>
              ) : m.upcoming ? (
                <span style={{ fontSize: 10, fontWeight: 700, color: "#059669", letterSpacing: "0.08em" }}>NEXT</span>
              ) : (
                <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "#9CA3AF" }}>—</span>
              )}
            </div>
          </div>
        );
      })}
      <div style={{ display: "flex", gap: 12, fontSize: 10, color: "#6B7280", marginTop: 4, paddingLeft: 112 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 10, height: 10, background: "#10B981" }} />&lt;2.5</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 10, height: 10, background: "#6EE7B7" }} />2.5-3.0</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 10, height: 10, background: "#FDE68A" }} />3.0-3.5</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 10, height: 10, background: "#FCA5A5" }} />3.5-4.0</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 10, height: 10, background: "#F87171" }} />&gt;4.0</span>
      </div>
    </div>
  );
}

function InflationSection({ viz }) {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Inflation & consumer prices"
        title="Monthly CPI releases · Market expectations"
        meta="Kalshi kxcpi* · Polymarket inflation"
        count={58}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <Card pad={24}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 20, fontWeight: 600, color: "#111827", margin: 0 }}>
                CPI release calendar
              </h3>
              <p style={{ fontSize: 13, color: "#6B7280", margin: "4px 0 0" }}>
                Modal outcome per month · Mar &amp; Apr already released
              </p>
            </div>
            <SourceChip src="kalshi" />
          </div>
          {viz === "stacked" ? <CPIStackedViz /> : <CPICalendarViz />}
          <FooterNote left="April CPI printed 2.8% — markets had priced 2.5-3.0 at 41%" right="Next: May 13" />
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <h3 style={{ fontSize: 20, fontWeight: 600, color: "#111827", margin: 0 }}>
              Related markets
            </h3>
          </div>
          {INFL_SIDE.map((m, i) => (
            <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} compact />
          ))}
          <FooterNote left="4 markets · PCE, international, sentiment" />
        </Card>
      </div>
    </section>
  );
}

Object.assign(window, { InflationSection });
