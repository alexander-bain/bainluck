/* Static design study: no API calls, analytics, mutations, or production imports. */
'use strict';
const cases = [
 {key:'nba',title:'Celtics at 76ers',sport:'NBA',date:'Nov 10',names:['Celtics','76ers'],
 pre:[54,46],projection:[110,108],score:[111,87],liveProjection:[121,100],now:[100,0],final:[123,101],winner:0,
 beforeMeta:'5:00 PM PT',duringMeta:'Q4 · 5:35',
 source:'Public API · historical replay',
 notes:'Final 123–101. Pregame 54% / 46%; projected 109.5 / 107.8 → 110 / 108. Replay: Nov 10, 7:15 PM PT; latest score 7:14:48 PM, blended chance 99.6025% / 0.3975% → 100% / 0%.',sample:[]},
 {key:'nfl',title:'Patriots at Lions',sport:'NFL',date:'Nov 15',names:['Patriots','Lions'],
 pre:[41,59],projection:[null,null],sampleProjection:[24,27],score:[17,14],liveProjection:[30,24],now:[68,32],final:[31,27],winner:0,
 beforeMeta:'6:30 AM PT',duringMeta:'Q3 · 6:42',
 source:'Before: API snapshot · later states: samples',
 notes:'Nov 11, 1:31 PM PT API read: 41% / 59% as supplied by rendered-percent fields; no recent projected lines. Before stays blank. Later scores, projections and frozen pregame chances are sample scenarios, not forecasts or results.',sample:['during-live','during-pregame','after']},
 {key:'soccer',title:'North FC at South FC',sport:'SOCCER',date:'Sample',names:['North FC','South FC','Draw'],
 pre:[45,30,25],projection:[2,1,null],score:[1,1,null],liveProjection:[2,2,null],now:[31,24,45],final:[2,2,null],winner:2,
 beforeMeta:'Sample',duringMeta:'68′',source:'Sample fixture · all numbers invented',
 notes:'Draw has a chance, never a score or projected score. A drawn final emphasizes the Draw row; no 100% result column. Both projection options use whole goals.',sample:['before','during-live','during-pregame','after']},
 {key:'tennis',title:'Rivera vs Chen',sport:'TENNIS',date:'Sample',names:['Rivera','Chen'],
 pre:[58,42],projection:[null,null],score:[1,0],liveProjection:[null,null],now:[72,28],final:[2,0],winner:0,
 beforeMeta:'Sample',duringMeta:'Sets · Set 2',source:'Sample fixture · no projected score',
 notes:'Scores are sets won. Projected stays visibly empty, including its header. No replacement dash, fake zero, squeezed type or sideways shift into the empty slot.',sample:['before','during-live','during-pregame','after']}
];
const params=new URLSearchParams(location.search);
const variant=params.get('variant')==='B'?'B':'A';
document.body.classList.add(`variant-${variant}`);
if(params.has('case')) document.body.classList.add('focus');
if(params.get('text')==='large') document.body.classList.add('zoom');
document.querySelector(`[data-variant="${variant}"]`).setAttribute('aria-current','page');
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const percent=v=>v===null?null:`${v}%`;
const values=(c,state)=>({
 score:state==='before'?[null,null,null]:state==='after'?c.final:c.score,
 projection:state==='during-live'?c.liveProjection:(state==='before'?c.projection:(c.sampleProjection||c.projection)),
 pre:c.pre, now:state.startsWith('during')?c.now:[]
});
function card(c,state){
 const wrap=el('section','specimen');wrap.dataset.state=state;
 const labels={before:'Before', 'during-live':'During · live projection', 'during-pregame':'During · pregame projection',after:'After · pregame projection'};
 const label=el('h3','specimen-label',labels[state]);
 if(c.sample.includes(state))label.append(el('span','sample','Sample'));
 wrap.append(label);
 const article=el('article','card');article.setAttribute('aria-label',`${c.title}, ${labels[state]}`);
 article.dataset.sport=c.key;article.dataset.state=state;
 const meta=el('div','meta');meta.append(el('span','',`${c.sport} · ${c.date}`),el('span','',state==='before'?c.beforeMeta:state==='after'?(c.key==='tennis'?'Sets':''):c.duringMeta));article.append(meta);
 const v=values(c,state);
 // Variant B uses the active chance only; settled cards have no chance bar.
 if(state!=='after'){const bar=el('div','rule');bar.setAttribute('aria-hidden','true');(state==='before'?c.pre:c.now).forEach(n=>{const s=el('i');s.style.width=`${n}%`;bar.append(s);});article.append(bar);}
 const table=el('div','table');table.setAttribute('role','table');table.setAttribute('aria-label','Game numbers');
 const headers=['',state==='before'?'':state==='after'?'Final':'Score',v.projection.some(x=>x!==null)?'Projected':'','Pregame',state.startsWith('during')?'Now':''];
 const hr=el('div','row');hr.setAttribute('role','row');headers.forEach((h,i)=>{const e=el('div',`cell head${!h?' empty':''}`,h||'');e.setAttribute('role','columnheader');e.dataset.col=i;hr.append(e);});table.append(hr);
 c.names.forEach((name,i)=>{
 const row=el('div','row');row.setAttribute('role','row');
 const winner=state==='after'&&i===c.winner;
 const nameCell=el('div',`cell name side-${i}${winner?' winner':''}`);nameCell.setAttribute('role','rowheader');nameCell.dataset.col=0;
 nameCell.append(el('span','dot'),el('span','name-text',name));row.append(nameCell);
 [v.score[i],v.projection[i],percent(v.pre[i]),percent(v.now[i]??null)].forEach((n,j)=>{
 const absent=n===null||n===undefined;
 const primary=state==='after'?j===0:state==='before'?j===2:j===3;
 const cell=el('div',`cell${absent?' empty':''}${primary?' primary':''}${winner?' winner':''}`,absent?'':String(n));
 cell.setAttribute('role','cell');cell.dataset.col=j+1;if(absent)cell.setAttribute('aria-label','Not applicable or unavailable');row.append(cell);
 });table.append(row);
 });article.append(table);wrap.append(article);return wrap;
}
const gallery=document.getElementById('gallery');
cases.filter(c=>!params.has('case')||c.key===params.get('case')).forEach(c=>{
 const section=el('section','case');section.dataset.case=c.key;
 const head=el('header','case-head');head.append(el('div','eyebrow',`${variant} · ${variant==='A'?'QUIET TABLE':'FINE RULE'} · 390 PX`),el('h2','',c.title),el('p','',c.source));section.append(head);
 ['before','during-live','during-pregame','after'].forEach(s=>section.append(card(c,s)));
 section.append(el('p','audit',c.notes));gallery.append(section);
});
