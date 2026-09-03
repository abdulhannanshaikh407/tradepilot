import React, { useEffect, useState } from "react";
import Link from "next/link";
import Head from "next/head";
import {
  ArrowRight,
  BarChart3,
  Bell,
  CheckCircle2,
  FlaskConical,
  PlayCircle,
  Radio,
  Search,
  ShieldAlert,
  Signal,
  Sparkles,
  TrendingUp,
  Video,
} from "lucide-react";

import { useAuth } from "lib/auth";

export default function Landing() {
  const { user } = useAuth();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const analyzeHref = mounted && user ? "/dashboard/analyzer" : "/login";

  return (
    <div className="min-h-screen bg-bg text-slate-200">
      <Head>
        <title>TradePilot AI — Turn Trading Videos Into Testable Strategies</title>
        <meta
          name="description"
          content="Extract trading rules with AI, backtest them against historical data, and monitor paper-trading signals from one intelligent workspace."
        />
        <meta property="og:title" content="TradePilot AI" />
        <meta
          property="og:description"
          content="Turn trading videos into testable strategies. AI extraction, backtesting, signal intelligence and TradingView alerts."
        />
        <meta property="og:type" content="website" />
      </Head>

      {/* Nav */}
      <header className="sticky top-0 z-20 border-b border-line bg-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15">
              <BarChart3 className="h-[18px] w-[18px] text-emerald-400" />
            </div>
            <span className="text-sm font-bold text-white">TradePilot AI</span>
          </div>
          <nav className="flex items-center gap-2">
            {mounted && user ? (
              <Link href="/dashboard" className="btn-primary">
                Open Dashboard <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <>
                <Link href="/demo" className="btn-secondary">
                  <FlaskConical className="h-4 w-4" /> Explore Demo
                </Link>
                <Link href="/login" className="btn-primary">
                  Sign In <ArrowRight className="h-4 w-4" />
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.12),transparent_55%)]" />
        <div className="relative mx-auto max-w-6xl px-6 py-20 text-center sm:py-28">
          <div className="mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent-soft px-3 py-1 text-xs font-medium text-emerald-300">
            <Sparkles className="h-3.5 w-3.5" /> AI trading strategy research & testing
          </div>
          <h1 className="mx-auto max-w-3xl text-4xl font-extrabold leading-tight text-white sm:text-6xl">
            Turn Trading Videos Into{" "}
            <span className="bg-gradient-to-r from-emerald-400 to-sky-400 bg-clip-text text-transparent">
              Testable Strategies
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base text-slate-400 sm:text-lg">
            Extract trading rules with AI, backtest them against historical data, and monitor
            paper-trading signals from one intelligent workspace.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href={analyzeHref} className="btn-primary px-6 py-3 text-base">
              <Video className="h-5 w-5" /> Analyze a Strategy
            </Link>
            <Link href="/demo" className="btn-secondary px-6 py-3 text-base">
              <PlayCircle className="h-5 w-5" /> Explore Live Demo
            </Link>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center text-2xl font-bold text-white sm:text-3xl">How it works</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[
            { step: "1", title: "YouTube", desc: "Paste any trading video URL.", icon: Video },
            { step: "2", title: "AI", desc: "We extract the methodology.", icon: Sparkles },
            { step: "3", title: "Strategy", desc: "Structured, reviewable rules.", icon: Search },
            { step: "4", title: "Backtest", desc: "Test it on historical data.", icon: BarChart3 },
            { step: "5", title: "Signals", desc: "Paper signals + TradingView alerts.", icon: Signal },
          ].map((item) => (
            <div key={item.step} className="card p-5 text-center">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft">
                <item.icon className="h-5 w-5 text-emerald-400" />
              </div>
              <div className="mt-3 text-xs font-bold uppercase tracking-widest text-emerald-400">
                Step {item.step}
              </div>
              <div className="mt-1 text-sm font-semibold text-white">{item.title}</div>
              <p className="mt-1 text-xs text-slate-500">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Dashboard preview */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="overflow-hidden rounded-2xl border border-line shadow-card">
          <div className="border-b border-line bg-bg-card px-5 py-3">
            <div className="flex gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
            </div>
          </div>
          <div className="grid gap-4 bg-bg-card p-6 sm:grid-cols-6">
            {["Portfolio Value", "Net P&L", "Win Rate", "Active Signals", "Max Drawdown"].map(
              (label, i) => (
                <div key={label} className="card p-4">
                  <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
                  <div className="number mt-1.5 text-lg font-bold text-white">
                    {i === 1 ? "+1,247" : i === 2 ? "58.9%" : i === 3 ? "12" : i === 4 ? "-4.8%" : "$11,247"}
                  </div>
                </div>
              )
            )}
            <div className="card p-4">
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Signal</div>
              <div className="mt-1.5 text-base font-bold text-emerald-400">BTC/USD LONG</div>
            </div>
            <div className="card col-span-6 flex h-40 items-center justify-center">
              <div className="flex w-full items-end justify-around gap-3 px-8">
                {[42, 55, 48, 66, 58, 74, 70, 86, 79, 95, 88, 100].map((h, i) => (
                  <div
                    key={i}
                    className="w-full rounded-t-md bg-gradient-to-t from-accent/40 to-accent/10"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center text-2xl font-bold text-white sm:text-3xl">
          Everything a strategy researcher needs
        </h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            {
              icon: Sparkles,
              title: "AI Strategy Extraction",
              desc: "Feed a YouTube video — get structured entry, confirmation, exit and risk rules. No invented parameters.",
            },
            {
              icon: BarChart3,
              title: "Real Backtesting",
              desc: "Win rate, profit factor, expectancy, max drawdown and full equity curves — calculated, not estimated.",
            },
            {
              icon: Signal,
              title: "Signal Intelligence",
              desc: "Explainable paper-trading signals showing exactly which rule triggered and why.",
            },
            {
              icon: Radio,
              title: "TradingView Alerts",
              desc: "Point a TradingView webhook at your workspace and let alerts turn into trackable signals.",
            },
            {
              icon: TrendingUp,
              title: "Performance Analytics",
              desc: "Strategy comparison, asset and timeframe breakdowns, monthly P&L in one terminal.",
            },
            {
              icon: Bell,
              title: "Notifications & Monitoring",
              desc: "In-app alerts for analyses, backtests, signals and webhook events.",
            },
          ].map((feature) => (
            <div key={feature.title} className="card p-6">
              <feature.icon className="h-6 w-6 text-emerald-400" />
              <h3 className="mt-3 text-sm font-semibold text-white">{feature.title}</h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Risk disclaimer */}
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="flex items-start gap-3 rounded-xl border border-warn/30 bg-warn-soft p-5">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <p className="text-xs leading-relaxed text-amber-200/90">
            <strong>Risk disclaimer.</strong> This platform provides trading research, analysis and
            simulated results for informational purposes only. It does not provide financial advice
            or guarantee future performance. Backtest results are hypothetical and past performance
            does not guarantee future results. Trading involves substantial risk.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-line bg-bg-card/40 py-16">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-2xl font-bold text-white sm:text-3xl">
            Find your next edge — and prove it works.
          </h2>
          <p className="mt-3 text-sm text-slate-400">
            No credit card. The demo runs fully simulated — no API keys, no TradingView account, no
            market-data subscription.
          </p>
          <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
            <Link href="/demo" className="btn-primary px-6 py-3">
              <CheckCircle2 className="h-5 w-5" /> Try the Demo in 30 seconds
            </Link>
            <Link href="/signup" className="btn-secondary px-6 py-3">
              Create a free account
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-line py-6">
        <p className="text-center text-[11px] text-slate-600">
          © {new Date().getFullYear()} TradePilot AI. Research, backtesting and paper-trading tools.
        </p>
      </footer>
    </div>
  );
}