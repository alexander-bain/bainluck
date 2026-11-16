"use client";

import Link from "next/link";
import { collegeSchoolName, isCollegeSport } from "@/lib/teamShortName";
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
  const label = children ?? (isCollegeSport(sportKey) ? collegeSchoolName(name) : name);

  if (!url) {
    return <span className={className} style={style}>{label}</span>;
  }

  return (
    <Link
      href={url}
      onClick={(e) => e.stopPropagation()}
      className={className}
      style={style}
    >
      {label}
    </Link>
  );
}
