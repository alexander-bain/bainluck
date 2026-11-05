import {firstScorerLeaders} from './hockeyFirstLeaders';
import {probabilityLabel} from './probabilityLabel';
import type {HockeyScoringRow} from './hockeyScoringEvidence';
export function HockeyFirstChances<T extends HockeyScoringRow>({rows,selectedID,onSelect}:{rows:T[];selectedID:string;onSelect:(row:T)=>void}){
 const {known,leaders,ceiling}=firstScorerLeaders(rows);
 if(!leaders.length)return null;
 return <section className="hockey-first-chances" aria-label="Highest captured pregame first-scorer chances">
  <h4>Highest captured pregame chances</h4>
  <div className="hockey-first-axis" aria-hidden="true"><span/><div><span>0%</span><span>{probabilityLabel(ceiling/2)}</span><span>{probabilityLabel(ceiling)}</span></div><span/></div>
  {leaders.map(({row,baseline})=><button key={row.key} className="hockey-first-mark" aria-pressed={selectedID===row.key} aria-label={`${row.outcome_name}, pregame first-goalscorer chance ${probabilityLabel(baseline.value)}. Select prop.`} onClick={()=>onSelect(row)}>
   <span>{row.outcome_name}</span><svg aria-hidden="true"><g className="hockey-first-grid">{[3,50,97].map(x=><line key={x} x1={`${x}%`} x2={`${x}%`} y1="2" y2="26"/>)}</g><line className="hockey-first-stem" x1="3%" x2={`${3+94*baseline.value/ceiling}%`} y1="14" y2="14"/><circle className="hockey-first-dot" cx={`${3+94*baseline.value/ceiling}%`} cy="14" r="4"/></svg><strong>{probabilityLabel(baseline.value)}</strong>
  </button>)}
  <p className="hockey-goal-key">{known.length} of {rows.length} players have a captured pregame trade. Select a player for their trade time and result.</p>
 </section>;
}
