-- Independent socket-free interpreter checks. Commands are a deterministic model.
local Fake=assert(loadfile('atomic-numeric-encoding/fake_redis.lua'))()
local script=arg[1] or 'atomic-numeric-encoding/authority.lua'
local n=0
local function eq(a,b) assert(a==b, 'expected '..tostring(b)..', got '..tostring(a)) end
local function check(name,f) f();n=n+1;print('PASS '..name) end
local function fresh() local s=Fake.new(script);eq(s:claim()[1],'claimed');return s end
local function no_incr(s)
 for _,t in ipairs(s.trace) do assert(t.command~='INCR','unexpected counter mutation') end
end
check('large predecessor owner cannot publish after exact successor claim',function()
 local s=fresh();s.kv.epoch='100000000000000';eq(s:claim()[2],'100000000000001');eq(s:claim()[2],'100000000000002')
 eq(s:offer('5',{epoch='100000000000001',payload='OLD'})[1],'fenced');eq(#s.publications,0)
 eq(s:offer('5',{epoch='100000000000002',payload='NEW'})[1],'published_retained');eq(s:snapshot()[8],'NEW')
end)
check('rounded legacy sequence cannot let delayed payload replace newer',function()
 local s=fresh();s:offer('100000000000002',{payload='NEW'});s:offer('100000000000001',{payload='OLD'})
 eq(s.hash.event.seq,'100000000000002');eq(s:snapshot()[8],'NEW')
end)
check('MAX owner is exact and exhaustion changes neither counter nor owner',function()
 local s=fresh();s.kv.epoch='9007199254740990';eq(s:claim()[2],'9007199254740991');s:offer('1')
 s.trace={};eq(s:claim()[1],'claim_error');no_incr(s);eq(s.kv.epoch,'9007199254740991');eq(s.kv.owner,'9007199254740991');eq(s.kv.enabled,nil)
end)
check('MAX revoke dominates immediately preceding preview',function()
 local s=fresh();s:offer('9007199254740990');s:offer('9007199254740991',{kind='revoke'});s:offer('9007199254740990')
 eq(s.hash.event.seq,'9007199254740991');eq(s:snapshot()[1],'revoked')
end)
check('large floor advancement cannot be rounded away or decreased',function()
 local s=fresh();s:offer('1',{base='100000000000001'});s:run('committed','100000000000002','COMMIT')
 eq(s:snapshot('100000000000001')[1],'coverage_behind');eq(s:snapshot('100000000000002')[1],'newer_commit')
 s:run('committed','100000000000001','OLD-COMMIT');eq(s.hash.event.floor,'100000000000002')
end)
check('MAX expiry budget remains exact through TIME and same-chain cap',function()
 local s=fresh();s.now=9007199254740000
 s:offer('1',{issued='9007199254740000',expiry='9007199254740991',ttl='991'})
 local r=s:snapshot();eq(r[1],'valid');eq(r[6],991);eq(r[7],'9007199254740991')
 s.now=9007199254740990;eq(s:snapshot()[6],1)
 s.now=9007199254740991;eq(s:snapshot()[1],'expired')
end)
check('numeric MAX plus ttl cannot extend a canonically bounded expiry',function()
 local s=fresh();s.now=9007199254740990
 eq(s:offer('1',{issued='9007199254740990',expiry='9007199254740991',ttl='60000'})[1],'published_retained')
 eq(s:snapshot()[6],1)
end)
local bad={'9007199254740992','9007199254740991.4','1e0','0x1','01','+1','-0',' 1','1\0junk','NaN'}
check('malformed epoch, sequence, floor and counter inputs cannot grant authority',function()
 for _,v in ipairs(bad) do
  local s=fresh();eq(s:offer(v)[1],'invalid');eq(#s.publications,0)
  eq(s:offer('1',{epoch=v})[1],'invalid');eq(#s.publications,0)
  eq(s:run('uncached',v,'blend','bad')[1],'invalid');eq(#s.publications,0)
  eq(s:run('committed',v,'bad')[1],'invalid');eq(#s.publications,0)
  eq(s:snapshot(v)[1],'invalid_coverage')
  s.kv.epoch=v;s.trace={};eq(s:claim()[1],'claim_error');no_incr(s);eq(s.kv.epoch,v);eq(s.kv.enabled,nil)
 end
end)
check('malformed retention-only metadata preserves accepted live but never replay',function()
 for _,field in ipairs({'base','expiry','issued','ttl'}) do
  local s=fresh();local opts={};opts[field]='9007199254740991.4'
  eq(s:offer('1',opts)[1],'published_replay_disabled');eq(#s.publications,1);eq(s:snapshot()[1],'replay_disabled')
 end
end)
check('corrupt stored numeric fence disables snapshot and newer offer cannot heal it',function()
 for _,field in ipairs({'epoch','seq','base','expiry','floor'}) do
  for _,v in ipairs({'1e14','9007199254740991.4','1\0junk'}) do
   local s=fresh();s:offer('1');s.hash.event[field]=v
   eq(s:snapshot()[1],'storage_error');eq(s.kv.enabled,nil)
   eq(s:offer('2')[1],'published_replay_disabled');eq(s:snapshot()[1],'replay_disabled')
  end
 end
end)
check('corrupt stored floor cannot be treated as missing during committed publication',function()
 local s=fresh();s:offer('1');s.hash.event.floor='1e14'
 eq(s:run('committed','1','COMMIT')[1],'committed_replay_disabled');eq(s.hash.event.floor,'1e14');eq(s.kv.enabled,nil)
 eq(s.publications[#s.publications].payload,'COMMIT')
end)
check('valid missing floor remains zero rather than falsely corrupt',function()
 local s=fresh();s:offer('1',{base='0'});eq(s.hash.event.floor,nil);eq(s:snapshot('0')[1],'valid')
end)
check('corrupt owner refuses blends without suppressing independent committed truth',function()
 local s=fresh();s.kv.owner='1e14';s.kv.enabled='1e14'
 eq(s:offer('1',{epoch='100000000000000'})[1],'authority_read_error');eq(#s.publications,0)
 eq(s:run('committed','1','COMMIT')[1],'committed_replay_disabled');eq(s.publications[1].payload,'COMMIT')
end)
check('large old-owner revoke delivers but cannot mutate current epoch record',function()
 local s=fresh();s.kv.epoch='100000000000000';s:claim();s:claim();s:offer('9007199254740991',{payload='CURRENT'})
 eq(s:offer('9007199254740991',{epoch='100000000000001',kind='revoke'})[1],'old_revoke_published')
 eq(s:snapshot()[8],'CURRENT');eq(s.hash.event.epoch,'100000000000002')
end)
print('RESULT '..n..' independent cases passed; engine='.._VERSION..'; deterministic Redis commands only')
