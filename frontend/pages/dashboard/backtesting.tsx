import React, { useCallback, useEffect, useMemo, useState } from "react";
import Head from "next/head";
import { BarChart3, RefreshCw, Trash2 } from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, EmptyState, Skeleton, StatCard, useToast } from "components/ui";
import { EquityCurve, MonthlyPerformance, WinLossDonut } from "components/charts";
import { api, formatNumber, formatSigned } from "lib/api";
import type { Backtest, OptimizationMetric, OptimizationResult, Strategy } from "lib/types";

interface Form {
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  initial_capital: string;
  risk_percent: string;
  fee_percent: string;
  slippage_percent: string;
}

const DEFAULT_FORM: Form = {
  strategy_id: "",
  strategy_name: "",
  symbol: "BTC/USD",
  timeframe: "4H",
  initial_capital: "10000",
  risk_percent: "1",
  fee_percent: "0.05",
  slippage_percent: "0.02",
};

const RESULT_STORAGE_KEY = "tp_last_backtest_result";

function loadStoredResult(): Backtest | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Backtest;
    return parsed && parsed.metrics ? parsed : null;
  } catch {
    return null;
  }
}

function storeResult(result: Backtest | null) {
  if (typeof window === "undefined") return;
  try {
    if (result) window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(result));
    else window.sessionStorage.removeItem(RESULT_STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode) — ignore */
  }
}

const ASSETS = ["BTC/USD", "ETH/USD", "SOL/USD", "XAUUSD", "XAGUSD", "GOLD", "EUR/USD", "US30", "SPX500"];
const TIMEFRAMES = ["15M", "1H", "4H", "1D", "1W"];

const OPT_METRICS: { value: OptimizationMetric; label: string }[] = [
  { value: "return_percent", label: "Return %" },
  { value: "sharpe_ratio", label: "Sharpe Ratio" },
  { value: "sortino_ratio", label: "Sortino Ratio" },
  { value: "calmar_ratio", label: "Calmar Ratio" },
  { value: "cagr", label: "CAGR" },
  { value: "profit_factor", label: "Profit Factor" },
  { value: "win_rate", label: "Win Rate" },
  { value: "max_drawdown", label: "Max Drawdown (minimize)" },
  { value: "expectancy", label: "Expectancy" },
  { value: "average_r", label: "Avg R" },
  { value: "net_pnl", label: "Net P&L" },
];

interface OptParamRow {
  path: string;
  min: string;
  max: string;
  step: string;
}

interface OptForm {
  mode: "grid" | "walk_forward";
  metric: OptimizationMetric;
  folds: string;
  test_ratio: string;
  max_evals: string;
  params: OptParamRow[];
}

const DEFAULT_OPT_FORM: OptForm = {
  mode: "grid",
  metric: "return_percent",
  folds: "3",
  test_ratio: "0.2",
  max_evals: "400",
  params: [{ path: "entry.conditions.0.params.period", min: "10", max: "30", step: "5" }],
};

const OPT_PARAM_HINT =
  "Paths like entry.conditions.0.params.period (or stop_loss_value / take_profit_value / rsi threshold .level).";

function fmtMetric(metrics: Record<string, number> | null | undefined, key: string, postfix = ""): string {
  const v = metrics?.[key];
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return `${formatNumber(v)}${postfix}`;
}

