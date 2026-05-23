// Trending Now hero — three variant layouts
// variant: 'editorial' (lead + 4 stack) | 'guide' (4-col equal grid) | 'ticker' (marquee + 3 cards)

function HeroCard({ item, variant = 'editorial', lead = false }) {
  const isLead = lead;
  return (
    <div className={`bl-card hero-card ${lead ? 'lead' : ''}`} style={{
      padding: lead ? 18 : 14,
      display: 'flex', flexDirection: 'column', gap: 10,
      minHeight: lead ? 280 : 0,
      cursor: 'pointer',
    }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <Cover art={item.art} title={item.headline} size={lead ? 72 : 44} big={lead} className="hero-art" />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4, flexWrap: 'wrap' }}>
            <TagChip emoji={kindEmoji(item.kind)} label={kindLabel(item.kind)} />
            {item.live && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--accent-live)', fontSize: 10, fontWeight: 700, letterSpacing: '0.06em' }}><span className="live-dot" />LIVE</span>}
          </div>
          <div style={{ fontSize: lead ? 18 : 14, fontWeight: 600, lineHeight: 1.25, letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>
            {item.headline}
          </div>
          {item.lede && <div style={{ fontSize: lead ? 13 : 12, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.4 }}>{item.lede}</div>}
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {item.kind === 'spotify-1' && <HeroSpotify item={item} lead={lead} />}
      {item.kind === 'rt' && <HeroRT item={item} lead={lead} />}
      {item.kind === 'reality' && <HeroBinary legA={item.legA} legB={item.legB} lead={lead} />}
      {item.kind === 'multi' && <HeroMulti outcomes={item.outcomes} lead={lead} />}
      {item.kind === 'eurovision' && <HeroMulti outcomes={item.outcomes} lead={lead} flags />}

      <MetaRow source={item.source} volume={item.volume} resolves={item.resolves} />
    </div>
  );
}

function HeroSpotify({ item, lead }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600 }}>{item.leader.name} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>· {item.leader.artist}</span></div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
          <Pct v={item.leader.prob} size={lead ? 28 : 20} />
          <Delta value={item.leader.delta} />
        </div>
      </div>
      <ProbBar value={item.leader.prob} height={lead ? 8 : 6} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 8 }}>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{item.runnerUp.name} <span style={{ color: 'var(--text-muted)' }}>· {item.runnerUp.artist}</span></div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
          <Pct v={item.runnerUp.prob} size={13} />
          <Delta value={item.runnerUp.delta} />
        </div>
      </div>
    </div>
  );
}

function HeroRT({ item, lead }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>P({item.threshold})</div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
          <Pct v={item.prob} size={lead ? 28 : 20} />
          <Delta value={item.delta} />
        </div>
      </div>
      {/* Mini distribution */}
      <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 32, marginTop: 4 }}>
        {item.distribution.map((p, i) => (
          <div key={i} style={{
            flex: 1, height: `${p * 100}%`,
            background: i === item.distribution.length - 2 ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 25%, transparent)',
            borderRadius: '3px 3px 0 0',
          }} />
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        <span>55</span><span>60</span><span>65</span><span>70</span><span>75</span><span>80</span>
      </div>
    </div>
  );
}

function HeroBinary({ legA, legB, lead }) {
  const aLead = legA.prob >= legB.prob;
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 6 }}>
        <div>
          <div style={{ fontSize: 11, color: aLead ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>{legA.label}</div>
          <Pct v={legA.prob} size={lead ? 24 : 18} />
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 11, color: !aLead ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>{legB.label}</div>
          <Pct v={legB.prob} size={lead ? 24 : 18} />
        </div>
      </div>
      <div style={{ display: 'flex', height: 6, gap: 1.5, borderRadius: 9999, overflow: 'hidden' }}>
        <span style={{ width: `${legA.prob*100}%`, background: aLead ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 40%, transparent)', borderRadius: 9999 }} />
        <span style={{ width: `${legB.prob*100}%`, background: !aLead ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 40%, transparent)', borderRadius: 9999 }} />
      </div>
    </div>
  );
}

function HeroMulti({ outcomes, lead, flags = false }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {outcomes.slice(0, lead ? 5 : 3).map((o, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', minWidth: 0 }}>
            {flags && o.flag && <span style={{ marginRight: 6 }}>{o.flag}</span>}
            {o.label}
          </span>
          <ProbBar value={o.prob} height={4} />
          <Pct v={o.prob} size={12} />
        </div>
      ))}
    </div>
  );
}

function kindEmoji(k) {
  return { 'spotify-1': '🎧', 'rt': '🎬', 'reality': '📺', 'multi': '🌐', 'eurovision': '🎤' }[k] || '✦';
}
function kindLabel(k) {
  return { 'spotify-1': 'Spotify', 'rt': 'Rotten Tomatoes', 'reality': 'Reality TV', 'multi': 'Internet', 'eurovision': 'Eurovision' }[k] || 'Market';
}

// ─────────────────────────────────────────────
// Variant 1: editorial — lead card + 4 stacked
// ─────────────────────────────────────────────
function HeroEditorial({ items }) {
  return (
    <div className="hero-grid">
      <HeroCard item={items[0]} lead variant="editorial" />
      {items.slice(1, 5).map(it => <HeroCard key={it.id} item={it} variant="editorial" />)}
    </div>
  );
}

// ─────────────────────────────────────────────
// Variant 2: guide — 4 equal cards (TV guide)
// ─────────────────────────────────────────────
function HeroGuide({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
      {items.slice(0, 4).map(it => <HeroCard key={it.id} item={it} variant="guide" />)}
    </div>
  );
}

// ─────────────────────────────────────────────
// Variant 3: ticker — marquee + 3 cards
// ─────────────────────────────────────────────
function HeroTicker({ items }) {
  const tickerItems = items.flatMap(it => [
    { label: kindLabel(it.kind), text: it.headline, prob: it.prob || it.leader?.prob || it.legB?.prob || it.outcomes?.[0]?.prob || 0.5 },
  ]);
  // Duplicate for seamless loop
  const looped = [...tickerItems, ...tickerItems];
  return (
    <div>
      <div style={{ background: 'var(--surface-card)', border: '1px solid var(--surface-border)', borderRadius: 10, marginBottom: 12 }}>
        <div className="marquee">
          <div className="marquee-track">
            {looped.map((t, i) => (
              <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--accent-page)', textTransform: 'uppercase' }}>{t.label}</span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{t.text}</span>
                <span className="prob-hero" style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{Math.round(t.prob*100)}%</span>
                <span style={{ color: 'var(--text-muted)' }}>·</span>
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="grid-3">
        {items.slice(0, 3).map(it => <HeroCard key={it.id} item={it} variant="ticker" />)}
      </div>
    </div>
  );
}

function Hero({ items, variant }) {
  if (variant === 'guide') return <HeroGuide items={items} />;
  if (variant === 'ticker') return <HeroTicker items={items} />;
  return <HeroEditorial items={items} />;
}

Object.assign(window, { Hero, HeroEditorial, HeroGuide, HeroTicker, HeroCard });
