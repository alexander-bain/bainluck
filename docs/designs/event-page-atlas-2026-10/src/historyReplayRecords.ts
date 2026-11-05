import type {FinalHistoryPoint} from './finalHistoryEvidence';
export type HistoryUpdateMode='original'|'reverse'|'thin'|'omit'|'empty';
/** Preview-only membership/order changes. Values and clocks are unchanged captured records. */
export function historyUpdatePreview<T extends FinalHistoryPoint>(points:T[],mode:HistoryUpdateMode,omittedAt:number|null){
 let received=mode==='empty'?[]:mode==='thin'?points.filter((_,i)=>i%2===0):mode==='omit'&&omittedAt!==null?points.filter(p=>p.t!==omittedAt):[...points];
 if(mode==='reverse')received.reverse();
 received=received.map((p,index)=>({...p,index}));
 const ordered=received.sort((a,b)=>a.t-b.t);let segment=0;
 return ordered.map((p,i)=>{if(i&&(p.segment!==ordered[i-1].segment||p.t-ordered[i-1].t>300_000))segment++;return {...p,segment};});
}
