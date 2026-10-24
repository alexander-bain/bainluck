-- Read-only, bounded metadata inventory; no price/base/pending payload values.
local L = KEYS[1]
if #KEYS ~= 5 or #ARGV ~= 0 then return redis.error_reply('arguments') end
if redis.call('TYPE', L).ok ~= 'hash' then return redis.error_reply('ledger_missing_or_wrong_type') end
local size = redis.call('HLEN', L)
if size > 32768 then return redis.error_reply('field_cap') end
local policy, names = 0, {}
for _,f in ipairs(redis.call('HKEYS', L)) do
  if f == 'reservation_policy' or string.match(f, '^r:') or string.match(f, '^policy_owner:')
      or string.match(f, '^e:.*:r_') then
    policy = policy + 1
    if #names < 16 then names[#names + 1] = f end
  end
end
local fields = {'epoch','retired','nevents','owner:kalshi','read_owner:kalshi',
  'owner:polymarket','read_owner:polymarket','policy_owner:kalshi','policy_owner:polymarket'}
local headers = {}
for _,f in ipairs(fields) do headers[f] = redis.call('HGET', L, f) or cjson.null end
local t = redis.call('TIME')
return cjson.encode({headers=headers, policy_field_count=policy, policy_field_examples=names,
  hlen=size, initialized=redis.call('GET', KEYS[2]) or cjson.null,
  shared_epoch=redis.call('GET', KEYS[3]) or cjson.null,
  singleton_owners={redis.call('GET', KEYS[4]) or cjson.null, redis.call('GET', KEYS[5]) or cjson.null},
  redis_time=t})
