// Politics page — atomic components
// All depend on tokens in design-system/colors_and_type.css

// ── Probability bar (two-segment, gap, favorite full / underdog 40%) ──
function ProbBar({ outcomes, height = 6 }) {
  return (
    <div style={{ display: 'flex', gap: 1.5, height, width: '100%' }}>
      {outcomes.map((o, i) => {
        const isLeader = o.prob === Math.max(...outcomes.map(x => x.prob));
        return (
          <div key={i} style={{
            width: `${o.prob * 100}%`,
            background: o.color,
            opacity: isLeader ? 1 : 0.4,
            borderRadius:
              i === 0 ? `${height/2}px 0 0 ${height/2}px` :
              i === outcomes.length - 1 ? `0 ${height/2}px ${height/2}px 0` : 0,
            boxShadow: isLeader ? 'inset 0 1px 2px rgba(0,0,0,0.10)' : 'none',
            transition: 'width 400ms cubic-bezier(0.25,0.1,0.25,1)',
          }} />
        );
      })}
    </div>
  );
}

// ── Movement (delta with up/down arrow) ──
function Movement({ value, size = 11 }) {
  if (value == null || Math.abs(value) < 0.0005) return null;
  const up = value > 0;
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: size, fontWeight: 600,
      color: up ? 'var(--accent-live)' : 'var(--accent-danger)',
      fontVariantNumeric: 'tabular-nums',
    }}>{up ? '↑' : '↓'}{(Math.abs(value) * 100).toFixed(1)}%</span>
  );
}

// ── Probability number (mono, tabular) ──
function Prob({ value, size = 'md' }) {
  const sizes = { hero: 36, lg: 28, md: 20, sm: 16, xs: 13 };
  const tracking = { hero: '-0.03em', lg: '-0.02em', md: '-0.02em', sm: '-0.01em', xs: '-0.01em' };
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontWeight: 700,
      fontSize: sizes[size], letterSpacing: tracking[size], lineHeight: 1,
      fontVariantNumeric: 'tabular-nums',
    }}>{Math.round(value * 100)}%</span>
  );
}

// ── Section title (uppercase micro-xs) ──
function SectionTitle({ children, count, action }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 8,
      margin: '28px 0 12px',
    }}>
      <span style={{
        fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
        textTransform: 'uppercase', color: 'var(--text-muted)',
      }}>{children}</span>
      {count != null && (
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>· {count}</span>
      )}
      <div style={{ flex: 1, height: 1, background: 'var(--surface-border)' }} />
      {action && (
        <a style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
          textTransform: 'uppercase', color: 'var(--text-secondary)', cursor: 'pointer',
        }}>{action} →</a>
      )}
    </div>
  );
}

// ── Card shell ──
function Card({ topBorder, children, style, onClick }) {
  return (
    <div onClick={onClick} className="bl-card" style={{
      background: 'var(--surface-card)',
      border: '1px solid var(--surface-border)',
      borderTop: topBorder ? `2px solid ${topBorder}` : '1px solid var(--surface-border)',
      borderRadius: 'var(--radius-card)',
      boxShadow: 'var(--shadow-card)',
      transition: 'all 200ms var(--ease-standard)',
      cursor: onClick ? 'pointer' : 'default',
      ...style,
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.background = 'var(--surface-elevated)';
      e.currentTarget.style.boxShadow = 'var(--shadow-card-hover)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = 'var(--surface-card)';
      e.currentTarget.style.boxShadow = 'var(--shadow-card)';
    }}>
      {children}
    </div>
  );
}

// ── Race card (presidency / senate / house) ──
const POLITICS_BLUE = 'rgba(59,130,246,0.6)';

function RaceCard({ race, size = 'md' }) {
  const leader = race.outcomes.reduce((a, b) => a.prob > b.prob ? a : b);
  const big = size === 'lg';
  return (
    <Card topBorder={POLITICS_BLUE} style={{ padding: big ? 18 : 14, display: 'flex', flexDirection: 'column', gap: big ? 14 : 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.02em' }}>
          🏛 {race.subtitle}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {race.sources} src
        </span>
      </div>
      <h3 style={{ margin: 0, fontSize: big ? 18 : 15, fontWeight: 600, lineHeight: 1.25, letterSpacing: '-0.01em' }}>
        {race.title}
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {race.outcomes.map((o, i) => {
          const isLeader = o.name === leader.name;
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
              <span style={{
                width: 8, height: 8, borderRadius: 2, background: o.color, flexShrink: 0,
                opacity: isLeader ? 1 : 0.5,
              }} />
              <span style={{
                flex: 1,
                color: isLeader ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontWeight: isLeader ? 500 : 400,
              }}>{o.name}</span>
              <Movement value={o.change} size={10} />
              <span style={{
                fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
                fontWeight: 700, fontSize: big ? 16 : 14,
                color: isLeader ? 'var(--text-primary)' : 'var(--text-muted)',
                minWidth: 40, textAlign: 'right',
              }}>{(o.prob * 100).toFixed(0)}%</span>
            </div>
          );
        })}
      </div>

      <ProbBar outcomes={race.outcomes} height={6} />

      <div style={{
        display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)',
        paddingTop: 4,
      }}>
        <span>Updated {race.updatedAt}</span>
        <span style={{ cursor: 'pointer' }}>Detail →</span>
      </div>
    </Card>
  );
}

