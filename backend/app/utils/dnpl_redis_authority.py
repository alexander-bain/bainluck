"""Atomic namespace guard for the existing DNPL ledger (not yet wired live).

Postgres authorizes the incarnation. These scripts cannot create that authority
and never reset an existing namespace. Same-identity Redis rollback remains a
separate qualification premise; a dirty guard is not durable rollback evidence.
"""

from app.services.dnpl_authority import Authority
from app.utils.blend_preview import LEDGER_SCRIPT


def namespace_keys(authority: Authority) -> tuple[str, ...]:
    if authority.incarnation == 0:
        raise ValueError("migration seed has no Redis namespace")
    prefix = f"live:blend_preview:v3:{authority.incarnation}:{authority.namespace}:"
    return tuple(
        prefix + suffix
        for suffix in (
            "ledger",
            "initialized",
            "epoch",
            "owner:kalshi",
            "owner:polymarket",
            "guard",
        )
    )


def guard_token(authority: Authority) -> str:
    return ":".join(
        (
            str(authority.incarnation),
            str(authority.namespace),
            authority.redis_run_id,
            authority.redis_master_replid,
            authority.policy_fingerprint,
        )
    )


# Atomic INFO validation is mandatory, not a preceding Python round trip.
# Exactly which primary transitions change these fields must still be proved
# for the supported service/version before this adapter is qualified.
_IDENTITY = r"""
local function infofield(info, key)
  return string.match('\r\n' .. info, '\r\n' .. key .. ':([^\r\n]*)')
end
local server = redis.call('INFO', 'server')
local replication = redis.call('INFO', 'replication')
if infofield(server, 'run_id') ~= ARGV[2]
    or infofield(replication, 'role') ~= 'master'
    or infofield(replication, 'master_replid') ~= ARGV[3] then
  return {'identity_changed'}
end
"""

INITIALIZE_SCRIPT = _IDENTITY + r"""
local token, guard = ARGV[1], KEYS[6]
if #KEYS ~= 6 or not token or token == '' then return {'malformed'} end
for _, key in ipairs(KEYS) do
  if redis.call('EXISTS', key) == 1 then return {'exists'} end
end
redis.call('SET', guard, 'initializing:' .. token)
redis.call('HSET', KEYS[1], 'epoch', '0', 'retired', '0', 'nevents', '0')
redis.call('SET', KEYS[2], '1')
redis.call('SET', KEYS[3], '0')
redis.call('SET', guard, 'clean:' .. token)
return {'initialized'}
"""

INITIAL_READBACK_SCRIPT = _IDENTITY + r"""
local token = ARGV[1]
if #KEYS ~= 6 or redis.call('GET', KEYS[6]) ~= 'clean:' .. token
    or redis.call('TYPE', KEYS[1]).ok ~= 'hash'
    or redis.call('HLEN', KEYS[1]) ~= 3
    or redis.call('HGET', KEYS[1], 'epoch') ~= '0'
    or redis.call('HGET', KEYS[1], 'retired') ~= '0'
    or redis.call('HGET', KEYS[1], 'nevents') ~= '0'
    or redis.call('GET', KEYS[2]) ~= '1'
    or redis.call('GET', KEYS[3]) ~= '0'
    or redis.call('EXISTS', KEYS[4], KEYS[5]) ~= 0 then
  return {'not_initial'}
end
return {'initial_verified'}
"""


VALIDATE_NAMESPACE_SCRIPT = _IDENTITY + r"""
if #KEYS ~= 6 or redis.call('GET', KEYS[6]) ~= 'clean:' .. ARGV[1]
    or redis.call('TYPE', KEYS[1]).ok ~= 'hash'
    or redis.call('HEXISTS', KEYS[1], 'epoch') ~= 1
    or redis.call('HEXISTS', KEYS[1], 'retired') ~= 1
    or redis.call('GET', KEYS[2]) ~= '1'
    or redis.call('EXISTS', KEYS[3]) ~= 1 then return {'unavailable'} end
local policy = redis.call('HGET', KEYS[1], 'reservation_policy')
if policy and policy ~= ARGV[4] then return {'policy_mismatch'} end
return {'valid'}
"""


