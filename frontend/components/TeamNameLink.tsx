"use client";

import Link from "next/link";
import { buildTeamPageUrl } from "@/lib/teamUrls";

interface TeamNameLinkProps {
  name: string;
  sportKey: string | null | undefined;
  className?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export default function TeamNameLink({
  name,
  sportKey,
  className,
  style,
  children,
}: TeamNameLinkProps) {
  const url = buildTeamPageUrl(name, sportKey);

  if (!url) {
    const spanClassName = className
      ? className.replace(/\bhover:underline\b/g, "").replace(/\s+/g, " ").trim()
      : undefined;
    return <span className={spanClassName || undefined} style={style}>{children ?? name}</span>;
  }

  return (
    <Link
      href={url}
      onClick={(e) => e.stopPropagation()}
      className={className}
      style={style}
    >
      {children ?? name}
    </Link>
  );
}
