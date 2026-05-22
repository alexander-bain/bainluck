"use client";

import { Suspense } from "react";
import AdminAuthProvider from "@/components/admin/AdminAuthProvider";
import AdminSidebar from "@/components/admin/AdminSidebar";
import AdminErrorBoundary from "@/components/admin/AdminErrorBoundary";
import StoryBanner from "@/components/admin/StoryMode";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminAuthProvider>
      <div className="flex min-h-[calc(100vh-64px)]">
        <AdminSidebar />
        <div className="flex-1 min-w-0 px-4 md:px-6 py-4">
          <Suspense fallback={null}>
            <StoryBanner />
          </Suspense>
          <AdminErrorBoundary>
            {children}
          </AdminErrorBoundary>
        </div>
      </div>
    </AdminAuthProvider>
  );
}
