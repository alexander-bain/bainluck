"use client";

/**
 * @deprecated Use EIBadge instead. This file is a backward-compatibility wrapper.
 */

import type { EIData } from "@/lib/types";
import EIBadge, { EIInline } from "./EIBadge";

interface PulseBadgeProps {
  pulse: EIData;
  size?: "sm" | "md" | "lg";
  showTooltip?: boolean;
  linkToExplainer?: boolean;
}

export default function PulseBadge({
  pulse,
  size = "sm",
  showTooltip = true,
  linkToExplainer = true,
}: PulseBadgeProps) {
  return (
    <EIBadge
      ei={pulse}
      size={size}
      showTooltip={showTooltip}
      linkToExplainer={linkToExplainer}
    />
  );
}

export function PulseInline({ pulse }: { pulse: EIData }) {
  return <EIInline ei={pulse} />;
}
