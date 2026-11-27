-- Real generated producer metadata, exact numeric Lua, fake Redis commands.
-- Not an actual Redis engine and NOT an implementation of atomic batch publication.
local root=arg[1] or 'producer-chain-metadata/'
local Fake=assert(loadfile('atomic-numeric-encoding/fake_redis.lua'))()
local cases=assert(loadfile(root..'composition/producer-commands.lua'))()
local unpack=unpack or table.unpack
local n=0
local function eq(a,b) assert(a==b,tostring(a)..' ~= '..tostring(b)) end
local function check(name,f)f();n=n+1;print('PASS '..name)end
local function fresh()local s=Fake.new('atomic-numeric-encoding/authority.lua');s:claim();return s end
local function apply(s,item)s.now=item[1];return s:run(unpack(item[2]))end
check('actual current producer repeated lease retains exactly one original deadline',function()
 local s=fresh();local expiry
 for i=1,5 do
  eq(apply(s,cases[i])[1],'published_retained')
  expiry=expiry or s.hash.event.expiry;eq(s.hash.event.expiry,expiry)
  local snap=s:snapshot(10,'live');eq(snap[1],'valid');eq(snap[6],59999-(i-1)*2000)
 end
 eq(#s.publications,5)
end)
check('original expiry is final even without later publication',function()
 local s=fresh();apply(s,cases[1]);s.now=tonumber(s.hash.event.expiry)
 eq(s:snapshot(10,'live')[1],'expired')
end)
check('actual commit floor independently retires earlier-base producer preview',function()
 local s=fresh();for _,item in ipairs(cases)do apply(s,item)end
 eq(s:snapshot(11,'live')[1],'newer_commit');eq(#s.publications,6)
end)
check('optional retained write error preserves accepted live and disables later replay',function()
 local s=fresh();apply(s,cases[1]);s:fault('HSET','before');eq(apply(s,cases[2])[1],'published_replay_disabled')
 eq(#s.publications,2);eq(s:snapshot(10,'live')[1],'replay_disabled')
 eq(apply(s,cases[3])[1],'published_replay_disabled');eq(#s.publications,3)
 eq(s:snapshot(10,'live')[1],'replay_disabled')
end)
check('post-mutation retained error does not imply rollback or epoch healing',function()
 local s=fresh();apply(s,cases[1]);s:fault('HSET','after');eq(apply(s,cases[2])[1],'published_replay_disabled')
 eq(s.hash.event.seq,'2');eq(s.kv.enabled,nil);apply(s,cases[3]);eq(s.kv.enabled,nil);eq(#s.publications,3)
end)
check('superseded producer offer cannot create retained authority',function()
 local s=fresh();apply(s,cases[1]);s:claim();eq(apply(s,cases[2])[1],'fenced')
 eq(#s.publications,1);eq(s:snapshot(10,'live')[1],'cold_or_replaced_owner')
end)
check('missing original metadata is explicit live-only rather than TTL reanchoring',function()
 local s=fresh();apply(s,cases[1]);eq(s:run('uncached',1,'blend',cases[2][2][11])[1],'published_replay_disabled')
 eq(#s.publications,2);eq(s:snapshot(10,'live')[1],'replay_disabled')
end)
print('RESULT '..n..' deterministic composition checks passed; no atomic batch or Redis server claim')
