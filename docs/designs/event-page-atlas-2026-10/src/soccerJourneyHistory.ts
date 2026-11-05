import type {SoccerLifecycleContext} from './soccerLifecycle';
export type JourneyHistoryPoint={at:string;value:number};
// Read only the displayed frame, including while newer arrivals wait.
export function journeyHistoryPoints(context:SoccerLifecycleContext):JourneyHistoryPoint[]{
 return context.history.filter(p=>Date.parse(p.at)<=Date.parse(context.at));
}
export function journeyHistorySelection(context:SoccerLifecycleContext,at:string|null){
 const points=journeyHistoryPoints(context),index=at===null?-1:points.findIndex(p=>p.at===at),point=points[index<0?points.length-1:index];
 if(!point)throw new Error('No displayed match observation');
 const score=context.phase==='before'?null:context.scores.filter(s=>Date.parse(s.timestamp)<=Date.parse(point.at)).at(-1)??null;
 return {point,index:index<0?points.length-1:index,inspecting:index>=0,score};
}
export function journeyHistoryPlot(context:SoccerLifecycleContext){
 const points=journeyHistoryPoints(context);
 return points.flatMap((p,i)=>{const current={time:Date.parse(p.at),chance:p.value*100};
 return i&&Date.parse(p.at)-Date.parse(points[i-1].at)>300000?[{time:(Date.parse(p.at)+Date.parse(points[i-1].at))/2,chance:null},current]:[current]});
}
