local root=arg[1] or 'atomic-retention/'
local Fake=assert(loadfile(root..'fake_redis.lua'))()
local passed=0
local function eq(a,b) assert(a==b,'expected '..tostring(b)..', got '..tostring(a)) end
local function test(name, fn) fn();passed=passed+1;print('PASS '..name) end
local function fresh() local s=Fake.new(root..'authority.lua');eq(s:claim()[1],'claimed');return s end
local function valid(s,seq) local a=s:snapshot();eq(a[1],'valid');eq(a[3],seq);return a end

test('accepted publication retained in same operation',function() local s=fresh();eq(s:offer(1)[1],'published_retained');valid(s,1);eq(#s.publications,1) end)
test('higher owner without first publication refuses predecessor',function()local s=fresh();s:offer(1);s:claim();eq(s:snapshot()[1],'cold_or_replaced_owner');eq(s:offer(2,{epoch=1})[1],'fenced');eq(#s.publications,1)end)
test('owner claim before old offer fences',function()local s=fresh();s:claim();s:offer(1,{epoch=1});eq(s:snapshot()[1],'cold_or_replaced_owner')end)
test('old owner revoke still publishes and cannot erase successor',function()local s=fresh();s:offer(1);s:claim();s:offer(2);eq(s:offer(3,{epoch=1,kind='revoke'})[1],'old_revoke_published');valid(s,2);eq(#s.publications,3)end)
test('current revoke seq prevents delayed older blend',function()local s=fresh();s:offer(4);s:offer(5,{kind='revoke'});s:offer(4);local r=s:snapshot();eq(r[1],'revoked');eq(r[3],5)end)
test('duplicates and newer same-chain cannot extend deadline',function()local s=fresh();s:offer(1,{expiry=110000});s:offer(1,{expiry=130000});s:offer(2,{expiry=140000});eq(valid(s,2)[7],'110000');s.now=110000;eq(s:snapshot()[1],'expired')end)
test('revoke preserves fixed same-chain deadline',function()local s=fresh();s:offer(1,{expiry=110000});s:offer(2,{kind='revoke'});s:offer(3,{expiry=140000});eq(valid(s,3)[7],'110000')end)
test('remaining duration freshly decreases without write',function()local s=fresh();s:offer(1);eq(valid(s,1)[6],60000);s.now=100300;eq(valid(s,1)[6],59700)end)
test('commit higher floor invalidates older base',function()local s=fresh();s:offer(1);s:run('committed',1,'commit');eq(s:snapshot(tonumber(s.hash.event.floor) or 0)[1],'newer_commit')end)
test('preview recomposed on equal commit floor survives',function()local s=fresh();s:offer(1,{base=1});s:run('committed',1,'commit');eq(s:snapshot(1)[1],'valid')end)
test('commit floor survives new owner claim',function()local s=fresh();s:run('committed',3,'commit');s:claim();s:offer(1,{base=2});eq(s:snapshot(tonumber(s.hash.event.floor) or 0)[1],'newer_commit')end)
test('out-of-order commits cannot lower known floor',function()local s=fresh();s:run('committed',4,'new');s:run('committed',2,'old');s:offer(1,{base=3});eq(s:snapshot(tonumber(s.hash.event.floor) or 0)[1],'newer_commit')end)
test('fresh DB floor catches commit without notification',function()local s=fresh();s:offer(1);eq(s:snapshot(1)[1],'newer_commit');eq(s:snapshot(0)[1],'coverage_behind')end)
test('same WPS revision terminal coverage blocks and latches',function()local s=fresh();s:offer(1);eq(s:snapshot(0,'final')[1],'nonquote_latched');s:run('committed',0,'delayed-live');eq(s:snapshot(0,'live')[1],'nonquote_latched');s:claim();s:offer(2);eq(s:snapshot()[1],'nonquote_latched')end)
test('different nonterminal status refuses mismatched preview',function()local s=fresh();s:offer(1);eq(s:snapshot(0,'suspended')[1],'status_mismatch')end)
test('missing owner fails closed',function()local s=fresh();s:offer(1);s.kv.owner=nil;eq(s:snapshot()[1],'replay_disabled')end)
test('missing marker cannot be restored by snapshot offer or commit',function()local s=fresh();s:offer(1);s.kv.enabled=nil;eq(s:snapshot()[1],'replay_disabled');s:offer(2);s:run('committed',1,'c');eq(s.kv.enabled,nil);eq(s:snapshot()[1],'replay_disabled')end)
for _,phase in ipairs({'before','after'}) do
 test('HSET '..phase..' error leaves replay disabled after healthy publication',function()local s=fresh();s:offer(1);s:fault('HSET',phase);eq(s:offer(3)[1],'published_replay_disabled');eq(#s.publications,2);s:offer(2);s:offer(4);eq(#s.publications,4);eq(s:snapshot()[1],'replay_disabled');eq(s.kv.enabled,nil)end)
 test('marker restore '..phase..' error does not reopen replay',function()local s=fresh();s:offer(1);s:fault('SET',phase);eq(s:offer(2)[1],'published_replay_disabled');eq(s.kv.enabled,nil);eq(s:snapshot()[1],'replay_disabled')end)
 test('PUBLISH '..phase..' error cannot retain offered authority',function()local s=fresh();s:offer(1);s:fault('PUBLISH',phase);eq(s:offer(2)[1],'publish_error_replay_disabled');eq(s.hash.event.seq,'1');eq(s:snapshot()[1],'replay_disabled')end)
 test('commit write '..phase..' error disables replay, publish survives',function()local s=fresh();s:offer(1);s:fault('HSET',phase);eq(s:run('committed',2,'commit')[1],'committed_replay_disabled');eq(#s.publications,2);eq(s:snapshot()[1],'replay_disabled')end)
 test('coverage write '..phase..' error disables replay',function()local s=fresh();s:offer(1);s:fault('HSET',phase);eq(s:snapshot(2)[1],'storage_error');eq(s:snapshot()[1],'replay_disabled')end)
end
test('failed delete barrier stops before PUBLISH',function()local s=fresh();s:offer(1);s:fault('DEL');local ok=pcall(function()s:offer(2)end);eq(ok,false);eq(#s.publications,1)end)
test('cold/wrong-type retention does not suppress accepted live',function()local s=fresh();s.kv.event='wrongtype';eq(s:offer(1)[1],'published_replay_disabled');eq(#s.publications,1);eq(s:snapshot()[1],'replay_disabled')end)
test('owner read error is not bypassed as healthy acceptance',function()local s=fresh();s:fault('GET');eq(s:offer(1)[1],'authority_read_error');eq(#s.publications,0)end)
test('new claim after disabled epoch can recover only successor authority',function()local s=fresh();s:offer(1);s:fault('HSET');s:offer(2);s:claim();eq(s:snapshot()[1],'cold_or_replaced_owner');s:offer(1);valid(s,1)end)
test('failed claim owner mutation cannot leave replay enabled',function()local s=fresh();s:offer(1);s:fault('SET','after');eq(s:claim()[1],'claim_error');eq(s.kv.enabled,nil);eq(s:snapshot()[1],'replay_disabled')end)
test('invalid original deadline preserves live but disables replay',function()local s=fresh();eq(s:offer(1,{expiry=170001})[1],'published_replay_disabled');eq(#s.publications,1);eq(s:snapshot()[1],'replay_disabled')end)
test('expired preview retains floor but cannot replay',function()local s=fresh();s.now=170000;s:offer(1);eq(s:snapshot()[1],'expired');s:offer(1,{expiry=230000,issued=170000});eq(s:snapshot()[1],'expired')end)
-- Exhaust all serializations of claim/publish and commit/publish: atomic read observes
-- only whole operations, unlike the retained baseline split between PUBLISH and SET.
for _,order in ipairs({'offer-first','commit-first'}) do
 test('commit/offer race '..order,function()local s=fresh();if order=='offer-first' then s:offer(1);s:run('committed',1,'c')else s:run('committed',1,'c');s:offer(1)end;eq(s:snapshot(tonumber(s.hash.event.floor) or 0)[1],'newer_commit')end)
end
test('first successor revoke does not inherit predecessor lease cap',function()local s=fresh();s:offer(1,{expiry=101000});s:claim();s:offer(1,{kind='revoke'});s:offer(2,{expiry=150000});eq(valid(s,2)[7],'150000')end)
test('coverage behind Redis floor cannot certify current status',function()local s=fresh();s:offer(1,{base=2});s:run('committed',2,'commit');eq(s:snapshot(1,'live')[1],'coverage_behind');eq(s:snapshot(2,'live')[1],'valid')end)
test('future issued time cannot produce oversized remaining lease',function()local s=fresh();s:offer(1,{issued=200000,expiry=260000});eq(s:snapshot()[1],'replay_disabled');eq(#s.publications,1)end)
test('preview newer base itself requires newer DB coverage',function()local s=fresh();s:offer(1,{base=1});eq(s:snapshot(0)[1],'coverage_behind_preview_base');eq(s:snapshot(1)[1],'valid')end)
test('owner read failure does not suppress independent committed publication',function()local s=fresh();s:offer(1);s:fault('GET');eq(s:run('committed',1,'commit')[1],'committed_replay_disabled');eq(#s.publications,2);eq(s:snapshot()[1],'replay_disabled')end)
test('uncached producer frame preserves live and invalidates replay',function()local s=fresh();s:offer(1);eq(s:run('uncached',1,'blend','new-live')[1],'published_replay_disabled');eq(#s.publications,2);eq(s:snapshot()[1],'replay_disabled')end)
test('optional marker read failure preserves proven owner live acceptance',function()local s=fresh();s:offer(1);s:fault('GET','before',2);eq(s:offer(2)[1],'published_replay_disabled');eq(#s.publications,2);eq(s:snapshot()[1],'replay_disabled')end)
print('RESULT '..passed..' passed, 0 failed')
