// Cultural Moments — masonry-style feed for one-off markets
function CulturalCard({ item }) {
  const isMulti = !!item.outcomes;
  return (
    <div className="bl-card" style={{ padding: 16, breakInside: 'avoid', marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <TagChip emoji={item.tagEmoji} label={item.tag} />
        <div style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)' }}>Resolves {item.resolves}</div>
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.3, letterSpacing: '-0.01em', marginBottom: 4 }}>
        {item.headline}
      </div>
      {item.detail && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.45 }}>{item.detail}</div>}
      {isMulti ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {item.outcomes.map((o, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', minWidth: 0 }}>
                {o.flag && <span style={{ marginRight: 6 }}>{o.flag}</span>}
                {o.label}
              </span>
              <ProbBar value={o.prob} height={4} />
              <Pct v={o.prob} size={12} />
            </div>
          ))}
        </div>
      ) : (
        <YesNoBar yes={item.yesNo.yes} no={item.yesNo.no} />
      )}
      <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--surface-border)' }}>
        <MetaRow source={item.source} volume={item.volume} />
      </div>
    </div>
  );
}

function CulturalMomentsSection() {
  const D = window.ENT_DATA;
  return (
    <section className="section">
      <SectionHead
        eyebrow="Cultural moments"
        title="Pop culture prediction feed"
        sub="One-off markets around live events, celebrity drama, and headline-watching"
      />
      <div style={{ columnCount: 3, columnGap: 12 }} className="cultural-feed">
        {D.CULTURAL.map(item => <CulturalCard key={item.id} item={item} />)}
      </div>
      <style>{`
        @media (max-width: 900px) { .cultural-feed { column-count: 2 !important; } }
        @media (max-width: 600px) { .cultural-feed { column-count: 1 !important; } }
      `}</style>
    </section>
  );
}

// ────────────────────────────────────────────────────────────
// TECH & CULTURE — sidebar (Elon, TikTok, podcasts)
// ────────────────────────────────────────────────────────────
function TechCultureSidebar() {
  const D = window.ENT_DATA;
  const T = D.TECH;
  return (
    <aside className="sidebar">
      <div className="sidebar-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <h3>Tech &amp; Culture</h3>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>26 markets</span>
        </div>
        <p className="sub">Net worth, social media, and platform bets</p>
      </div>

      {/* Elon: tweets */}
      <div className="sidebar-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 20 }}>𝕏</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700 }}>Elon tweet count</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{T.elon.tweets.range} · {T.elon.tweets.current} so far</div>
          </div>
          <SourceChip source="kalshi" />
        </div>
        <Histogram data={T.elon.tweets.breakdown} height={56} />
      </div>

      {/* Trillionaire timeline */}
      <div className="sidebar-card">
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>When Elon hits $1T</div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 10 }}>Net worth threshold · per Bloomberg index</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {T.elon.trillionaire.breakdown.map((b, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: 'var(--text-secondary)', minWidth: 50 }}>{b.range}</span>
              <ProbBar value={b.prob} height={4} />
              <Pct v={b.prob} size={11} />
            </div>
          ))}
        </div>
      </div>

      {/* Sports team yes/no */}
      <div className="sidebar-card">
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{T.elon.sportsTeam.label}</div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 8 }}>Polymarket</div>
        <YesNoBar yes={T.elon.sportsTeam.yes} no={T.elon.sportsTeam.no} />
      </div>

      {/* TikTok acquirer */}
      <div className="sidebar-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: 16 }}>📱</span>
          <div style={{ fontSize: 12, fontWeight: 700 }}>{T.tiktok.headline}</div>
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 10 }}>Vol {T.tiktok.volume} · Resolves {T.tiktok.resolves}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {T.tiktok.outcomes.map((o, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'center' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 11, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{o.label}</div>
                <ProbBar value={o.prob} height={3} />
              </div>
              <Pct v={o.prob} size={11} />
            </div>
          ))}
        </div>
      </div>

      {/* Podcasts */}
      <div className="sidebar-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <span style={{ fontSize: 16 }}>🎙</span>
          <div style={{ fontSize: 12, fontWeight: 700 }}>Podcast watch</div>
        </div>
        {T.podcasts.map((p, i) => (
          <div key={i} style={{ padding: '8px 0', borderTop: i > 0 ? '1px solid var(--surface-border)' : 'none' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{p.show}</div>
            <div style={{ fontSize: 11, color: 'var(--text-primary)', margin: '2px 0 6px' }}>{p.q}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ProbBar value={p.yes} height={4} />
              <Pct v={p.yes} size={11} />
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

Object.assign(window, { CulturalMomentsSection, TechCultureSidebar });
