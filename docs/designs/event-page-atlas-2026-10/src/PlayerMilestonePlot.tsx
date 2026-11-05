import {readerTime} from './readerTime';
import {nflCaptures} from './nflReconciliation';
import {completionPregameNote} from './nflCompletion';
import {catalogOutcomeIdentity} from './catalogSelection';
import {catalogPresentation,type CatalogContext} from './probabilityPresentation';
import {probabilityLabel} from './probabilityLabel';
import {playerFinalActual,type PlayerProfile,type PlayerProfileRow} from './playerCatalogProfile';
import './playerCatalogProfile.css';
export function PlayerCatalogProfile<T extends PlayerProfileRow>({profile,selected,visibleRows,context,choose}:{profile:PlayerProfile<T>;selected:T;visibleRows:T[];context:CatalogContext;choose:(row:T)=>void}){
 const ids=new Set(visibleRows.map(catalogOutcomeIdentity)),current=profile.points.find(p=>catalogOutcomeIdentity(p.row)===catalogOutcomeIdentity(selected));
 const subject=current?.playerID??profile.points.find(p=>ids.has(catalogOutcomeIdentity(p.row)))?.playerID;
 const points=profile.points.filter(p=>p.playerID===subject&&ids.has(catalogOutcomeIdentity(p.row))).sort((a,b)=>a.threshold-b.threshold);
 const player=profile.players.find(p=>p.id===subject);
 const choices=profile.players.filter(p=>p.id===subject||profile.points.some(r=>r.playerID===p.id&&ids.has(catalogOutcomeIdentity(r.row))));
 const actual=context.status==='completed'&&subject?playerFinalActual(profile,subject):null;
 const high=Math.max(actual??0,1,...points.map(p=>p.threshold),current?.threshold??0),left=36,right=308,top=18,bottom=166;
 const x=(n:number)=>left+n/high*(right-left),y=(chance:number)=>bottom-chance*(bottom-top);
 const selectedState=current?catalogPresentation(current.row,context):null;
 const currentChance=selectedState?.kind==='quote'?selectedState.value:null;
 const delta=current?.pregame!=null&&currentChance!=null?(currentChance-current.pregame)*100:null;
 return <section className="player-catalog-profile" aria-label={`${profile.unit} player profile`}>
  <label className="player-profile-select">Player<select aria-label={`Player in ${selected.market_name}`} value={subject??''} onChange={e=>{const point=profile.points.find(p=>p.playerID===e.target.value&&ids.has(catalogOutcomeIdentity(p.row)));if(point)choose(point.row)}}>{choices.map(p=><option key={p.id} value={p.id}>{p.name} · {p.count} milestones</option>)}</select></label>
  <div className="player-profile-caption"><b>{player?.name}</b><span>Chance to reach each milestone</span></div>
  {actual!==null&&<div className="player-final-actual"><strong>{actual}<small>{profile.unit}</small></strong><span>FINAL ACTUAL</span></div>}
  {points.length?<svg viewBox="0 0 330 212" role="img" aria-label={`${player?.name}, ${profile.unit}. Hollow marks: supplied pregame chances. Solid marks: recorded chances when available. A thick vertical rule shows final actual in sport units. Each point is an offered threshold, not a predicted distribution.`} onClick={event=>{
   const matrix=event.currentTarget.getScreenCTM();if(!matrix)return;const at=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
   if(at.x<left||at.x>right||at.y<top||at.y>bottom)return;
   choose(points.reduce((a,b)=>Math.abs(x(b.threshold)-at.x)<Math.abs(x(a.threshold)-at.x)?b:a).row);
  }}>
   {[0,.5,1].map(p=><g key={p}><line x1={left} x2={right} y1={y(p)} y2={y(p)} className="player-profile-grid"/><text x={left-6} y={y(p)+4} textAnchor="end">{p*100}%</text></g>)}
   {current&&ids.has(catalogOutcomeIdentity(current.row))&&<line x1={x(current.threshold)} x2={x(current.threshold)} y1={top} y2={bottom} className="player-profile-selected"/>}
   {actual!==null&&<line x1={x(actual)} x2={x(actual)} y1={top} y2={bottom} className="player-profile-actual"/>}
   {points.map(point=>{const state=catalogPresentation(point.row,context),q=state.kind==='quote'?state.value:null;return <g key={point.row.key}>
    {point.pregame!==null&&q!==null&&<line x1={x(point.threshold)} x2={x(point.threshold)} y1={y(point.pregame)} y2={y(q)} className="player-profile-change"/>}
    {point.pregame!==null&&<circle cx={x(point.threshold)} cy={y(point.pregame)} r={4} className="player-profile-pregame"/>}
    {q!==null&&<circle cx={x(point.threshold)} cy={y(q)} r={3.5} className="player-profile-recorded"/>}
   </g>})}
   {[0,high/2,high].map(n=><text key={n} x={x(n)} y={bottom+20} textAnchor="middle">{Number(n.toFixed(1))}</text>)}
   <text x={(left+right)/2} y={bottom+40} textAnchor="middle">{profile.unit} · at least</text>
  </svg>:<p className="player-profile-filtered">This player's milestones are outside this filter. Your selection stays below.</p>}
  <div className="player-profile-key"><span>○ Pregame</span>{context.status==='completed'?<span>┃ Final actual</span>:<span>● Recorded</span>}</div>
  {current&&<p className="player-profile-delta">{current.pregame===null?'Pregame chance unavailable':`Pregame ${probabilityLabel(current.pregame)}`}{delta!==null&&<> · <strong>{Math.abs(delta)<.05?'Unchanged':`${Math.abs(Number(delta.toFixed(1)))} percentage points ${delta>0?'above':'below'} pregame`}</strong></>}</p>}
  {currentChance===null&&<p className="player-profile-hold">{selectedState?.label??'Current probability unavailable'}</p>}
  <label className="player-profile-select">Milestone<select aria-label={`Milestone for ${player?.name}`} value={current&&points.some(p=>p.row.key===current.row.key)?current.row.key:''} onChange={e=>{const point=points.find(p=>p.row.key===e.target.value);if(point)choose(point.row)}}>
   {(!current||!points.some(p=>p.row.key===current.row.key))&&<option value="">Selected milestone outside filter</option>}
   {points.map(p=><option key={p.row.key} value={p.row.key}>{p.threshold}+ {profile.unit}</option>)}
  </select></label>
  <p className="player-profile-note">{completionPregameNote(selected)??'Pregame observation time unavailable.'} Each recorded quote keeps its own time in details. {context.status==='completed'?(actual===null?'Final actual unavailable.':`Final actual from the ${readerTime(nflCaptures.actualCapturedAt)} capture; stat observation time unavailable.`):'No player actual is supplied to this card.'}</p>
 </section>;
}
