"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function PlayoffsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/sport");
  }, [router]);
  return null;
}
