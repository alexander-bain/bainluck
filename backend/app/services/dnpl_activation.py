"""Explicit attended recovery, never a startup hook or a retry loop.

Caller owns the all-writer interlock and the exact preparing allocation. This
module cannot acquire that interlock, allocate an incarnation, change policy,
restart Redis or start producers. A failed/uncertain mutation ends the attempt;
only readback may resolve it. The operator must retain the candidate identity.

One admission fence and two physical namespace slots keep storage bounded even
when a rollback restores a forgotten predecessor. Missing admission evidence on
an unchanged primary refuses recovery, rather than letting a delayed old arm
resurrect deleted keys.
Primary identity/rollback guarantees still require provider qualification.
"""

import asyncio
from dataclasses import replace

from app.services.dnpl_authority import Authority, AuthorityConflict, AuthorityStore
from app.utils.dnpl_redis_authority import (
    _IDENTITY,
    INITIALIZE_SCRIPT,
    INITIAL_READBACK_SCRIPT,
    guard_token,
    namespace_keys,
)

ADMISSION_KEY = "live:blend_preview:v3:activation"
COMMAND_BUDGET_S = 0.150

# Args: ordinary guard/run/repl, exact activation token, incarnation, bootstrap.
# A missing fence may be created only by the one durable arm permission issued
# at the first allocation for a primary identity. Successors use HSET on an
# existing lower fence; neither eviction nor retry authorizes recreating it.
ARM_SCRIPT = _IDENTITY + r"""
if #KEYS ~= 1 then return {'malformed'} end
local key = KEYS[1]
if redis.call('EXISTS', key) == 0 then
  if ARGV[6] ~= '1' then return {'admission_lost'} end
else
  if redis.call('TYPE', key).ok ~= 'hash' or redis.call('HLEN', key) ~= 3 then
    return {'admission_corrupt'}
  end
  local old = redis.call('HGET', key, 'incarnation')
  local state = redis.call('HGET', key, 'state')
  local token = redis.call('HGET', key, 'token')
  if not old or not string.match(old, '^[1-9][0-9]*$') or #old > 16
      or not token or #token > 512 or string.sub(token, 1, #old + 1) ~= old .. '|'
      or (state ~= 'armed' and state ~= 'used') then
    return {'admission_corrupt'}
  end
  if tonumber(old) >= tonumber(ARGV[5]) then return {'superseded'} end
end
redis.call('HSET', key, 'incarnation', ARGV[5], 'token', ARGV[4], 'state', 'armed')
return {'armed'}
"""

# Exactly matches the current operation, before inspecting/removing old keys.
_FENCE = r"""
if #KEYS ~= 7 then return {'malformed'} end
local admission = KEYS[7]
if redis.call('TYPE', admission).ok ~= 'hash'
    or redis.call('HLEN', admission) ~= 3
    or redis.call('HGET', admission, 'token') ~= ARGV[4]
    or redis.call('HGET', admission, 'incarnation') ~= ARGV[5] then
  return {'admission_lost'}
end
local stage = redis.call('HGET', admission, 'state')
"""

INITIALIZE_ONCE_SCRIPT = _IDENTITY + _FENCE + r"""
if stage ~= 'armed' then return {'send_consumed'} end
-- Consume BEFORE initializer writes. Partial failure cannot authorize replay.
redis.call('HSET', admission, 'state', 'used')
table.remove(KEYS, 7)
""" + INITIALIZE_SCRIPT

VERIFY_INITIAL_SCRIPT = _IDENTITY + _FENCE + r"""
if stage ~= 'used' then return {'not_initialized'} end
table.remove(KEYS, 7)
""" + INITIAL_READBACK_SCRIPT


# A physical slot may now hold a newer incarnation. Even replacement cleanup,
# whose old admission fence was lost, must compare the exact occupant atomically.
# Absence is safe to acknowledge; partial loss without the guard is not identity.
def _occupant_check(argument: int) -> str:
    return r"""
if redis.call('EXISTS', KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6]) ~= 0 then
  if redis.call('TYPE', KEYS[6]).ok ~= 'string' then return {'occupant_unknown'} end
  local occupant = redis.call('GET', KEYS[6])
  local expected = ARGV[""" + str(argument) + r"""]
  if not expected or expected == '' then return {'occupant_unknown'} end
  if occupant ~= 'clean:' .. expected and occupant ~= 'dirty:' .. expected
      and occupant ~= 'initializing:' .. expected then return {'occupant_changed'} end
end
"""