// ── Mini race (compact, single bar) ──
function MiniRace({ race }) {
  const leader = race.outcomes.reduce((a, b) => a.prob > b.prob ? a : b);
  return (
    <Card topBorder={POLITICS_BLUE} style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.02em', textTransform: 'uppercase', fontWeight: 600 }}>
        {race.title}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>{leader.name}</span>
        <Movement value={leader.change} />
        <span style={{ marginLeft: 'auto' }}><Prob value={leader.prob} size="md" /></span>
      </div>
      <ProbBar outcomes={race.outcomes} height={5} />
    </Card>
  );
}

// ── Story cards ──
function LeadStory({ story, size = 'lg' }) {
  const big = size === 'lg';
  return (
    <Card style={{ padding: big ? 20 : 16, display: 'flex', flexDirection: 'column', gap: 10 }}
      onClick={() => {}}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
        <span style={{
          fontSize: 10, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
          color: 'var(--accent-brand)',
        }}>{story.kicker}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>· {story.time}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>
          {story.readTime} min read
        </span>
      </div>
      <h2 style={{
        margin: 0,
        fontSize: big ? 26 : 20,
        fontWeight: 600,
        letterSpacing: '-0.015em',
        lineHeight: 1.2,
        textWrap: 'pretty',
      }}>{story.title}</h2>
      {story.dek && (
        <p style={{
          margin: 0, fontSize: big ? 15 : 13.5, color: 'var(--text-secondary)',
          lineHeight: 1.5, textWrap: 'pretty',
        }}>{story.dek}</p>
      )}
      {story.probHook && (
        <div style={{
          marginTop: 4, padding: '10px 12px',
          background: 'var(--surface-elevated)',
          border: '1px solid var(--surface-border)',
          borderRadius: 8,
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
            Market
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-primary)', flex: 1 }}>{story.probHook.label}</span>
          <Movement value={story.probHook.change} size={11} />
          <Prob value={story.probHook.prob} size="md" />
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
        <span style={{
          width: 22, height: 22, borderRadius: '50%',
          background: 'var(--surface-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)',
        }}>{story.author.split(' ').map(n=>n[0]).join('')}</span>
        <span>{story.author}</span>
        <span style={{ color: 'var(--text-muted)' }}>·</span>
        {story.tags && story.tags.map(t => (
          <span key={t} style={{
            fontSize: 11, color: 'var(--text-secondary)',
            background: 'var(--surface-elevated)',
            padding: '2px 8px', borderRadius: 4,
          }}>{t}</span>
        ))}
      </div>
    </Card>
  );
}

function CompactStory({ story }) {
  return (
    <div style={{
      padding: '12px 0', borderBottom: '1px solid var(--surface-border)',
      display: 'flex', flexDirection: 'column', gap: 6, cursor: 'pointer',
    }}>
      <div style={{ display: 'flex', gap: 8, fontSize: 10, alignItems: 'baseline' }}>
        <span style={{
          fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
          color: 'var(--accent-brand)',
        }}>{story.kicker}</span>
        <span style={{ color: 'var(--text-muted)' }}>· {story.time}</span>
      </div>
      <h4 style={{ margin: 0, fontSize: 15, fontWeight: 500, lineHeight: 1.3, letterSpacing: '-0.005em', textWrap: 'pretty' }}>
        {story.title}
      </h4>
      {story.dek && (
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{story.dek}</p>
      )}
      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        {story.author} · {story.readTime} min
      </div>
    </div>
  );
}

// ── Op-Ed card ──
function OpEdCard({ op }) {
  return (
    <Card style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }} onClick={() => {}}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: '50%',
          background: 'var(--surface-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
          border: '1px solid var(--surface-border)',
        }}>{op.author.split(' ').map(n=>n[0]).join('').slice(0,2)}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)' }}>{op.author}</div>
          {op.role && <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{op.role}</div>}
        </div>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>Op-ed</span>
      </div>
      <h4 style={{
        margin: 0, fontSize: 14.5, fontWeight: 500, lineHeight: 1.35,
        letterSpacing: '-0.005em', textWrap: 'pretty',
        fontStyle: 'italic',
      }}>"{op.title}"</h4>
      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{op.readTime} min · {op.time}</div>
    </Card>
  );
}

