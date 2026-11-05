import {capturedProfile,dgMarkets,dgWire,forecastValue,type ForecastMarket} from './golfOutlookEvidence.ts';
export const outlookBands=['A–C','D–G','H–L','M–P','Q–S','T–Z'] as const;
export type OutlookBand=typeof outlookBands[number];
export type OutlookPickerState={view:'suggested'|'all';band:OutlookBand};
export const initialOutlookPicker=():OutlookPickerState=>({view:'suggested',band:'A–C'});
export function outlookBand(name:string):OutlookBand {
 const first=name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase()[0];
 return first<='C'?'A–C':first<='G'?'D–G':first<='L'?'H–L':first<='P'?'M–P':first<='S'?'Q–S':'T–Z';
}
export const outlookPercent=(value:number|null)=>value===null?'Unavailable':value===0?'0%':value<.001?'<0.1%':`${Math.round(value*1000)/10}%`;
export function outlookChoices(markets:ForecastMarket[]=dgMarkets){
 const winners=markets.filter(m=>m.source==='datagolf'&&m.external_id===`${dgWire.eventKey}:win`);
 if(winners.length!==1)return [];
 return winners[0].outcomes.filter(row=>winners[0].outcomes.filter(r=>r.name===row.name||r.id===row.id).length===1).map(row=>{
  const profile=capturedProfile(row.name,markets);
  return {id:row.id,name:row.name,band:outlookBand(row.name),values:profile.map(p=>forecastValue(p?.row.probability)),originals:profile};
 });
}
export type OutlookChoice=ReturnType<typeof outlookChoices>[number];
export function suggestedOutlooks(selected:string,rows:OutlookChoice[]=outlookChoices()){
 const chosen=rows.find(r=>r.name===selected);
 const ranked=rows.filter(r=>r.values[0]!==null&&r.name!==selected).sort((a,b)=>b.values[0]!-a.values[0]!||a.name.localeCompare(b.name));
 return [...(chosen?[chosen]:[]),...ranked.slice(0,3)];
}
export function outlooksInBand(band:OutlookBand,rows:OutlookChoice[]=outlookChoices()){
 return rows.filter(row=>row.band===band).sort((a,b)=>a.name.localeCompare(b.name));
}