async def validate_namespace(client, authority: Authority) -> bool:
    """Read-only, atomic identity and clean-guard check for a fresh PG row."""
    if authority.state != "ready":
        return False
    result = await client.eval(
        VALIDATE_NAMESPACE_SCRIPT,
        6,
        *namespace_keys(authority),
        guard_token(authority),
        authority.redis_run_id,
        authority.redis_master_replid,
        authority.policy_fingerprint,
    )
    return result in (["valid"], [b"valid"])


def guarded_ledger_script(ledger_script: str = LEDGER_SCRIPT) -> str:
    """Wrap the unchanged ledger; mark dirty only at its first actual mutation.

    ARGV prefix: token, expected run_id/replid, source, current source claim.
    Remaining ARGV and first five KEYS are the existing ledger's exact contract.
    Claim requires no old claim; all other operations, including early revoke,
    require the current source/policy/read owner before the old script executes.
    """
    return (
        _IDENTITY
        + r"""
local token, guard = ARGV[1], KEYS[6]
local source, owner = ARGV[4], ARGV[5]
if #KEYS ~= 6 or (source ~= 'kalshi' and source ~= 'polymarket') then
  return {'malformed'}
end
if redis.call('GET', guard) ~= 'clean:' .. token then return {'guard_refused'} end
local bound_policy = string.match(token, '^[^:]+:[^:]+:[^:]+:[^:]+:(.+)$')
if not bound_policy or ARGV[6] ~= bound_policy then return {'policy_mismatch'} end
if redis.call('TYPE', KEYS[1]).ok ~= 'hash'
    or redis.call('HEXISTS', KEYS[1], 'epoch') ~= 1
    or redis.call('GET', KEYS[2]) ~= '1'
    or redis.call('EXISTS', KEYS[3]) ~= 1 then return {'lost'} end
local op = ARGV[7]
if op ~= 'claim' and (redis.call('HGET', KEYS[1], 'owner:' .. source) ~= owner
    or redis.call('HGET', KEYS[1], 'read_owner:' .. source) ~= owner
    or redis.call('HGET', KEYS[1], 'policy_owner:' .. source) ~= owner) then
  return {'fenced'}
end
-- Bind ordinary source arguments too; revoke has no source in its legacy body.
if op ~= 'revoke' and ARGV[8] ~= source then return {'malformed'} end
if op ~= 'claim' and op ~= 'revoke' and ARGV[9] ~= owner then return {'malformed'} end
table.remove(KEYS, 6)
for i = 1, 5 do table.remove(ARGV, 1) end
local raw, dirty = redis, false
local mutation = {SET=true, HSET=true, HINCRBY=true, HDEL=true, INCR=true, PUBLISH=true}
local reads = {EXISTS=true, GET=true, HEXISTS=true, HGET=true, HKEYS=true, TIME=true}
local redis = {call=function(command, ...)
  -- A newly added command requires a deliberate classification, not a silent
  -- unguarded mutation. Error after dirty intentionally leaves dirty behind.
  if not mutation[command] and not reads[command] then error('unclassified ledger command') end
  if mutation[command] and not dirty then
    raw.call('SET', guard, 'dirty:' .. token)
    dirty = true
  end
  return raw.call(command, ...)
end}
local function ledger()
"""
        + ledger_script
        + r"""
end
local result = ledger()
if dirty then
  -- Completion is operation-specific: some successful writes return a refusal
  -- to open a preview, or only advance a barrier/base with no pending value.
  -- Never let a status valid for another operation bless a partial mutation.
  local completed = {
    claim={ok=true}, classify={classified=true},
    propose={ok=true, expired=true, migration_debt=true},
    settle={ok=true, unchanged=true, current=true},
    terminal={ok=true, none=true},
    retire={ok=true, none=true}, retire_missing={ok=true, none=true},
    retire_idle={ok=true}, retire_policy={ok=true},
    publish={published=true}, revoke={published=true}
  }
  if type(result) ~= 'table' or not completed[op] or not completed[op][result[1]] then
    return {'dirty_result'}
  end
  if raw.call('GET', guard) ~= 'dirty:' .. token then return {'guard_lost'} end
  raw.call('SET', guard, 'clean:' .. token)
end
return result
"""
    )


GUARDED_LEDGER_SCRIPT = guarded_ledger_script()
