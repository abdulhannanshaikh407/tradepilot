import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import Head from "next/head";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Radio,
  TrendingUp,
  Trash2,
} from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, ConfidenceBar, DirectionBadge, EmptyState, RuleText, Skeleton, SourceBadge, useToast } from "components/ui";
import { api } from "lib/api";
import type { Backtest, Signal, Strategy } from "lib/types";

export default function StrategyDetail() {
  const router = useRouter();
  const id = Number(router.query.id);
  const { toast } = useToast();
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [backtests, setBacktests] = useState<Backtest[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    const [s, b, sig] = await Promise.all([
      api<Strategy>(`/strategies/${id}`),
      api<Backtest[]>(`/backtests?strategy_id=${id}`),
      api<Signal[]>(`/signals?strategy_id=${id}`),
    ]);
    setStrategy(s);
    setBacktests(b);
    setSignals(sig);
  }, [id]);

  useEffect(() => {
    load().catch((err) => toast(err instanceof Error ? err.message : "Failed to load strategy", "error"));
  }, [load, toast]);

  const runBacktest = async () => {
    if (!strategy) return;
    setRunning(true);
    try {
      await api("/backtests/run", {
        method: "POST",
        body: {
          strategy_id: strategy.id,
          symbol: strategy.asset,
          timeframe: strategy.timeframe,
          initial_capital: 10000,
          risk_percent: strategy.risk_per_trade || 1,
        },
      });
      toast("Backtest complete", "success");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Backtest failed", "error");
    } finally {
      setRunning(false);
    }
  };

  const deleteStrategy = async () => {
    if (!strategy) return;
    try {
      await api(`/strategies/${strategy.id}`, { method: "DELETE" });
      toast("Strategy deleted", "success");
      router.push("/dashboard/strategies");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Delete failed", "error");
    }
  };

  if (!strategy) {
    return (
      <DashboardPage>
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </DashboardPage>
    );
  }

  const latest = backtests[0];

  return (
    <DashboardPage>
      <Head>
        <title>{strategy.name} — TradePilot AI</title>
      </Head>

      <Link href="/dashboard/strategies" className="mb-4 inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300">
        <ArrowLeft className="h-3.5 w-3.5" /> All strategies
      </Link>

      <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-white">{strategy.name}</h1>
            {strategy.is_demo && <span className="chip bg-warn/15 text-amber-300">DEMO STRATEGY</span>}
            <SourceBadge source={strategy.source} />
            {!strategy.is_active && <span className="chip bg-danger-soft text-red-300">INACTIVE</span>}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="font-semibold text-slate-200">{strategy.asset}</span>
            <span className="text-slate-600">•</span>
            <span>{strategy.timeframe}</span>
            <span className="text-slate-600">•</span>
            <DirectionBadge direction={strategy.direction} />
            <span className="text-slate-600">•</span>
            <ConfidenceBar value={strategy.confidence} />
          </div>
          {strategy.description && (
            <p className="mt-2 max-w-2xl text-xs text-slate-500">{strategy.description}</p>
          )}
          {strategy.source_url && (
            <a
              href={strategy.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 hover:underline"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              View source video
            </a>
          )}
        </div>
        <div className="flex gap-2">
          <Button onClick={runBacktest} loading={running}>
            <BarChart3 className="h-4 w-4" /> Run Backtest
          </Button>
          <Button variant="danger" onClick={deleteStrategy}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Rules" subtitle="Structured conditions extracted from the source">
          <div className="space-y-5">
            <div>
              <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">Indicators</h3>
              <div className="flex flex-wrap gap-2">
                {(strategy.indicators || []).map((ind, i) => (
                  <span key={i} className="chip border border-line bg-bg-soft text-slate-300">
                    {ind.name}
                    {ind.period ? ` (${ind.period})` : ""}
                  </span>
                ))}
                {(strategy.indicators || []).length === 0 && (
                  <span className="text-xs text-slate-600">None specified</span>
                )}
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-emerald-400">Entry</h3>
              <ul className="space-y-1.5">
                {(strategy.entry_rules || []).map((rule, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs text-slate-300">
                    <ArrowRight className="h-3 w-3 shrink-0 text-emerald-400" />
                    <RuleText rule={rule} />
                  </li>
                ))}
              </ul>
            </div>

            {(strategy.confirmation_rules || []).length > 0 && (
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-sky-400">Confirmation</h3>
                <ul className="space-y-1.5">
                  {(strategy.confirmation_rules || []).map((rule, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs text-slate-300">
                      <CheckCircle2 className="h-3 w-3 shrink-0 text-sky-400" />
                      <RuleText rule={rule} />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-red-400">Exit</h3>
              <ul className="space-y-1.5">
                {(strategy.exit_rules || []).map((rule, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs text-slate-300">
                    <ArrowRight className="h-3 w-3 shrink-0 rotate-180 text-red-400" />
                    <RuleText rule={rule} />
                  </li>
                ))}
              </ul>
            </div>

            <div className="grid grid-cols-4 gap-3 rounded-lg border border-line bg-bg-soft p-3 text-center">
              <div>
                <div className="number text-sm font-bold text-red-400">
                  {strategy.stop_loss_value != null ? `${strategy.stop_loss_value}%` : "—"}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Stop loss</div>
              </div>
              <div>
                <div className="number text-sm font-bold text-emerald-400">
                  {strategy.take_profit_value != null ? `${strategy.take_profit_value}%` : "—"}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Target</div>
              </div>
              <div>
                <div className="number text-sm font-bold text-slate-200">
                  {strategy.risk_reward != null ? `1:${strategy.risk_reward}` : "—"}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500">R : R</div>
              </div>
              <div>
                <div className="number text-sm font-bold text-slate-200">
                  {strategy.risk_per_trade != null ? `${strategy.risk_per_trade}%` : "—"}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Risk / trade</div>
              </div>
            </div>

            {(strategy.assumptions || []).length > 0 && (
              <div>
                <h3 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">Assumptions</h3>
                <ul className="space-y-0.5 text-[11px] text-slate-500">
                  {strategy.assumptions.map((a, i) => <li key={i}>• {a}</li>)}
                </ul>
              </div>
            )}

            {(strategy.missing_information || []).length > 0 && (
              <div className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2.5">
                <div className="text-[10px] font-bold uppercase tracking-wider text-amber-300">Not specified</div>
                <ul className="mt-1 space-y-0.5 text-[11px] text-amber-200/80">
                  {(strategy.missing_information || []).map((m, i) => <li key={i}>• {m}</li>)}
                </ul>
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-6">
          <Card
            title="Latest Backtest"
            actions={
              <Link href="/dashboard/backtesting" className="text-xs text-emerald-400 hover:underline">Backtesting →</Link>
            }
          >
            {backtests.length === 0 ? (
              <EmptyState title="No backtests yet" message="Run a backtest to see metrics here." />
            ) : (
              <div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="number text-lg font-bold text-emerald-400">
                      {latest?.metrics?.return_percent != null ? `${latest.metrics.return_percent.toFixed(2)}%` : "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Return</div>
                  </div>
                  <div>
                    <div className="number text-lg font-bold text-sky-400">
                      {latest?.metrics?.win_rate != null ? `${latest.metrics.win_rate.toFixed(1)}%` : "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Win rate</div>
                  </div>
                  <div>
                    <div className="number text-lg font-bold text-slate-200">
                      {latest?.metrics?.total_trades ?? "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Trades</div>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3 rounded-lg border border-line bg-bg-soft p-3">
                  <div className="text-center">
                    <div className="number text-xs font-bold text-slate-300">{latest?.metrics?.profit_factor ?? "—"}</div>
                    <div className="text-[10px] text-slate-500">Profit factor</div>
                  </div>
                  <div className="text-center">
                    <div className="number text-xs font-bold text-slate-300">{latest?.metrics?.expectancy ?? "—"}</div>
                    <div className="text-[10px] text-slate-500">Expectancy</div>
                  </div>
                  <div className="text-center">
                    <div className="number text-xs font-bold text-slate-300">
                      {latest?.metrics?.max_drawdown != null ? `${latest.metrics.max_drawdown.toFixed(2)}%` : "—"}
                    </div>
                    <div className="text-[10px] text-slate-500">Max DD</div>
                  </div>
                </div>
              </div>
            )}
          </Card>

          <Card
            title="Signals"
            actions={
              <Link href="/dashboard/signals" className="text-xs text-emerald-400 hover:underline">Signals →</Link>
            }
          >
            {signals.length === 0 ? (
              <EmptyState title="No signals" message="Generate a paper signal to preview the strategy live." />
            ) : (
              <div className="space-y-2">
                {signals.slice(0, 6).map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-lg border border-line bg-bg-soft px-3 py-2">
                    <div className="flex items-center gap-2 text-xs">
                      <Radio className="h-3.5 w-3.5 text-emerald-400" />
                      <span className="font-semibold text-slate-200">{s.symbol}</span>
                      <DirectionBadge direction={s.direction} />
                    </div>
                    <div className="flex items-center gap-3 text-[11px]">
                      <span className="text-slate-500">{s.status}</span>
                      <TrendingUp className="h-3 w-3 text-slate-600" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </DashboardPage>
  );
}