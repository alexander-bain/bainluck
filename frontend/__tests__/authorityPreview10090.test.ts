import {
  EMPTY_AUTHORITY_PREVIEW, authorityPreviewMembership as membership,
  authorityPreviewOpen as open, authorityPreviewFrame as frame,
  authorityPreviewReset as reset, authorityPreviewFloor as floor, parseUniquePreviewJSON,
} from '@/lib/authorityPreview';
import examples from '../../docs/contracts/dnpl-authority-v3.examples.json';
const wire=JSON.stringify, m=examples.messages, a=m.singleton_open.authority;
const session2='cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const nextDomain={incarnation:'2',namespace:'22222222-2222-4222-8222-222222222222'};
const single=()=>open(membership(EMPTY_AUTHORITY_PREVIEW,{'42':10},42),wire(m.singleton_open),42);
const blend=(seq:number,extra={})=>({...m.singleton_blend,frame:{...m.singleton_blend.frame,
  preview:{...m.singleton_blend.frame.preview,seq,...extra}}});

test('requires adopted membership and explicit open; frames cannot establish a domain',()=>{
  const r=membership(EMPTY_AUTHORITY_PREVIEW,{'42':10},42);
  expect(frame(r,wire(m.singleton_blend),42,0,0)).toBe(r);
  expect(open(r,wire(m.folded_open),42)).toBe(r);
  expect(open(EMPTY_AUTHORITY_PREVIEW,wire(m.singleton_open),42)).toBe(EMPTY_AUTHORITY_PREVIEW);
  expect(frame(single(),wire(m.singleton_blend),42,100,130).preview.held?.expiresAt).toBe(900);
});
test.each(examples.invalid_incarnations)('rejects malformed incarnation %p',incarnation=>{
  const r=single();expect(open(r,wire({...m.singleton_open,authority:{...a,incarnation}}),42)).toBe(r);
});
test.each(examples.invalid_uuids)('rejects malformed UUID %p',namespace=>{
  const r=single();expect(open(r,wire({...m.singleton_open,authority:{...a,namespace}}),42)).toBe(r);
});
test.each([...examples.duplicate_key_fragments_rejected_at_any_depth,
  '{"frame":{"preview":{"seq":1,"\\u0073eq":2}}}', '{"a":[{"b":1,"b":2}]}','{"a":1e999}','{"a":1,}',
])('rejects duplicate decoded keys or invalid JSON: %s',raw=>expect(parseUniquePreviewJSON(raw)).toBeNull());
test('bounds UTF-8 size and depth; only inner unknown keys are additive',()=>{
  expect(parseUniquePreviewJSON(wire({s:'é'.repeat(9000)}))).toBeNull();
  expect(parseUniquePreviewJSON('['.repeat(66)+'0'+']'.repeat(66))).toBeNull();
  expect(parseUniquePreviewJSON('{"s":"a\\\"b","a":[true,false,null,-1.2e3]}')).toEqual({s:'a"b',a:[true,false,null,-1200]});
  const r=single();
  expect(frame(r,wire({...m.singleton_blend,extra:1}),42,0,0)).toBe(r);
  expect(frame(r,wire({...m.singleton_blend,frame:{...m.singleton_blend.frame,extra:1}}),42,0,0).preview.held?.p).toBe(.6);
});
test('resync retires tuples, reconnect ends the session, and fresh tuples still work',()=>{
  let r=frame(single(),wire(m.singleton_blend),42,100,100);
  expect(open(r,wire(m.singleton_open),42)).toBe(r);
  r=reset(r,false);expect(r.session).toBe(m.singleton_open.stream_session);
  expect(frame(r,wire(m.singleton_blend),42,200,200)).toBe(r);
  r=frame(r,wire(blend(2)),42,200,200);expect(r.preview.held?.seq).toBe(2);
  r=reset(r);expect(r.session).toBeNull();expect(frame(r,wire(blend(3)),42,300,300)).toBe(r);
  r=open(r,wire({...m.singleton_open,stream_session:session2}),42);
  expect(frame(r,wire({...blend(2),stream_session:session2}),42,300,300)).toBe(r);
  expect(frame(r,wire({...blend(3),stream_session:session2}),42,300,300).preview.held?.seq).toBe(3);
});
test('new domains clear preview order but preserve floors and refuse older/wrong domains',()=>{
  let r=frame(single(),wire(blend(800,{epoch:900})),42,0,0);
  r=floor(r,{'42':11});expect(r.preview.held).toBeNull();
  r=open(r,wire({...m.singleton_open,authority:nextDomain}),42);
  expect(r.preview.multiOrigin?.authorities).toEqual({});
  expect(frame(r,wire(m.singleton_blend),42,10,10)).toBe(r);
  expect(open(r,wire(m.singleton_open),42)).toBe(r);
  expect(open(r,wire({...m.singleton_open,authority:{...nextDomain,namespace:a.namespace}}),42)).toBe(r);
  r=frame(r,wire({...blend(1),authority:nextDomain}),42,10,10);expect(r.preview.held).toBeNull();
  r=frame(r,wire({...blend(2,{base_rev:11}),authority:nextDomain}),42,20,20);expect(r.preview.held?.p).toBe(.6);
});
test('client queue spends TTL; duplicates cannot extend expiry, change values or revive retirement',()=>{
  const initial=single();const late=frame(initial,wire(m.singleton_blend),42,100,900);
  expect(late.preview.held).toBeNull();expect(late.preview.multiOrigin!.authorities['42'].state).toBe('expired');
  expect(frame(late,wire(m.singleton_blend),42,901,901)).toBe(late);
  let r=frame(initial,wire(m.singleton_blend),42,100,200);
  r=frame(r,wire({...m.singleton_blend,frame:{...m.singleton_blend.frame,p:.9}}),42,500,500);
  expect(r.preview.held?.expiresAt).toBe(900);expect(r.preview.held?.p).toBe(.6);
  expect(frame(r,wire(m.singleton_blend),42,901,901)).toBe(r);
  r=frame(r,wire(m.singleton_revoke),42,600,600);expect(r.preview.held).toBeNull();
  expect(frame(r,wire(m.singleton_blend),42,700,700)).toBe(r);
});
const folded=(members:Record<string,number>={'42':10,'43':20},session=m.folded_open.stream_session,seq=1,origins=[42,43])=>({
  ...m.folded_blend,stream_session:session,frame:{...m.folded_blend.frame,preview:{...m.folded_blend.frame.preview,
    fold_session:session,fold_seq:seq,base_fold_revision:members,origin_authority:Object.fromEntries(origins.map(id=>[String(id),
      {epoch:id,seq,state:'pending',ttl_ms:800}]))}}});
