// Page header — sticky nav for the Bain Luck shell

function Header({ accent }) {
  const navItems = ['Feed', 'NFL', 'NBA', 'MLB', 'NHL', 'Politics', 'Economics', 'Weather', 'Entertainment'];
  return (
    <header className="bl-hdr">
      <div className="bl-hdr-inner">
        <div className="bl-brand">
          <span style={{ fontSize: 22 }}>🍀</span>
          <span>Bain Luck</span>
        </div>
        <nav className="bl-nav">
          {navItems.map(n => (
            <a key={n} className={n === 'Entertainment' ? 'active' : ''}>{n}</a>
          ))}
        </nav>
        <div className="bl-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input placeholder="Search markets…" />
        </div>
        <div className="bl-avatar">AB</div>
      </div>
    </header>
  );
}

Object.assign(window, { Header });
