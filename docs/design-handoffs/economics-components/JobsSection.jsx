// Jobs & Employment section

const { JOBS: JOBS_DATA } = window.ECON_DATA;

function JobsSection() {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Jobs & employment"
        title="Monthly reports. Weekly claims. Live revisions."
        meta="Kalshi kxunemployment*, kxjobless*"
        count={34}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr 1fr", gap: 14 }}>
        <Card>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 6 }}>
            Modal unemployment rate
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 10 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 56, fontWeight: 700, color: "#10B981", lineHeight: 1 }}>
              {JOBS_DATA.headline.val}
            </span>
          </div>
          <div style={{ fontSize: 13, color: "#6B7280", marginTop: 8 }}>{JOBS_DATA.headline.sub}</div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "#6B7280", marginTop: 6 }}>
            <span style={{ color: "#111827", fontWeight: 600 }}>{JOBS_DATA.headline.prob}%</span> probability bucket
          </div>
          <FooterNote left="Resolves May 2" right="Kalshi" />
        </Card>

        <Card>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 12 }}>
            Weekly initial claims
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 100 }}>
            {JOBS_DATA.claims.map((c, i) => {
              const max = 240;
              const h = (c.val / max) * 100;
              const col = c.resolved ? "#9CA3AF" : c.upcoming ? "#10B981" : "#6EE7B7";
              return (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600, color: col, marginBottom: 3 }}>{c.val}k</span>
                  <div style={{ width: "100%", height: `${h}%`, background: col, borderRadius: "3px 3px 0 0", opacity: c.resolved ? 0.5 : 1 }} />
                  <span style={{ fontSize: 10, color: "#9CA3AF", marginTop: 4 }}>{c.wk}</span>
                </div>
              );
            })}
          </div>
          <FooterNote left="Apr 19 resolved 219k · markets priced 221k" right="Thu 8:30am ET" />
        </Card>

        <Card>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 10 }}>
            Nonfarm payrolls
          </div>
          {JOBS_DATA.nfp.map((m, i) => (
            <MarketRow key={i} q={m.q} prob={m.prob} src={m.src} compact />
          ))}
        </Card>
      </div>
    </section>
  );
}

Object.assign(window, { JobsSection });
