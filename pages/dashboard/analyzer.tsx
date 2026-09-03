import React, { useCallback, useState } from "react";
import { useRouter } from "next/router";
import Head from "next/head";
import {
  ArrowRight,
  BarChart3,
  Check,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Signal,
  Sparkles,
  Video,
  Wand2,
} from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, ConfidenceBar, DirectionBadge, RuleText, SourceBadge, Spinner, useToast, EmptyState } from "components/ui";
import { api, ApiError } from "lib/api";
import type { Strategy, YouTubeAnalysis } from "lib/types";

const STEPS = [
  "Fetching transcript…",
  "Reading trading methodology…",
  "Identifying indicators…",
  "Extracting entry conditions…",
  "Extracting risk management…",
  "Building strategy…",
  "Validating rules…",
];

const SAMPLE_URLS = [
  "https://www.youtube.com/watch?v=SJ-pziY3Xj0",
  "https://www.youtube.com/watch?v=U5cC6vqqHB0",
];

export default function Analyzer() {
  const router = useRouter();
  const { toast } = useToast();
  const [url, setUrl] = useState("");
  const [analysis, setAnalysis] = useState<YouTubeAnalysis | null>(null);
  const [stepIndex, setStepIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [runBacktesting, setRunBacktesting] = useState(false);
  const [generatingSignals, setGeneratingSignals] = useState(false);

  const analyze = useCallback(
    async (targetUrl: string) => {
      setUrl(targetUrl);
      setError("");
      setAnalysis(null);
      setLoading(true);
      setStepIndex(0);

      let step = 0;
      const timer = setInterval(() => {
        step += 1;
        if (step < STEPS.length) setStepIndex(step);
        else clearInterval(timer);
      }, 350);

      try {
        const result = await api<YouTubeAnalysis>("/youtube/analyze", {
          method: "POST",
          body: { url: targetUrl },
        });
        clearInterval(timer);
        setStepIndex(STEPS.length - 1);
        setAnalysis(result);
        toast("Strategy extracted and saved", "success");
      } catch (err) {
        clearInterval(timer);
        setError(
          err instanceof ApiError ? err.detail : "Analysis failed. Check the URL and try again."
        );
      } finally {
        setLoading(false);
      }
    },
    [toast]
  );

  const useDemoSample = () => {
    const sample = SAMPLE_URLS[Math.floor(Math.random() * SAMPLE_URLS.length)];
    analyze(sample);
  };

  const runBacktest = async (strategy: Strategy) => {
    setRunBacktesting(true);
    try {
      const backtest = await api("/backtests/run", {
        method: "POST",
        body: {
          strategy_id: strategy.id,
          symbol: strategy.asset,
          timeframe: strategy.timeframe,
          initial_capital: 10000,
          risk_percent: strategy.risk_per_trade || 1,
          fee_percent: 0.05,
          slippage_percent: 0.02,
        },
      });
      toast("Backtest complete — open the Backtesting page to review it", "success");
      router.push("/dashboard/backtesting");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Backtest failed", "error");
    } finally {
      setRunBacktesting(false);
    }
  };

  const createSignals = async (strategy: Strategy) => {
    setGeneratingSignals(true);
    try {
      await api("/signals/generate", { method: "POST", body: { strategy_id: strategy.id } });
      toast("Paper signal generated from the strategy", "success");
      router.push("/dashboard/signals");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Signal generation failed", "error");
    } finally {
      setGeneratingSignals(false);
    }
  };

  return (
    <DashboardPage>
      <Head>
        <title>YouTube Strategy Analyzer — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">YouTube Strategy Analyzer</h1>
        <p className="text-xs text-slate-500">
          Paste a trading video URL — the platform extracts, structures and saves the strategy.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input column */}
        <div>
          <Card title="Analyze a strategy video" subtitle="Works with captioned trading videos. Demo fallback is automatic.">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Video className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  className="input pl-9"
                  placeholder="https://www.youtube.com/watch?v=…"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && url && analyze(url)}
                />
              </div>
              <Button onClick={() => url && analyze(url)} disabled={loading || !url} loading={loading}>
                Analyze
              </Button>
            </div>

            <div className="mt-3 flex items-center justify-between">
              <button
                onClick={useDemoSample}
                disabled={loading}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400 hover:underline disabled:opacity-50"
              >
                <Wand2 className="h-3.5 w-3.5" /> Use a demo video
              </button>
              <span className="text-[11px] text-slate-600">No OpenAI key needed — demo fallback built in</span>
            </div>

            {error && (
              <div className="mt-4 rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-xs text-red-300">
                {error}
              </div>
            )}

            {/* Processing rail */}
            {loading && (
              <div className="mt-6 space-y-2">
                {STEPS.map((step, i) => (
                  <div
                    key={step}
                    className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs transition ${
                      i <= stepIndex ? "bg-accent-soft text-emerald-200" : "text-slate-600"
                    }`}
                  >
                    {i < stepIndex ? (
                      <Check className="h-4 w-4 text-emerald-400" />
                    ) : i === stepIndex ? (
                      <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                    ) : (
                      <span className="h-4 w-4 rounded-full border border-slate-700" />
                    )}
                    {step}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {analysis?.used_demo_fallback && (
            <div className="mt-4 rounded-lg border border-warn/30 bg-warn-soft px-4 py-3 text-xs text-amber-200">
              <strong>Demo mode:</strong> {analysis.message || "A simulated demo transcript was used."}
              Strategies shown as D E M O are illustrative training data, not real transcript results.
            </div>
          )}
        </div>

        {/* Strategy card column */}
        <div>
          {!analysis && !loading && (
            <Card>
              <EmptyState
                title="Your structured strategy appears here"
                message="Run an analysis and the extracted rules, risk parameters and confidence will be shown as a reviewable card."
                icon={<Sparkles className="h-6 w-6" />}
              />
            </Card>
          )}

          {analysis && (
            <div className="card overflow-hidden shadow-glow animate-slide-up">
              <div className="border-b border-line bg-bg-soft/60 px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-bold text-white">{analysis.strategy.name}</h2>
                      {analysis.strategy.is_demo && (
                        <span className="chip bg-warn/15 text-amber-300">DEMO STRATEGY</span>
                      )}
                      <SourceBadge source={analysis.strategy.source} />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <span className="font-semibold text-slate-200">{analysis.strategy.asset}</span>
                      <span className="text-slate-600">•</span>
                      <span>{analysis.strategy.timeframe}</span>
                      <span className="text-slate-600">•</span>
                      <DirectionBadge direction={analysis.strategy.direction} />
                      <span className="text-slate-600">•</span>
                      <ConfidenceBar value={analysis.strategy.confidence} />
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
                      {analysis.video_title && (
                        <>
                          <FileText className="h-3 w-3" />
                          <span className="line-clamp-1">{analysis.video_title}</span>
                        </>
                      )}
                      {analysis.used_demo_fallback && (
                        <span className="chip bg-warn/10 text-amber-300">SIMULATED DATA</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-5 p-5">
                {/* Indicators */}
                <div>
                  <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Indicators
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {(analysis.strategy.indicators || []).map((ind, i) => (
                      <span key={i} className="chip border border-line bg-bg-soft text-slate-300">
                        {ind.name}
                        {ind.period ? ` (${ind.period})` : ""}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Entry */}
                <div>
                  <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-emerald-400">
                    Entry rules
                  </h3>
                  <ul className="space-y-1.5">
                    {(analysis.strategy.entry_rules || []).map((rule, i) => (
                      <li key={i} className="flex items-center gap-2 text-xs text-slate-300">
                        <ArrowRight className="h-3 w-3 shrink-0 text-emerald-400" />
                        <RuleText rule={rule} />
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Confirmation */}
                {analysis.strategy.confirmation_rules?.length ? (
                  <div>
                    <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-sky-400">
                      Confirmation rules
                    </h3>
                    <ul className="space-y-1.5">
                      {(analysis.strategy.confirmation_rules || []).map((rule, i) => (
                        <li key={i} className="flex items-center gap-2 text-xs text-slate-300">
                          <CheckCircle2 className="h-3 w-3 shrink-0 text-sky-400" />
                          <RuleText rule={rule} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {/* Risk */}
                <div className="grid grid-cols-3 gap-3 rounded-lg border border-line bg-bg-soft p-3 text-center">
                  <div>
                    <div className="number text-sm font-bold text-red-400">
                      {analysis.strategy.stop_loss_value != null
                        ? `${analysis.strategy.stop_loss_value}%`
                        : "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Stop loss</div>
                  </div>
                  <div>
                    <div className="number text-sm font-bold text-emerald-400">
                      {analysis.strategy.take_profit_value != null
                        ? `${analysis.strategy.take_profit_value}%`
                        : "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Target</div>
                  </div>
                  <div>
                    <div className="number text-sm font-bold text-slate-200">
                      {analysis.strategy.risk_reward != null ? `1:${analysis.strategy.risk_reward}` : "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Risk : Reward</div>
                  </div>
                </div>

                {/* Exit */}
                <div>
                  <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-red-400">
                    Exit rules
                  </h3>
                  <ul className="space-y-1.5">
                    {(analysis.strategy.exit_rules || []).map((rule, i) => (
                      <li key={i} className="flex items-center gap-2 text-xs text-slate-300">
                        <ArrowRight className="h-3 w-3 shrink-0 rotate-180 text-red-400" />
                        <RuleText rule={rule} />
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Missing info */}
                {analysis.strategy.missing_information?.length ? (
                  <div className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2.5">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-amber-300">
                      Not specified in the video
                    </div>
                    <ul className="mt-1 space-y-0.5 text-[11px] text-amber-200/80">
                      {analysis.strategy.missing_information.map((m, i) => (
                        <li key={i}>• {m}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {/* Actions */}
                <div className="grid gap-2 sm:grid-cols-3">
                  <Button onClick={() => runBacktest(analysis.strategy)} loading={runBacktesting}>
                    <BarChart3 className="h-4 w-4" /> Run Backtest
                  </Button>
                  <Button variant="secondary" onClick={() => createSignals(analysis.strategy)} loading={generatingSignals}>
                    <Signal className="h-4 w-4" /> Paper Signals
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => router.push(`/dashboard/strategies/${analysis.strategy.id}`)}
                  >
                    <Download className="h-4 w-4" /> Save / View
                  </Button>
                </div>

                {analysis.transcript_preview && (
                  <details className="group">
                    <summary className="cursor-pointer text-[11px] text-slate-500 hover:text-slate-300">
                      Transcript preview
                    </summary>
                    <p className="mt-2 line-clamp-4 text-[11px] leading-relaxed text-slate-500">
                      {analysis.transcript_preview}
                    </p>
                  </details>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardPage>
  );
}