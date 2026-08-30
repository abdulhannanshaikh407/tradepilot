import React, { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import { BellRing, CheckCheck, Trash2, X } from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, EmptyState, Skeleton, useToast } from "components/ui";
import { api, timeAgo } from "lib/api";
import type { Notification } from "lib/types";

function iconFor(type: string) {
  switch (type) {
    case "analysis":
      return "🧠";
    case "backtest":
      return "📊";
    case "signal":
      return "📡";
    case "webhook":
      return "🔗";
    case "billing":
      return "💳";
    default:
      return "🔔";
  }
}

export default function Notifications() {
  const { toast } = useToast();
  const [items, setItems] = useState<Notification[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api<Notification[]>("/notifications"));
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to load notifications", "error");
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const markAll = async () => {
    setBusy(true);
    try {
      await api("/notifications/read", { method: "POST" });
      toast("All notifications marked as read", "success");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Update failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const markOne = async (n: Notification) => {
    if (n.is_read) return;
    try {
      await api(`/notifications/${n.id}/read`, { method: "POST" });
      load();
    } catch {
      /* ignore */
    }
  };

  const del = async (id: number) => {
    try {
      await api(`/notifications/${id}`, { method: "DELETE" });
      load();
    } catch {
      toast("Delete failed", "error");
    }
  };

  const unread = items?.filter((n) => !n.is_read).length ?? 0;

  return (
    <DashboardPage>
      <Head>
        <title>Notifications — TradePilot AI</title>
      </Head>

      <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-white">
            <BellRing className="h-5 w-5 text-emerald-400" /> Notifications
          </h1>
          <p className="text-xs text-slate-500">{unread > 0 ? `${unread} unread` : "You're all caught up"}</p>
        </div>
        {unread > 0 && (
          <Button variant="secondary" loading={busy} onClick={markAll}>
            <CheckCheck className="h-4 w-4" /> Mark all read
          </Button>
        )}
      </div>

      <Card className="overflow-hidden p-0">
        {!items ? (
          <Skeleton className="h-48 w-full" />
        ) : items.length === 0 ? (
          <EmptyState title="No notifications" message="Analyses, backtests, signals and webhook events will land here." />
        ) : (
          <div className="divide-y divide-line/60">
            {items.map((n) => (
              <div
                key={n.id}
                onClick={() => markOne(n)}
                className={`flex cursor-pointer items-start gap-3 px-5 py-3.5 transition hover:bg-bg-soft ${n.is_read ? "" : "bg-accent-soft/40"}`}
              >
                <span className="mt-0.5 text-base">{iconFor(n.type)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-200">{n.title}</span>
                    {!n.is_read && (
                      <span className="h-2 w-2 rounded-full bg-emerald-400" title="Unread" />
                    )}
                    <span className="text-[11px] text-slate-500">{timeAgo(n.created_at)}</span>
                  </div>
                  {n.message && (
                    <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{n.message}</p>
                  )}
                  <span className="mt-1 inline-block text-[10px] uppercase tracking-widest text-slate-600">
                    {n.type}
                  </span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    del(n.id);
                  }}
                  className="rounded-lg p-1.5 text-slate-600 hover:bg-danger-soft hover:text-red-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </DashboardPage>
  );
}