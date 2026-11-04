export interface StoryStreamState {order:string[];active:string|null;held:boolean;pending:string[]|null}
export const uniqueStories=(ids:string[])=>[...new Set(ids.filter(Boolean))];
const same=(a:string[],b:string[])=>a.length===b.length&&a.every((id,i)=>id===b[i]);
export function createStoryStream(ids:string[]):StoryStreamState {const order=uniqueStories(ids);return {order,active:order[0]??null,held:false,pending:null}}
function apply(s:StoryStreamState,ids:string[]):StoryStreamState {const order=uniqueStories(ids);return {...s,order,active:s.active&&order.includes(s.active)?s.active:order[0]??null,pending:null}}
export function receiveStoryOrder(s:StoryStreamState,ids:string[]):StoryStreamState {
 const order=uniqueStories(ids);if(same(order,s.pending??s.order))return s;
 if(s.held)return {...s,pending:same(order,s.order)?null:order};
 return apply(s,order);
}
export function holdStories(s:StoryStreamState):StoryStreamState{return s.held?s:{...s,held:true}}
export function resumeStories(s:StoryStreamState):StoryStreamState{return {...apply(s,s.pending??s.order),held:false}}
export function advanceStory(s:StoryStreamState,delta=1,manual=false):StoryStreamState {
 if(!manual&&s.held)return s;
 if(!s.order.length)return manual?holdStories(s):s;
 const index=Math.max(0,s.order.indexOf(s.active??''));
 return {...s,held:manual||s.held,active:s.order[(index+delta+s.order.length)%s.order.length]};
}
export function canAdvanceStories(s:StoryStreamState,environment:{visible:boolean;hidden:boolean;reduced:boolean;readerOpen:boolean;scrolling?:boolean;pointerDown?:boolean}){
 return !s.held&&s.order.length>1&&environment.visible&&!environment.hidden&&!environment.reduced&&!environment.readerOpen&&!environment.scrolling&&!environment.pointerDown;
}

/** Explicit Explore-card activation only: never move a card on pointer-down or focus. */
export function selectStory(s:StoryStreamState,id:string):StoryStreamState {
 if(!s.order.includes(id))return s;
 if(s.active===id&&s.held)return s;
 return {...s,active:id,held:true};
}
