import {ComposedChart,Line,ReferenceDot,XAxis,YAxis,CartesianGrid,ResponsiveContainer} from 'recharts';
import {CheckCircledIcon,CrossCircledIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {soccerFinalChance as pct,type FinalSoccerRow} from './soccerFinalEvidence';
import {soccerHalfSnapshot,halfCompetitors,type HalfCompetitor,type HalfPhase} from './soccerHalfResults';
import './soccerHalfResults.css';
const colors={home:'var(--series-home)',draw:'var(--text-secondary)',away:'var(--series-away)'};
export function SoccerHalfResultsCard({selected,onSelect,onPick,phase='final'}:{selected:HalfCompetitor;phase?:HalfPhase;onSelect:(id:HalfCompetitor)=>void;onPick:(row:FinalSoccerRow)=>void}){
 const halves=soccerHalfSnapshot(phase);
 if(!halves)return null;
 const team=halfCompetitors.find(t=>t.id===selected)!;
 const points=halves.map((half,index)=>({half:index,...Object.fromEntries(half.outcomes.map(o=>[o.team.id,o.value===null?null:o.value*100]))}));
 const ceiling=Math.max(50,Math.ceil(Math.max(...halves.flatMap(h=>h.outcomes.map(o=>(o.value??0)*100)))/25)*25);
 const values=halves.map(h=>h.outcomes.find(o=>o.team.id===selected)!);
 const firstPriced=halves[0].outcomes.filter(o=>o.value!==null).sort((a,b)=>b.value!-a.value!);
 const firstFavorite=firstPriced.length===3&&firstPriced[0].value!==firstPriced[1].value?firstPriced[0].team:null;
 const winners=halves.map(h=>h.outcomes.find(o=>o.row.result==='won')?.team.label);
 return <article className="sf-card sh-card" aria-label="Half-by-half expectations">
  <span className="eyebrow">Half-by-half expectations</span>
  <h2>{phase!=='final'?'Two halves. Two sets of expectations.':winners[0]&&winners[0]===winners[1]?`${winners[0]} won both halves.`:'Each half had its own result.'}</h2>
  <p className="sh-intro">{firstFavorite?`${firstFavorite.id==='draw'?'A draw':firstFavorite.label} had the highest pre-match chance for the first half.`:'Compare the recorded pre-match chances for each half.'}</p>
  <div className="sh-legend" role="group" aria-label="Compare half-result chances">{halfCompetitors.map(t=><button key={t.id} aria-pressed={selected===t.id} onClick={()=>onSelect(t.id)} style={{'--half-color':colors[t.id]} as React.CSSProperties}><i aria-hidden="true"/>{t.label}</button>)}</div>
  <div className="sh-chart-title"><b>Pre-match chances</b><span>0–{ceiling}% scale</span></div>
  <div className="sh-chart" role="img" aria-label={`${team.label}: first-half ${pct(values[0].value)}, second-half ${pct(values[1].value)}. Both probabilities were recorded before the match. Lines compare halves, not changes over time.`}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={points} margin={{left:-22,right:32,top:18,bottom:8}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 5"/><XAxis type="number" dataKey="half" domain={[-.1,1.1]} ticks={[0,1]} tickFormatter={n=>n===0?'First half':'Second half'} tick={{fontSize:12}} axisLine={false} tickLine={false}/><YAxis domain={[0,ceiling]} ticks={[0,ceiling/2,ceiling]} tickFormatter={n=>n+'%'} tick={{fontSize:11}} axisLine={false} tickLine={false}/>{halfCompetitors.map(t=><Line key={t.id} dataKey={t.id} type="linear" stroke={colors[t.id]} strokeWidth={selected===t.id?3:1.5} strokeOpacity={selected===t.id?1:.35} dot={{r:4,fill:'var(--surface-card)',stroke:colors[t.id],strokeWidth:2}} connectNulls={false} activeDot={false} isAnimationActive={false}/>)}{values.map((v,i)=>v.value!==null&&<ReferenceDot key={i} x={i} y={v.value*100} r={5} fill="var(--surface-card)" stroke={colors[selected]} strokeWidth={3} label={{value:pct(v.value),position:'top',fontSize:13,fill:'var(--text-primary)'}}/>)}</ComposedChart></ResponsiveContainer></div>
  <p className="sh-caption">Each dot is a pre-match chance for that half.</p>
  <p className="sh-result-label">{phase==='final'?`Final results · ${team.label}`:phase==='before'?'Results · match not started':'Half results · unconfirmed'}</p><div className="sh-outcomes" aria-label={`${team.label} original half results`}>{values.map((v,i)=><button key={v.row.key} aria-label={`${halves[i].name} ${pct(v.value)} Pre-match · ${team.label} ${phase==='final'?(v.row.result==='won'?'Won':'Lost'):phase==='before'?'Not started':'Unconfirmed'}`} onClick={()=>onPick(v.row)}><span>{halves[i].name}</span><b>{phase==='final'&&(v.row.result==='won'?<CheckCircledIcon/>:<CrossCircledIcon/>)}{phase==='final'?(v.row.result==='won'?'Won':'Lost'):phase==='before'?'Not started':'Unconfirmed'}<ChevronRightIcon/></b></button>)}</div>
 </article>;
}