const openFold=(r:ReturnType<typeof single>,members:Record<string,number>,session=m.folded_open.stream_session)=>
  open(membership(r,members,42),wire({...m.folded_open,members:Object.keys(members).map(Number).sort((x,y)=>x-y),stream_session:session}),42);
test('fold/singleton/flap retains row authority and rejects shape or session mismatch',()=>{
  let r=frame(single(),wire(blend(2)),42,0,0);r=openFold(r,{'42':10,'43':20});
  expect(frame(r,wire({...m.singleton_blend,stream_session:r.session}),42,1,1)).toBe(r);
  r=frame(r,wire(folded(undefined,undefined,3)),42,2,2);expect(r.preview.held?.p).toBe(.6);
  r=openFold(r,{'42':10,'44':30},session2);expect(r.retired['43'].fence?.seq).toBe(3);
  r=frame(r,wire(folded({'42':10,'44':30},session2,4,[42,44])),42,3,3);
  r=openFold(r,{'42':10,'43':20});expect(frame(r,wire(folded(undefined,undefined,2)),42,4,4)).toBe(r);
  r=open(membership(r,{'42':10},42),wire(m.singleton_open),42);
  expect(frame(r,wire(blend(1,{epoch:42})),42,5,5)).toBe(r);
  expect(frame(r,wire(blend(5,{epoch:42})),42,5,5).preview.held?.seq).toBe(5);
});
test('fixed three-row membership can change election after a new session',()=>{
  const members={'42':10,'43':20,'44':30};let r=openFold(single(),members);
  r=frame(r,wire(folded(members)),42,0,0);r=openFold(reset(r),members,session2);
  r=frame(r,wire(folded(members,session2,2,[42,44])),42,1,1);expect(r.preview.held?.p).toBe(.6);
  expect(Object.keys(r.preview.multiOrigin!.authorities).sort()).toEqual(['42','43','44']);
});
test('retired floors survive new domains and temporarily absent detail membership',()=>{
  let r=openFold(single(),{'42':10,'43':25});r=membership(r,undefined,42);
  expect(open(r,wire(m.singleton_open),42)).toBe(r);
  r=membership(r,{'42':10},42);r=open(r,wire({...m.singleton_open,authority:nextDomain}),42);
  expect(r.retired['43'].floor).toBe(25);expect(r.retired['43'].fence).toBeUndefined();
  r=openFold(r,{'42':10,'43':20});expect(r.preview.floors!['43']).toBe(25);
});
test('capacity saturates rather than evicting evidence; new incarnation cannot reset it',()=>{
  let r=single();for(let id=100;id<110;id++)r=membership(r,{'42':10,[String(id)]:0},42);
  expect(r.saturated).toBe(true);expect(Object.keys(r.retired)).toHaveLength(9);
  expect(open(r,wire({...m.singleton_open,authority:nextDomain}),42)).toBe(r);
  expect(membership(r,{'42':10},42)).toBe(r);
  let full=membership(EMPTY_AUTHORITY_PREVIEW,Object.fromEntries(Array.from({length:32},(_,i)=>[String(42+i),0])),42);
  full=membership(full,{'42':0},42);expect(full.saturated).toBe(true);
  expect(Object.keys(full.retired)).toHaveLength(31);expect(full.visited).toHaveLength(32);
});


test.each(['3', '3.0', '3e0'])('D1 protocol uses the decoded integer value: %s', spelling => {
  const raw=wire(m.singleton_open).replace('"protocol":3', '"protocol":'+spelling);
  const r=membership(EMPTY_AUTHORITY_PREVIEW,{'42':10},42);
  expect(open(r,raw,42).domain).toEqual(a);
});
