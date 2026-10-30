function el(tag, cls, text){ const e = document.createElement(tag); if(cls) e.className = cls; if(text != null) e.textContent = text; return e; }
function svg(tag, attrs){ const e = document.createElementNS('http://www.w3.org/2000/svg', tag); for(const k in attrs) e.setAttribute(k, attrs[k]); return e; }
function numEl(r, cls){ const n = el('div', 'n num ' + (cls||'')); n.append(r.num); n.append(el('small', '', '%')); return n; }
function meter(r, alt){ const m = el('div', 'meter' + (alt ? ' b' : '')); const i = el('i'); i.style.width = Math.max(r.p*100, 0.6) + '%'; m.append(i); m.title = r.plain + ': ' + r.num + '%'; return m; }
function cap(s){ return s.charAt(0).toUpperCase() + s.slice(1); }

function rowList(c){
  const box = el('div', 'rows');
  c.rows.forEach(r => {
    const row = el('div', 'row');
    row.append(numEl(r), el('div', 't', r.cont ? r.text : cap(r.text)), meter(r));
    box.append(row);
  });
  return box;
}
function pairBlock(r, alt){
  const b = el('div', 'pair'); const top = el('div', 'top');
  top.append(numEl(r), el('div', 't', r.text)); b.append(top, meter(r, alt)); return b;
}
function fmtDate(ms, short){
  const d = new Date(ms); const M = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()];
  return short ? M + ' ' + d.getUTCDate() : M + ' ' + d.getUTCFullYear();
}
function clockChart(c){
  const W = 320, H = 138, L = 28, R = 18, T = 22, B = 22, pw = W-L-R, ph = H-T-B;
  const ts = c.rows.map(r => Date.parse(r.deadline + 'T00:00:00Z'));
  const t1 = ts[ts.length-1], span = t1 - ASOF;
  const x = t => L + Math.max(0, (t - ASOF)) / span * pw, y = v => T + (1 - v/100) * ph;
  const s = svg('svg', {viewBox:`0 0 ${W} ${H}`, class:'chart', role:'img'});
  s.setAttribute('aria-label', c.headline + ': ' + c.rows.map(r => r.text + ' ' + r.num + '%').join(', '));
  [0,50,100].forEach(v => {
    s.append(svg('line', {x1:L, x2:W-R, y1:y(v), y2:y(v), class:'grid'}));
    const t = svg('text', {x:L-6, y:y(v)+3.5, 'text-anchor':'end', class:'ax'}); t.textContent = v; s.append(t);
  });
  const pts = c.rows.map((r,i) => ({x:x(ts[i]), y:y(r.p*100), r}));
  const line = 'M' + L + ',' + y(0) + ' ' + pts.map(p => 'L' + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
  s.append(svg('path', {d: line + ' L' + pts[pts.length-1].x.toFixed(1) + ',' + y(0) + ' Z', class:'area'}));
  s.append(svg('path', {d: line, class:'ln'}));
  const placed = [];
  for(let i = pts.length-1; i >= 0; i--){
    const p = pts[i], nx = pts[i+1], w = 14 + 7*String(p.r.num).length;
    const steep = nx && (p.y - nx.y) > 18 && (nx.x - p.x) < 60;   // a sharp rise follows: move the label clear of the line
    const cx = Math.max(L + w/2, Math.min(steep ? p.x - 4 - w/2 : p.x, W - w/2 - 1));
    const bx = {x0:cx-w/2, x1:cx+w/2, y0:p.y-21, y1:p.y-7};
    if(placed.some(q => bx.x0 < q.x1 && bx.x1 > q.x0 && bx.y0 < q.y1 && bx.y1 > q.y0)) continue;
    placed.push(bx);
    const t = svg('text', {x:cx, y:p.y-9, 'text-anchor':'middle', class:'val'}); t.textContent = p.r.num + '%'; s.append(t);
  }
  pts.forEach(p => { const d = svg('circle', {cx:p.x, cy:p.y, r:4, class:'dot'}); const tt = svg('title', {}); tt.textContent = cap(p.r.text) + ': ' + p.r.num + '%'; d.append(tt); s.append(d); });
  const short = span < 200*864e5;
  const a = svg('text', {x:L, y:H-5, 'text-anchor':'start', class:'ax'}); a.textContent = 'now'; s.append(a);
  const z = svg('text', {x:W-R, y:H-5, 'text-anchor':'end', class:'ax'}); z.textContent = fmtDate(t1 - (c.rows[c.rows.length-1].text.indexOf('before') === 0 ? 864e5 : 0), short); s.append(z);
  return s;
}
function clockRows(c){
  const box = el('div', 'crows');
  c.rows.forEach(r => { const row = el('div', 'crow'); row.append(el('span', '', cap(r.text)), numEl(r)); box.append(row); });
  return box;
}

function duelChart(c){
  // two lines on a fixed 0 to 100 scale; no smoothing: each point is one observation from the venue's own price history
  const W = 320, H = 132, L = 26, R = 34, T = 8, B = 20, pw = W-L-R, ph = H-T-B;
  const x = t => L + (t - c.t0) / (c.t1 - c.t0) * pw, y = v => T + (1 - v) * ph;
  const s = svg('svg', {viewBox:`0 0 ${W} ${H}`, class:'chart duel', role:'img'});
  s.setAttribute('aria-label', c.rows.map((r, i) => r.text + ': ' + r.prev + '% to ' + r.num + '% ' + c.span).join('; '));
  [0,50,100].forEach(v => {
    s.append(svg('line', {x1:L, x2:W-R, y1:y(v/100), y2:y(v/100), class:'grid'}));
    const t = svg('text', {x:L-6, y:y(v/100)+3.5, 'text-anchor':'end', class:'ax'}); t.textContent = v; s.append(t);
  });
  const ends = [];
  c.series.forEach((pts, i) => {
    const d = pts.map((p, k) => (k ? 'L' : 'M') + x(p[0]).toFixed(1) + ',' + y(p[1]).toFixed(1)).join(' ');
    s.append(svg('path', {d, class:'ln' + (i ? ' b' : '')}));
    const last = pts[pts.length-1]; ends.push({i, x: x(last[0]), y: y(last[1]), num: c.rows[i].num});
  });
  if(ends.length === 2 && Math.abs(ends[0].y - ends[1].y) < 12){ const up = ends[0].y < ends[1].y ? 0 : 1; const mid = (ends[0].y + ends[1].y) / 2; ends[up].ly = mid - 6; ends[1-up].ly = mid + 6; }
  ends.forEach(e => {
    s.append(svg('circle', {cx:e.x, cy:e.y, r:3.5, class:'dot' + (e.i ? ' b' : '')}));
    const t = svg('text', {x:e.x + 7, y:(e.ly == null ? e.y : e.ly) + 4, 'text-anchor':'start', class:'val'}); t.textContent = e.num + '%'; s.append(t);
  });
  const a = svg('text', {x:L, y:H-5, 'text-anchor':'start', class:'ax'}); a.textContent = fmtDate(c.t0*1000, true); s.append(a);
  const z = svg('text', {x:W-R, y:H-5, 'text-anchor':'end', class:'ax'}); z.textContent = 'now'; s.append(z);
  return s;
}
function moverRows(c){
  const box = el('div', 'rows');
  c.rows.forEach((r, idx) => {
    if(idx === 1 && c.conn) box.append(el('div', 'conn', c.conn));
    const row = el('div', 'row'); const tx = el('div', 't'); if(c.series){ tx.append(el('i', idx ? 'sw b' : 'sw')); tx.append(' '); } tx.append(cap(r.text));
    const sub = el('div', 'was', (r.delta === 0 ? 'Unchanged ' : (r.delta > 0 ? 'Up ' : 'Down ') + Math.abs(r.delta) + ' ') + (c.span || 'in a week') + (r.delta === 0 ? '' : ', from ' + r.prev + '%') + (r.note ? '. ' + r.note : '')); tx.append(sub);
    const m = el('div', 'meter mv' + (c.series && idx ? ' b' : '')); const i = el('i'); i.style.width = Math.max(r.p*100, 0.6) + '%'; const k = el('b'); k.style.left = r.prev + '%'; m.append(i, k); m.title = r.plain + ': ' + r.num + '%, was ' + r.prev + '%';
    row.append(numEl(r), tx, m); box.append(row);
  });
  return box;
}
function h2hRows(c){
  const box = el('div', 'h2h');
  const lg = el('div', 'legend'); c.names.forEach((n, i) => { const s = el('span', 'lg'); s.append(el('i', i ? 'sw b' : 'sw'), n); lg.append(s); }); box.append(lg);
  for(let k = 0; k < c.rows.length; k += 2){
    const g = el('div', 'grp'); g.append(el('div', 'glabel', '…' + c.rows[k].label));
    [c.rows[k], c.rows[k+1]].forEach((r, i) => { const line = el('div', 'gline'); line.append(numEl(r), meter(r, i === 1)); g.append(line); });
    box.append(g);
  }
  return box;
}
function buildCard(c){
  const card = el('article', 'card');
  const kh = el('div', 'khead'); kh.append(el('span', 'kicker', c.kicker)); if(c.tag) kh.append(el('span', 'tag', c.tag)); card.append(kh);
  if(c.headline) card.append(el('h2', 'headline' + (c.headline.length > 44 ? ' long' : ''), c.headline));
  if(c.type === 'board' || c.type === 'band' || c.type === 'peer' || c.type === 'checklist' || (c.type === 'roundup' && c.rows[0].prev == null)) card.append(rowList(c));
  else if(c.type === 'when'){ card.append(el('div', 'callout', c.callout), clockChart(c), clockRows(c)); }
  else if(c.type === 'movers' || c.type === 'roundup' || c.type === 'swing' || c.type === 'newfav'){ if(c.series) card.append(duelChart(c)); card.append(moverRows(c)); }
  else if(c.type === 'h2h') card.append(h2hRows(c));
  else if(c.type === 'deadheat'){ card.append(pairBlock(c.rows[0], false), el('div', 'conn', 'level with'), pairBlock(c.rows[1], true), el('div', 'restline', 'Everyone else combined: ' + c.rest + '%')); }
  card.append(el('div', 'src', 'Venue prices: ' + c.venues.join(' and ')));
  return card;
}
function finePrint(c){
  const d = el('details'); d.append(el('summary', '', 'Fine print'));
  const fp = el('div', 'fp');
  fp.append(el('h4', '', 'What each number measures'));
  const ul = el('ul');
  c.rows.forEach(r => {
    const li = el('li'); li.append(el('div', 'q', r.plain + ' (' + r.num + '%)'));
    const parts = [];
    if(r.pK != null) parts.push('Kalshi ' + r.pK + '%'); if(r.pP != null) parts.push('Polymarket ' + r.pP + '%');
    li.append(el('div', 'v', 'Venue wording: “' + r.raw.trim() + '”. ' + parts.join(', ') + (parts.length > 1 ? ' (shown: the average)' : '') + '.' + (r.earlier ? ' Earlier value observed: ' + r.earlier + (parts.length > 1 ? ' (shown: the average)' : '') + '.' : '') + ' Ref ' + r.id + '.'));
    ul.append(li);
  });
  fp.append(ul);
  const gs = c.rows.filter(r => r.gotcha); if(gs.length){ fp.append(el('h4', '', 'Easy to misread')); const gl = el('ul'); gs.forEach(r => gl.append(el('li', '', r.gotcha))); fp.append(gl); }
  if(c.notes && c.notes.length){
    fp.append(el('h4', '', "Independent checker's notes"));
    const nl = el('ul'); c.notes.forEach(n => nl.append(el('li', '', n))); fp.append(nl);
  }
  if(c.series) fp.append(el('div', 'v', 'Chart: every point is one observation from the venue\'s own price history, drawn on a fixed 0 to 100 scale with no smoothing.'));
  fp.append(el('div', 'v', 'Card ' + c.cid + '.'));
  d.append(fp); return d;
}

