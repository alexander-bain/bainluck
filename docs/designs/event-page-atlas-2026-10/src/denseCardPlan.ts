export interface CardMeasurement {height:number;fullWidth?:boolean}
export interface CardFrame {x:number;y:number;width:number;height:number}
/** Source order stays intact. A full-width card is a barrier across all columns. */
export function denseCardPlan(width:number,columns:number,gap:number,cards:CardMeasurement[]):{frames:CardFrame[];height:number}{
 const count=Number.isFinite(columns)?Math.max(1,Math.floor(columns)):1;
 const safeWidth=Number.isFinite(width)?Math.max(0,width):0;
 const spacing=Number.isFinite(gap)?Math.max(0,gap):0;
 const cardWidth=Math.max(0,(safeWidth-spacing*(count-1))/count);
 const bottoms=Array(count).fill(0) as number[];
 const used=Array(count).fill(false) as boolean[];
 const frames=cards.map(card=>{
  const height=Number.isFinite(card.height)?Math.max(0,card.height):0;
  if(card.fullWidth){
   const y=Math.max(...bottoms.map((bottom,i)=>bottom+(used[i]?spacing:0)));
   bottoms.fill(y+height);used.fill(true);
   return {x:0,y,width:safeWidth,height};
  }
  const nextY=bottoms.map((bottom,i)=>bottom+(used[i]?spacing:0));
  const column=nextY.reduce((best,y,i)=>y<nextY[best]?i:best,0);
  const y=bottoms[column]+(used[column]?spacing:0);
  bottoms[column]=y+height;used[column]=true;
  return {x:column*(cardWidth+spacing),y,width:cardWidth,height};
 });
 return {frames,height:Math.max(0,...bottoms)};
}
