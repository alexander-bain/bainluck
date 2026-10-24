table.unpack = table.unpack or unpack -- test driver portability only
local root=arg[1] or 'atomic-retention/'
local Fake=assert(loadfile(root..'fake_redis.lua'))()
local count=0
local function eq(a,b)assert(a==b,tostring(a)..' ~= '..tostring(b))end
local function run(name,fn)fn();count=count+1;print('PASS '..name)end
local function fresh()local s=Fake.new(root..'authority.lua');s:claim();return s end
-- Negative control: split publish/write can install a stale record after a newer revoke.
run('split publication then write resurrects revoked preview (negative control)',function()
 local s={owner=1,record=nil,published={}}
 s.published[#s.published+1]='blend1' -- caller A pauses before its cache write
 s.published[#s.published+1]='revoke2';s.record={seq=2,kind='revoke'}
 s.record={seq=1,kind='blend'} -- late A write wins without atomic seq comparison
 eq(s.record.kind,'blend');eq(s.published[#s.published],'revoke2')
end)
-- Negative control: simply ignoring a newer cache error preserves stale recovery.
run('PUBLISH newer plus failed SET leaves old replay (negative control)',function()
 local s={record=1,published={1}};s.published[#s.published+1]=2 -- SET fails
 eq(s.record,1);eq(s.published[#s.published],2)
end)
local function permutations(xs)
 local out={}
 local function visit(prefix,rest)
  if #rest==0 then out[#out+1]=prefix;return end
  for i,x in ipairs(rest)do local p={table.unpack(prefix)};p[#p+1]=x;local r={};for j,y in ipairs(rest)do if i~=j then r[#r+1]=y end end;visit(p,r)end
 end
 visit({},xs);return out
end
-- Each total order is one possible Redis EVAL linearization. Includes snapshots
-- after EVERY operation, not only final state. Replay never moves behind a known
-- higher seq/revoke, and commit floor refuses old-base blends.
for _,order in ipairs(permutations({'one','three','revoke','commit'}))do
 run('atomic ordering '..table.concat(order,','),function()
  local s=fresh();local maxseq=0;local finalkind=nil;local floor=0
  for _,op in ipairs(order)do
   if op=='commit'then s:run('committed',1,'commit');floor=1
   else
    local seq=op=='one' and 1 or op=='three' and 3 or 4
    local kind=op=='revoke' and 'revoke' or 'blend'
    s:offer(seq,{kind=kind})
    if seq>maxseq then maxseq=seq;finalkind=kind end
   end
   local snap=s:snapshot(floor)
   if maxseq>0 then eq(tonumber(s.hash.event.seq),maxseq) end
   if snap[1]=='valid'then eq(finalkind,'blend');eq(snap[3],maxseq);eq(floor,0) end
   if finalkind=='revoke'then eq(snap[1],'revoked')end
  end
 end)
end
for _,order in ipairs(permutations({'claim','old-blend','old-revoke'}))do
 run('owner ordering '..table.concat(order,','),function()
  local s=fresh();s:offer(1);local claimed=false
  for _,op in ipairs(order)do
   if op=='claim'then s:claim();claimed=true
   elseif op=='old-blend'then s:offer(2,{epoch=1})
   else s:offer(3,{epoch=1,kind='revoke'})end
   local r=s:snapshot()
   if claimed then eq(r[1],'cold_or_replaced_owner')end
  end
 end)
end
-- Every command after the barrier is failed before and after its modeled side effect.
-- Whether publication actually happened is counted, not assumed from an error reply.
for _,cmd in ipairs({'PUBLISH','HSET','SET'})do
 for _,phase in ipairs({'before','after'})do
  run('partial failure '..cmd..' '..phase,function()
   local s=fresh();s:offer(1);s:fault(cmd,phase);s:offer(3)
   eq(s.kv.enabled,nil);s:offer(2);s:offer(4);eq(s:snapshot()[1],'replay_disabled')
   local expected=cmd=='PUBLISH' and phase=='before' and 3 or 4
   eq(#s.publications,expected)
  end)
 end
end
-- The deliberately unsolved SQL/Redis interval is executable, not hidden in prose.
run('DB status after coverage before notification is outside atomic Redis proof',function()
 local s=fresh();s:offer(1);local coverage_status='live';local actual_db_status='final'
 eq(s:snapshot(0,coverage_status)[1],'valid');eq(actual_db_status,'final')
 eq(s:snapshot(0,actual_db_status)[1],'nonquote_latched')
end)
print('RESULT '..count..' passed, 0 failed')
