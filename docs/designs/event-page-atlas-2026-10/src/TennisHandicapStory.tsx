import f from './tennisFinal.json';
import {tennisPropBaseline,tennisPropNote} from './tennisPropPregame';
import {probabilityLabel} from './probabilityLabel';
import './tennisHandicapStory.css';
type Row=typeof f.rows[number];
export function TennisHandicapStory({onPick}:{onPick:(row:Row)=>void}){
 const setRows=f.bindings.setHandicaps.map(id=>f.rows.find(r=>r._market_id===id)!);
 const game=f.rows.find(r=>r._market_id===f.bindings.gameHandicap)!;
 return <article className="atlas-card tennis-handicap-story">
  <span className="eyebrow">HANDICAPS · EXPECTATIONS, GRADED</span><h3>Both players took a set</h3>
  <p className="handicap-unit">Win at least one set</p>
  <div className="handicap-set-pair">{setRows.map((row,i)=><button key={row.key} onClick={()=>onPick(row)} aria-label={`${i?'Tiafoe':'Fokina'} to win at least one set; pre-match ${probabilityLabel(tennisPropBaseline(row)?.value??null)}; actual ${i?f.awaySets:f.homeSets} ${i?'set':'sets'}; Won. Open original +1.5 sets prop.`}>
   <span>{i?'Tiafoe':'Fokina'}</span><HandicapChance row={row}/><div className="handicap-actual"><strong>{i?f.awaySets:f.homeSets}</strong><span>{i?'set':'sets'} won · final</span></div><div className="handicap-set-blocks" aria-hidden="true">{[0,1].map(n=><i key={n} className={n<(i?f.awaySets:f.homeSets)?'filled':''}/>)}</div><span className="handicap-result">✓ Won · +1.5 sets ›</span>
  </button>)}</div>
  <div className="handicap-games"><p className="handicap-unit">Finish level or ahead on games</p><button onClick={()=>onPick(game)} aria-label="Fokina to finish level or ahead on games; pre-match 47%; actual 18–18 games; Won. Open original +0.5 games prop.">
   <span>Fokina</span><HandicapChance row={game}/><span className="handicap-result">Final games</span><div className="handicap-game-score"><div><strong>{f.homeGames}</strong><span>Fokina</span></div><b>level</b><div><strong>{f.awayGames}</strong><span>Tiafoe</span></div></div><span className="handicap-result">✓ Won · +0.5 games ›</span>
  </button></div>
  <details className="tennis-games-evidence"><summary>How these props work</summary><p>For this completed best-of-three match, +1.5 sets means winning at least one set. +0.5 games means finishing level or ahead in total games. These are separate outcomes, not a combined prediction.</p><p>{tennisPropNote(game)}</p><p>Original contracts and their settled results remain available by tapping each panel.</p></details>
 </article>
}
function HandicapChance({row}:{row:Row}){const b=tennisPropBaseline(row);return <div className="handicap-chance"><strong>{probabilityLabel(b?.value??null)}</strong><span>Pre-match chance</span>{b&&<svg viewBox="0 0 120 20" aria-hidden="true"><line x1="5" x2="115" y1="10" y2="10"/><line x1="60" x2="60" y1="6" y2="14"/><circle cx={5+110*b.value} cy="10" r="4"/></svg>}</div>}
