import {featuredGolfers,journeyFor,journeyNames,windowPoints,type JourneyWindow} from './golfJourneyEvidence.ts';
export const golferBands=['A–C','D–G','H–L','M–P','Q–S','T–Z'] as const;
export type GolferBand=typeof golferBands[number];
export type GolfPickerState={all:boolean;more:boolean;band:GolferBand};
export const initialGolfPicker=():GolfPickerState=>({all:false,more:false,band:'A–C'});
// This fixture has two compound surnames; production should supply structured sort names.
const compoundSurnames:Record<string,string>={'Erik Van Rooyen':'Van Rooyen','Adrien Dumont De Chassart':'Dumont De Chassart'};
const surname=(name:string)=>(compoundSurnames[name]??name.trim().split(/\s+/).at(-1)!).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
export function golferBand(name:string):GolferBand {const first=surname(name)[0];return first<='C'?'A–C':first<='G'?'D–G':first<='L'?'H–L':first<='P'?'M–P':first<='S'?'Q–S':'T–Z'}
export const golfersInBand=(band:GolferBand)=>journeyNames.filter(name=>golferBand(name)===band).sort((a,b)=>surname(a).localeCompare(surname(b))||a.localeCompare(b));
export function golfChoice(name:string,period:JourneyWindow,through?:string){
 const row=journeyFor(name);if(!row)return null;
 const points=windowPoints(name,period,through),last=points.at(-1)??null;
 const cutoff=through?Date.parse(through):Infinity;
 const baseline=row.baseline&&Date.parse(row.baseline.timestamp)<=cutoff?row.baseline:null;
 return {id:row.original.id,name,baseline,last,change:last&&baseline?last.probability-baseline.probability:null,count:points.length};
}
export function golfChoices(selected:string,period:JourneyWindow,through?:string){
 const inChart=featuredGolfers(period,selected,through).map(n=>golfChoice(n,period,through)!);
 const more=journeyNames.filter(n=>!inChart.some(r=>r.name===n)).map(n=>golfChoice(n,period,through)!).filter(r=>r.last).sort((a,b)=>b.last!.probability-a.last!.probability||a.name.localeCompare(b.name));
 return {inChart,more,available:inChart.filter(r=>r.last).length+more.length};
}
export function choiceWindow(period:JourneyWindow){return period==='All'?'Week':period==='Pre'?'Before tournament':period}
export function chanceMovement(change:number|null){
 if(change===null)return 'Before-tournament comparison unavailable';
 if(change===0)return 'Unchanged from before tournament';
 const magnitude=Math.abs(change)*100;
 return `${change>0?'Up':'Down'} ${magnitude<0.1?'less than 0.1':magnitude.toFixed(1)} percentage points vs before tournament`;
}
