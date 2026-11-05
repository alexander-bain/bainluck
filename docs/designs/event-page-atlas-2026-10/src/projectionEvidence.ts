export type ProjectionPoint={at:string;home:number;away:number};
export type ProjectionBundle={key:string;eventID:number;home:string;away:string;source:string;sourceKey:string;phase:'during'|'after';start:string;end:string;yMax:number;latest:ProjectionPoint;latestActual?:ProjectionPoint;latestUnavailable:boolean;segments:ProjectionPoint[][];actuals:ProjectionPoint[];scoreObservations?:ProjectionPoint[];markers:{at:string;label:string}[];result?:ProjectionPoint;baseline?:ProjectionPoint;withheldCount:number};
export function headlineProjection(bundle:ProjectionBundle|undefined,mode:string):ProjectionPoint|null {
 return bundle&&bundle.phase!=='after'&&!bundle.latestUnavailable&&mode==='captured'?bundle.latest:null;
}
export function finalDifference(bundle:ProjectionBundle,side:'home'|'away'):number|null {
 return bundle.result&&bundle.baseline?bundle.result[side]-bundle.baseline[side]:null;
}
export function stepPath(points:ProjectionPoint[],side:'home'|'away',x:(at:string)=>number,y:(value:number)=>number):string {
 return points.map((point,i)=>i?`H${x(point.at)}V${y(point[side])}`:`M${x(point.at)},${y(point[side])}`).join('');
}
