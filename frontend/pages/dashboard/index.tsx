import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Head from "next/head";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Flame,
  Radio,
  Signal,
  TrendingUp,
  Wallet,
} from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Card, DirectionBadge, EmptyState, Skeleton, SourceBadge, StatCard, StatusBadge, useToast } from "components/ui";
import { EquityCurve } from "components/charts";
import { api, formatNumber, formatSigned, timeAgo } from "lib/api";
import type { DashboardStats } from "lib/types";

export default function DashboardOverview() {
  const { toast } = useToast();
  const [data, setData] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const stats = await api<DashboardStats>("/dashboard/stats");
      setData(stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pnlPositive = (data?.net_pnl ?? 0) >= 0;

  return (
    <DashboardPage>
      <Head>
        <title>Overview — TradePilot AI</title>
      </Head>

      <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold text-white">Overview</h1>
          <p className="text-xs text-slate-500">Your trading research workspace.</p>
        </div>
        <Link href="/dashboard/analyzer" className="btn-primary">
          Analyze a YouTube Strategy <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Stat grid */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard
          label="Portfolio Value"
          value={`$${formatNumber(data?.portfolio_value)}`}
          icon={<Wallet className="h-4 w-4" />}
          loading={!data}
          tone={pnlPositive ? "green" : "red"}
        />
        <StatCard
          label="Net P&L"
          value={formatSigned(data?.net_pnl)}
          change={
            pnlPositive ? (
              <span className="inline-flex items-center gap-1 text-emerald-400">
                <ArrowUpRight className="h-3 w-3" /> simulated
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-red-400">
                <ArrowDownRight className="h-3 w-3" /> simulated
              </span>
            )
          }
          loading={!data}
          tone={pnlPositive ? "green" : "red"}
        />
        <StatCard label="Win Rate" value={`${formatNumber(data?.win_rate, 1)}%`} loading={!data} tone="info" />
        <StatCard
          label="Active Signals"
          value={data?.active_signals ?? "—"}
          icon={<Signal className="h-4 w-4" />}
          loading={!data}
        />
        <StatCard
          label="Total Trades"
          value={data?.total_trades ?? "—"}
          icon={<Activity className="h-4 w-4" />}
          loading={!data}
        />
        <StatCard
          label="Max Drawdown"
          value={`-${formatNumber(data?.max_drawdown, 1)}%`}
          icon={<Flame className="h-4 w-4" />}
          loading={!data}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* Equity curve */}
        <div className="lg:col-span-2">
          <Card title="Equity Curve" subtitle="Simulated paper-trading returns">
            {data ? (
              data.equity_curve.length > 1 ? (
                <EquityCurve data={data.equity_curve} height={280} />
              ) : (
                <EmptyState title="No trading data yet" message="Create a strategy and run your first backtest." />
              )
            ) : (
              <Skeleton className="h-72 w-full" />
            )}
          </Card>
        </div>

        {/* Strategy performance */}
        <Card title="Strategy Performance" subtitle="Latest backtest per strategy">
          {data ? (
            data.strategy_performance.length === 0 ? (
              <EmptyState title="No strategies" message="Analyze a video to get started." />
            ) : (
              <div className="space-y-3">
                {data.strategy_performance.map((s) => (
                  <div key={s.name} className="rounded-lg border border-line bg-bg-soft p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-semibold text-slate-200">{s.name}</span>
                      <span className="number text-xs font-bold text-slate-400">{s.trades} trades</span>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                      <div>
                        <div className="number text-sm font-bold text-sky-400">{formatNumber(s.win_rate, 1)}%</div>
                        <div className="text-[10px] text-slate-500">Win rate</div>
                      </div>
                      <div>
                        <div className="number text-sm font-bold text-emerald-400">
                          {formatSigned(s.return_percent, 1)}%
                        </div>
                        <div className="text-[10px] text-slate-500">Return</div>
                      </div>
                      <div>
                        <div className="number text-sm font-bold text-slate-300">{formatNumber(s.profit_factor)}</div>
                        <div className="text-[10px] text-slate-500">Profit factor</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Recent signals */}
        <Card
          title="Recent Signals"
          actions={
            <Link href="/dashboard/signals" className="text-xs text-emerald-400 hover:underline">
              View all
            </Link>
          }
        >
          {data ? (
            data.recent_signals.length === 0 ? (
              <EmptyState title="No signals yet" message="Generate signals from a strategy or use the TradingView test alert." />
            ) : (
              <div className="-mx-5">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="th">Time</th>
                      <th className="th">Asset</th>
                      <th className="th">Signal</th>
                      <th className="th">Status</th>
                      <th className="th">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_signals.map((s) => (
                      <tr key={s.id} className="tr-hover border-b border-line/60 last:border-0">
                        <td className="td whitespace-nowrap text-xs text-slate-500">{timeAgo(s.created_at)}</td>
                        <td className="td font-semibold">{s.symbol}</td>
                        <td className="td"><DirectionBadge direction={s.direction} /></td>
                        <td className="td"><StatusBadge status={s.status} /></td>
                        <td className="td"><SourceBadge source={s.source} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </Card>

        {/* Recent activity */}
        <Card
          title="Recent Activity"
          actions={
            <Link href="/dashboard/notifications" className="text-xs text-emerald-400 hover:underline">
              Notifications
            </Link>
          }
        >
          {data ? (
            data.recent_activity.length === 0 ? (
              <EmptyState title="Nothing yet" message="Your actions will appear here." />
            ) : (
              <div className="space-y-3">
                {data.recent_activity.map((a, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-bg-hover">
                      {a.type.includes("backtest") ? (
                        <BarChart3 className="h-3.5 w-3.5 text-sky-400" />
                      ) : a.type.includes("signal") || a.type.includes("webhook") ? (
                        <Radio className="h-3.5 w-3.5 text-emerald-400" />
                      ) : a.type.includes("strategy") ? (
                        <TrendingUp className="h-3.5 w-3.5 text-purple-400" />
                      ) : (
                        <Activity className="h-3.5 w-3.5 text-slate-400" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-200">{a.title}</div>
                      {a.message && (
                        <div className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">{a.message}</div>
                      )}
                    </div>
                    <div className="ml-auto shrink-0 text-[10px] text-slate-600">{a.created_at}</div>
                  </div>
                ))}
              </div>
            )
          ) : (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          )}
        </Card>
      </div>
    </DashboardPage>
  );
}