import React, { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import { Activity, Copy, Radio, RefreshCw, ShieldCheck } from "lucide-react";

import DashboardPage from "components/DashboardPage";
import TVChart, { TV_PRESETS } from "components/TradingViewChart";
import { Button, Card, EmptyState, Skeleton, StatusBadge, useToast } from "components/ui";
import { api, API_URL, formatNumber, timeAgo } from "lib/api";
import type { MarketLive, TradingViewInfo, WebhookEvent } from "lib/types";

export default function TradingView() {
  const { toast } = useToast();
  const [info, setInfo] = useState<TradingViewInfo | null>(null);
  const [events, setEvents] = useState<WebhookEvent[] | null>(null);
  const [testing, setTesting] = useState(false);
  const [symbol, setSymbol] = useState("OANDA:XAUUSD");
  const [live, setLive] = useState<MarketLive | null>(null);
  const [payload, setPayload] = useState<Record<string, unknown>>({
    symbol: "XAUUSD",
    direction: "LONG",
    price: 2410.5,
    strategy: "Gold Trend",
    timeframe: "4H",
    timestamp: new Date().toISOString(),
  });

  const load = useCallback(async () => {
    try {
      const [i, ev] = await Promise.all([api<TradingViewInfo>("/dashboard/tradingview-info"), api<WebhookEvent[]>("/webhook/events")]);
      setInfo(i);
      setEvents(ev);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to load integration", "error");
    }
  }, [toast]);

  const loadLive = useCallback(async () => {
    try {
      setLive(await api<MarketLive>("/market/live"));
    } catch {
      /* board fills in later; not fatal */
    }
  }, []);

  useEffect(() => {
    load();
    loadLive();
    const timer = setInterval(loadLive, 20000);
    return () => clearInterval(timer);
  }, [load, loadLive]);

  const sendTest = async () => {
    setTesting(true);
    try {
      await api<{ id: number }>("/webhook/tradingview/test", { method: "POST", body: payload });
      toast("Test alert sent — a signal was created", "success");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Test alert failed", "error");
    } finally {
      setTesting(false);
    }
  };

  const copy = (text: string, label: string) => {
    navigator.clipboard?.writeText(text).then(
      () => toast(`${label} copied to clipboard`, "success"),
      () => toast("Copy failed — select the text manually", "error")
    );
  };

  const webhookUrl = info
    ? `${API_URL.replace(/\/$/, "")}${info.webhook_path}`
    : "";
  const examplePayload = info ? JSON.stringify(info.example_payload, null, 2) : "";

  return (
    <DashboardPage>
      <Head>
        <title>TradingView Integration — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">TradingView Markets</h1>
        <p className="text-xs text-slate-500">Live charts via TradingView plus webhook alerts turned into tracked paper signals.</p>
      </div>

      {/* Live chart */}
      <Card
        title="Live chart"
        subtitle={symbol}
        actions={
          <span className={`flex items-center gap-1.5 text-[11px] ${live && live.live_count > 0 ? "text-emerald-400" : "text-slate-500"}`}>
            <Activity className="h-3.5 w-3.5" />
            {live && live.live_count > 0 ? `${live.live_count} live via TradingView alerts` : "Live prices arrive via TradingView alerts"}
          </span>
        }
        className="mb-6"
      >
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {TV_PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => setSymbol(p.symbol)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                symbol === p.symbol
                  ? "border-accent bg-accent-soft text-emerald-300"
                  : "border-line bg-bg-soft text-slate-400 hover:text-slate-200"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="overflow-hidden rounded-xl border border-line">
          <TVChart symbol={symbol} />
        </div>

        {live && Object.keys(live.quotes).length > 0 && (
          <div className="mt-5">
            <div className="label mb-2">Live watchlist</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {Object.values(live.quotes)
                .slice(0, 24)
                .map((q) => (
                  <div key={q.symbol} className="rounded-lg border border-line bg-bg-soft px-3 py-2">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold text-slate-300">{q.symbol}</span>
                      <span className={`chip ${q.source === "tradingview" ? "bg-accent-soft text-emerald-300" : "bg-bg-soft text-slate-500"}`}>
                        {q.source === "tradingview" ? "Live" : "Sim"}
                      </span>
                    </div>
                    <div className="mt-1 font-mono text-sm font-bold text-white">{formatNumber(q.price, 2)}</div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Webhook URL" subtitle="Paste this into TradingView → Alerts → Webhook URL">
          {!info ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <input className="input flex-1 font-mono text-[11px]" readOnly value={webhookUrl} />
                <Button variant="secondary" onClick={() => copy(webhookUrl, "Webhook URL")}>
                  <Copy className="h-3.5 w-3.5" /> Copy
                </Button>
              </div>

              <div className="rounded-lg border border-line bg-bg-soft p-3">
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <ShieldCheck className="h-4 w-4 text-emerald-400" />
                  Your secret (sent as the payload&apos;s <code className="font-mono text-emerald-400">secret</code> field):
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <input className="input font-mono text-[11px]" readOnly value={info.user_secret} />
                  <Button variant="ghost" onClick={() => copy(info.user_secret, "Secret")}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <p className="mt-2 text-[10px] text-slate-600">
                  Keep it secure. Webhooks without a valid secret still write a rejected event so you can debug.
                </p>
              </div>

              <div>
                <div className="label mb-1.5">Example payload</div>
                <pre className="max-h-52 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-emerald-300/80">
                  {examplePayload || JSON.stringify(payload, null, 2)}
                </pre>
              </div>

              <Button onClick={sendTest} loading={testing}>
                <Radio className="h-4 w-4" /> Send Test Alert
              </Button>
            </div>
          )}
        </Card>

        <Card title="Recent Webhook Events">
          {!events ? (
            <Skeleton className="h-64 w-full" />
          ) : events.length === 0 ? (
            <EmptyState
              title="No webhook events yet"
              message="Send a test alert, or wire up TradingView and alerts will stream here."
              icon={<Radio className="h-6 w-6" />}
            />
          ) : (
            <div className="-mx-5">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-line">
                    <th className="th">Time</th>
                    <th className="th">Signal</th>
                    <th className="th">Secret</th>
                    <th className="th">Status</th>
                    <th className="th">Payload</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.id} className="tr-hover border-b border-line/60 last:border-0">
                      <td className="td whitespace-nowrap text-xs text-slate-500">{timeAgo(ev.created_at)}</td>
                      <td className="td text-xs">
                        {ev.signal_id ? (
                          <span className="font-semibold text-emerald-400">#{ev.signal_id}</span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="td">
                        <span className={`chip ${ev.secret_valid ? "bg-accent-soft text-emerald-300" : "bg-warn/15 text-amber-300"}`}>
                          {ev.secret_valid ? "valid" : "invalid"}
                        </span>
                      </td>
                      <td className="td"><StatusBadge status={ev.status} /></td>
                      <td className="td">
                        <span className="line-clamp-1 max-w-[220px] font-mono text-[10px] text-slate-500">
                          {JSON.stringify(ev.payload)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Card title="TradingView Alert Message" className="mt-6">
        <p className="mb-3 text-xs text-slate-500">
          Pushes since June 2026 also feed the live prices above and the signal engine. Use <code className="font-mono text-emerald-400">{"{{close}}"}</code>, <code className="font-mono text-emerald-400">{"{{ticker}}"}</code> and <code className="font-mono text-emerald-400">{"{{interval}}"}</code> placeholders. Example alert message (XAUUSD):
        </p>
        <pre className="overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-slate-300">
{`{
  "secret": "YOUR_WEBHOOK_SECRET",
  "symbol": "{{ticker}}",
  "direction": "LONG",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "strategy": "Gold Alerts"
}`}
        </pre>
      </Card>
    </DashboardPage>
  );
}