// Energy & Commodities section

const { ENERGY: ENERGY_DATA } = window.ECON_DATA;

function EnergySection() {
  const gas = ENERGY_DATA.gas;
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Energy & commodities"
        title="Gas, oil, and the price at the pump"
        meta="Kalshi kxgasprice*, kxwti*, kxbrent*"
        count={46}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 0.8fr", gap: 14 }}>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: "#111827", margin: 0 }}>US national gas · 2026 peak</h3>
            <SourceChip src="kalshi" />
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 32, fontWeight: 700, color: "#10B981" }}>{gas.national.val}</span>
            <span style={{ fontSize: 12, color: "#6B7280" }}>modal · {gas.national.prob}%</span>
          </div>
          <Histogram buckets={gas.national.brackets} color="#10B981" height={70} />
          <FooterNote left={'"How high will gas go in 2026?"'} right="Resolves EOY" />
        </Card>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: "#111827", margin: 0 }}>California · 2026 peak</h3>
            <SourceChip src="kalshi" />
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 32, fontWeight: 700, color: "#F59E0B" }}>{gas.ca.val}</span>
            <span style={{ fontSize: 12, color: "#6B7280" }}>modal · {gas.ca.prob}%</span>
          </div>
          <Histogram buckets={gas.ca.brackets} color="#F59E0B" height={70} />
          <FooterNote left="CA historically runs $1.30-1.50 above US" />
        </Card>
        <Card>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 10 }}>
            Crude oil · today
          </div>
          {ENERGY_DATA.oil.map((o, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "60px 1fr 50px", alignItems: "center", gap: 10, padding: "10px 0", borderTop: i > 0 ? "1px solid #F3F4F6" : "none" }}>
              <span style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: 13 }}>{o.sym}</span>
              <span style={{ fontSize: 12, color: "#6B7280" }}>{o.range}</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: probColor(o.prob), textAlign: "right" }}>
                {o.prob}%
              </span>
            </div>
          ))}
          <FooterNote left="Daily brackets · 5-8 per contract" right="Kalshi" />
        </Card>
      </div>
    </section>
  );
}

Object.assign(window, { EnergySection });
