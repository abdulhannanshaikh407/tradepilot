import React, { useEffect } from "react";
import { useRouter } from "next/router";

import Layout from "components/Layout";
import { useAuth } from "lib/auth";

export default function DashboardPage({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="animate-pulse text-sm text-slate-500">Loading workspace…</div>
      </div>
    );
  }

  return <Layout>{children}</Layout>;
}