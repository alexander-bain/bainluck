import capture from './racingEvidence.json' with {type:'json'};
import {BEFORE,FINAL,raceStage} from './racingLifecycle.ts';
export type PathRow=typeof capture.rows[number];
export type PodiumDriver={id:string;name:string;win:PathRow;podium:PathRow};
export function podiumDrivers(rows:PathRow[]=capture.rows):PodiumDriver[]{
 const ids=[...new Set(rows.filter(r=>r.family==='winner'||r.family==='podium').map(r=>r.athleteID).filter((id):id is string=>typeof id==='string'&&id.length>0))];
 return ids.flatMap(id=>{
  const wins=rows.filter(r=>r.family==='winner'&&r.athleteID===id),pods=rows.filter(r=>r.family==='podium'&&r.athleteID===id);
  if(wins.length!==1||pods.length!==1)return [];
  const win=wins[0],podium=pods[0];
  if(win.eventID!==1123912||podium.eventID!==1123926||win.selected!=='Yes'||podium.selected!=='Yes'||win.name!==podium.name||!win.conditionID||!podium.conditionID||!win.tokenID||!podium.tokenID||win.key===podium.key)return [];
  return [{id,name:win.name,win,podium}];
 }).sort((a,b)=>(pathBaseline(b.podium)?.value??-1)-(pathBaseline(a.podium)?.value??-1)||a.name.localeCompare(b.name));
}
export function pathBaseline(row:PathRow){const b=row.baseline;return b&&Number.isFinite(b.value)&&b.value>0&&b.value<1&&Number.isFinite(Date.parse(b.at))&&Date.parse(b.at)<Date.parse(capture.start)&&Date.parse(b.at)>=Date.parse(capture.start)-86400000&&Number.isFinite(b.size)&&b.size>0?b:null;}
export function pathSnapshot(driver:PodiumDriver,stage:number){
 if(!raceStage(stage))return null;
 const position=stage===FINAL&&driver.win.position===driver.podium.position?driver.win.position:null;
 return {driver,phase:stage===BEFORE?'before':stage===FINAL?'final':'in-race',position,
  win:{key:driver.win.key,baseline:pathBaseline(driver.win),result:stage===FINAL?driver.win.result:null},
  podium:{key:driver.podium.key,baseline:pathBaseline(driver.podium),result:stage===FINAL?driver.podium.result:null}};
}
export const podiumPathDrivers=podiumDrivers();
export function pathWindow(selected:string,drivers=podiumPathDrivers){const index=drivers.findIndex(d=>d.id===selected);if(index<0)return [];const start=Math.min(Math.max(0,index-2),Math.max(0,drivers.length-5));return drivers.slice(start,start+5);}
export const defaultPathDriver=podiumPathDrivers.find(d=>d.name==='Kimi Antonelli')?.id??podiumPathDrivers[0]?.id;
export function pathPlace(n:number){const mod=n%100;return `${n}${mod>=11&&mod<=13?'th':n%10===1?'st':n%10===2?'nd':n%10===3?'rd':'th'}`;}
export function pathShortName(name:string){return name.replace(/\s+Jr\.$/,'').split(' ').at(-1)??name;}
