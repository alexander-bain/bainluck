// Government & Fiscal section

const { GOV: GOV_DATA } = window.ECON_DATA;

function GovSection() {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Government & fiscal"
        title="Shutdowns, debt, DOGE"
        meta="Polymarket + Kalshi"
        count={12}
      />
      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
          {GOV_DATA.map((m, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr auto auto auto", alignItems: "center", gap: 10, borderTop: i > 0 ? "1px solid #F3F4F6" : "none", padding: "12px" }}>
              <span style={{ fontSize: 13, color: "#374151" }}>{m.q}</span>
              <Delta v={m.delta} />
              <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: probColor(m.prob), minWidth: 42, textAlign: "right" }}>
                {m.prob}%
              </span>
              <SourceChip src={m.src} />
            </div>
          ))}
        </div>
      </Card>
    </section>
  );
}

Object.assign(window, { GovSection });
