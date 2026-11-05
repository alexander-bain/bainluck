// Preview entry points only. These are captured specimens, not production routes.
export function previewRoute(search:string,known:readonly string[]){
 const params=new URLSearchParams(search),events=params.getAll('event'),stages=params.getAll('stage');
 const requested=events[0],valid=events.length<=1&&(!requested||known.includes(requested));
 const event=valid?(requested||'nba'):'nba';
 const hasStage=event==='horse-racing'||event==='soccer'||event==='nfl-live'||event==='aflw-refresh';
 const stageValid=stages.length<=1&&(!stages[0]||(hasStage&&['earlier','final'].includes(stages[0])));
 return {event,stage:hasStage&&stageValid&&stages[0]?stages[0]:'final',warning:!valid||!stageValid?'Preview link not recognized completely. Check the selected event and stage.':null};
}
