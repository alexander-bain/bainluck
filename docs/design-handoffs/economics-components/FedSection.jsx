// Fed rates section — two viz variants (timeline dot-plot + heatmap)

const { FOMC, RATE_CUTS_2026, RATE_SIDE, CURRENT_RATE, probColor: fedPC } = window.ECON_DATA;

function FedTimeline() {
  // Dot plot: each FOMC meeting is a column; rate outcomes are rows
  const rates = ["5.00+", "4.75-5.00", "4.50-4.75", "4.25-4.50", "4.00-4.25", "3.75-4.00", "3.50-3.75"];
  // Map to get prob for (mtgIdx, rateLabel)
  const get = (m, r) => {
    const found = m.dist.find((d) => d[1] === r || d[1].startsWith(r));
    return found ? found[0] : 0;
  };
  const currentRateIdx = rates.indexOf(CURRENT_RATE);

  return (
    <div>
      {/* Legend */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, fontSize: 11, color: "#6B7280" }}>
        <span style={{ fontFamily: "var(--mono)" }}>
          <span style={{ color: "#374151", fontWeight: 600 }}>Current: {CURRENT_RATE}</span>
          <span style={{ marginLeft: 12, color: "#9CA3AF" }}>Bubble size = probability</span>
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 10 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#9CA3AF" }} /> Resolved
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#10B981" }} /> Modal outcome
          </span>
        </div>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "70px repeat(8, 1fr)",
        alignItems: "center",
      }}>
        {/* Header row */}
        <div />
        {FOMC.map((m) => (
          <div key={m.mo} style={{ textAlign: "center", paddingBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: m.upcoming ? "#10B981" : "#374151" }}>{m.mo}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "#9CA3AF" }}>{m.date}</div>
            {m.upcoming && (
              <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.08em", color: "#059669", marginTop: 2 }}>NEXT</div>
            )}
          </div>
        ))}

        {/* Grid rows */}
        {rates.map((r, ri) => (
          <React.Fragment key={r}>
            <div style={{
              fontFamily: "var(--mono)", fontSize: 10, color: "#6B7280",
              textAlign: "right", paddingRight: 8,
              borderBottom: "1px dashed #F3F4F6", padding: "14px 8px 14px 0",
            }}>
              {r}%
            </div>
            {FOMC.map((m, mi) => {
              const prob = get(m, r);
              const modal = m.dist.reduce((best, d, i) => (d[0] > m.dist[best][0] ? i : best), 0);
              const modalRate = m.dist[modal][1];
              const isModal = modalRate === r || modalRate.startsWith(r);
              const size = prob === 0 ? 0 : 6 + Math.sqrt(prob) * 3.5;
              const resolved = m.resolved;
              let color = "#10B981";
              if (resolved) color = "#9CA3AF";
              else if (!isModal) color = "#C4B5FD";
              return (
                <div key={mi} style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  height: 44, borderBottom: "1px dashed #F3F4F6", position: "relative",
                  background: m.upcoming ? "#F0FDF4" : "transparent",
                }}>
                  {prob > 0 && (
                    <div style={{
                      width: size, height: size, borderRadius: "50%",
                      background: color,
                      opacity: isModal ? 1 : 0.55,
                      cursor: "pointer",
                      position: "relative",
                    }} title={`${m.mo} · ${r}%: ${prob}% prob`}>
                      {isModal && prob >= 30 && (
                        <span style={{
                          position: "absolute", top: "50%", left: "50%",
                          transform: "translate(-50%, -50%)",
                          fontFamily: "var(--mono)", fontSize: 9, fontWeight: 700,
                          color: "#fff", whiteSpace: "nowrap",
                        }}>
                          {prob}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>

      {/* Current-rate baseline */}
      <div style={{ marginTop: 12, fontSize: 11, color: "#6B7280", lineHeight: 1.4 }}>
        Markets price a <span style={{ color: "#111827", fontWeight: 600 }}>gradual easing path</span> through 2026 — modal outcome drifts from {CURRENT_RATE} today to <span style={{ color: "#10B981", fontWeight: 600, fontFamily: "var(--mono)" }}>3.75-4.00%</span> by December.
      </div>
    </div>
  );
}

function FedHeatmap() {
  const rates = ["5.00+", "4.75-5.00", "4.50-4.75", "4.25-4.50", "4.00-4.25", "3.75-4.00", "3.50-3.75"];
  const get = (m, r) => {
    const found = m.dist.find((d) => d[1] === r || d[1].startsWith(r));
    return found ? found[0] : 0;
  };
  const cellColor = (p) => {
    if (p === 0) return "#FAFBFC";
    const intensity = Math.min(1, p / 60);
    return `rgba(16, 185, 129, ${0.08 + intensity * 0.72})`;
  };
  return (
    <div>
      <div style={{ fontSize: 11, color: "#6B7280", marginBottom: 10, fontFamily: "var(--mono)" }}>
        Probability heatmap · Darker = more likely
      </div>
      <div style={{
        display: "grid",
        gridTemplateColumns: "70px repeat(8, 1fr)",
        gap: 2,
      }}>
        <div />
        {FOMC.map((m) => (
          <div key={m.mo} style={{ textAlign: "center", paddingBottom: 6 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: m.upcoming ? "#10B981" : "#374151" }}>{m.mo}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "#9CA3AF" }}>{m.date}</div>
          </div>
        ))}
        {rates.map((r) => (
          <React.Fragment key={r}>
            <div style={{
              fontFamily: "var(--mono)", fontSize: 10, color: "#6B7280",
              textAlign: "right", paddingRight: 8, height: 38, display: "flex",
              alignItems: "center", justifyContent: "flex-end",
            }}>
              {r}%
            </div>
            {FOMC.map((m, mi) => {
              const prob = get(m, r);
              const modal = m.dist.reduce((best, d, i) => (d[0] > m.dist[best][0] ? i : best), 0);
              const modalRate = m.dist[modal][1];
              const isModal = modalRate === r || modalRate.startsWith(r);
              return (
                <div key={mi} style={{
                  height: 38, background: cellColor(prob),
                  border: isModal ? "1.5px solid #10B981" : "1px solid #F3F4F6",
                  borderRadius: 4,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600,
                  color: prob >= 30 ? "#064E3B" : prob >= 10 ? "#374151" : "#9CA3AF",
                }}>
                  {prob > 0 ? prob : ""}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function FedSection({ viz }) {
  return (
    <section style={{ marginBottom: 48 }}>
      <SectionHeader
        kicker="Federal Reserve"
        title="Rate-path dot plot — but from markets, not the Fed"
        meta="8 FOMC meetings · Kalshi kxfedfunds*"
        count={96}
      />

      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <Card pad={24}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 20, fontWeight: 600, color: "#111827", margin: 0 }}>
                2026 rate path
              </h3>
              <p style={{ fontSize: 13, color: "#6B7280", margin: "4px 0 0" }}>
                Market-implied probability of each Fed funds bracket at every FOMC meeting
              </p>
            </div>
            <SourceChip src="kalshi" />
          </div>
          {viz === "heatmap" ? <FedHeatmap /> : <FedTimeline />}
          <FooterNote left="Each column = one FOMC meeting · Bubble size = probability" right="Resolves post-FOMC" />
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 6 }}>
              How many cuts in 2026?
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
              {RATE_CUTS_2026.map((r, i) => {
                const max = Math.max(...RATE_CUTS_2026.map((c) => c.prob));
                const w = (r.prob / max) * 100;
                const col = probColor(r.prob);
                const isModal = r.prob === max;
                return (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "60px 1fr 40px", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: isModal ? 600 : 500, color: isModal ? "#111827" : "#6B7280" }}>
                      {r.label}
                    </span>
                    <div style={{ height: 8, background: "#F3F4F6", borderRadius: 999, overflow: "hidden" }}>
                      <div style={{ width: `${w}%`, height: "100%", background: col, borderRadius: 999 }} />
                    </div>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: col, textAlign: "right" }}>
                      {r.prob}%
                    </span>
                  </div>
                );
              })}
            </div>
            <FooterNote left="Modal: 3 cuts" right="Kalshi" />
          </Card>

          <Card>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#9CA3AF", textTransform: "uppercase", marginBottom: 10 }}>
              Side markets
            </div>
            {RATE_SIDE.map((r, i) => (
              <MarketRow key={i} q={r.q} prob={r.prob} src={r.src} compact />
            ))}
          </Card>
        </div>
      </div>
    </section>
  );
}

Object.assign(window, { FedSection });
