import React, { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import { Check, Cpu, Layers, Sparkles, TerminalSquare, Video } from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, Skeleton, useToast } from "components/ui";
import { useAuth } from "lib/auth";
import { api } from "lib/api";
import type { BillingPlan, CurrentPlan } from "lib/types";

const PLAN_META: Record<string, { color: string; icon: React.ReactNode }> = {
  FREE: { color: "text-slate-300", icon: <Sparkles className="h-5 w-5" /> },
  PRO: { color: "text-emerald-300", icon: <Cpu className="h-5 w-5" /> },
  BUSINESS: { color: "text-sky-300", icon: <TerminalSquare className="h-5 w-5" /> },
};

export default function Billing() {
  const { toast } = useToast();
  const { refreshUser } = useAuth();
  const [plans, setPlans] = useState<BillingPlan | null>(null);
  const [current, setCurrent] = useState<CurrentPlan | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [p, c] = await Promise.all([
      api<BillingPlan>("/billing/plans"),
      api<CurrentPlan>("/billing/current"),
    ]);
    setPlans(p);
    setCurrent(c);
  }, []);

  useEffect(() => {
    load().catch((err) => toast(err instanceof Error ? err.message : "Failed to load billing", "error"));
  }, [load, toast]);

  const select = async (planKey: string) => {
    setSelecting(planKey);
    try {
      const res = await api<{ message?: string }>(`/billing/select-plan?plan=${planKey}`, { method: "POST" });
      await refreshUser();
      toast(res?.message || `Switched to the ${planKey} plan`, "success");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Plan update failed", "error");
    } finally {
      setSelecting(null);
    }
  };

  const LIMIT_ALIAS: Record<string, string> = {
    analyses: "analyses_per_day",
    backtests: "backtests_per_day",
    signals: "signals_per_day",
    webhooks: "webhooks_per_day",
    strategies: "strategies",
    notifications: "strategies",
  };

  const usageLimit = (key: string) => {
    if (!current) return null;
    const used = current.usage[key] ?? 0;
    const limit = current.limits[LIMIT_ALIAS[key]];
    return { used, limit };
  };

  return (
    <DashboardPage>
      <Head>
        <title>Billing — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">Billing & Plans</h1>
        <p className="text-xs text-slate-500">
          Current plan: <span className="font-semibold text-emerald-400">{current?.plan ?? "FREE"}</span>
        </p>
      </div>

      {!plans || !current ? (
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-64 w-full" />)}
        </div>
      ) : (
        <div>
          <div className="grid gap-4 md:grid-cols-3">
            {Object.entries(plans).map(([key, plan]) => {
              const p = plan as { label: string; price: number; features: string[] };
              const isCurrent = current.plan === key;
              const meta = PLAN_META[key] ?? PLAN_META.FREE;
              const featured = key === "PRO";
              return (
                <div
                  key={key}
                  className={`card relative flex flex-col p-6 ${featured ? "border-accent/50 shadow-glow" : ""} ${
                    isCurrent ? "ring-1 ring-accent/60" : ""
                  }`}
                >
                  {featured && (
                    <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-accent px-3 py-0.5 text-[10px] font-bold uppercase tracking-wider text-black">
                      Most popular
                    </span>
                  )}
                  <div className={`flex items-center gap-2 ${meta.color}`}>
                    {meta.icon}
                    <span className="text-sm font-bold text-white">{p.label}</span>
                    {isCurrent && <span className="chip bg-accent-soft text-emerald-300">CURRENT</span>}
                  </div>
                  <div className="mt-4">
                    <span className="number text-3xl font-extrabold text-white">${p.price}</span>
                    <span className="text-xs text-slate-500">/month</span>
                  </div>
                  <ul className="mt-5 flex-1 space-y-2.5">
                    {p.features.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" /> {f}
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="mt-6 w-full"
                    variant={isCurrent ? "ghost" : featured ? "primary" : "secondary"}
                    disabled={isCurrent}
                    loading={selecting === key}
                    onClick={() => select(key)}
                  >
                    {isCurrent ? "Current plan" : `Switch to ${p.label}`}
                  </Button>
                </div>
              );
            })}
          </div>

          <Card title="Usage" className="mt-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {["analyses", "backtests", "signals", "webhooks", "strategies"].map((key) => {
                const u = usageLimit(key);
                if (u == null) return null;
                const pct =
                  u.limit == null || u.limit === 0
                    ? 100
                    : Math.min(100, Math.round((u.used / u.limit) * 100));
                const over = u.limit != null && u.limit > 0 && u.used >= u.limit;
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1.5 capitalize text-slate-400">
                        {key === "analyses" && <Video className="h-3.5 w-3.5" />}
                        {key === "backtests" && <TerminalSquare className="h-3.5 w-3.5" />}
                        {key === "signals" && <Layers className="h-3.5 w-3.5" />}
                        {key}
                      </span>
                      <span className={`number font-bold ${over ? "text-red-400" : "text-slate-300"}`}>
                        {u.used} / {u.limit == null || u.limit === 0 ? "∞" : u.limit}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-bg-hover">
                      <div
                        className={`h-full rounded-full ${
                          over ? "bg-red-400" : u.limit == null || u.limit === 0 ? "bg-accent/50" : "bg-emerald-400"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-4 text-[11px] text-slate-600">
              Usage resets daily. Payments are a placeholder — no card is charged.
            </p>
          </Card>
        </div>
      )}
    </DashboardPage>
  );
}