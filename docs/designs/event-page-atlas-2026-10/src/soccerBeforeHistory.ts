import capture from './soccerBeforeHistory.json' with {type:'json'};
export const soccerBeforeCapture=capture;
export function beforeSoccerHistory(cutoff:string=capture.baseline.at){
 const time=Date.parse(cutoff);if(!Number.isFinite(time)||time>Date.parse(capture.baseline.at))throw new Error('Invalid pre-match cutoff');
 return capture.points.filter(p=>Date.parse(p.at)<=time);
}
export function beforeSoccerPlot(cutoff:string=capture.baseline.at){
 const points=beforeSoccerHistory(cutoff);return points.flatMap((p,i)=>{
 const entry={time:Date.parse(p.at),chance:p.value*100};
 return i&&Date.parse(p.at)-Date.parse(points[i-1].at)>7200000?[{time:(Date.parse(p.at)+Date.parse(points[i-1].at))/2,chance:null},entry]:[entry];
 });
}
export function beforeSoccerInspection(index:number){const points=beforeSoccerHistory();if(!Number.isInteger(index)||index<0||index>=points.length)throw new Error('Unknown observation');return points[index]}
