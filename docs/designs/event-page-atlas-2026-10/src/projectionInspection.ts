import type {ProjectionBundle,ProjectionPoint} from './projectionEvidence';
export type ProjectionObservation={id:string;point:ProjectionPoint;ordinalAtTime:number;countAtTime:number};
export type ProjectionChoice={kind:'record';id:string;at:string}|{kind:'gap';at:string};
export function projectionObservations(bundle:ProjectionBundle):ProjectionObservation[]{
 const points=bundle.segments.flat(),counts=new Map<number,number>(),seen=new Map<string,number>(),times=new Map<number,number>();
 for(const point of points){const time=Date.parse(point.at);counts.set(time,(counts.get(time)??0)+1)}
 return points.map(point=>{
  const time=Date.parse(point.at),base=JSON.stringify([bundle.eventID,bundle.sourceKey,time,point.home,point.away]);
  const occurrence=seen.get(base)??0;seen.set(base,occurrence+1);
  const ordinal=(times.get(time)??0)+1;times.set(time,ordinal);
  return {id:JSON.stringify([base,occurrence]),point,ordinalAtTime:ordinal,countAtTime:counts.get(time)!};
 });
}
export const recordChoice=(row:ProjectionObservation):ProjectionChoice=>({kind:'record',id:row.id,at:row.point.at});
export function inspectProjection(bundle:ProjectionBundle,choice:ProjectionChoice|null){
 if(choice?.kind!=='record')return null;
 const observation=projectionObservations(bundle).find(row=>row.id===choice.id);
 if(!observation)return null;
 // Drawing-only boundary holds are not score observations.
 const lastScore=(bundle.scoreObservations??[]).filter(p=>Date.parse(p.at)<=Date.parse(observation.point.at)).reduce<ProjectionPoint|null>((last,p)=>!last||Date.parse(p.at)>=Date.parse(last.at)?p:last,null);
 return {observation,lastScore};
}
export function chooseProjection(bundle:ProjectionBundle,at:string):ProjectionChoice{
 const time=Date.parse(at),gap:ProjectionChoice={kind:'gap',at};
 if(!Number.isFinite(time)||time<Date.parse(bundle.start)||time>Date.parse(bundle.end))return gap;
 const segment=bundle.segments.find(s=>s.length&&time>=Date.parse(s[0].at)&&time<=Date.parse(s.at(-1)!.at));
 if(!segment)return gap;
 const nearest=segment.reduce((a,b)=>Math.abs(Date.parse(b.at)-time)<Math.abs(Date.parse(a.at)-time)?b:a);
 const rows=projectionObservations(bundle).filter(row=>Date.parse(row.point.at)===Date.parse(nearest.at));
 return rows.length?recordChoice(rows.at(-1)!):gap;
}
export function stepProjection(bundle:ProjectionBundle,choice:ProjectionChoice|null,forward:boolean):ProjectionChoice|null{
 const rows=projectionObservations(bundle);
 if(!choice){const row=forward?rows[0]:rows.at(-1);return row?recordChoice(row):null}
 const index=choice.kind==='record'?rows.findIndex(row=>row.id===choice.id):-1;
 if(index>=0){const next=rows[index+(forward?1:-1)];return next?recordChoice(next):null}
 const row=forward?rows.find(r=>Date.parse(r.point.at)>Date.parse(choice.at)):[...rows].reverse().find(r=>Date.parse(r.point.at)<Date.parse(choice.at));
 return row?recordChoice(row):null;
}
