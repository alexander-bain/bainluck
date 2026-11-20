local Fake=assert(loadfile('atomic-numeric-encoding/fake_redis.lua'))()
local passed=0
local function eq(a,b)assert(a==b,'expected '..tostring(b)..', got '..tostring(a))end
local function test(name,fn)fn();passed=passed+1;print('PASS '..name)end
local function fresh()local s=Fake.new('atomic-numeric-encoding/authority.lua');eq(s:claim()[1],'claimed');return s end
local function exact(n)return string.format('%.0f',n)end
local seeds={'9999999999999','99999999999999','100000000000000','999999999999999','9007199254740989'}
for _,seed in ipairs(seeds)do
 test('distinct exact owner claims after '..seed,function()
  local s=fresh();s.kv.epoch=seed;local a=s:claim();local b=s:claim()
  eq(a[2],exact(tonumber(seed)+1));eq(b[2],exact(tonumber(seed)+2));assert(a[2]~=b[2]);eq(s.kv.owner,b[2])
 end)
end
test('MAX claim exhaustion disables replay before wrapping or rounding',function()
 local s=fresh();s.kv.epoch='9007199254740991';eq(s:claim()[1],'claim_error');eq(s.kv.enabled,nil);eq(s.kv.owner,'1');eq(s.kv.epoch,'9007199254740991')
end)
test('large owner fence accepts exact current and rejects previous',function()
 local s=fresh();s.kv.epoch='100000000000000';s:claim();s:claim()
 eq(s:offer('1',{epoch='100000000000001'})[1],'fenced');eq(s:offer('1',{epoch='100000000000002'})[1],'published_retained')
 eq(s:snapshot()[2],'100000000000002')
end)
for _,seq in ipairs({'100000000000001','9007199254740990','9007199254740991'})do
 test('large sequence stored exactly '..seq,function()
  local s=fresh();s:offer(seq);eq(s.hash.event.seq,seq)
  local older=exact(tonumber(seq)-1);eq(s:offer(older)[1],'published_duplicate_or_older');eq(s.hash.event.seq,seq)
 end)
end
test('large revoke own seq rejects older blend',function()
 local s=fresh();s:offer('100000000000001');s:offer('100000000000002',{kind='revoke'});s:offer('100000000000001')
 eq(s:snapshot()[1],'revoked');eq(s.hash.event.seq,'100000000000002')
end)
test('large commit floor and equal preview base preserve exact values',function()
 local s=fresh();s:offer(1,{base='9007199254740991'});s:run('committed','9007199254740991','commit')
 eq(s.hash.event.base,'9007199254740991');eq(s.hash.event.floor,'9007199254740991')
 eq(s:snapshot('9007199254740991')[1],'valid');eq(s:snapshot('9007199254740990')[1],'coverage_behind')
end)
test('large original expiry serializes exact and does not extend',function()
 local s=fresh();s.now=100000000000001;s:offer(1,{issued='100000000000001',expiry='100000000000101',ttl=100})
 eq(s.hash.event.expiry,'100000000000101');eq(s:snapshot()[6],100)
 s:offer(2,{issued='100000000000001',expiry='100000000000201',ttl=200});eq(s.hash.event.expiry,'100000000000101')
end)
for _,bad in ipairs({'9007199254740992','9007199254740991.1','9007199254740991.4','1.0','1e2','01','-1','+1','-0','0x10','nan','inf','', ' 1','1 ','1\0'})do
 test('noncanonical or unsafe seq refused '..bad,function()
  local s=fresh();eq(s:offer(bad)[1],'invalid');eq(#s.publications,0)
 end)
end
test('malformed coverage cannot become known floor',function()
 local s=fresh();s:offer(1);eq(s:snapshot('1e2')[1],'invalid_coverage');eq(s.hash.event.floor,nil)
end)
test('zero remains exact for base and coverage',function()
 local s=fresh();s:offer(1,{base='0'});eq(s:snapshot('0')[1],'valid');eq(s.hash.event.base,'0')
end)
for _,field in ipairs({'epoch','seq','base','expiry','floor'}) do
 test('present corrupt '..field..' disables rather than defaulting',function()
  local s=fresh();s:offer(1);s.hash.event[field]='1e2';eq(s:snapshot()[1],'storage_error');eq(s.kv.enabled,nil)
 end)
end
test('legacy scientific owner cannot be treated as valid authority',function()
 local s=fresh();s:offer(1);s.kv.owner='1e14';s.kv.enabled='1e14';eq(s:snapshot()[1],'authority_read_error');eq(s.kv.enabled,nil)
end)
test('legacy invalid counter cannot be incremented or reenabled',function()
 local s=fresh();s.kv.epoch='1e14';eq(s:claim()[1],'claim_error');eq(s.kv.epoch,'1e14');eq(s.kv.enabled,nil)
end)
print('RESULT '..passed..' passed, 0 failed; engine='.._VERSION)
