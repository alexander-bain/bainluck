import {selectStory,holdStories,type StoryStreamState} from './storyStreamState.ts';
import {hockeyBefore,type BeforeProp} from './hockeyBeforeEvidence.ts';
import type {ContributionKind} from './hockeyContributions';
import type {ContributionVisualProfile} from './HockeyContributionVisual';
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
/** Accept only the whitelisted pre-game snapshot; no final row or original record crosses this boundary. */
export function beforeContributionProfiles(rows:BeforeProp[],eventID:unknown,kind:ContributionKind):ContributionVisualProfile<BeforeProp>[]{
 if(eventID!==hockeyBefore.eventID)return [];
 const market=kind==='points'?64871068:64870807;
 const admitted=rows.filter(p=>p.family===kind&&p.marketID===market&&p.source==='kalshi'&&p.player!==null&&p.count!==null&&Number.isInteger(p.count)&&p.count>=1&&p.count<=3&&p.title===p.player+': '+p.count+'+'&&hockeyBefore.props.filter(q=>q.key===p.key&&stable(p)===stable(q)).length===1);
 const unique=admitted.filter(p=>admitted.filter(q=>q.key===p.key).length===1);
 const names=[...new Set(unique.map(p=>p.player!))],preferred=['Quinn Hughes','Kirill Kaprizov','Joel Eriksson Ek'];
 names.sort((a,b)=>(preferred.includes(a)?preferred.indexOf(a):99)-(preferred.includes(b)?preferred.indexOf(b):99)||a.localeCompare(b));
 return names.map(name=>{const props=unique.filter(p=>p.player===name).sort((a,b)=>a.count!-b.count!),team=props[0].team;return {name,team:team==='home'?'Minnesota':team==='away'?'Boston':null,records:props.map(row=>({key:row.key,threshold:row.count!,baseline:row.chance!==null&&row.at!==null?{value:row.chance,at:row.at}:null,actual:null,result:null,row}))}});
}

export function activateBeforeReader(stream:StoryStreamState,id:string){return id==='history'?holdStories(stream):selectStory(stream,id)}

export function beforeContributionOrder(rows:BeforeProp[],eventID:unknown){return ['scorers',...(['points','assists'] as const).filter(kind=>beforeContributionProfiles(rows,eventID,kind).length>0),'totals','first']}
