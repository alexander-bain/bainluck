/**
 * Discover card kernels — the unified card family (Queue L2-125 / Item 0, Phase 1).
 *
 * Shape → kernel (see lib/marketShape.ts):
 *   claim → ClaimKernel (number+delta)   ·   duel → DuelKernel (split)
 * Quantity / Field / Container land in later phases; they still render on the
 * existing FuturesCard/Comparison/Tournament components until then.
 *
 * All kernels share KernelCard chrome (state + ONE angle + footer) and the
 * AngleBadge system (the WHY-now, replacing the Just Happened badge soup).
 */

export { KernelCard } from "./KernelCard";
export type { KernelState, KernelGrade } from "./KernelCard";
export { AngleBadge, pickAngle, MOVER_THRESHOLD_POINTS } from "./AngleBadge";
export type { Angle, AngleValue, AngleSignals } from "./AngleBadge";
export { ClaimKernel } from "./ClaimKernel";
export type { ClaimKernelProps } from "./ClaimKernel";
export { DuelKernel } from "./DuelKernel";
export type { DuelKernelProps } from "./DuelKernel";
