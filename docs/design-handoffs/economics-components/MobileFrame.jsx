// Mobile frame — condensed economics page for phone

const MOBILE_TICKER = window.ECON_DATA.TICKER.slice(0, 5);

function MobileFrame() {
  return (
    <div style={{
      width: 375, height: 780, borderRadius: 36,
      background: "#0F172A", padding: 10,
      boxShadow: "0 30px 60px rgba(0,0,0,0.25), 0 0 0 1px rgba(0,0,0,0.06)",
      flexShrink: 0, position: "sticky", top: 20,
    }}>
      <div style={{
        width: "100%", height: "100%", borderRadius: 28,
        background: "#F5F5F7", overflow: "hidden",
        position: "relative", display: "flex", flexDirection: "column",
      }}>
        {/* Status bar */}
        <div style={{ height: 34, display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 22px", fontSize: 13, fontWeight: 600, color: "#111827", background: "#fff", borderBottom: "1px solid #F3F4F6" }}>
          <span>9:41</span>
          <span style={{ fontFamily: "var(--mono)" }}>●●● 5G</span>
        </div>

        {/* App header */}
        <div style={{ padding: "14px 16px 10px", background: "#fff", borderBottom: "1px solid #F3F4F6" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>📈</span>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#111827" }}>Economics</span>
            <span style={{ marginLeft: "auto", fontSize: 10, color: "#6B7280", fontFamily: "var(--mono)" }}>1,284 markets</span>
          </div>
        </div>

        {/* Scroll content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
          {/* Hero */}
          <h1 style={{ fontSize: 22, fontWeight: 600, color: "#111827", lineHeight: 1.15, letterSpacing: "-0.02em", marginBottom: 14 }}>
            What do markets think about <span style={{ color: "#10B981" }}>the economy</span>?
          </h1>

          {/* Ticker strip */}
          <div style={{ background: "#0F172A", borderRadius: 10, padding: "10px 0", marginBottom: 14, overflow: "hidden", position: "relative" }}>
            <style>{`@keyframes mticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }`}</style>
            <div style={{ display: "flex", gap: 0, animation: "mticker 30s linear infinite", width: "max-content" }}>
              {[...MOBILE_TICKER, ...MOBILE_TICKER].map((it, i) => (
                <div key={i} style={{ display: "flex", gap: 6, padding: "0 12px", borderRight: "1px solid rgba(255,255,255,0.08)", whiteSpace: "nowrap", alignItems: "center" }}>
                  <span style={{ fontSize: 9, color: "#94A3B8", textTransform: "uppercase" }}>{it.q}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, color: "#F8FAFC" }}>{it.val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Key indicators grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
            {[
              { q: "June rate cut", v: 64, col: "#10B981" },
              { q: "Recession '26", v: 23, col: "#94A3B8" },
              { q: "CPI <3%", v: 72, col: "#10B981" },
              { q: "Shutdown", v: 19, col: "#94A3B8" },
            ].map((c, i) => (
              <div key={i} style={{ background: "#fff", borderRadius: 10, border: "1px solid #E5E7EB", padding: 12 }}>
                <div style={{ fontSize: 10, color: "#6B7280", fontWeight: 500 }}>{c.q}</div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 24, fontWeight: 700, color: c.col, marginTop: 4 }}>{c.v}%</div>
              </div>
            ))}
          </div>

          {/* Fed section */}
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#059669", textTransform: "uppercase", marginBottom: 6 }}>Federal Reserve</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#111827", marginBottom: 10 }}>3 cuts is the modal outcome</div>
          <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #E5E7EB", padding: 12, marginBottom: 14 }}>
            {window.ECON_DATA.RATE_CUTS_2026.map((r, i) => {
              const col = probColor(r.prob);
              const max = 31;
              return (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "54px 1fr 32px", alignItems: "center", gap: 6, padding: "4px 0" }}>
                  <span style={{ fontSize: 11, color: "#6B7280" }}>{r.label}</span>
                  <div style={{ height: 6, background: "#F3F4F6", borderRadius: 999, overflow: "hidden" }}>
                    <div style={{ width: `${(r.prob / max) * 100}%`, height: "100%", background: col, borderRadius: 999 }} />
                  </div>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color: col, textAlign: "right" }}>{r.prob}%</span>
                </div>
              );
            })}
          </div>

          {/* CPI section */}
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#059669", textTransform: "uppercase", marginBottom: 6 }}>Inflation</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#111827", marginBottom: 10 }}>May CPI · Tue May 13</div>
          <div style={{ background: "#F0FDF4", borderRadius: 10, border: "1px solid #BBF7D0", padding: 12, marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 26, fontWeight: 700, color: "#10B981" }}>48%</span>
              <span style={{ fontSize: 12, color: "#374151" }}>price 2.5-3.0%</span>
            </div>
            <div style={{ display: "flex", gap: 2, marginTop: 10, height: 34 }}>
              {[22, 48, 22, 6, 2].map((p, i) => {
                const cols = ["#10B981", "#10B981", "#FDE68A", "#FCA5A5", "#F87171"];
                return <div key={i} style={{ flex: 1, background: cols[i], opacity: p === 48 ? 1 : 0.5, borderRadius: 2, alignSelf: "flex-end", height: `${(p / 48) * 100}%` }} />;
              })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 8, color: "#9CA3AF", marginTop: 4 }}>
              <span>&lt;2.5</span><span>2.5-3</span><span>3-3.5</span><span>3.5-4</span><span>&gt;4</span>
            </div>
          </div>

          {/* Recession */}
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#059669", textTransform: "uppercase", marginBottom: 6 }}>Recession</div>
          <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #E5E7EB", padding: 16, marginBottom: 14, textAlign: "center" }}>
            <div style={{ fontSize: 11, color: "#6B7280" }}>Recession by end of 2026</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 56, fontWeight: 700, color: "#22C55E", lineHeight: 1, marginTop: 6 }}>23<span style={{ fontSize: 24, opacity: 0.7 }}>%</span></div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "#22C55E", fontWeight: 600, marginTop: 4 }}>▼ 2pp · down from 34% in Jan</div>
          </div>

          {/* Resolved chip */}
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#6B7280", textTransform: "uppercase", marginBottom: 6 }}>Yesterday resolved</div>
          <div style={{ background: "#F0FDF4", borderRadius: 10, border: "1px solid #BBF7D0", padding: 12, fontSize: 12, marginBottom: 14 }}>
            <div style={{ color: "#374151", marginBottom: 4 }}>Initial jobless claims</div>
            <div style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
              <span style={{ textDecoration: "line-through", color: "#9CA3AF" }}>221k priced</span> → 219k actual ✓
            </div>
          </div>

          <div style={{ textAlign: "center", fontSize: 10, color: "#9CA3AF", padding: "20px 0" }}>
            9 more sections ↓
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MobileFrame });
