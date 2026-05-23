// Music section: Spotify Race, Billboard, Albums, Artist Streaming
// Spotify variants: 'horse-race' (chosen) | 'avatar-list' | 'bar-chart' | 'leaderboard'

// ────────────────────────────────────────────────────────────
// SPOTIFY RACE — variant 1: horse race (chosen)
// ────────────────────────────────────────────────────────────
function SpotifyHorseRace({ data }) {
  const { contenders, refreshedAt, resolvesAt, source, volume } = data;
  return (
    <div className="bl-card" style={{ padding: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--accent-page)' }}>🎧 Spotify Chart Race</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>Who's #1 on US Spotify this week?</div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Refreshed {refreshedAt}</div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {contenders.map((c, i) => {
          const isLeader = i === 0;
          return (
            <div key={c.rank} style={{ display: 'grid', gridTemplateColumns: '24px 36px 1fr auto', gap: 10, alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 14, color: isLeader ? 'var(--accent-page)' : 'var(--text-muted)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                {c.rank}
              </span>
              <Cover art={c.art} title={c.name} size={36} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.artist}</div>
                <div style={{ marginTop: 5 }}>
                  <ProbBar value={c.prob} height={6} color={isLeader ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 40%, transparent)'} />
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, minWidth: 70 }}>
                <Pct v={c.prob} size={16} />
                <Delta value={c.delta} />
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--surface-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
        <MetaRow source={source} volume={volume} resolves={resolvesAt} />
      </div>
    </div>
  );
}

// Variant 2: avatar list (artist-photo-led)
function SpotifyAvatarList({ data }) {
  return (
    <div className="bl-card" style={{ padding: 18 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--accent-page)', marginBottom: 12 }}>🎧 Spotify #1 — variant: avatar list</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {data.contenders.slice(0, 5).map(c => (
          <div key={c.rank} style={{ display: 'grid', gridTemplateColumns: '40px 1fr auto', gap: 12, alignItems: 'center' }}>
            <Cover art={c.art} title={c.artist} size={40} />
            <div>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{c.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.artist}</div>
              <div style={{ marginTop: 4, height: 3, background: 'var(--surface-elevated)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ width: `${c.prob*100}%`, height: '100%', background: 'var(--text-primary)' }} />
              </div>
            </div>
            <Pct v={c.prob} size={14} />
          </div>
        ))}
      </div>
    </div>
  );
}

// Variant 3: vertical bar chart
function SpotifyBarChart({ data }) {
  const max = Math.max(...data.contenders.map(c => c.prob));
  return (
    <div className="bl-card" style={{ padding: 18 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--accent-page)', marginBottom: 12 }}>🎧 Spotify #1 — variant: bar chart</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 140, padding: '12px 0' }}>
        {data.contenders.slice(0, 6).map(c => (
          <div key={c.rank} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <span className="prob-hero" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{Math.round(c.prob*100)}%</span>
            <div style={{ width: '100%', height: `${(c.prob/max)*100}%`, background: c.rank === 1 ? 'var(--accent-page)' : 'color-mix(in oklab, var(--accent-page) 30%, transparent)', borderRadius: '4px 4px 0 0' }} />
            <Cover art={c.art} title={c.name} size={26} />
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textAlign: 'center', fontWeight: 600, maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Variant 4: numbered leaderboard (compact)
function SpotifyLeaderboard({ data }) {
  return (
    <div className="bl-card" style={{ padding: 18 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--accent-page)', marginBottom: 12 }}>🎧 Spotify #1 — variant: leaderboard</div>
      {data.contenders.map((c, i) => (
        <div key={c.rank} style={{ display: 'grid', gridTemplateColumns: '20px 1fr auto auto', gap: 12, alignItems: 'center', padding: '10px 0', borderBottom: i < data.contenders.length - 1 ? '1px solid var(--surface-border)' : 'none' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{String(c.rank).padStart(2, '0')}</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.artist}</div>
          </div>
          <Delta value={c.delta} />
          <Pct v={c.prob} size={14} />
        </div>
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// BILLBOARD HOT 100 — distribution heatmap
// ────────────────────────────────────────────────────────────
function BillboardWatch({ data }) {
  const positions = [1, 2, 3, 4, 5, 6, 7];
  const cellColor = (p) => {
    if (p < 0.05) return 'transparent';
    const intensity = Math.min(1, p / 0.4);
    return `color-mix(in oklab, var(--accent-page) ${Math.round(intensity * 80)}%, transparent)`;
  };
  return (
    <div className="bl-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Where will songs land on Hot 100?</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{data.week} · Probability of finishing at each chart position</div>
        </div>
        <SourceChip source={data.source} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1.6fr) repeat(7, 1fr)', borderTop: '1px solid var(--surface-border)' }}>
        <div style={{ background: 'var(--surface-elevated)', padding: '8px 14px', fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', borderRight: '1px solid var(--surface-border)' }}>Song</div>
        {positions.map(p => (
          <div key={p} style={{ background: 'var(--surface-elevated)', padding: '8px 4px', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'center', borderRight: p === 7 ? 'none' : '1px solid var(--surface-border)' }}>#{p}</div>
        ))}
        {data.rows.map((row, i) => {
          const peak = Math.max(...row.positions);
          return (
            <React.Fragment key={i}>
              <div style={{ padding: '10px 14px', borderTop: '1px solid var(--surface-border)', borderRight: '1px solid var(--surface-border)', display: 'flex', flexDirection: 'column', gap: 1 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>{row.song}</span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{row.artist}</span>
              </div>
              {row.positions.map((p, j) => (
                <div key={j} style={{
                  borderTop: '1px solid var(--surface-border)',
                  borderRight: j === 6 ? 'none' : '1px solid var(--surface-border)',
                  background: cellColor(p),
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, fontVariantNumeric: 'tabular-nums',
                  color: p === peak ? 'var(--text-primary)' : (p < 0.04 ? 'var(--text-muted)' : 'var(--text-primary)'),
                  cursor: 'pointer',
                }} title={`${row.song} at #${j+1}: ${Math.round(p*100)}%`}>
                  {p < 0.02 ? '·' : Math.round(p*100)}
                </div>
              ))}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// ALBUMS — first-week sales over/under
// ────────────────────────────────────────────────────────────
function Albums({ data }) {
  return (
    <div className="grid-3">
      {data.map(a => (
        <div key={a.title} className="bl-card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
            <Cover art={a.art} title={a.title} size={56} big />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>Drops {a.releaseDate}</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginTop: 2 }}>{a.title}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{a.artist}</div>
            </div>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>First-week {a.thresholdLabel} · O/U <b style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{a.threshold}</b></div>
          <Histogram data={a.breakdown} format={(d) => d.range} />
          <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--surface-border)' }}>
            <MetaRow source={a.source} volume={a.volume} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// ARTIST STREAMING — compact grid
// ────────────────────────────────────────────────────────────
function ArtistStreaming({ data }) {
  return (
    <div className="bl-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--surface-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Weekly streaming direction</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>P(streams up vs. last week) · refreshed Mondays</div>
        </div>
        <SourceChip source="polymarket" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
        {data.map((a, i) => (
          <div key={a.artist} style={{
            display: 'grid', gridTemplateColumns: '32px 1fr auto', gap: 10,
            padding: '12px 16px', alignItems: 'center',
            borderRight: '1px solid var(--surface-border)',
            borderBottom: '1px solid var(--surface-border)',
          }}>
            <Cover art={a.art} title={a.artist} size={32} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.artist}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{a.weeklyStreams}/wk</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
              <span className="prob-hero" style={{ fontSize: 13, color: a.direction === 'up' ? 'var(--accent-live)' : 'var(--accent-danger)' }}>
                {a.direction === 'up' ? '↑' : '↓'} {Math.round(a.prob*100)}%
              </span>
              <Delta value={a.delta} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// MUSIC SECTION (with tab switcher)
// ────────────────────────────────────────────────────────────
function MusicSection({ spotifyVariant = 'horse-race' }) {
  const [tab, setTab] = React.useState('spotify');
  const D = window.ENT_DATA;

  const SpotifyEl = {
    'horse-race': SpotifyHorseRace,
    'avatar-list': SpotifyAvatarList,
    'bar-chart': SpotifyBarChart,
    'leaderboard': SpotifyLeaderboard,
  }[spotifyVariant] || SpotifyHorseRace;

  return (
    <section className="section">
      <SectionHead
        eyebrow="Music"
        title="Charts, drops, and streams"
        sub="The biggest recurring theme — six markets on Spotify, Billboard, first-week sales and weekly streams"
        right={<>
          <Tabs value={tab} onChange={setTab} options={[
            { value: 'spotify', label: 'Spotify Race' },
            { value: 'billboard', label: 'Billboard' },
            { value: 'albums', label: 'Album drops' },
            { value: 'streaming', label: 'Artist streaming' },
          ]} />
        </>}
      />
      {tab === 'spotify' && <SpotifyEl data={D.SPOTIFY_RACE} />}
      {tab === 'billboard' && <BillboardWatch data={D.BILLBOARD} />}
      {tab === 'albums' && <Albums data={D.ALBUMS} />}
      {tab === 'streaming' && <ArtistStreaming data={D.ARTIST_STREAMING} />}
    </section>
  );
}

Object.assign(window, { MusicSection, SpotifyHorseRace, SpotifyAvatarList, SpotifyBarChart, SpotifyLeaderboard, BillboardWatch, Albums, ArtistStreaming });
