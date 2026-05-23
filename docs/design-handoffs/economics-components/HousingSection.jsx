// Housing & Mortgages section

const { HOUSING: HOUSING_DATA } = window.ECON_DATA;

function HousingSection() {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Housing & mortgages"
        title="Rates, prices, and the American dream"
        meta="Kalshi kxmortgage* · Polymarket"
        count={28}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14 }}>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 600, color: "#111827", margin: 0 }}>30-year mortgage rate</h3>
              <div style={{ fontSize: 12, color: "#6B7280", marginTop: 2 }}>
                Where will it settle in 2026? · Currently <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>{HOUSING_DATA.mortgage.current}%</span>
              </div>
            </div>
            <SourceChip src="kalshi" />
          </div>
          <Histogram buckets={HOUSING_DATA.mortgage.brackets} color="#8B5CF6" height={90} />
          <FooterNote left="Modal: 6.5-7.0% (34%)" right="Resolves EOY 2026" />
        </Card>
        <Card>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 10 }}>
            Housing markets
          </div>
          {HOUSING_DATA.markets.map((m, i) => (
            <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} compact />
          ))}
        </Card>
      </div>
    </section>
  );
}

Object.assign(window, { HousingSection });
