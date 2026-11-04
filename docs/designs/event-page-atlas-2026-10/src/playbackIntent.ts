/** Keep the requested action stable when a scrolling parent holds on pointer-down. */
export function playbackIntent(held:boolean,reduced:boolean,heldAtPointerDown:boolean|null=null):'hold'|'resume'{
 return reduced||(heldAtPointerDown??held)?'resume':'hold';
}
