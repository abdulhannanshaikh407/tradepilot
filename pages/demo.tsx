import React, { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Head from "next/head";

import { useAuth } from "lib/auth";
import { BarChart3 } from "lucide-react";

export default function Demo() {
  const router = useRouter();
  const { demo, user } = useAuth();
  const [status, setStatus] = useState("Preparing your demo workspace…");

  useEffect(() => {
    const enter = async () => {
      try {
        await demo();
        router.replace("/dashboard");
      } catch {
        setStatus("Could not enter the demo. Please try again.");
      }
    };
    if (!user) {
      const timer = setTimeout(enter, 800);
      return () => clearTimeout(timer);
    }
    router.replace("/dashboard");
  }, [user, demo, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-bg px-4">
      <Head>
        <title>Demo — TradePilot AI</title>
      </Head>
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft">
        <BarChart3 className="h-6 w-6 animate-pulse text-emerald-400" />
      </div>
      <p className="mt-4 animate-pulse text-sm text-slate-400">{status}</p>
    </div>
  );
}