CLEAN_PREDECESSOR_SCRIPT = _IDENTITY + _FENCE + r"""
if stage ~= 'armed' and stage ~= 'used' then return {'admission_corrupt'} end
-- Python derives all six keys from the exact durable predecessor, never a scan.
for i = 1, 6 do
  if KEYS[i] == admission then return {'malformed'} end
end
""" + _occupant_check(6) + r"""
redis.call('DEL', KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6])
if redis.call('EXISTS', KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6]) ~= 0 then
  return {'cleanup_unverified'}
end
return {'retired'}
"""


VERIFY_RETIRED_SCRIPT = _IDENTITY + _FENCE + r"""
if stage ~= 'armed' and stage ~= 'used' then return {'admission_corrupt'} end
if redis.call('EXISTS', KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6]) ~= 0 then
  return {'cleanup_unverified'}
end
return {'retired'}
"""


# Replacement-primary cleanup cannot require the lost primary's admission
# fence. Atomic INFO must instead prove a different identity from BOTH records:
# neither current nor retired in-flight command may execute on this primary.
_REPLACEMENT_IDENTITY = _IDENTITY + r"""
if #KEYS ~= 6 or #ARGV ~= 8 then return {'malformed'} end
if (ARGV[2] == ARGV[4] and ARGV[3] == ARGV[5])
    or (ARGV[2] == ARGV[6] and ARGV[3] == ARGV[7]) then
  return {'identity_not_replaced'}
end
"""
_VERIFY_ABSENCE = r"""
if redis.call('EXISTS', KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6]) ~= 0 then
  return {'cleanup_unverified'}
end
return {'retired'}
"""
CLEAN_REPLACED_PREDECESSOR_SCRIPT = _REPLACEMENT_IDENTITY + _occupant_check(8) + r"""
redis.call('DEL', KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6])
""" + _VERIFY_ABSENCE
VERIFY_REPLACED_PREDECESSOR_SCRIPT = _REPLACEMENT_IDENTITY + _VERIFY_ABSENCE


def activation_token(authority: Authority) -> str:
    return f"{authority.incarnation}|{authority.operation_id}|{guard_token(authority)}"


def arguments(authority: Authority) -> tuple[str, ...]:
    return (
        guard_token(authority),
        authority.redis_run_id,
        authority.redis_master_replid,
        activation_token(authority),
        str(authority.incarnation),
    )


class ActivationRefused(RuntimeError):
    """No automatic resend, recovery allocation or ready transition permitted."""


async def eval_once(client, script, keys, args):
    """One low-level send/read; bypass redis-py's automatic command retry path.

    A timeout may leave a command queued at Redis. Disconnecting is hygiene, not
    proof of non-execution. Durable send consumption + Lua admission fence make
    that ambiguity safe. Redis connection setup may retry connection/handshake;
    it must not resend this EVAL. No register_script/NOSCRIPT fallback either.
    """
    pool = client.connection_pool
    connection = None
    try:
        async with asyncio.timeout(COMMAND_BUDGET_S):
            connection = await pool.get_connection()
            await connection.send_command(
                "EVAL", script, len(keys), *keys, *args, check_health=False
            )
            result = await connection.read_response()
        return result
    except BaseException:
        if connection is not None:
            try:
                async with asyncio.timeout(COMMAND_BUDGET_S):
                    await connection.disconnect()
            except (Exception, asyncio.CancelledError):
                pass
        raise
    finally:
        if connection is not None:
            await pool.release(connection)


def require_result(result, status):
    if result not in ([status], [status.encode()]):
        raise ActivationRefused(f"expected {status}, got {result!r}")


