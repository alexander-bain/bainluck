import type {PointerEvent} from 'react';
/** A native range thumb owns drags that start on it. Keep its browser default,
 * while excluding ancestor card-paging and simulated vertical-scroll sessions. */
export function rangePointerDown(event:PointerEvent<HTMLInputElement>,onStart?:(event:PointerEvent<HTMLInputElement>)=>void){
 event.stopPropagation();
 onStart?.(event);
}
export const rangeGestureProps={
 'data-scroll-drag':'ignore',
 onPointerDown:(event:PointerEvent<HTMLInputElement>)=>rangePointerDown(event),
} as const;
