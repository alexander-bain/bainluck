// Shared atoms used across the entertainment page.

function SourceChip({ source }) {
  const label = source === 'kalshi' ? 'Kalshi' : source === 'polymarket' ? 'Polymarket' : source;
  return (
    <span className={`src-chip ${source}`}>
      <span className="dot" />{label}
    </span>
  );
}

function Cover({ art, title, size = 44, big = false, className = '' }) {
  const [base, tone] = art || ['#1F2937', '#475569'];
  // First word, max 2 letters of two words
  const words = (title || '').split(/\s+/).slice(0, 2);
  const initials = words.length === 2
    ? words.map(w => w[0]).join('')
    : (title || '').slice(0, 6);
  return (
    <div
      className={`cover ${big ? 'lg' : ''} ${className}`}
      style={{
        '--art-base': base, '--art-tone': tone,
        width: size, height: size,
      }}
      aria-hidden="true"
    >{initials.toUpperCase()}</div>
  );
}

function ProbBar({ value, height = 6, color, track = 'var(--surface-elevated)' }) {
  const c = color || 'var(--accent-page)';
  return (
    <div className="prob-bar" style={{ height, background: track, borderRadius: 9999 }}>
      <span style={{ width: `${value * 100}%`, background: c }} />
    </div>
  );
}

function YesNoBar({ yes, no }) {
  return (
    <div className="yn-bar">
      <span className="yes" style={{ width: `${yes * 100}%` }}>YES {Math.round(yes*100)}%</span>
      <span className="no" style={{ width: `${no * 100}%` }}>NO {Math.round(no*100)}%</span>
    </div>
  );
}

function Delta({ value, suffix = '%' }) {
  if (!value || Math.abs(value) < 0.001) return <span className="delta" style={{ color: 'var(--text-muted)' }}>—</span>;
  const up = value > 0;
  return <span className={`delta ${up ? 'up' : 'down'}`}>{up ? '↑' : '↓'} {Math.abs(value*100).toFixed(1)}{suffix}</span>;
}

function Pct({ v, size = 14, weight = 700 }) {
  return <span className="prob-hero" style={{ fontSize: size, fontWeight: weight, letterSpacing: size > 24 ? '-0.02em' : '-0.01em' }}>
    {Math.round(v*100)}<span style={{ fontSize: size * 0.65, opacity: 0.7 }}>%</span>
  </span>;
}

// Histogram with optional peak highlight + axis labels
function Histogram({ data, format = (d) => d.range, peak = true, height = 88 }) {
  const maxV = Math.max(...data.map(d => d.prob));
  return (
    <div>
      <div className="hist" style={{ height }}>
        {data.map((d, i) => (
          <div
            key={i}
            className={`bar${peak && d.prob === maxV ? ' peak' : ''}`}
            style={{ height: `${(d.prob / maxV) * 100}%` }}
            title={`${format(d)} · ${Math.round(d.prob*100)}%`}
          >
            <span className="v">{Math.round(d.prob*100)}</span>
          </div>
        ))}
      </div>
      <div className="hist-row">
        {data.map((d, i) => <span key={i} className="lbl">{format(d)}</span>)}
      </div>
    </div>
  );
}

// Tag chip with category emoji
function TagChip({ emoji, label, color }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, fontWeight: 600,
      letterSpacing: '0.04em', textTransform: 'uppercase',
      color: color || 'var(--text-muted)',
      padding: '2px 7px', borderRadius: 4,
      background: 'var(--surface-elevated)',
    }}>
      {emoji && <span style={{ fontSize: 11 }}>{emoji}</span>}
      {label}
    </span>
  );
}

function MetaRow({ source, volume, resolves }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
      <SourceChip source={source} />
      {volume && <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>Vol {volume}</span>}
      {resolves && <span>· Resolves {resolves}</span>}
    </div>
  );
}

function SectionHead({ eyebrow, title, sub, right }) {
  return (
    <div className="section-head">
      <div>
        {eyebrow && <div className="eyebrow" style={{ marginBottom: 4 }}>{eyebrow}</div>}
        <h2>{title}</h2>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {right && <div className="meta">{right}</div>}
    </div>
  );
}

function Tabs({ value, onChange, options }) {
  return (
    <div className="section-tabs" role="tablist">
      {options.map(o => (
        <button key={o.value} className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

Object.assign(window, { SourceChip, Cover, ProbBar, YesNoBar, Delta, Pct, Histogram, TagChip, MetaRow, SectionHead, Tabs });