class ActivationController:
    """Explicit operator steps only; ordinary producers never call this class."""

    def __init__(self, store: AuthorityStore, redis):
        self.store = store
        self.redis = redis

    async def arm(self, prepared: Authority) -> None:
        bootstrap = await self.store.take_activation_step(prepared, 1)
        require_result(
            await eval_once(
                self.redis,
                ARM_SCRIPT,
                (ADMISSION_KEY,),
                (*arguments(prepared), "1" if bootstrap else "0"),
            ),
            "armed",
        )

    async def initialize(self, prepared: Authority) -> None:
        await self.store.take_activation_step(prepared, 2)
        require_result(
            await eval_once(
                self.redis,
                INITIALIZE_ONCE_SCRIPT,
                (*namespace_keys(prepared), ADMISSION_KEY),
                arguments(prepared),
            ),
            "initialized",
        )

    async def ready(self, prepared: Authority) -> Authority:
        if (
            prepared.state != "preparing"
            or await self.store.activation_step(prepared) != 2
        ):
            raise AuthorityConflict(
                "initialization send not consumed for current preparation"
            )
        require_result(
            await eval_once(
                self.redis,
                VERIFY_INITIAL_SCRIPT,
                (*namespace_keys(prepared), ADMISSION_KEY),
                arguments(prepared),
            ),
            "initial_verified",
        )
        return await self.store.ready(prepared)

    async def retire(self, current: Authority) -> None:
        if await self.store.read() != current:
            raise AuthorityConflict("cleanup current authority changed")
        old = await self.store.read_retirement()
        if old is None or not 0 < old.incarnation < current.incarnation:
            raise AuthorityConflict("no exact older namespace to retire")
        require_result(
            await eval_once(
                self.redis,
                CLEAN_PREDECESSOR_SCRIPT,
                (*namespace_keys(old), ADMISSION_KEY),
                (*arguments(current), guard_token(old)),
            ),
            "retired",
        )
        await self.store.complete_retirement(current, old)

    async def acknowledge_retirement(self, current: Authority) -> None:
        """Resolve a lost cleanup reply with reads, never another Redis deletion.

        An exact newer admission fence prevents an old delayed initializer from
        changing the observed absence. Lost PG acknowledgement is resolved by
        read_retirement(); this method never infers success from an absent receipt.
        """
        if await self.store.read() != current:
            raise AuthorityConflict("cleanup current authority changed")
        old = await self.store.read_retirement()
        if old is None or not 0 < old.incarnation < current.incarnation:
            raise AuthorityConflict("no exact older namespace to acknowledge")
        require_result(
            await eval_once(
                self.redis,
                VERIFY_RETIRED_SCRIPT,
                (*namespace_keys(old), ADMISSION_KEY),
                arguments(current),
            ),
            "retired",
        )
        await self.store.complete_retirement(current, old)

    async def retire_after_primary_change(
        self,
        current: Authority,
        *,
        redis_run_id: str,
        redis_master_replid: str,
        readback_only: bool = False,
    ) -> None:
        """Free the exact predecessor before allocating on a replacement primary.

        This does not rewrite current authority or erase its namespace. Atomic
        INFO must prove the supplied identity differs from current AND retired;
        their delayed commands then cannot execute here. Delete/verify only the
        recorded predecessor, retain exact PG CAS, then ordinary prepare can
        record the current namespace as the next predecessor. No extra slot.
        Same-identity rollback remains excluded by provider qualification.
        """
        if await self.store.read() != current:
            raise AuthorityConflict("cleanup current authority changed")
        old = await self.store.read_retirement()
        if old is None or not 0 < old.incarnation < current.incarnation:
            raise AuthorityConflict("no exact older namespace to retire")
        replacement = replace(
            current,
            redis_run_id=redis_run_id,
            redis_master_replid=redis_master_replid,
        )
        identity = (replacement.redis_run_id, replacement.redis_master_replid)
        if identity in (
            (current.redis_run_id, current.redis_master_replid),
            (old.redis_run_id, old.redis_master_replid),
        ):
            raise ActivationRefused("replacement must fence both retained identities")
        script = (
            VERIFY_REPLACED_PREDECESSOR_SCRIPT
            if readback_only
            else CLEAN_REPLACED_PREDECESSOR_SCRIPT
        )
        require_result(
            await eval_once(
                self.redis,
                script,
                namespace_keys(old),
                (
                    guard_token(replacement),
                    *identity,
                    current.redis_run_id,
                    current.redis_master_replid,
                    old.redis_run_id,
                    old.redis_master_replid,
                    guard_token(old),
                ),
            ),
            "retired",
        )
        await self.store.complete_retirement(current, old)

    async def read_ready(self, prepared: Authority) -> bool:
        """Resolve a lost ready reply without replay or a new allocation.

        This answers only the durable transition. Runtime still independently
        validates namespace/identity; it is not a command to start any writer.
        """
        return await self.store.read() == replace(prepared, state="ready")