// ── Poll card ──
function PollCard({ poll }) {
  return (
    <Card style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600, letterSpacing: '-0.005em' }}>{poll.question}</h4>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
          {poll.pollster}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {poll.bars.map((b, i) => (
          <div key={i}>
            <div style={{ display: 'flex', alignItems: 'baseline', fontSize: 12, marginBottom: 3 }}>
              <span style={{ color: 'var(--text-secondary)' }}>{b.label}</span>
              <span style={{
                marginLeft: 'auto', fontFamily: 'var(--font-mono)',
                fontVariantNumeric: 'tabular-nums', fontWeight: 700, fontSize: 13,
                color: 'var(--text-primary)',
              }}>{(b.value * 100).toFixed(0)}%</span>
            </div>
            <div style={{ height: 4, background: 'var(--surface-elevated)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${b.value * 100}%`, background: b.color,
                borderRadius: 2,
                transition: 'width 400ms var(--ease-standard)',
              }} />
            </div>
          </div>
        ))}
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)',
        paddingTop: 4, borderTop: '1px solid var(--surface-border)',
      }}>
        <span>n = {poll.n.toLocaleString()}</span>
        <span>·</span>
        <span>{poll.field}</span>
        {poll.delta && (
          <>
            <span style={{ marginLeft: 'auto' }}>{poll.delta.label}</span>
            <Movement value={poll.delta.value} size={10} />
          </>
        )}
      </div>
    </Card>
  );
}

// ── Bill row ──
function BillRow({ bill }) {
  const stages = ['Introduced', 'Committee', 'Floor', 'Passed', 'Enacted'];
  return (
    <Card style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }} onClick={() => {}}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
          color: 'var(--text-muted)', letterSpacing: '0.02em',
        }}>{bill.number}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>{bill.sponsor}</span>
      </div>
      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 500, lineHeight: 1.3 }}>{bill.title}</h4>

      {/* Stage progress */}
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        {stages.map((s, i) => (
          <React.Fragment key={s}>
            <div style={{
              width: 8, height: 8, borderRadius: 4,
              background: i <= bill.stageIdx ? 'var(--accent-brand)' : 'var(--surface-border)',
              boxShadow: i === bill.stageIdx ? '0 0 0 3px rgba(16,185,129,0.18)' : 'none',
            }} />
            {i < stages.length - 1 && (
              <div style={{
                flex: 1, height: 1.5,
                background: i < bill.stageIdx ? 'var(--accent-brand)' : 'var(--surface-border)',
              }} />
            )}
          </React.Fragment>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
        {stages.map((s, i) => (
          <span key={s} style={{
            color: i === bill.stageIdx ? 'var(--accent-brand)' : 'var(--text-muted)',
            fontWeight: i === bill.stageIdx ? 700 : 600,
            fontSize: 9,
          }}>{s}</span>
        ))}
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, paddingTop: 8,
        borderTop: '1px solid var(--surface-border)',
      }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, flex: 1 }}>
          Passage probability
        </span>
        <Movement value={bill.change} />
        <Prob value={bill.probPassage} size="md" />
      </div>
    </Card>
  );
}

// ── World row ──
function WorldRow({ row }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0',
      borderBottom: '1px solid var(--surface-border)', cursor: 'pointer',
    }}>
      <span style={{ fontSize: 18 }}>{row.flag}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
          {row.country}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.market}
        </div>
      </div>
      <Movement value={row.change} />
      <Prob value={row.prob} size="sm" />
    </div>
  );
}

