import wire from './markets.json' with {type:'json'};
import flags from './finalCatalogFlags.json' with {type:'json'};
export type ReceptionRow=(typeof wire)[number];
export const receptionID='catches:Dontayvion Wicks' as const;
const bindings=[
 {market:63066495,line:1.5,keys:['player_props:582','player_props:647']},
 {market:63066551,line:2.5,keys:['player_props:584','player_props:648']},
 {market:63066552,line:3.5,keys:['player_props:586','player_props:649']},
 {market:63001576,line:4.5,keys:['player_props:588','player_props:650']},
 {market:62705546,line:5.5,keys:['player_props:590','player_props:651']},
] as const;
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n);
export function receptionProfile(phase:string,rows:readonly ReceptionRow[]=wire,eventID=14780549){
 if(eventID!==14780549)return null;
 const own=rows.filter(r=>bindings.some(b=>b.market===r._market_id));
 if(own.length!==10||new Set(own.map(r=>r.row_key)).size!==10)return null;
 const points=bindings.map(b=>{
  const pair=own.filter(r=>r._market_id===b.market);
  if(pair.length!==2||pair.some(r=>r.source!=='polymarket'||r.category!=='player_props'||r.period!=null||r.market_name!=='Dontayvion Wicks: Receptions O/U '+b.line||r.threshold!==b.line||!b.keys.some(k=>k===r.row_key)))return null;
  const over=pair.find(r=>r.outcome_name==='Over'&&r._inverted===false),under=pair.find(r=>r.outcome_name==='Under'&&r._inverted===true);
  if(!over||!under)return null;
  const p=over.pregame_mark;
  const baseline=finite(p)&&p>=0&&p<=1&&under.pregame_mark===p?p:null;
  return {needed:b.line+.5,line:b.line,over,under,baseline};
 });
 if(points.some(p=>p===null))return null;
 const complete=points.filter(p=>p!==null),a=own[0].actual;
 const actual=phase==='Final'&&finite(a)&&Number.isSafeInteger(a)&&a>=0&&own.every(r=>r.actual===a)?a:null;
 const scored=complete.map(q=>({q,score:q.baseline===null?null:phase!=='Final'?q.baseline:actual===null?null:actual>=q.needed?1-q.baseline:q.baseline}));
 const ranked=scored.filter(x=>x.score!==null).sort((a,b)=>b.score!-a.score!||a.q.needed-b.q.needed);
 return {name:'Dontayvion Wicks',id:receptionID,points:complete,actual,defaultKey:ranked[0]?.q.over.row_key??complete[0].over.row_key,score:ranked[0]?.score??null};
}
export function receptionPoint(phase:string,key?:string){const p=receptionProfile(phase);return p?.points.find(q=>q.over.row_key===(key??p.defaultKey))??p?.points[0]??null}
export function receptionOwns(row:ReceptionRow){return receptionProfile('Final')?.points.some(q=>[q.over,q.under].some(r=>r.row_key===row.row_key&&r._market_id===row._market_id&&r.outcome_name===row.outcome_name&&r.market_name===row.market_name&&r.source===row.source&&r.threshold===row.threshold&&r._inverted===row._inverted&&r.category===row.category&&row.period==null))??false}
/** A sporting threshold comparison is separate from a market's settlement. */
export function receptionComparison(actual:number|null,needed:number){return actual===null?'Actual unavailable':actual===needed?'Reached this milestone':actual>=needed?`${actual-needed} ${actual-needed===1?'catch':'catches'} beyond this milestone`:`${needed-actual} ${needed-actual===1?'catch':'catches'} short of this milestone`}
export function receptionSettlement(row:ReceptionRow,phase:string){
 if(phase!=='Final')return null;
 return flags[row.row_key as keyof typeof flags]!==true&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'?(row.is_winner?'Won':'Lost'):'Unconfirmed';
}

export function receptionOriginalComparison(actual:number|null,needed:number,under:boolean){
 if(actual===null)return 'Unavailable';
 if(under){const limit=needed-1;return `${actual<=limit?'at or below':'above'} the limit of ${limit} ${limit===1?'catch':'catches'}`}
 return `${actual>=needed?'at or above':'below'} the ${needed} catches needed`;
}
