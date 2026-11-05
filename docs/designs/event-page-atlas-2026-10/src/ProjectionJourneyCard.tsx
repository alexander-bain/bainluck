import {eventReaderTime} from './eventReaderTime';
import {useEffect,useRef,useState} from 'react';
import bundles from './projectionBundles.json';
import {finalDifference,headlineProjection,stepPath,type ProjectionBundle} from './projectionEvidence';
import {projectionObservations,recordChoice,inspectProjection,chooseProjection,stepProjection,type ProjectionChoice,type ProjectionObservation} from './projectionInspection';
import './projectionJourney.css';
export const projectionFor=(key:string)=>(bundles as ProjectionBundle[]).find(bundle=>bundle.key===key);
export {headlineProjection};
const clock=(at:string)=>eventReaderTime.full(at,true);
const axisStamp=(at:string)=>eventReaderTime.short(at);
const number=(value:number)=>Number(value.toFixed(1)).toString();
export function ProjectionJourneyCard(props:{bundle:ProjectionBundle;mode?:string}) { return <ProjectionJourneyBody key={props.bundle.eventID} {...props}/> }
function ProjectionJourneyBody({bundle,mode='captured'}:{bundle:ProjectionBundle;mode?:string}) {
 const ref=useRef<HTMLElement>(null);
 const [defaultExpanded,setDefaultExpanded]=useState(false);
 const [choice,setChoice]=useState<boolean|null>(null);
 const [selected,setSelected]=useState<ProjectionChoice|null>(null);
 const [inspectionOpen,setInspectionOpen]=useState(false);
 useEffect(()=>{
  const page=ref.current?.closest('.event-content');if(!page)return;
  const resize=()=>setDefaultExpanded(page.getBoundingClientRect().width>=600&&!page.classList.contains('large-text'));
  const observer=new ResizeObserver(resize);observer.observe(page);
  const mutation=new MutationObserver(resize);mutation.observe(page,{attributes:true,attributeFilter:['class']});resize();
  return()=>{observer.disconnect();mutation.disconnect()};
 },[]);
 const expanded=choice??defaultExpanded;
 const current=headlineProjection(bundle,mode),isFinal=bundle.phase==='after';
 const records=projectionObservations(bundle);
 const effective=selected??(records.length?recordChoice(records.at(-1)!):null);
 const inspection=inspectProjection(bundle,effective),inspected=inspection?.observation.point;
 const observationLabel=(row:ProjectionObservation)=>clock(row.point.at)+(row.countAtTime>1?` · ${row.ordinalAtTime}/${row.countAtTime}`:'');
 const previous=stepProjection(bundle,effective,false),next=stepProjection(bundle,effective,true);
 const left=36,right=390,top=30,bottom=236;
 const x=(at:string)=>left+(Date.parse(at)-Date.parse(bundle.start))/(Date.parse(bundle.end)-Date.parse(bundle.start))*(right-left);
 const y=(v:number)=>bottom-v/bundle.yMax*(bottom-top);
 const tickStep=Math.max(1,Math.ceil(bundle.yMax/4/5)*5);
 const ticks=Array.from({length:Math.ceil(bundle.yMax/tickStep)},(_,i)=>i*tickStep).concat(bundle.yMax);
 const title=isFinal?'Final vs forecast':expanded?'Projected final':'Projection history';
 return <article ref={ref} className={`projection-journey ${expanded?'expanded':'collapsed'}`} data-projection-key={bundle.key}>
  <button className="projection-toggle" aria-expanded={expanded} onClick={()=>setChoice(!expanded)}>
   <span><strong>{title}</strong>{!expanded&&<small>See projected finish and actual score</small>}</span><span aria-hidden="true">{expanded?'⌃':'⌄'}</span>
  </button>
  {expanded&&<div className="projection-body">
   <p className="projection-date">Archived game · {eventReaderTime.range(bundle.start,bundle.end)} · Your local time</p>
   <div className="projection-teams">{(['home','away'] as const).map(side=>{
    const difference=finalDifference(bundle,side);
    return <div className={`projection-team projection-${side}`} key={side}><b>{bundle[side]}</b>
     <strong>{isFinal?(bundle.result?number(bundle.result[side]):'Final score unavailable'):current?number(current[side]):'No recent projection'}</strong>
     <span>{isFinal?'final score':current?'projected final':''}</span>
     {!isFinal&&bundle.latestActual&&<span>{number(bundle.latestActual[side])} scored</span>}
     {isFinal&&<><span>{bundle.baseline?'Pregame '+number(bundle.baseline[side]):'Pregame projection unavailable'}</span>{difference!==null&&<b className="projection-difference">{Math.abs(difference)<.05?'Matched pregame':`${number(Math.abs(difference))} points ${difference>0?'above':'below'} pregame`}</b>}</>}
    </div>
   })}</div>
   <div className="projection-times">
    {isFinal&&bundle.baseline&&<p>Pregame projection · {clock(bundle.baseline.at)}</p>}
    <p>{isFinal?'Last forecast':'Archived projection'} · {clock(bundle.latest.at)}</p>
    <p>{isFinal?'Game completed · '+clock(bundle.end):bundle.latestActual?'Score observed · '+clock(bundle.latestActual.at):'Score observation unavailable'}</p>
    {!isFinal&&!current&&<p>No recent projection. Dated history remains below.</p>}
   </div>
   <svg onClick={event=>{
    const matrix=event.currentTarget.getScreenCTM();if(!matrix)return;
    const at=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
    if(at.x<left||at.x>right||at.y<top||at.y>bottom)return;
    const time=Date.parse(bundle.start)+(at.x-left)/(right-left)*(Date.parse(bundle.end)-Date.parse(bundle.start));
    setSelected(chooseProjection(bundle,new Date(time).toISOString()));setInspectionOpen(true);setChoice(true);
   }} className="projection-svg" viewBox="0 0 410 268" role="img" aria-label={`${bundle.home} and ${bundle.away} projected final points in solid lines and actual scores in dashed steps. Missing projection readings remain gaps.`}>
    <text x={left} y={12} className="projection-axis">Points</text>
    {ticks.map(value=><g key={value}><line x1={left} x2={right} y1={y(value)} y2={y(value)} className="projection-grid"/><text x={left-6} y={y(value)+5} textAnchor="end" className="projection-axis">{number(value)}</text></g>)}
    {bundle.markers.map((marker,i)=><g key={marker.at+marker.label}><line x1={x(marker.at)} x2={x(marker.at)} y1={top} y2={bottom} className="projection-period"/><text x={x(marker.at)+3} y={i%2?26:16} className="projection-axis">{marker.label}</text></g>)}
    {(['home','away'] as const).map(side=><g key={side} className={`projection-${side}`}>
     {bundle.segments.map((points,i)=>points.length===1?<circle key={i} cx={x(points[0].at)} cy={y(points[0][side])} r={3} fill="currentColor"/>:<path key={i} d={stepPath(points,side,x,y)} fill="none" stroke="currentColor" strokeWidth={2.5}/>)}
     <path d={stepPath(bundle.actuals,side,x,y)} fill="none" stroke="currentColor" strokeWidth={2} strokeDasharray="5 4" opacity={.65}/>
    </g>)}
    {selected!==null&&inspected&&<g className="projection-selected-marks">
     <line x1={x(inspected.at)} x2={x(inspected.at)} y1={top} y2={bottom} className="projection-inspector"/>
     {(['home','away'] as const).map(side=><rect key={side} className={`projection-${side}`} x={x(inspected.at)-5} y={y(inspected[side])-5} width={10} height={10} fill="var(--surface-card)" stroke="currentColor" strokeWidth={2.5}/>)}
    </g>}
    <text x={left} y={258} className="projection-axis">{axisStamp(bundle.start)}</text><text x={right} y={258} textAnchor="end" className="projection-axis">{axisStamp(bundle.end)}</text>
   </svg>
   <div className="projection-key"><span>━ Projected final</span><span>┄ Actual score · steps</span></div>
   <p className="projection-help">Missing projection readings stay gaps.</p>
   <details className="projection-inspection" open={inspectionOpen} onToggle={event=>{setInspectionOpen(event.currentTarget.open);if(event.currentTarget.open)setChoice(true)}}><summary>Inspect recorded projections</summary>
    <div className="projection-inspection-controls">
     <button aria-label="Previous projection reading" disabled={!previous} onClick={()=>setSelected(previous)}>‹</button>
     <select aria-label="Recorded projection pair" value={inspection?.observation.id??''} onChange={event=>{const row=records.find(r=>r.id===event.target.value);if(row)setSelected(recordChoice(row))}}>
      {!inspection&&<option value="">Reading unavailable</option>}
      {records.map(row=><option key={row.id} value={row.id}>{observationLabel(row)} · {number(row.point.home)}–{number(row.point.away)}</option>)}
     </select>
     <button aria-label="Next projection reading" disabled={!next} onClick={()=>setSelected(next)}>›</button>
    </div>
    <div className="projection-reading" aria-live="polite" aria-atomic="true">
     {inspection&&inspected?<>
      <p>Recorded forecast · {observationLabel(inspection.observation)}</p>
      <div className="projection-teams">{(['home','away'] as const).map(side=><div key={side} className={`projection-team projection-${side}`}><b>{bundle[side]}</b><strong>{number(inspected[side])}</strong><span>projected points</span></div>)}</div>
      <p>{inspection.lastScore?`Last score before this quote: ${number(inspection.lastScore.home)}–${number(inspection.lastScore.away)} · ${clock(inspection.lastScore.at)}`:'No earlier score observation'}</p>
     </>:<><p><b>{selected?.kind==='gap'?'No projection reading in this gap':'Selected reading unavailable in this update'}</b></p><p>Choose a recorded reading or use the arrows.</p></>}
    </div>
    <p>Shared timestamps are numbered. Score and forecast have independent observation times.</p>
    <button onClick={()=>setSelected(null)} disabled={!records.length}>Return to latest recorded pair</button>
   </details>
   <details className="projection-guide"><summary>How to read this</summary><p>Solid lines show each team’s projected finish; dashed steps show points already scored. Projection source: {bundle.source}, using full-game margin and total recorded together. This is separate from Bain Luck’s blended win probability. Period labels are observed boundaries and may be late. Forecasts are never joined to final results.</p></details>
  </div>}
 </article>;
}
