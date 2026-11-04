/** CSS-pixel exclusion for an opaque sticky header, including its top safe area. */
export function pinnedStoryInset(top:number,height:number):number {
 return (Number.isFinite(top)?Math.max(0,top):0)+(Number.isFinite(height)?Math.max(0,height):0);
}
