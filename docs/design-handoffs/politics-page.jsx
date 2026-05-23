// Politics page — three hero variants and the shared body sections.
// Each variant is a full self-contained page section that can sit inside a DCArtboard.

const COLUMN_MAX = 1180;

// ── Shared section rendered after every hero ──
function PoliticsBody() {
  const D = window.POLITICS_DATA;
  const [storyTab, setStoryTab] = React.useState('All');
  const [worldTab, setWorldTab] = React.useState('All');

  const tabs = ['All', 'Congress', 'Courts', 'Campaign', 'World', 'Tech', 'Money'];
  const filtered = storyTab === 'All' ? D.STORIES : D.STORIES.filter(s =>
    (s.tags || []).some(t => t.toLowerCase() === storyTab.toLowerCase()) || s.kicker === storyTab
  );

  return (
    <>
      {/* ── Top stories ─────────────────────────────────────── */}
      <SectionTitle action="See all">Top stories</SectionTitle>
      <FilterTabs tabs={tabs} active={storyTab} onChange={setStoryTab} />
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', gap: 12,
      }}>
        {(filtered.length ? filtered : D.STORIES).slice(0, 6).map(s => (
          <LeadStory key={s.id} story={s} size="md" />
        ))}
      </div>

      {/* ── Congress + Polls split ─────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 24, marginTop: 8 }}>
        <div>
          <SectionTitle count={D.BILLS.length} action="Tracker">Congress · bills moving</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))', gap: 12 }}>
            {D.BILLS.map(b => <BillRow key={b.id} bill={b} />)}
          </div>
        </div>
        <div>
          <SectionTitle count={D.POLLS.length} action="More">Polls</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {D.POLLS.map(p => <PollCard key={p.id} poll={p} />)}
          </div>
        </div>
      </div>

      {/* ── Op-Eds ────────────────────────────────────────── */}
      <SectionTitle count={D.OPEDS.length} action="Opinion">Opinion</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))', gap: 12 }}>
        {D.OPEDS.map(o => <OpEdCard key={o.id} op={o} />)}
      </div>

      {/* ── World + Most read ─────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 24, marginTop: 8 }}>
        <div>
          <SectionTitle count={D.WORLD.length} action="World tracker">World politics</SectionTitle>
          <Card style={{ padding: '4px 16px' }}>
            {D.WORLD.map(w => <WorldRow key={w.id} row={w} />)}
          </Card>
        </div>
        <div>
          <SectionTitle action="Top 50">Most read</SectionTitle>
          <Card style={{ padding: '4px 16px' }}>
            {D.MOST_READ.map((title, i) => (
              <div key={i} style={{
                display: 'flex', gap: 14, padding: '12px 0',
                borderBottom: i < D.MOST_READ.length - 1 ? '1px solid var(--surface-border)' : 'none',
                cursor: 'pointer',
              }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 22,
                  color: 'var(--text-muted)', letterSpacing: '-0.02em', minWidth: 24,
                }}>{i + 1}</span>
                <h4 style={{ margin: 0, fontSize: 13.5, fontWeight: 500, lineHeight: 1.35, letterSpacing: '-0.005em' }}>
                  {title}
                </h4>
              </div>
            ))}
          </Card>
        </div>
      </div>

      {/* ── Audio + Newsletter ────────────────────────────── */}
      <SectionTitle count={D.AUDIO.length} action="All shows">Listen &amp; watch</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))', gap: 12 }}>
        {D.AUDIO.map(a => (
          <Card key={a.id} style={{ padding: 14, display: 'flex', alignItems: 'center', gap: 12 }} onClick={() => {}}>
            <div style={{
              width: 44, height: 44, borderRadius: 8, flexShrink: 0,
              background: a.kind === 'pod' ? 'var(--accent-futures)' : 'var(--accent-brand)',
              color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {a.kind === 'pod' ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
              )}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 700 }}>
                {a.show}
              </div>
              <h5 style={{ margin: '2px 0 4px', fontSize: 13, fontWeight: 500, lineHeight: 1.3 }}>
                {a.title}
              </h5>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{a.length} · {a.released}</div>
            </div>
          </Card>
        ))}
      </div>

      <div style={{ marginTop: 28 }}>
        <NewsletterStrip />
      </div>

      <div style={{ height: 60 }} />
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Variant A — RACE TRACKER hero
//   Three large race cards (Presidency / Senate / House) front and center.
//   The "data-forward / 538" interpretation: scoreboard on top.
// ─────────────────────────────────────────────────────────────────────
function PoliticsHeroA() {
  const D = window.POLITICS_DATA;
  return (
    <>
      <PageTitle />
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginTop: 18,
      }}>
        <RaceCard race={D.RACES.presidency} size="lg" />
        <RaceCard race={D.RACES.senate}     size="lg" />
        <RaceCard race={D.RACES.house}      size="lg" />
      </div>
      <div style={{ marginTop: 12 }}>
        <LiveTicker items={D.TICKER} />
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Variant B — EDITORIAL SPLIT hero
//   Big lead story + two flanking probability/race modules.
//   Magazine-y; numbers in service of the story.
// ─────────────────────────────────────────────────────────────────────
function PoliticsHeroB() {
  const D = window.POLITICS_DATA;
  return (
    <>
      <PageTitle />
      <div style={{
        display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 16, marginTop: 18,
      }}>
        <LeadStory story={D.STORIES[0]} size="lg" />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <MiniRace race={D.RACES.presidency} />
          <MiniRace race={D.RACES.senate} />
          <MiniRace race={D.RACES.house} />
        </div>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12,
      }}>
        <LeadStory story={D.STORIES[1]} size="md" />
        <LeadStory story={D.STORIES[3]} size="md" />
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Variant C — LIVE NIGHT hero
//   Dark live ticker on top, single dominant race chart, leaderboard rail.
//   Election-night feel.
// ─────────────────────────────────────────────────────────────────────
function PoliticsHeroC() {
  const D = window.POLITICS_DATA;
  const [range, setRange] = React.useState('Full');
  const ranges = ['24h', '7d', '30d', 'Full'];

  // Build SVG path for the presidency series
  const series = D.PRESIDENCY_HISTORY.series;
  const W = 760, H = 220, padL = 38, padR = 14, padT = 14, padB = 22;
  const w = W - padL - padR, h = H - padT - padB;
  const min = 0.30, max = 0.70;
  const yScale = v => padT + h - ((v - min) / (max - min)) * h;
  const xScale = (i, n) => padL + (i / (n - 1)) * w;
  const buildPath = vals => {
    const n = vals.length; let d = `M ${xScale(0,n)},${yScale(vals[0])}`;
    for (let i = 1; i < n; i++) {
      const x0 = xScale(i-1,n), x1 = xScale(i,n);
      const y0 = yScale(vals[i-1]), y1 = yScale(vals[i]);
      const cx = (x0+x1)/2;
      d += ` C ${cx},${y0} ${cx},${y1} ${x1},${y1}`;
    }
    return d;
  };

  return (
    <>
      <PageTitle />
      <div style={{ marginTop: 18 }}>
        <LiveTicker items={D.TICKER} />
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16, marginTop: 12,
      }}>
        {/* Big race chart */}
        <Card topBorder={POLITICS_BLUE} style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.02em', textTransform: 'uppercase', fontWeight: 600 }}>
              🏛 Headline race
            </span>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em' }}>
              {D.RACES.presidency.title}
            </h3>
            <div style={{ marginLeft: 'auto', display: 'inline-flex', background: 'var(--surface-elevated)', borderRadius: 8, padding: 2 }}>
              {ranges.map(r => (
                <button key={r} onClick={() => setRange(r)} style={{
                  background: range === r ? 'var(--surface-card)' : 'transparent',
                  border: 'none', padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500,
                  color: range === r ? 'var(--text-primary)' : 'var(--text-secondary)',
                  cursor: 'pointer', boxShadow: range === r ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                  fontFamily: 'inherit',
                }}>{r}</button>
              ))}
            </div>
          </div>

          {/* Current standings */}
          <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
            {D.RACES.presidency.outcomes.slice(0, 2).map(o => (
              <div key={o.short} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{
                  width: 10, height: 10, borderRadius: 2, background: o.color,
                }} />
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{o.name}</span>
                <Prob value={o.prob} size="lg" />
                <Movement value={o.change} />
              </div>
            ))}
          </div>

          {/* Chart */}
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H, display: 'block' }}>
            {[0.35, 0.45, 0.50, 0.55, 0.65].map(v => (
              <line key={v} x1={padL} y1={yScale(v)} x2={W - padR} y2={yScale(v)}
                stroke={v === 0.50 ? '#D1D5DB' : '#EEF0F3'}
                strokeWidth={v === 0.50 ? 1 : 1}
                strokeDasharray={v === 0.50 ? '4 4' : undefined} />
            ))}
            {[0.35, 0.45, 0.55, 0.65].map(v => (
              <text key={v} x={padL - 6} y={yScale(v) + 3} textAnchor="end"
                fontSize="10" fill="#9CA3AF" fontFamily="JetBrains Mono, monospace">
                {(v*100).toFixed(0)}%
              </text>
            ))}
            <text x={W - padR} y={yScale(0.50) - 4} textAnchor="end" fontSize="9" fill="#9CA3AF" fontFamily="Inter, sans-serif">
              50% line
            </text>
            {D.PRESIDENCY_HISTORY.xLabels.map((label, i) => (
              <text key={i}
                x={padL + (i / (D.PRESIDENCY_HISTORY.xLabels.length - 1)) * w}
                y={H - 6}
                textAnchor={i === 0 ? 'start' : i === D.PRESIDENCY_HISTORY.xLabels.length - 1 ? 'end' : 'middle'}
                fontSize="10" fill="#9CA3AF">
                {label}
              </text>
            ))}
            {series.map(s => (
              <path key={s.id} d={buildPath(s.values)} fill="none"
                stroke={s.color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            ))}
          </svg>
        </Card>

        {/* Leaderboard rail (Dem nominee) */}
        <Card topBorder={POLITICS_BLUE} style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{D.DEM_NOMINEE.title}</h3>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
              {D.DEM_NOMINEE.sources} src
            </span>
          </div>
          {D.DEM_NOMINEE.outcomes.map((o, i) => {
            const isLeader = i === 0;
            return (
              <div key={o.name} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 0', borderBottom: i < D.DEM_NOMINEE.outcomes.length - 1 ? '1px solid var(--surface-border)' : 'none',
              }}>
                <span style={{
                  width: 18, fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 600,
                  color: 'var(--text-muted)', textAlign: 'right',
                }}>{i + 1}</span>
                <span style={{
                  flex: 1, fontSize: 12.5, fontWeight: isLeader ? 500 : 400,
                  color: isLeader ? 'var(--text-primary)' : 'var(--text-secondary)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>{o.name}</span>
                <Movement value={o.change} size={10} />
                <span style={{
                  fontFamily: 'var(--font-mono)', fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums', fontSize: 13,
                  color: isLeader ? 'var(--text-primary)' : 'var(--text-muted)',
                  minWidth: 36, textAlign: 'right',
                }}>{(o.prob * 100).toFixed(0)}%</span>
              </div>
            );
          })}
        </Card>
      </div>

      {/* Three small races below */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginTop: 12 }}>
        <MiniRace race={D.RACES.presidency} />
        <MiniRace race={D.RACES.senate} />
        <MiniRace race={D.RACES.house} />
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Page wrapper — header + container + body
// ─────────────────────────────────────────────────────────────────────
function PoliticsPage({ hero, density = 'regular', dark = false, font = 'sans', accent }) {
  const Hero = { A: PoliticsHeroA, B: PoliticsHeroB, C: PoliticsHeroC }[hero] || PoliticsHeroA;

  // Density adjusts container padding via inline style
  const pad = density === 'compact' ? '12px 16px 60px' : density === 'comfy' ? '32px 28px 80px' : '20px 20px 60px';

  // Light/dark — flip surface tokens
  const themeStyle = dark ? {
    '--surface-deep': '#0F141B',
    '--surface-card': '#1A2230',
    '--surface-elevated': '#222C3C',
    '--surface-border': '#2A3447',
    '--text-primary': '#F1F5F9',
    '--text-secondary': '#94A3B8',
    '--text-muted': '#64748B',
  } : {};

  // Font swap
  const fontStyle = font === 'serif' ? {
    '--font-sans': "'Source Serif 4', Georgia, serif",
  } : font === 'mixed' ? {
    '--font-sans': "'Inter', system-ui, sans-serif",
  } : {};

  // Accent recolor
  const accentStyle = accent ? { '--accent-brand': accent } : {};

  return (
    <div data-screen-label="Politics Page" style={{
      ...themeStyle, ...fontStyle, ...accentStyle,
      background: 'var(--surface-deep)', color: 'var(--text-primary)',
      minHeight: 800, fontFamily: 'var(--font-sans)',
    }}>
      <Header density={density} />
      <main style={{ maxWidth: COLUMN_MAX, margin: '0 auto', padding: pad }}>
        <Hero />
        <PoliticsBody />
      </main>
    </div>
  );
}

Object.assign(window, {
  PoliticsBody, PoliticsHeroA, PoliticsHeroB, PoliticsHeroC, PoliticsPage,
});
