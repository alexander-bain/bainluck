/** One observation controls both plotting and dwell, so a watched card cannot be blank. */
export function storyCardVisibility(entry:{isIntersecting:boolean;intersectionRatio:number},requireCardVisibility:boolean){
 const visible=entry.isIntersecting;
 return {visible,watched:requireCardVisibility&&visible&&Number.isFinite(entry.intersectionRatio)&&entry.intersectionRatio>=.55};
}
