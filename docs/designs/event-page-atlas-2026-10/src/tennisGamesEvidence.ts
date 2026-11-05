import retained from './tennisGamesEvidence.json' with {type:'json'};
export type TennisGamesInput=typeof retained;
export function tennisGamesEvidence(input:TennisGamesInput){
 const d=input,l=d.linescore,integer=(n:unknown):n is number=>typeof n==='number'&&Number.isSafeInteger(n)&&n>=0&&n<1000;
 if(d.eventID!==15310688||d.home!=='Alexander Zverev'||d.away!=='Ben Shelton'||d.status!=='completed'||l?.source!=='espn'||!Array.isArray(l.sets)||!l.sets.length||!integer(d.homeSets)||!integer(d.awaySets)||!integer(l.home_games)||!integer(l.away_games))return null;
 if(!l.sets.every(s=>Array.isArray(s)&&s.length===2&&s.every(integer)&&s[0]!==s[1]))return null;
 const home=l.sets.reduce((n,s)=>n+s[0],0),away=l.sets.reduce((n,s)=>n+s[1],0);
 if(home!==l.home_games||away!==l.away_games||l.sets.filter(s=>s[0]>s[1]).length!==d.homeSets||l.sets.filter(s=>s[0]<s[1]).length!==d.awaySets)return null;
 const p=d.projection,valid=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
 const projection=p&&valid(p.projected_home_score)&&valid(p.projected_away_score)&&Number.isFinite(Date.parse(p.timestamp))&&Date.parse(p.timestamp)<Date.parse(d.commenceTime)?{home:p.projected_home_score,away:p.projected_away_score,total:p.projected_home_score+p.projected_away_score,at:p.timestamp}:null;
 return {home,away,total:home+away,source:l.source,capturedAt:d.capturedAt,actualObservedAt:d.actualObservedAt,projection};
}
export const retainedTennisGames=tennisGamesEvidence(retained);
