// Atoms: shared UI components for economics page

const { probColor, probLabel, deltaColor, SOURCES, sparkFrom } = window.ECON_DATA;

function SectionHeader({ kicker, title, meta, count, right }) {
  return (
    <div style={{ marginBottom: 18, display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "#059669" }}>
          {kicker}
        </span>
        <h2 style={{ fontSize: 28, fontWeight: 600, color: "#111827", lineHeight: 1.2, marginTop: 4, letterSpacing: "-0.01em" }}>
          {title}
        </h2>
        {meta && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "#9CA3AF", marginTop: 6 }}>
            {meta}
          </div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {count != null && (
          <span style={{ fontSize: 11, fontWeight: 600, color: "#6B7280", background: "#F3F4F6", padding: "4px 10px", borderRadius: 999 }}>
            {count} active
          </span>
        )}
        {right}
      </div>
    </div>
  );
}

function Card({ children, pad = 22, radius = 16, style = {}, ...rest }) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #E5E7EB",
        borderRadius: radius,
        padding: pad,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

function SourceChip({ src, merged }) {
  const s = SOURCES[src] || SOURCES.kalshi;
  if (merged || src === "cross") {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        background: `linear-gradient(90deg, ${SOURCES.kalshi.bg} 50%, ${SOURCES.polymarket.bg} 50%)`,
        border: "1px solid #E5E7EB", borderRadius: 999,
        fontSize: 10, fontWeight: 600, letterSpacing: "0.04em",
        padding: "3px 8px", color: "#374151",
      }}>
        <span style={{ width: 5, height: 5, borderRadius: "50%", background: SOURCES.kalshi.color }} />
        <span style={{ width: 5, height: 5, borderRadius: "50%", background: SOURCES.polymarket.color }} />
        CROSS-SOURCE
      </span>
    );
  }
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: s.bg, color: s.fg,
      fontSize: 11, fontWeight: 500, padding: "3px 8px", borderRadius: 999,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: s.color }} />
      {s.label}
    </span>
  );
}

function CrossSourceReveal({ k, p, parentProb }) {
  // k = kalshi %, p = polymarket %, parentProb = merged %
  const [open, setOpen] = React.useState(false);
  return (
    <span
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
      style={{ position: "relative", cursor: "pointer" }}
    >
      <SourceChip merged />
      {open && (
        <span style={{
          position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 40,
          background: "#111827", color: "#F9FAFB",
          fontSize: 11, fontFamily: "var(--mono)", padding: "6px 10px",
          borderRadius: 8, whiteSpace: "nowrap",
          boxShadow: "0 8px 24px rgba(0,0,0,0.2)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: SOURCES.kalshi.color, display: "inline-block" }} />
            Kalshi {k}%
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: SOURCES.polymarket.color, display: "inline-block" }} />
            Polymarket {p}%
          </div>
        </span>
      )}
    </span>
  );
}

function ProbNum({ value, size = 36, color, suffix = "%" }) {
  const c = color || probColor(value);
  const pctSize = size * 0.42;
  return (
    <span style={{
      fontFamily: "var(--mono)", fontSize: size, fontWeight: 600,
      letterSpacing: "-0.02em", color: c, lineHeight: 1,
    }}>
      {typeof value === "number" ? Math.round(value) : value}
      {suffix && <span style={{ fontSize: pctSize, opacity: 0.7 }}>{suffix}</span>}
    </span>
  );
}

function ProbBar({ value, max = 100, color, height = 6, bgOpacity = 0.12 }) {
  const c = color || probColor(value);
  const w = Math.max(1, (value / max) * 100);
  return (
    <div style={{
      flex: 1, height, background: "#F3F4F6",
      borderRadius: 999, overflow: "hidden",
    }}>
      <div style={{
        width: `${w}%`, height: "100%", background: c,
        borderRadius: 999, transition: "width 0.6s ease-out",
      }} />
    </div>
  );
}

function Delta({ v, unit = "pp" }) {
  if (v === 0 || v == null) return <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "#9CA3AF" }}>—</span>;
  const col = deltaColor(v);
  const arrow = v > 0 ? "▲" : "▼";
  return (
    <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, fontWeight: 600, color: col }}>
      {arrow} {Math.abs(v)}{unit}
    </span>
  );
}