// ── Sparkline (used in mini hero) ──
function Sparkline({ values, color, height = 28, width = 100 }) {
  if (!values?.length) return null;
  const min = Math.min(...values), max = Math.max(...values);
  const r = (max - min) || 0.01;
  const pts = values.map((v, i) => `${(i/(values.length-1))*width},${height - ((v-min)/r)*height}`).join(' ');
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Live ticker ──
function LiveTicker({ items }) {
  return (
    <div style={{
      background: 'var(--surface-card)',
      border: '1px solid var(--surface-border)',
      borderRadius: 10,
      overflow: 'hidden',
      display: 'flex', alignItems: 'center',
      height: 36,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '0 14px', height: '100%',
        background: 'var(--text-primary)', color: 'var(--surface-deep)',
        fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
      }}>
        <span className="live-dot" style={{ background: 'var(--accent-live)' }} />
        Live
      </div>
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        <div style={{
          display: 'flex', gap: 28, alignItems: 'center', height: '100%',
          paddingLeft: 16,
          animation: 'ticker-scroll 60s linear infinite',
          width: 'max-content',
        }}>
          {[...items, ...items, ...items].map((it, i) => (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              {it.kind === 'move' ? (
                <>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-muted)', fontSize: 11 }}>{it.symbol}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{it.label}</span>
                  <Movement value={it.delta} />
                </>
              ) : (
                <>
                  <span style={{
                    width: 4, height: 4, borderRadius: '50%', background: 'var(--accent-brand)',
                  }} />
                  <span style={{ color: 'var(--text-primary)' }}>{it.label}</span>
                </>
              )}
              <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>{it.time}</span>
              <span style={{ color: 'var(--surface-border)' }}>·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Section tabs (filter pills) ──
function FilterTabs({ tabs, active, onChange }) {
  return (
    <div style={{
      display: 'flex', gap: 6, padding: '4px 0 12px',
      overflowX: 'auto', scrollbarWidth: 'none',
    }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 9999, border: 'none',
            fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', cursor: 'pointer',
            background: active === t ? 'var(--text-primary)' : 'var(--surface-elevated)',
            color: active === t ? 'var(--surface-deep)' : 'var(--text-secondary)',
            transition: 'all 120ms',
            fontFamily: 'inherit',
          }}>
          {t}
        </button>
      ))}
    </div>
  );
}

// ── Header ──
function Header({ density = 'regular' }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 40,
      background: 'rgba(245,245,247,0.85)',
      backdropFilter: 'saturate(180%) blur(12px)',
      WebkitBackdropFilter: 'saturate(180%) blur(12px)',
      borderBottom: '1px solid var(--surface-border)',
    }}>
      <div style={{
        maxWidth: 1180, margin: '0 auto', padding: '0 20px',
        display: 'flex', alignItems: 'center', gap: 18, height: 56,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 16, fontWeight: 600 }}>
          <img src="design-system/assets/logo-mark.svg" width="22" height="22" alt="" />
          Bain Luck
        </div>
        <nav style={{ display: 'flex', gap: 2, marginLeft: 8 }}>
          {['Feed', 'Sports', 'Politics', 'World', 'Markets', 'My Stuff'].map(n => (
            <a key={n} style={{
              fontSize: 13, fontWeight: 500, padding: '6px 10px', borderRadius: 8,
              cursor: 'pointer', color: n === 'Politics' ? 'var(--accent-brand)' : 'var(--text-muted)',
              background: n === 'Politics' ? 'rgba(16,185,129,0.1)' : 'transparent',
            }}>{n}</a>
          ))}
        </nav>
        <div style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--surface-elevated)', borderRadius: 8, padding: '6px 12px',
          minWidth: 220, color: 'var(--text-muted)', fontSize: 13,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <span>Senators, bills, races…</span>
        </div>
        <button style={{
          width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-brand)',
          color: '#fff', border: 'none', fontSize: 11, fontWeight: 600, cursor: 'pointer',
        }}>AB</button>
      </div>
    </header>
  );
}

// ── Page-title block ──
function PageTitle({ density }) {
  return (
    <div style={{ marginTop: 24, marginBottom: 8 }}>
      <div style={{ fontSize: 11, color: 'var(--accent-brand)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 8 }}>
        🏛 Politics
      </div>
      <h1 style={{
        margin: 0, fontSize: 34, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.1,
      }}>Today in politics</h1>
      <p style={{
        margin: '6px 0 0', fontSize: 14, color: 'var(--text-secondary)',
      }}>Races, bills, and stories ranked by movement. Probability over opinion.</p>
    </div>
  );
}

// Newsletter strip
function NewsletterStrip() {
  return (
    <Card style={{
      padding: 18, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
    }}>
      <div style={{ flex: 1, minWidth: 240 }}>
        <div style={{ fontSize: 10, color: 'var(--accent-brand)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 4 }}>
          The Brief · daily
        </div>
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em' }}>
          Five things moving in politics, in your inbox by 7 a.m.
        </h4>
        <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--text-secondary)' }}>
          Probabilities, not predictions. About 4 minutes to read.
        </p>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input placeholder="you@domain" style={{
          padding: '9px 12px', border: '1px solid var(--surface-border)', borderRadius: 8,
          fontSize: 13, width: 220, background: 'var(--surface-card)', color: 'var(--text-primary)',
          fontFamily: 'inherit', outline: 'none',
        }} />
        <button style={{
          padding: '9px 16px', border: 'none', borderRadius: 8,
          background: 'var(--text-primary)', color: 'var(--surface-deep)',
          fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
        }}>Subscribe</button>
      </div>
    </Card>
  );
}

Object.assign(window, {
  ProbBar, Movement, Prob, SectionTitle, Card,
  RaceCard, MiniRace, LeadStory, CompactStory, OpEdCard,
  PollCard, BillRow, WorldRow, Sparkline, LiveTicker,
  FilterTabs, Header, PageTitle, NewsletterStrip,
  POLITICS_BLUE,
});
