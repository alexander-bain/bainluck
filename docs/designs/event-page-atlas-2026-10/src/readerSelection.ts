/** Identity survives re-ranking. Removal chooses the closest surviving old neighbor;
 * ties prefer the following card. Only when no old card survives use the new first. */
export function reconcileReaderSelection(previous:string[],selected:string|null,next:string[]):string|null {
 if(selected!==null&&next.includes(selected))return selected;
 if(!next.length)return null;
 const index=previous.indexOf(selected??'');
 if(index>=0){
  for(let distance=1;distance<previous.length;distance++){
   for(const candidate of [previous[index+distance],previous[index-distance]]){
    if(candidate!==undefined&&next.includes(candidate))return candidate;
   }
  }
 }
 return next[0];
}
