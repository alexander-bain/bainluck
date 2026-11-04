import type {BeforeFrame} from './dunhillBefore.ts';
export type DunhillChoiceMode='chances'|'movement'|'all';
export type DunhillChoiceState={mode:DunhillChoiceMode;band:string;page:number};
export const initialDunhillChoice=():DunhillChoiceState=>({mode:'chances',band:'A–D',page:0});
const ranges=[['A–D','A','D'],['E–H','E','H'],['I–L','I','L'],['M–P','M','P'],['Q–T','Q','T'],['U–Z','U','Z']] as const;
const surname=(name:string)=>name.trim().split(/\s+/).at(-1)??'';
export function dunhillNameBand(name:string){
 const first=surname(name).normalize('NFD').replace(/\p{M}/gu,'').toUpperCase()[0]??'';
 return ranges.find(([,from,to])=>first>=from&&first<=to)?.[0]??'#';
}
export function dunhillChoices(frame:BeforeFrame,state:DunhillChoiceState){
 const bands=[...ranges.map(([label])=>label),...(frame.entries.some(r=>dunhillNameBand(r.name)==='#')?['#']:[])].map(label=>({label,count:frame.entries.filter(r=>dunhillNameBand(r.name)===label).length}));
 const band=bands.some(b=>b.label===state.band)?state.band:bands[0].label;
 const rows=state.mode==='chances'?frame.ranked:state.mode==='movement'?frame.movement.filter(r=>r.change!==0):frame.entries.filter(r=>dunhillNameBand(r.name)===band).sort((a,b)=>surname(a.name).localeCompare(surname(b.name))||a.name.localeCompare(b.name));
 const pages=Math.max(1,Math.ceil(rows.length/12)),page=Math.min(pages-1,Math.max(0,Math.trunc(Number.isFinite(state.page)?state.page:0)));
 return {rows,visible:rows.slice(page*12,(page+1)*12),page,pages,bands,band,start:rows.length?page*12+1:0,end:Math.min(rows.length,(page+1)*12)};
}

/** Shared symmetric comparison scale; small probabilities must not hide meaningful changes. */
export function dunhillMovementScale(rows:BeforeFrame['entries']){
 return Math.max(.005,Math.ceil(Math.max(0,...rows.map(r=>Math.abs(r.change??0)))*200)/200);
}
