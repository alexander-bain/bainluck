type Point = {row_key:string;x:number};
// Contract identity survives reordering; a missing selection is never a different threshold.
export function selectedProfilePoint<T extends Point>(points:T[],rowKey:string){
 return points.find(point=>point.row_key===rowKey)??null;
}
