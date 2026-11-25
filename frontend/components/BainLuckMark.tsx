/**
 * Brand clover emblem (`original artwork supplied by Alex`, Decision 382: B / 390: A).
 * Clear-background transparent mark for UI chrome (`layout`, `Footer`, nav, `/about`).
 */
export function BainLuckMark({
  size = 24,
  alt = "",
  className = "",
}: {
  size?: number;
  alt?: string;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/brand/bainluck-mark-128.png"
      alt={alt}
      width={size}
      height={size}
      aria-hidden={alt === "" ? true : undefined}
      data-testid="bainluck-brand-mark"
      className={`shrink-0 inline-block align-middle object-contain ${className}`.trim()}
    />
  );
}

export default BainLuckMark;
