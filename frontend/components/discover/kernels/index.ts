/**
 * Discover card kernels — the unified card family (Queue L2-125 / Item 0, Phase 1).
 *
 * Shape → kernel (see lib/marketShape.ts) — the full five-kernel family:
 *   claim     → ClaimKernel      (number+delta)
 *   quantity  → QuantityKernel   (ladder-strip)
 *   duel      → DuelKernel       (split)
 *   field     → FieldKernel      (top-3 leaderboard)
 *   container → ContainerKernel  (headliner + bundle count)
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
export { FieldKernel } from "./FieldKernel";
export type { FieldKernelProps, FieldEntrant } from "./FieldKernel";
export { QuantityKernel } from "./QuantityKernel";
export type { QuantityKernelProps, QuantitySettledRung } from "./QuantityKernel";
export { ContainerKernel } from "./ContainerKernel";
export type { ContainerKernelProps } from "./ContainerKernel";
