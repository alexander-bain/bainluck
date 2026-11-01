-- Same modeled commands and Lua5.1, frozen baseline versus isolated candidate.
local Fake=assert(loadfile('atomic-numeric-encoding/fake_redis.lua'))()
for _,entry in ipairs({{'baseline','evidence/negative-controls/authority-unsafe-serialization.txt'},{'candidate','atomic-numeric-encoding/authority.lua'}}) do
 local s=Fake.new(entry[2]);s:claim()
 s:offer('100000000000004',{payload='NEW'})
 local delayed=s:offer('100000000000003',{payload='OLD'})
 print(entry[1]..': delayed-old result='..delayed[1]..'; stored seq='..s.hash.event.seq..'; retained payload='..s.hash.event.payload)
 local t=Fake.new(entry[2]);t:claim()
 t:offer('100000000000006',{payload='PREVIEW'})
 local revoke=t:offer('100000000000007',{kind='revoke',payload='REVOKE'})
 print(entry[1]..': newer-revoke result='..revoke[1]..'; stored seq='..t.hash.event.seq..'; retained kind='..t.hash.event.kind)
 if entry[1]=='baseline' then assert(s.hash.event.payload=='OLD');assert(t.hash.event.kind=='blend')
 else assert(s.hash.event.payload=='NEW');assert(t.hash.event.kind=='revoke') end
end
print('PASS both old failures reproduced and corrected; interpreter plus deterministic commands only')
