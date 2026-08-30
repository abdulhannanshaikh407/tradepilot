import React, { useCallback, useEffect, useState } from "react";
import Head from "next/head";

import DashboardPage from "components/DashboardPage";
import { Card, EmptyState, Skeleton, StatCard } from "components/ui";
import { AssetPerformance, EquityCurve, MonthlyPerformance, StrategyComparison } from "components/charts";
import { api, formatNumber, formatSigned } from "lib/api";
import type { PerformanceSummary } from "lib/types";

export default function Performance() {
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);
  const [strategies, setStrategies] = useState<{ strategies: any[] } | null>(null);
  const [assets, setAssets] = useState<{ assets: any[] } | null>(null);
  const [equity, setEquity] = useState<{ equity_curve: { timestamp: string; equity: number }[] } | null>(null);
  const [monthly, setMonthly] = useState<{ monthly: any[] } | null>(null);

  const loadAll = useCallback(async () => {
    const [summ, st, as, eq, mo] = await Promise.all([
      api<PerformanceSummary>("/performance/summary"),
      api<{ strategies: any[] }>("/performance/strategies"),
      api<{ assets: any[] }>("/performance/assets"),
      api<{ equity_curve: { timestamp: string; equity: number }[] }>("/performance/equity"),
      api<{ monthly: any[] }>("/performance/monthly"),
    ]);
    setSummary(summ);
    setStrategies(st);
    setAssets(as);
    setEquity(eq);
    setMonthly(mo);
  }, []);

  useEffect(() => {
    loadAll().catch(() => setSummary(null));
  }, [loadAll]);

  if (!summary) {
    return (
      <DashboardPage>
        <div className="mb-6">
          <h1 className="text-xl font-bold text-white">Performance</h1>
          <p className="text-xs text-slate-500">The honest numbers behind every strategy.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
        <div className="mt-6 space-y-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </DashboardPage>
    );
  }

  return (
    <DashboardPage>
      <Head>
        <title>Performance — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">Performance Analytics</h1>
        <p className="text-xs text-slate-500">
          Derived from simulated backtests and paper signals. Not a predictor of future returns.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Net P&L" value={formatSigned(summary.net_pnl)} tone={summary.net_pnl >= 0 ? "green" : "red"} />
        <StatCard label="Return" value={`${formatNumber(summary.return_percent, 2)}%`} tone={summary.return_percent >= 0 ? "green" : "red"} />
        <StatCard label="Win Rate" value={`${formatNumber(summary.win_rate, 1)}%`} tone="info" />
        <StatCard label="Profit Factor" value={formatNumber(summary.profit_factor)} tone="info" />
        <StatCard label="Max Drawdown" value={`-${formatNumber(summary.max_drawdown, 2)}%`} tone="red" />
        <StatCard label="Total Trades" value={String(summary.total_trades)} />
        <StatCard label="Expectancy" value={formatSigned(summary.expectancy)} />
        <StatCard label="Avg R" value={formatNumber(summary.average_r)} />
        <StatCard label="Strategies" value={String(summary.total_strategies)} />
        <StatCard label="Signals" value={String(summary.total_signals)} />
      </div>

      <div className="mt-6 space-y-6">
        <Card title="Equity Curve" subtitle="Cumulative simulated P&L">
          {equity && equity.equity_curve.length > 1 ? (
            <EquityCurve data={equity.equity_curve} height={300} />
          ) : (
            <EmptyState title="No closed trades" message="Run backtests or close signals to build an equity curve." />
          )}
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Strategy Comparison" subtitle="Return vs win rate per strategy">
            {strategies && strategies.strategies.length ? (
              <StrategyComparison data={strategies.strategies} height={300} />
            ) : (
              <EmptyState title="No strategy data" message="Backtest strategies to compare them." />
            )}
          </Card>
          <Card title="Asset Performance" subtitle="P&L and win rate by asset">
            {assets && assets.assets.length ? (
              <AssetPerformance data={assets.assets} height={300} />
            ) : (
              <EmptyState title="No asset data" message="Closed trades will appear here." />
            )}
          </Card>
        </div>

        <Card title="Monthly Performance" subtitle="Simulated P&L by month">
          {monthly && monthly.monthly.length ? (
            <MonthlyPerformance data={monthly.monthly} height={240} />
          ) : (
            <EmptyState title="No monthly data" message="Close some signals to see monthly breakdowns." />
          )}
        </Card>
      </div>
    </DashboardPage>
  );
}