function Sparkline({ data, color = "#10B981", width = 80, height = 24 }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 2;
  const pw = width - pad * 2;
  const ph = height - pad * 2;
  const pts = data.map((v, i) => ({
    x: pad + (i / (data.length - 1)) * pw,
    y: pad + ph - ((v - min) / range) * ph,
  }));
  const parts = [`M${pts[0].x},${pts[0].y}`];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    parts.push(`C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`);
  }
  const line = parts.join(" ");
  const last = pts[pts.length - 1];
  const area = `${line} L${last.x},${height} L${pts[0].x},${height} Z`;
  const gid = "spark-" + Math.random().toString(36).slice(2);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.2} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last.x} cy={last.y} r={2} fill={color} />
    </svg>
  );
}

function ResolvedBadge({ actual, expected, correct }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "3px 8px", borderRadius: 999,
      background: correct ? "#F0FDF4" : "#FEF2F2",
      border: `1px solid ${correct ? "#BBF7D0" : "#FECACA"}`,
      color: correct ? "#15803D" : "#B91C1C",
      fontSize: 10.5, fontWeight: 600, letterSpacing: "0.04em",
    }}>
      <span style={{ textTransform: "uppercase" }}>Resolved</span>
      {expected && (
        <span style={{ fontFamily: "var(--mono)", color: "#6B7280", fontWeight: 500 }}>
          <span style={{ textDecoration: "line-through" }}>{expected}</span> → {actual}
        </span>
      )}
    </span>
  );
}

function Histogram({ buckets, color, peakLabel = true, height = 90 }) {
  const max = Math.max(...buckets.map((b) => b[0]));
  const peak = buckets.reduce((best, b, i) => (b[0] > buckets[best][0] ? i : best), 0);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height }}>
        {buckets.map((b, i) => {
          const h = max > 0 ? (b[0] / max) * 100 : 0;
          const isPeak = i === peak;
          return (
            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%", position: "relative" }}>
              {peakLabel && isPeak && (
                <span style={{ fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600, color: "#374151", marginBottom: 3 }}>
                  {b[0]}%
                </span>
              )}
              <div style={{
                width: "100%",
                height: `${h}%`,
                minHeight: b[0] > 0 ? 3 : 0,
                background: color,
                opacity: isPeak ? 1 : 0.3 + (b[0] / max) * 0.5,
                borderRadius: "3px 3px 0 0",
                transition: "height 500ms ease",
              }} />
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
        {buckets.map((b, i) => (
          <div key={i} style={{ flex: 1, textAlign: "center", fontFamily: "var(--mono)", fontSize: 9, color: "#9CA3AF" }}>
            {b[1]}
          </div>
        ))}
      </div>
    </div>
  );
}

function MarketRow({ q, prob, src, delta, resolved, actual, expected, correct, compact }) {
  const col = probColor(prob);
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 110px 60px 36px",
      alignItems: "center", gap: 12,
      padding: "10px 0",
      borderTop: compact ? "1px solid #F3F4F6" : "1px solid #F3F4F6",
    }}>
      <div style={{ fontSize: 13, color: resolved ? "#9CA3AF" : "#374151", lineHeight: 1.35 }}>
        <span style={{ textDecoration: resolved ? "line-through" : "none" }}>{q}</span>
        {resolved && (
          <span style={{ marginLeft: 8 }}>
            <ResolvedBadge actual={actual} expected={expected} correct={correct} />
          </span>
        )}
      </div>
      <ProbBar value={prob} color={col} height={5} />
      <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, color: col, textAlign: "right" }}>
        {prob}%
      </span>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <SourceChip src={src} />
      </div>
    </div>
  );
}

function FooterNote({ left, right }) {
  return (
    <div style={{
      marginTop: 14, paddingTop: 10,
      borderTop: "1px dashed #E5E7EB",
      display: "flex", justifyContent: "space-between", alignItems: "center",
      fontSize: 11, color: "#9CA3AF",
    }}>
      <span>{left}</span>
      {right && <span style={{ fontFamily: "var(--mono)" }}>{right}</span>}
    </div>
  );
}

Object.assign(window, {
  SectionHeader, Card, SourceChip, CrossSourceReveal, ProbNum, ProbBar,
  Delta, Sparkline, ResolvedBadge, Histogram, MarketRow, FooterNote,
});