export default function Backtesting() {
  const { toast } = useToast();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [assets, setAssets] = useState<string[]>(ASSETS);
  const [timeframes, setTimeframes] = useState<string[]>(TIMEFRAMES);
  const [form, setForm] = useState<Form>(DEFAULT_FORM);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Backtest | null>(() => loadStoredResult());
  const [history, setHistory] = useState<Backtest[] | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [optForm, setOptForm] = useState<OptForm>(DEFAULT_OPT_FORM);
  const [optimizing, setOptimizing] = useState(false);
  const [optResult, setOptResult] = useState<OptimizationResult | null>(null);

  const loadMeta = useCallback(async () => {
    try {
      const [s, a, t] = await Promise.all([
        api<Strategy[]>("/strategies"),
        api<{ assets: { symbol: string }[] }>("/market/assets"),
        api<{ timeframes: string[] }>("/market/timeframes"),
      ]);
      setStrategies(s);
      setAssets(a.assets.map((x) => x.symbol));
      setTimeframes(t.timeframes);
    } catch {
      /* fall back to defaults */
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const list = await api<Backtest[]>("/backtests");
      setHistory(list);
    } catch {
      toast("Failed to load backtest history", "error");
    } finally {
      setLoadingHistory(false);
    }
  }, [toast]);

  useEffect(() => {
    loadMeta();
    loadHistory();
  }, [loadMeta, loadHistory]);

  const strategy = useMemo(
    () => strategies.find((s) => String(s.id) === form.strategy_id),
    [strategies, form.strategy_id]
  );

  const set = (key: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const value = e.target.value;
    setForm((f) => ({ ...f, [key]: value }));
    if (key === "strategy_id" && value) {
      const s = strategies.find((st) => String(st.id) === value);
      if (s) setForm((f) => ({ ...f, symbol: s.asset || f.symbol, timeframe: s.timeframe || f.timeframe }));
    }
  };

  const setOpt = <K extends keyof OptForm>(key: K, value: OptForm[K]) =>
    setOptForm((f) => ({ ...f, [key]: value }));

  const setOptParam = (i: number, key: keyof OptParamRow, value: string) =>
    setOptForm((f) => ({
      ...f,
      params: f.params.map((p, idx) => (idx === i ? { ...p, [key]: value } : p)),
    }));

  const runOptimize = async () => {
    setOptimizing(true);
    try {
      const parameters = optForm.params
        .filter((p) => p.path.trim())
        .map((p) => ({
          path: p.path.trim(),
          min: parseFloat(p.min) || 1,
          max: parseFloat(p.max) || 100,
          step: parseFloat(p.step) || 1,
        }));
      if (parameters.length === 0) {
        toast("Add at least one parameter path", "error");
        setOptimizing(false);
        return;
      }
      const payload: Record<string, unknown> = {
        symbol: form.symbol,
        timeframe: form.timeframe,
        initial_capital: parseFloat(form.initial_capital) || 10000,
        risk_percent: parseFloat(form.risk_percent) || 1,
        fee_percent: parseFloat(form.fee_percent) || 0,
        slippage_percent: parseFloat(form.slippage_percent) || 0,
        optimization: {
          parameters,
          metric: optForm.metric,
          mode: optForm.mode,
          folds: parseInt(optForm.folds, 10) || 5,
          test_ratio: parseFloat(optForm.test_ratio) || 0,
          max_evals: parseInt(optForm.max_evals, 10) || 400,
          max_bars: 2000,
        },
      };
      if (strategy) {
        payload.strategy_id = strategy.id;
      } else if (form.strategy_name.trim()) {
        payload.strategy_name = form.strategy_name.trim();
      } else {
        toast("Pick a strategy or enter a strategy name", "error");
        setOptimizing(false);
        return;
      }
      const res = await api<OptimizationResult>("/backtests/optimize", { method: "POST", body: payload });
      setOptResult(res);
      toast(`Optimization complete — ${res.grid_total_evals} combination(s) tested`, "success");
      loadHistory();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Optimization failed", "error");
    } finally {
      setOptimizing(false);
    }
  };

  const runBacktest = async () => {
    setRunning(true);
    try {
      const payload: Record<string, unknown> = {
        symbol: form.symbol,
        timeframe: form.timeframe,
        initial_capital: parseFloat(form.initial_capital) || 10000,
        risk_percent: parseFloat(form.risk_percent) || 1,
        fee_percent: parseFloat(form.fee_percent) || 0,
        slippage_percent: parseFloat(form.slippage_percent) || 0,
      };
      if (strategy) {
        payload.strategy_id = strategy.id;
      } else if (form.strategy_name.trim()) {
        payload.strategy_name = form.strategy_name.trim();
      } else {
        toast("Pick a strategy or enter a strategy name", "error");
        setRunning(false);
        return;
      }
      const res = await api<Backtest>("/backtests/run", { method: "POST", body: payload });
      setResult(res);
      storeResult(res);
      toast("Backtest complete", "success");
      loadHistory();
    } catch (err) {
      // Keep the previous result on the screen when a new run fails, so the
      // panel never flashes and disappears on error.
      toast(err instanceof Error ? err.message : "Backtest failed", "error");
    } finally {
      setRunning(false);
    }
  };

  const deleteBacktest = async (id: number) => {
    try {
      await api(`/backtests/${id}`, { method: "DELETE" });
      if (result?.id === id) {
        setResult(null);
        storeResult(null);
      }
      loadHistory();
      toast("Backtest deleted", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Delete failed", "error");
    }
  };

  const m = result?.metrics;

  return (
    <DashboardPage>
      <Head>
        <title>Backtesting — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">Backtesting Engine</h1>
        <p className="text-xs text-slate-500">
          Deterministic engine. Simulated OHLCV data, position sizing on set risk. Results are hypothetical.
        </p>
      </div>

      <Card title="Configure backtest" className="mb-6">
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <div>
            <label className="label">Strategy</label>
            <select className="input" value={form.strategy_id} onChange={set("strategy_id")}>
              <option value="">— Custom / none —</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.asset} {s.timeframe}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">...or strategy name</label>
            <input
              className="input"
              placeholder="Trend Momentum v1"
              value={form.strategy_name}
              onChange={set("strategy_name")}
            />
          </div>
          <div>
            <label className="label">Asset</label>
            <select className="input" value={form.symbol} onChange={set("symbol")}>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Timeframe</label>
            <select className="input" value={form.timeframe} onChange={set("timeframe")}>
              {timeframes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Risk / trade</label>
            <input className="input" type="number" inputMode="decimal" value={form.risk_percent} onChange={set("risk_percent")} />
          </div>
          <div>
            <label className="label">Capital</label>
            <input className="input" type="number" value={form.initial_capital} onChange={set("initial_capital")} />
          </div>
          <div>
            <label className="label">Fees %</label>
            <input className="input" type="number" inputMode="decimal" value={form.fee_percent} onChange={set("fee_percent")} />
          </div>
          <div>
            <label className="label">Slippage %</label>
            <input className="input" type="number" inputMode="decimal" value={form.slippage_percent} onChange={set("slippage_percent")} />
          </div>
          <Button className="sm:col-span-2 lg:mt-6" onClick={runBacktest} loading={running}>
            <BarChart3 className="h-4 w-4" /> Run Backtest
          </Button>
        </div>
        {strategy && (
          <p className="mt-3 text-[11px] text-slate-500">
            Using strategy <span className="font-semibold text-slate-300">{strategy.name}</span> rules
            ({strategy.entry_rules.length} entry · {strategy.exit_rules.length} exit).
          </p>
        )}
      </Card>

      {running && (
        <Card className="mb-6">
          <div className="flex items-center gap-3 text-sm text-slate-400">
            <RefreshCw className="h-4 w-4 animate-spin text-emerald-400" />
            Running backtest over {form.symbol} {form.timeframe} data…
          </div>
        </Card>
      )}

      {/* Optimizer */}
      <Card
        title="Optimize strategy parameters"
        subtitle="Grid search across parameter values, or walk-forward validate the best set out-of-sample."
        className="mb-6"
      >
        <div className="grid gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <div>
            <label className="label">Mode</label>
            <select className="input" value={optForm.mode} onChange={(e) => setOpt("mode", e.target.value as OptForm["mode"])}>
              <option value="grid">Grid search</option>
              <option value="walk_forward">Walk-forward</option>
            </select>
          </div>
          <div>
            <label className="label">Target metric</label>
            <select className="input" value={optForm.metric} onChange={(e) => setOpt("metric", e.target.value as OptimizationMetric)}>
              {OPT_METRICS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          {optForm.mode === "walk_forward" && (
            <div>
              <label className="label">Folds</label>
              <input className="input" type="number" value={optForm.folds} onChange={(e) => setOpt("folds", e.target.value)} />
            </div>
          )}
          <div>
            <label className="label">Test ratio</label>
            <input className="input" type="number" inputMode="decimal" min="0" max="0.4" step="0.1" value={optForm.test_ratio} onChange={(e) => setOpt("test_ratio", e.target.value)} />
          </div>
          <div>
            <label className="label">Max evals</label>
            <input className="input" type="number" value={optForm.max_evals} onChange={(e) => setOpt("max_evals", e.target.value)} />
          </div>
        </div>

        <div className="label mt-5 mb-1.5">Parameters (dotted paths into the strategy)</div>
        <div className="space-y-2">
          {optForm.params.map((p, i) => (
            <div key={i} className="grid grid-cols-5 gap-2">
              <input
                className="input col-span-2 font-mono text-xs"
                placeholder="entry.conditions.0.params.period"
                value={p.path}
                onChange={(e) => setOptParam(i, "path", e.target.value)}
              />
              <input className="input" type="number" placeholder="min" value={p.min} onChange={(e) => setOptParam(i, "min", e.target.value)} />
              <input className="input" type="number" placeholder="max" value={p.max} onChange={(e) => setOptParam(i, "max", e.target.value)} />
              <div className="flex items-center gap-2">
                <input className="input" type="number" placeholder="step" value={p.step} onChange={(e) => setOptParam(i, "step", e.target.value)} />
                <button
                  type="button"
                  onClick={() => setOptForm((f) => ({ ...f, params: f.params.filter((_, idx) => idx !== i) }))}
                  className="px-2 text-slate-600 hover:text-red-300"
                  title="Remove parameter"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setOptForm((f) => ({ ...f, params: [...f.params, { path: "", min: "1", max: "100", step: "1" }] }))}
          className="mt-3 text-xs font-medium text-emerald-400 hover:underline"
        >
          + Add parameter
        </button>
        <p className="mt-2 text-[11px] text-slate-600">{OPT_PARAM_HINT}</p>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-[11px] text-slate-500">
            Runs on {form.symbol || "BTC/USD"} {form.timeframe} · {optForm.mode === "walk_forward" ? `${optForm.folds || "5"} folds · out-of-sample` : "train/test split"}
          </span>
          <Button onClick={runOptimize} loading={optimizing}>
            <BarChart3 className="h-4 w-4" /> Run Optimization
          </Button>
        </div>
      </Card>

      {/* Optimization results */}
      {optResult && (
        <Card title="Optimization results" className="mb-6" subtitle={optResult.mode === "walk_forward" ? "Walk-forward · combined test-set performance" : `Grid search · ${optResult.grid_total_evals} combination(s) tested`}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label="Best Return" value={fmtMetric(optResult.best_metrics, "return_percent", "%")} tone="green" />
            <StatCard label="Best Sharpe" value={fmtMetric(optResult.best_metrics, "sharpe_ratio")} tone="info" />
            <StatCard label="Best PF" value={fmtMetric(optResult.best_metrics, "profit_factor")} tone="info" />
            <StatCard label="Out-of-sample Return" value={fmtMetric(optResult.out_of_sample_metrics, "return_percent", "%")} tone={optResult.mode === "walk_forward" ? "green" : "info"} />
            <StatCard label="Out-of-sample Sharpe" value={fmtMetric(optResult.out_of_sample_metrics, "sharpe_ratio")} tone="info" />
          </div>

          {optResult.best_params && (
            <div className="mt-5">
              <div className="label mb-1.5">Best parameter set</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(optResult.best_params).map(([k, v]) => (
                  <span key={k} className="chip border border-line bg-bg-soft font-mono text-slate-300">
                    {k} = {formatNumber(v)}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5">
            <div className="label mb-1.5">Top combinations</div>
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-line">
                    <th className="th">Params</th>
                    <th className="th">Return %</th>
                    <th className="th">Sharpe</th>
                    <th className="th">PF</th>
                    <th className="th">Trades</th>
                    <th className="th">Max DD %</th>
                  </tr>
                </thead>
                <tbody>
                  {(optResult.top_results || []).map((r, i) => (
                    <tr key={i} className="border-b border-line/60 last:border-0">
                      <td className="td font-mono text-[11px] text-slate-400">
                        {Object.entries(r.params)
                          .map(([k, v]) => `${k}=${formatNumber(v)}`)
                          .join(", ")}
                      </td>
                      <td className={`td number font-semibold ${(r.metrics.return_percent ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {formatNumber(r.metrics.return_percent)}%
                      </td>
                      <td className="td number">{formatNumber(r.metrics.sharpe_ratio)}</td>
                      <td className="td number">{formatNumber(r.metrics.profit_factor)}</td>
                      <td className="td number">{r.metrics.total_trades ?? "—"}</td>
                      <td className="td number text-red-400">-{formatNumber(r.metrics.max_drawdown)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {optResult.mode === "walk_forward" && optResult.walk_forward && (
            <div className="mt-5">
              <div className="label mb-1.5">Fold summary</div>
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="th">Fold</th>
                      <th className="th">Test period</th>
                      <th className="th">Trades</th>
                      <th className="th">Test return %</th>
                      <th className="th">Test Sharpe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {optResult.walk_forward.folds.map((f) => (
                      <tr key={f.fold} className="border-b border-line/60 last:border-0">
                        <td className="td text-xs font-semibold text-slate-300">{f.fold + 1}</td>
                        <td className="td text-xs text-slate-400">{f.test_start.slice(0, 10)} → {f.test_end.slice(0, 10)}</td>
                        <td className="td number">{f.test_trades}</td>
                        <td className={`td number ${(f.test_metrics.return_percent ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {formatNumber(f.test_metrics.return_percent)}%
                        </td>
                        <td className="td number">{formatNumber(f.test_metrics.sharpe_ratio)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                Combined out-of-sample: return {formatNumber(optResult.walk_forward.combined_metrics.return_percent)}% · Sharpe {formatNumber(optResult.walk_forward.combined_metrics.sharpe_ratio)} · {optResult.walk_forward.combined_metrics.total_trades ?? "—"} trades.
              </p>
            </div>
          )}

          {optResult.backtest_id != null && (
            <p className="mt-4 text-[11px] text-slate-500">
              Persisted to history as backtest #{optResult.backtest_id}.
            </p>
          )}
        </Card>
      )}

      {/* Results */}
      {result && m && (
        <div className="mb-8 rounded-2xl border border-accent/30 bg-bg-card shadow-glow">
          <div className="flex flex-col justify-between gap-2 border-b border-line/60 px-6 py-4 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-base font-bold text-white">
                {result.strategy_name || "Backtest"} <span className="text-slate-500">· {result.symbol} {result.timeframe}</span>
              </h2>
              {result.is_demo && <span className="chip mt-1 bg-warn/15 text-amber-300">SIMULATED DATA</span>}
            </div>
            <button
              onClick={() => {
                setResult(null);
                storeResult(null);
              }}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              Dismiss results
            </button>
          </div>

          <div className="grid gap-4 p-6 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label="Net P&L" value={formatSigned(m.net_pnl)} tone={m.net_pnl >= 0 ? "green" : "red"} />
            <StatCard label="Return" value={`${formatNumber(m.return_percent, 2)}%`} tone={m.return_percent >= 0 ? "green" : "red"} />
            <StatCard label="Win Rate" value={`${formatNumber(m.win_rate, 1)}%`} tone="info" />
            <StatCard label="Profit Factor" value={formatNumber(m.profit_factor)} tone="info" />
            <StatCard label="Max Drawdown" value={`-${formatNumber(m.max_drawdown, 2)}%`} tone="red" />
            <StatCard label="Total Trades" value={String(m.total_trades)} />
            <StatCard label="Expectancy" value={formatSigned(m.expectancy)} />
            <StatCard label="Avg R" value={formatNumber(m.average_r)} />
            <StatCard label="Largest Win" value={formatSigned(m.largest_win)} tone="green" />
            <StatCard label="Largest Loss" value={formatSigned(m.largest_loss)} tone="red" />
            <StatCard label="Sharpe Ratio" value={m.sharpe_ratio != null ? formatNumber(m.sharpe_ratio) : "—"} tone="info" />
            <StatCard label="Sortino Ratio" value={m.sortino_ratio != null ? formatNumber(m.sortino_ratio) : "—"} tone="info" />
            <StatCard label="CAGR" value={m.cagr != null ? `${formatNumber(m.cagr)}%` : "—"} tone={m.cagr != null && m.cagr >= 0 ? "green" : "red"} />
            <StatCard label="Calmar" value={m.calmar_ratio != null ? formatNumber(m.calmar_ratio) : "—"} tone="info" />
          </div>

          <div className="grid gap-6 p-6 pt-0 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <EquityCurve data={result.equity_curve || []} height={300} />
            </div>
            <div className="grid gap-6">
              <WinLossDonut wins={m.winning_trades || 0} losses={m.losing_trades || 0} />
              <MonthlyPerformance data={result.monthly_performance || []} height={140} />
            </div>
          </div>

          {/* Trade table */}
          <div className="mx-6 mb-6 overflow-hidden rounded-xl border border-line">
            <div className="border-b border-line bg-bg-soft px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Trade history ({(result.trade_history || []).length})
            </div>
            <div className="max-h-72 overflow-y-auto">
              <table className="w-full">
                <thead className="sticky top-0 bg-bg-card">
                  <tr>
                    <th className="th">Entry</th>
                    <th className="th">Exit</th>
                    <th className="th">Direction</th>
                    <th className="th">Entry px</th>
                    <th className="th">Exit px</th>
                    <th className="th">Size</th>
                    <th className="th">P&L</th>
                    <th className="th">R</th>
                    <th className="th">Exit reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.trade_history || []).map((t, i) => (
                    <tr key={i} className="border-b border-line/60 last:border-0">
                      <td className="td whitespace-nowrap text-xs text-slate-400">{t.entry_timestamp}</td>
                      <td className="td whitespace-nowrap text-xs text-slate-400">{t.exit_timestamp}</td>
                      <td className="td">
                        <span className={`font-bold ${t.direction === "LONG" ? "text-emerald-400" : "text-red-400"}`}>{t.direction}</span>
                      </td>
                      <td className="td number">{formatNumber(t.entry_price, 2)}</td>
                      <td className="td number">{formatNumber(t.exit_price, 2)}</td>
                      <td className="td number">{formatNumber(t.size)}</td>
                      <td className={`td number font-bold ${(t.pnl || 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {formatSigned(t.pnl)}
                      </td>
                      <td className={`td number font-bold ${(t.r_multiple || 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {formatNumber(t.r_multiple, 2)}R
                      </td>
                      <td className="td"><span className="chip">{t.exit_reason}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* History */}
      <Card title="Backtest History">
        {loadingHistory ? (
          <Skeleton className="h-40 w-full" />
        ) : !history || history.length === 0 ? (
          <EmptyState title="Run your first backtest" message="Pick a strategy, configure the parameters above and hit run." />
        ) : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-line">
                  <th className="th">Strategy</th>
                  <th className="th">Symbol</th>
                  <th className="th">TF</th>
                  <th className="th">Trades</th>
                  <th className="th">Win rate</th>
                  <th className="th">Return</th>
                  <th className="th">PF</th>
                  <th className="th">Max DD</th>
                  <th className="th">Created</th>
                  <th className="th"></th>
                </tr>
              </thead>
              <tbody>
                {history.map((b) => (
                  <tr key={b.id} className="tr-hover cursor-pointer border-b border-line/60 last:border-0" onClick={() => setResult(b)}>
                    <td className="td max-w-[200px] truncate text-xs font-semibold text-slate-200">
                      {b.strategy_name || "—"}
                    </td>
                    <td className="td font-semibold">{b.symbol}</td>
                    <td className="td text-xs">{b.timeframe}</td>
                    <td className="td number">{b.metrics?.total_trades ?? "—"}</td>
                    <td className="td number">{b.metrics?.win_rate != null ? `${formatNumber(b.metrics.win_rate, 1)}%` : "—"}</td>
                    <td className={`td number font-bold ${(b.metrics?.return_percent ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {b.metrics?.return_percent != null ? `${formatNumber(b.metrics.return_percent, 2)}%` : "—"}
                    </td>
                    <td className="td number">{formatNumber(b.metrics?.profit_factor)}</td>
                    <td className="td number text-red-400">
                      {b.metrics?.max_drawdown != null ? `-${formatNumber(b.metrics.max_drawdown, 2)}%` : "—"}
                    </td>
                    <td className="td text-xs text-slate-500">{b.created_at || "—"}</td>
                    <td className="td">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteBacktest(b.id);
                        }}
                        className="rounded-lg p-1.5 text-slate-600 hover:bg-danger-soft hover:text-red-300"
                        title="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </DashboardPage>
  );
}