// Trade & Tariffs section

const { TRADE: TRADE_DATA } = window.ECON_DATA;

function TradeSection() {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Trade & tariffs"
        title="The economic story of 2026"
        meta="Policy · truce · sector impact"
        count={67}
      />
      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
          {TRADE_DATA.map((m, i) => (
            <div key={i} style={{ padding: "0 12px" }}>
              <MarketRow q={m.q} prob={m.prob} src={m.src} compact />
            </div>
          ))}
        </div>
      </Card>
    </section>
  );
}

Object.assign(window, { TradeSection });
