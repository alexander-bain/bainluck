// Movies & TV: RT heatmap (with histogram variant), Box Office, Reality TV

// ────────────────────────────────────────────────────────────
// RT HEATMAP — rows × score-threshold cols (Fed-heatmap style)
// ────────────────────────────────────────────────────────────
function RTHeatmap({ data }) {
  const cellColor = (p) => {
    // Probability of "score above this threshold"
    const intensity = Math.min(1, p);
    return `color-mix(in oklab, var(--accent-page) ${Math.round(intensity * 70 + 5)}%, transparent)`;
  };
  return (
    <div className="rt-grid">
      <div className="h title">Movie · Release</div>
      {data.thresholds.map(t => (
        <div key={t} className="h">≥{t}</div>
      ))}
      {data.movies.map((m, i) => (
        <div key={i} className="row">
          <div className="name">
            <Cover art={m.art} title={m.title} size={32} />
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.title}</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{m.releaseDate} · {m.volume}</span>
            </div>
          </div>
          {m.dist.map((p, j) => (
            <div key={j} className="cell" style={{
              background: cellColor(p),
              color: p > 0.5 ? 'var(--text-primary)' : 'var(--text-secondary)',
            }} title={`${m.title} ≥${data.thresholds[j]}: ${Math.round(p*100)}%`}>
              {Math.round(p*100)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// Variant: per-movie histograms
function RTHistograms({ data }) {
  return (
    <div className="grid-3">
      {data.movies.map((m, i) => {
        const thresholds = data.thresholds;
        // P(in bucket) ≈ p[i] - p[i+1]
        const buckets = thresholds.map((t, j) => {
          const upper = j === thresholds.length - 1 ? 0.02 : m.dist[j+1];
          return { range: j === thresholds.length - 1 ? `≥${t}` : `${t}–${thresholds[j+1]}`, prob: Math.max(0, m.dist[j] - upper) };
        });
        // Normalize-ish: also include 'fail' bucket
        const bucketsFinal = [{ range: '<55', prob: 1 - m.dist[0] }, ...buckets];
        return (
          <div key={i} className="bl-card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
              <Cover art={m.art} title={m.title} size={48} big />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{m.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{m.releaseDate}</div>
              </div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>RT score distribution</div>
            <Histogram data={bucketsFinal} />
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--surface-border)' }}>
              <MetaRow source={m.source} volume={m.volume} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// BOX OFFICE
// ────────────────────────────────────────────────────────────
function BoxOffice({ data }) {
  return (
    <div className="bl-card" style={{ padding: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Weekend box office</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{data.weekend} · domestic gross</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {data.rows.map((r, i) => (
          <div key={i}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <Cover art={r.art} title={r.title} size={40} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{r.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Most likely: <b style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{r.leader}</b></div>
              </div>
              <SourceChip source={r.source} />
            </div>
            <Histogram data={r.breakdown} height={56} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// REALITY TV — outcome cards
// ────────────────────────────────────────────────────────────
function RealityTV({ data }) {
  return (
    <div className="grid-3">
      {data.map((r, i) => (
        <div key={i} className="bl-card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
            <Cover art={r.art} title={r.show} size={44} big />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{r.season}</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{r.show}</div>
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10 }}>{r.question}</div>
          {r.legA && r.legB ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 6 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600 }}>{r.legA.label}</div>
                  <Pct v={r.legA.prob} size={20} />
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, fontWeight: 600 }}>{r.legB.label}</div>
                  <Pct v={r.legB.prob} size={20} />
                </div>
              </div>
              <div style={{ display: 'flex', height: 6, gap: 1.5, borderRadius: 9999, overflow: 'hidden' }}>
                <span style={{ width: `${r.legA.prob*100}%`, background: r.legA.prob >= r.legB.prob ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 40%, transparent)', borderRadius: 9999 }} />
                <span style={{ width: `${r.legB.prob*100}%`, background: r.legB.prob >= r.legA.prob ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 40%, transparent)', borderRadius: 9999 }} />
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {r.outcomes.map((o, j) => (
                <div key={j} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{o.label}</div>
                    <ProbBar value={o.prob} height={4} />
                  </div>
                  <Pct v={o.prob} size={13} />
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--surface-border)' }}>
            <MetaRow source={r.source} volume={r.volume} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// MOVIES & TV SECTION
// ────────────────────────────────────────────────────────────
function MoviesTVSection({ rtVariant = 'heatmap' }) {
  const [tab, setTab] = React.useState('rt');
  const D = window.ENT_DATA;
  return (
    <section className="section">
      <SectionHead
        eyebrow="Movies & TV"
        title="Critic scores, box office, and reality outcomes"
        sub="Rotten Tomatoes thresholds, weekend gross brackets, and active reality competitions"
        right={<Tabs value={tab} onChange={setTab} options={[
          { value: 'rt', label: 'Rotten Tomatoes' },
          { value: 'box', label: 'Box office' },
          { value: 'reality', label: 'Reality TV' },
        ]} />}
      />
      {tab === 'rt' && (rtVariant === 'histogram' ? <RTHistograms data={D.RT_GRID} /> : <RTHeatmap data={D.RT_GRID} />)}
      {tab === 'box' && <BoxOffice data={D.BOX_OFFICE} />}
      {tab === 'reality' && <RealityTV data={D.REALITY} />}
    </section>
  );
}

Object.assign(window, { MoviesTVSection, RTHeatmap, RTHistograms, BoxOffice, RealityTV });
