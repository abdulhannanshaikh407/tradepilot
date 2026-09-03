import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import clsx from "clsx";
import {
  BarChart3,
  Bell,
  FlaskConical,
  Flame,
  LayoutDashboard,
  LogOut,
  Menu,
  Radio,
  Settings,
  Signal,
  User,
  Video,
  X,
  Zap,
  CreditCard,
  Layers,
  Building2,
} from "lucide-react";

import { api, timeAgo, TOKEN_KEY } from "lib/api";
import { useAuth } from "lib/auth";
import type { Notification } from "lib/types";
import { useToast } from "./ui";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/builder", label: "Strategy Builder", icon: Layers },
  { href: "/dashboard/analyzer", label: "YouTube Analyzer", icon: Video },
  { href: "/dashboard/strategies", label: "Strategies", icon: Zap },
  { href: "/dashboard/signals", label: "Signals", icon: Signal },
  { href: "/dashboard/backtesting", label: "Backtesting", icon: BarChart3 },
  { href: "/dashboard/performance", label: "Performance", icon: Flame },
  { href: "/dashboard/tradingview", label: "TradingView", icon: Radio },
  { href: "/dashboard/broker-settings", label: "Broker Settings", icon: Building2 },
  { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, logout, loading } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const { toast } = useToast();

  const loadNotifications = useCallback(async () => {
    try {
      const [countRes, listRes] = await Promise.all([
        api<{ count: number }>("/notifications/unread-count"),
        api<Notification[]>("/notifications?limit=6"),
      ]);
      setUnread(countRes.count);
      setNotifs(listRes);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (user) loadNotifications();
  }, [user, loadNotifications]);

  useEffect(() => {
    setSidebarOpen(false);
  }, [router.pathname]);

  const handleLogout = () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_KEY);
    }
    logout();
    router.push("/");
  };

  const markAllRead = async () => {
    await api("/notifications/read", { method: "POST" });
    setUnread(0);
    setNotifs((prev) => prev.map((n) => ({ ...n, is_read: true })));
    toast("All notifications marked as read", "success");
  };

  const sidebar = (
    <aside className="flex h-full w-64 flex-col border-r border-line bg-bg-soft">
      <Link href="/dashboard" className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15">
          <BarChart3 className="h-4.5 w-4.5 h-[18px] w-[18px] text-emerald-400" />
        </div>
        <div>
          <div className="text-sm font-bold text-white">TradePilot AI</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">Intelligence</div>
        </div>
      </Link>

      <div className="mx-4 mb-3 rounded-lg border border-line bg-bg-card px-3 py-2">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">Plan</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
          <FlaskConical className="h-3 w-3" /> {user?.plan || "FREE"}
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3">
        {NAV.map((item) => {
          const active =
            item.href === "/dashboard"
              ? router.pathname === "/dashboard"
              : router.pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition",
                active
                  ? "bg-accent-soft text-emerald-300"
                  : "text-slate-400 hover:bg-bg-hover hover:text-slate-200"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
              {item.href === "/dashboard/notifications" && unread > 0 && (
                <span className="ml-auto rounded-full bg-danger px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {unread}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line p-3">
        <div className="mb-3 rounded-lg border border-line bg-bg-card p-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Demo workspace</div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
            All data here is simulated for demonstration.
          </p>
        </div>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] text-slate-400 transition hover:bg-bg-hover hover:text-red-300"
        >
          <LogOut className="h-4 w-4" /> Log out
        </button>
      </div>
    </aside>
  );

  return (
    <div className="flex min-h-screen bg-bg">
      {/* Desktop sidebar */}
      <div className="fixed inset-y-0 left-0 z-30 hidden lg:block">{sidebar}</div>

      {/* Mobile sidebar */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/70" onClick={() => setSidebarOpen(false)} />
          <div className="absolute inset-y-0 left-0 animate-fade-in">
            <button
              onClick={() => setSidebarOpen(false)}
              className="absolute -right-10 top-4 text-slate-400"
            >
              <X className="h-6 w-6" />
            </button>
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        {/* Top bar */}
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-bg/80 px-4 py-3 backdrop-blur sm:px-6">
          <button
            className="text-slate-400 hover:text-white lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <Link
            href="/dashboard/analyzer"
            className="btn-primary hidden sm:inline-flex"
          >
            <Video className="h-4 w-4" /> Analyze a Video
          </Link>
          <div className="flex-1" />

          <div className="relative">
            <button
              className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-bg-card text-slate-400 hover:text-white"
              onClick={() => {
                setNotifOpen((v) => !v);
                if (!notifOpen) loadNotifications();
              }}
            >
              <Bell className="h-4 w-4" />
              {unread > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </button>
            {notifOpen && (
              <div className="absolute right-0 top-11 w-80 overflow-hidden rounded-xl border border-line bg-bg-card shadow-card animate-fade-in">
                <div className="flex items-center justify-between border-b border-line px-4 py-3">
                  <span className="text-sm font-semibold text-slate-100">Notifications</span>
                  <button onClick={markAllRead} className="text-xs text-emerald-400 hover:underline">
                    Mark all read
                  </button>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {notifs.length === 0 ? (
                    <div className="px-4 py-8 text-center text-xs text-slate-500">
                      No notifications
                    </div>
                  ) : (
                    notifs.map((n) => (
                      <div
                        key={n.id}
                        className={clsx(
                          "border-b border-line/60 px-4 py-3 last:border-0",
                          !n.is_read && "bg-accent-soft"
                        )}
                      >
                        <div className="text-xs font-semibold text-slate-200">{n.title}</div>
                        {n.message && (
                          <div className="mt-0.5 line-clamp-2 text-[11px] text-slate-500">{n.message}</div>
                        )}
                        <div className="mt-1 text-[10px] text-slate-600">{timeAgo(n.created_at)}</div>
                      </div>
                    ))
                  )}
                </div>
                <Link
                  href="/dashboard/notifications"
                  className="block border-t border-line px-4 py-2.5 text-center text-xs text-emerald-400 hover:bg-bg-hover"
                >
                  View all
                </Link>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="hidden text-right sm:block">
              <div className="text-xs font-semibold text-slate-200">{user?.name}</div>
              <div className="flex items-center justify-end gap-1 text-[10px] text-slate-500">
                {user?.is_demo && <span className="chip bg-warn/15 text-amber-300">DEMO</span>}
                <span>{user?.plan}</span>
              </div>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-sm font-bold text-emerald-400">
              {(user?.name || "T").slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6">{children}</main>

        <footer className="border-t border-line px-6 py-4">
          <p className="text-center text-[11px] leading-relaxed text-slate-600">
            Trading involves substantial risk. Backtest results are hypothetical and past
            performance does not guarantee future results.
          </p>
        </footer>
      </div>
    </div>
  );
}