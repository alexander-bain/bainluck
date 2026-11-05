import {selectedPregame} from './pregameEvidence';
import {probabilityLabel} from './probabilityLabel';
import {catalogOutcomeIdentity} from './catalogSelection';
import {catalogPresentation,type CatalogContext} from './probabilityPresentation';
import {finalPlayerActual,finalPlayerIsField,finalPlayerFieldWindow,type FinalPlayerProfile,type FinalPlayerRow} from './finalPlayerMilestones';
import './finalPlayerMilestones.css';
export function FinalPlayerMilestoneCard<T extends FinalPlayerRow>({profile,selected,visibleRows,context,choose}:{profile:FinalPlayerProfile<T>;selected:T;visibleRows:T[];context:CatalogContext;choose:(row:T)=>void}){
 const current=profile.points.find(p=>catalogOutcomeIdentity(p.row)===catalogOutcomeIdentity(selected)),player=current?.player;
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity));
 const points=profile.points.filter(p=>p.player===player&&visible.has(catalogOutcomeIdentity(p.row))).sort((a,b)=>a.threshold-b.threshold);
 const field=finalPlayerIsField(profile),fieldPoints=finalPlayerFieldWindow(profile,visibleRows,current?.row??null);
 const actual=player?finalPlayerActual(profile,player):null;
 const high=Math.max(1,actual??0,...points.map(p=>p.threshold)),x=(v:number)=>32+v/high*246;
 return <section className="final-player-milestones" aria-label="Final player milestones">
  <label>Player<select aria-label={`Player in ${selected.market_name}`} value={player??''} onChange={e=>{const p=profile.points.find(p=>p.player===e.target.value&&visible.has(catalogOutcomeIdentity(p.row)));if(p)choose(p.row)}}>
   {!player&&<option value="">Selected player absent from update</option>}
   {profile.players.filter(name=>name===player||profile.points.some(p=>p.player===name&&visible.has(catalogOutcomeIdentity(p.row)))).map(name=><option key={name}>{name}</option>)}
  </select></label>
  {!field&&<div className="final-player-actual"><strong>{actual??'—'}</strong><span>{actual===null?'Actual unavailable':`${actual===1?profile.unit.slice(0,-1):profile.unit} · final actual`}</span></div>}
  {field&&<div className="final-player-field" role="group" aria-label="Player goal counts and source results">{fieldPoints.map(p=>{const count=finalPlayerActual(profile,p.player),grade=catalogPresentation(p.row,context).label;return <button key={p.row.key} aria-pressed={p.row.key===current?.row.key} onClick={()=>choose(p.row)}><strong>{p.player}</strong><span>Pregame {selectedPregame(p.row)===null?'unavailable':probabilityLabel(selectedPregame(p.row))}</span><span className="final-field-count">{count===null?'Actual unavailable':`${count} ${count===1?'goal':'goals'}`}<span aria-hidden="true">{Array.from({length:Math.min(count??0,4)},(_,i)=><i key={i}/>)}</span></span><span className={grade==='Won'?'final-field-won':''}>{grade==='Won'?'✓ ':grade==='Lost'?'× ':'? '}{grade}</span></button>})}</div>}
  {profile.unit==='points'&&<p className="final-player-definition">Points = goals + assists</p>}
  {!field&&(points.length?(actual!==null?<svg viewBox="0 0 310 184" role="img" aria-label={`${player}. ${actual===null?'Actual unavailable':`Final actual ${actual} ${profile.unit}`}. Checks and crosses are source results, not probabilities.`} onClick={e=>{const m=e.currentTarget.getScreenCTM();if(!m)return;const at=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse());if(at.x<32||at.x>278||at.y<32||at.y>132)return;choose(points.reduce((a,b)=>Math.abs(x(b.threshold)-at.x)<Math.abs(x(a.threshold)-at.x)?b:a).row)}}>
   <line x1="32" x2="278" y1="142" y2="142" className="final-player-axis"/>
   {[0,high/2,high].filter(n=>Number.isInteger(n)).map(n=><g key={n}><line x1={x(n)} x2={x(n)} y1="138" y2="147" className="final-player-axis"/><text x={x(n)} y="162" textAnchor="middle">{n}</text></g>)}
   {actual!==null&&<><line x1="32" x2={x(actual)} y1="48" y2="48" className="final-player-actual-span"/><line x1={x(actual)} x2={x(actual)} y1="32" y2="70" className="final-player-actual-rule"/><text x={x(actual)} y="22" textAnchor={actual===0?'start':actual===high?'end':'middle'}>Actual {actual}</text></>}
   {points.map(p=>{const s=catalogPresentation(p.row,context),label=s.kind==='result'?s.label:'Result pending',glyph=label==='Won'?'✓':label==='Lost'?'×':'?';return <g key={p.row.key}>
    {current?.row.key===p.row.key&&<rect x={x(p.threshold)-13} y="79" width="26" height="29" rx="5" className="final-player-selection"/>}
    <text x={x(p.threshold)} y="101" textAnchor="middle" className={label==='Won'?'final-player-won':'final-player-grade'}>{glyph}</text><text x={x(p.threshold)} y="124" textAnchor="middle">{p.threshold}+</text>
   </g>})}
   <text x="155" y="180" textAnchor="middle">{profile.unit} · offered milestones</text>
  </svg>:null):<p>This player's milestones are outside this filter. Your selection stays below.</p>)}
  {!field&&<div className="final-player-targets" role="group" aria-label={`Milestones for ${player??'selected player'}`}>{points.map(p=><button key={p.row.key} aria-pressed={p.row.key===current?.row.key} onClick={()=>choose(p.row)}>{p.threshold}+ <span>{catalogPresentation(p.row,context).kind==='result'?catalogPresentation(p.row,context).label:'Result pending'}</span></button>)}</div>}
  <p className="final-player-note">Actual observation time unavailable. Contract results come from source settlement.</p>
 </section>;
}
