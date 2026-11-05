import {retainContenderColors} from './contenderColors.ts';
import {beforeHours,beforeFrame,beforeCohort,type BeforeFrame} from './dunhillBefore.ts';
export const dunhillHours=beforeHours();
export const dunhillEnd=dunhillHours.at(-1)!;
const finalFrame=beforeFrame(dunhillEnd)!;
export type DunhillReading={at:number;ids:string[];pinned:string|null;highlighted:string;full:boolean;colorSlots:Record<string,number>};
export type DunhillAction={type:'inspect';at:number}|{type:'choose';id:string}|{type:'highlight';id:string}|{type:'scale'}|{type:'latest'};
export function initialDunhillReading():DunhillReading{return {at:dunhillEnd,ids:beforeCohort(finalFrame).map(r=>r.id),pinned:null,highlighted:beforeCohort(finalFrame)[0].id,full:false,colorSlots:retainContenderColors({},beforeCohort(finalFrame).map(r=>r.id))};}
export function dunhillReadingReducer(state:DunhillReading,action:DunhillAction):DunhillReading {
 if(action.type==='inspect')return dunhillHours.includes(action.at)?{...state,at:action.at}:state;
 if(action.type==='highlight')return state.ids.includes(action.id)?{...state,highlighted:action.id}:state;
 if(action.type==='latest')return {...state,at:dunhillEnd};
 if(action.type==='scale')return {...state,full:!state.full};
 const frame=beforeFrame(state.at)!;
 if(!frame.entries.some(r=>r.id===action.id))return state;
 const ids=beforeCohort(frame,action.id).map(r=>r.id);
 return {...state,pinned:action.id,highlighted:action.id,ids,colorSlots:retainContenderColors(state.colorSlots,ids)};
}
/** Inspecting history never silently changes the followed golfers, clock or scale. */
export function dunhillReadingFrame(state:DunhillReading){
 const frame=beforeFrame(state.at)!;
 return {...frame,colorSlots:state.colorSlots,cohort:state.ids.map(id=>frame.entries.find(r=>r.id===id)).filter((r):r is BeforeFrame['entries'][number]=>!!r),domain:[dunhillHours[0],dunhillEnd] as const,ceiling:state.full?1:finalFrame.ceiling};
}
export function dunhillChance(value:number|null|undefined){return value==null?'Not recorded':`${(value*100).toFixed(1).replace(/\.0$/,'')}%`;}
/** Spread direct endpoint labels without altering the probability coordinates. */
export function dunhillLabels(entries:{id:string;y:number}[],top:number,bottom:number,gap=24){
 const sorted=[...entries].sort((a,b)=>a.y-b.y);
 const result=sorted.map((r,i)=>({...r,labelY:Math.max(top+i*gap,r.y)}));
 for(let i=1;i<result.length;i++)result[i].labelY=Math.max(result[i].labelY,result[i-1].labelY+gap);
 const overshoot=Math.max(0,(result.at(-1)?.labelY??bottom)-bottom);
 return result.map(r=>({...r,labelY:r.labelY-overshoot}));
}

/** Short visual names supplement the full names above the plot; never become identity keys. */
export function dunhillTraceName(name:string,names:readonly string[]){
 const surname=name.split(' ').at(-1)!;
 const shared=names.filter(n=>n.split(' ').at(-1)===surname).length>1;
 const label=shared?`${name[0]}. ${surname}`:surname;
 return label.length>14?`${label.slice(0,13)}…`:label;
}

/** Labels follow the inspection cursor; their leader must never resemble future price history. */
export function dunhillTraceLeader(pointX:number,selectedX:number,pointY:number,labelY:number,recorded:boolean){
 const labelX=Math.min(311,selectedX+17);
 const path=recorded?`M${pointX+5},${pointY} L${labelX-11},${labelY} L${labelX-5},${labelY}`:`M${labelX-11},${labelY} L${labelX-5},${labelY}`;
 return {labelX,path};
}
