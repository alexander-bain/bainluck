"use client";

export default function RuntimeActionButton({
  title,
  description,
  busy,
  onClick,
}: {
  title: string;
  description: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="text-left rounded-lg border border-surface-border bg-surface-card p-3 hover:border-accent-brand/40 disabled:opacity-60"
    >
      <div className="text-xs font-semibold text-text-primary">
        {busy ? "Applying..." : title}
      </div>
      <div className="mt-1 text-[11px] leading-4 text-text-muted">{description}</div>
    </button>
  );
}
