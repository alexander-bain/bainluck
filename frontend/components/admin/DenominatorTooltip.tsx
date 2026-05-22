"use client";

import { useState, useRef, useEffect } from "react";
import { Info } from "lucide-react";

interface DenominatorTooltipProps {
  numerator: string;
  denominator: string;
  exclusions?: string[];
  note?: string;
}

export default function DenominatorTooltip({
  numerator,
  denominator,
  exclusions,
  note,
}: DenominatorTooltipProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <span className="relative inline-flex" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="p-0.5 text-text-muted hover:text-text-secondary transition-colors"
        title="How this metric is calculated"
      >
        <Info className="w-3 h-3" />
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 w-64 bg-surface-card border border-surface-border rounded-lg shadow-lg p-3 text-xs">
          <div className="mb-2">
            <span className="font-semibold text-accent-brand">Numerator: </span>
            <span className="text-text-primary">{numerator}</span>
          </div>
          <div className="mb-2">
            <span className="font-semibold text-text-primary">Denominator: </span>
            <span className="text-text-primary">{denominator}</span>
          </div>
          {exclusions && exclusions.length > 0 && (
            <div className="mb-2">
              <span className="font-semibold text-text-secondary">Excluded:</span>
              <ul className="list-disc list-inside text-text-muted mt-0.5">
                {exclusions.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}
          {note && <p className="text-text-muted italic">{note}</p>}
        </div>
      )}
    </span>
  );
}
