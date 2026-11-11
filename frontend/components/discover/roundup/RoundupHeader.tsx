/**
 * #10357 — the round-up card's header: kicker left, tag right, then the
 * headline. A NEW part, built to Fable's R4 reference; it is deliberately not
 * `BundleHeader` (Alex, 2026-10-06: "The header and rows are not the existing
 * grouped-card parts").
 *
 * R4 measurements: kicker 11px/600/0.09em uppercase in ink3; tag 11px/600 in
 * --text-secondary-strong on --surface-elevated, 2×9 padding, fully rounded;
 * headline 23px/1.2/700/−0.015em balanced, 8 below the header line (the card's
 * 14 gap less 6), dropping to 19px/1.25 over 44 characters.
 */
export function RoundupHeader({
  kicker,
  tag,
  title,
  subtitle,
  longHeadline,
}: {
  kicker: string;
  tag: string | null;
  title: string;
  subtitle?: string | null;
  longHeadline: boolean;
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-[10px]" data-testid="roundup-header">
        <span className="text-[11px] font-semibold uppercase tracking-[0.09em] text-text-secondary">{kicker}</span>
        {tag ? (
          <span
            className="rounded-full bg-surface-elevated px-[9px] py-[2px] text-[11px] font-semibold text-text-secondary-strong"
            data-testid="roundup-tag"
          >
            {tag}
          </span>
        ) : null}
      </div>
      <h3
        className={`-mt-[6px] font-bold tracking-[-0.015em] text-text-primary [text-wrap:balance] ${
          longHeadline ? "text-[19px] leading-[1.25]" : "text-[23px] leading-[1.2]"
        }`}
        data-testid="roundup-headline"
        data-long={longHeadline ? "true" : undefined}
      >
        {title}
      </h3>
      {subtitle ? (
        <p
          className="-mt-[6px] text-[13px] font-medium leading-[1.35] text-text-secondary"
          data-testid="roundup-subtitle"
        >
          {subtitle}
        </p>
      ) : null}
    </>
  );
}
