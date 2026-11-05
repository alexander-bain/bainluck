import {readerTime} from './readerTime';
import {nflActual,nflCaptures} from './nflReconciliation';
import {catalogOutcomeIdentity} from './catalogSelection';
import {catalogPresentation,type CatalogContext} from './probabilityPresentation';
import {binaryPregame,dialPoint,type BinaryDial,type BinaryDialRow} from './binaryCatalogDial';
import {probabilityLabel} from './probabilityLabel';
import './binaryProbabilityDial.css';
export function BinaryProbabilityDial<T extends BinaryDialRow>({data,selected,visibleRows,context,choose}:{data:BinaryDial<T>;selected:T;visibleRows:T[];context:CatalogContext;choose:(row:T)=>void}){
 const current=data.rows.find(r=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected));
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity));
 const state=catalogPresentation(current??selected,current?context:{...context,mode:'stale'}),quote=state.kind==='quote'?state.value:null;
 const baseline=binaryPregame(current??selected),start=baseline==null?null:dialPoint(baseline),end=quote==null?null:dialPoint(quote);
 const actuals=data.rows.map(nflActual),actual=context.status==='completed'&&actuals[0]!==null&&actuals[0]===actuals[1]?actuals[0]:null;
 const delta=baseline==null||quote==null?null:(quote-baseline)*100;
 return <section className="binary-probability-dial" aria-label="Selected side probability">
  <div className="binary-side-choices" role="group" aria-label={`Sides of ${selected.market_name}`}>
   {data.rows.filter(row=>visible.has(catalogOutcomeIdentity(row))).map(row=><button key={row.key} aria-pressed={catalogOutcomeIdentity(row)===catalogOutcomeIdentity(selected)} onClick={()=>choose(row)}>{row.outcome_name} {data.threshold}</button>)}
  </div>
  <svg viewBox="0 0 300 173" role="img" aria-label={`${selected.outcome_name} ${data.threshold}. Pregame ${baseline===null?'unavailable':probabilityLabel(baseline)}. ${quote===null?state.label:`Recorded ${probabilityLabel(quote)}`}. Each side retains its own observation.`}>
   <path d="M38 138 A112 112 0 0 1 262 138" className="binary-dial-track"/>
   {[0,.5,1].map(p=>{const pt=dialPoint(p);return <circle key={p} cx={pt.x} cy={pt.y} r="2" className="binary-dial-tick"/>})}
   {start&&end&&Math.abs((quote??0)-(baseline??0))>0.00001&&<path d={`M${start.x} ${start.y} A112 112 0 0 ${quote!>baseline!?1:0} ${end.x} ${end.y}`} className="binary-dial-change"/>}
   {start&&<circle cx={start.x} cy={start.y} r="6" className="binary-dial-pregame"/>}
   {end&&<circle cx={end.x} cy={end.y} r="5" className="binary-dial-recorded"/>}
   <text x="150" y="95" textAnchor="middle" className={quote===null?'binary-dial-hold':'binary-dial-value'}>{quote===null?state.label:probabilityLabel(quote)}</text>
   <text x="150" y="116" textAnchor="middle">{quote===null?'Selected side':`Recorded · ${selected.outcome_name} ${data.threshold}`}</text>
   <text x="38" y="161" textAnchor="middle">0%</text><text x="150" y="14" textAnchor="middle">50%</text><text x="262" y="161" textAnchor="middle">100%</text>
  </svg>
  <p className="binary-dial-baseline"><span>○ Pregame {baseline==null?'unavailable':probabilityLabel(baseline)}</span>{context.status!=='completed'&&<span>● Recorded</span>}</p>
  {actual!==null&&<p className="binary-dial-delta">Final actual <strong>{actual}</strong> · target {data.threshold}<small> · captured {readerTime(nflCaptures.actualCapturedAt)}; stat time unavailable</small></p>}
  {delta!==null&&<p className="binary-dial-delta">{Math.abs(delta)<.05?'Unchanged':`${Math.abs(Number(delta.toFixed(1)))} percentage points ${delta>0?'above':'below'} pregame`}</p>}
  <p className="binary-dial-note">Each side keeps its own quote time. Pregame time unavailable.</p>
 </section>;
}
