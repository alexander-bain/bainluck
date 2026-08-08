/**
 * My Stuff identity boundary (L2-217 Item 1 / C88).
 *
 * The implementation moved to `@/lib/clientPrincipal` in UX-P017 (#1496), where
 * three more surfaces needed the identical rule. This file stays as the My Stuff
 * facade for one reason worth stating: `myStuffKey` must keep emitting the exact
 * same array it emitted before the move. It is a live SWR cache key, so changing
 * its shape would not be a refactor — it would be a cache miss for every signed
 * in user, silently re-running L2-217's fix as a regression.
 *
 * `__tests__/lib/myStuffIdentity.test.ts` pins that shape.
 */

import { principalKey } from "./clientPrincipal";

export {
  resolvePrincipal as resolveMyStuffPrincipal,
  bindToPrincipal,
  dataForPrincipal,
} from "./clientPrincipal";

export type {
  AuthSnapshot as MyStuffAuthSnapshot,
  PrincipalBound,
} from "./clientPrincipal";

/**
 * The SWR key for one My Stuff record, or `null` to SUPPRESS the request.
 *
 * Byte-identical to the pre-UX-P017 output: `["my-stuff", resource, principal,
 * ...extra]`.
 */
export function myStuffKey(
  principal: string | null,
  resource: string,
  extra: ReadonlyArray<string | number> = []
): (string | number)[] | null {
  return principalKey("my-stuff", principal, resource, extra);
}
