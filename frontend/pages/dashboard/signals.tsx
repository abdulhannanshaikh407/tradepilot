import React, { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import { Radio, X } from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, DirectionBadge, EmptyState, Modal, Skeleton, SourceBadge, StatusBadge, useToast } from "components/ui";
import { api, formatNumber, timeAgo } from "lib/api";
import type { Signal } from "lib/types";

const STATUSES = ["ALL", "PENDING", "ACTIVE", "CLOSED", "CANCELLED"];

export default function Signals() {
  const { toast } = useToast();
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [status, setStatus] = useState("ALL");
  const [selected, setSelected] = useState<Signal | null>(null);
  const [updating, setUpdating] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api<Signal[]>(`/signals${status !== "ALL" ? `?status=${status}` : ""}`);
      setSignals(list);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to load signals", "error");
    }
  }, [status, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const setSignalStatus = async (sig: Signal, newStatus: string) => {
    setUpdating(true);
    try {
      await api(`/signals/${sig.id}/status`, { method: "PATCH", body: { status: newStatus } });
      toast(`Signal ${newStatus.toLowerCase()}`, "success");
      setSelected(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Update failed", "error");
    } finally {
      setUpdating(false);
    }
  };

  const resetSignal = async (sig: Signal) => {
    setUpdating(true);
    try {
      await api(`/signals/${sig.id}/status`, { method: "PATCH", body: { status: "PENDING" } });
      toast("Signal reset to pending", "success");
      setSelected(null);
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Reset failed", "error");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <DashboardPage>
      <Head>
        <title>Signals — TradePilot AI</title>
      </Head>

      <div className="mb-6">
        <h1 className="text-xl font-bold text-white">Signal Terminal</h1>
        <p className="text-xs text-slate-500">
          Paper-trading signals from strategies and TradingView alerts. Never financial advice.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`chip transition ${status === s ? "bg-accent-soft text-emerald-300" : "bg-bg-soft text-slate-500 hover:text-slate-300"}`}
          >
            {s}
          </button>
        ))}
      </div>

      <Card className="overflow-hidden p-0">
        {!signals ? (
          <Skeleton className="h-64 w-full" />
        ) : signals.length === 0 ? (
          <EmptyState
            title="No signals"
            message="Generate a paper signal from a strategy, or send a TradingView test alert."
            icon={<Radio className="h-6 w-6" />}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-line">
                  <th className="th">Time</th>
                  <th className="th">Asset</th>
                  <th className="th">Signal</th>
                  <th className="th">Entry</th>
                  <th className="th">Stop / Target</th>
                  <th className="th">R : R</th>
                  <th className="th">Status</th>
                  <th className="th">Source</th>
                  <th className="th">Reason</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
                  <tr key={s.id} className="tr-hover cursor-pointer border-b border-line/60 last:border-0" onClick={() => setSelected(s)}>
                    <td className="td whitespace-nowrap text-xs text-slate-500">{timeAgo(s.created_at)}</td>
                    <td className="td font-semibold">{s.symbol}</td>
                    <td className="td"><DirectionBadge direction={s.direction} /></td>
                    <td className="td number">{s.entry_price != null ? formatNumber(s.entry_price, 2) : "—"}</td>
                    <td className="td text-xs text-slate-400">
                      {s.stop_loss != null ? formatNumber(s.stop_loss, 2) : "—"} /{" "}
                      {s.take_profit != null ? formatNumber(s.take_profit, 2) : "—"}
                    </td>
                    <td className="td number">{s.risk_reward ?? "—"}</td>
                    <td className="td"><StatusBadge status={s.status} /></td>
                    <td className="td"><SourceBadge source={s.source} /></td>
                    <td className="td"><span className="line-clamp-1 max-w-[220px] text-xs text-slate-500">{s.reason || "—"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={!!selected} onClose={() => setSelected(null)} title="Signal detail">
        {selected && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-lg font-bold text-white">{selected.symbol}</span>
                <DirectionBadge direction={selected.direction} />
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={selected.status} />
                <SourceBadge source={selected.source} />
                {selected.is_demo && <span className="chip bg-warn/15 text-amber-300">SIMULATED</span>}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <div className="label">Entry</div>
                <div className="number text-sm font-bold text-slate-200">
                  {selected.entry_price != null ? formatNumber(selected.entry_price, 2) : "—"}
                </div>
              </div>
              <div>
                <div className="label">Stop loss</div>
                <div className="number text-sm font-bold text-red-400">
                  {selected.stop_loss != null ? formatNumber(selected.stop_loss, 2) : "—"}
                </div>
              </div>
              <div>
                <div className="label">Take profit</div>
                <div className="number text-sm font-bold text-emerald-400">
                  {selected.take_profit != null ? formatNumber(selected.take_profit, 2) : "—"}
                </div>
              </div>
              <div>
                <div className="label">Risk : Reward</div>
                <div className="number text-sm font-bold text-sky-400">{selected.risk_reward ?? "—"}</div>
              </div>
            </div>

            <div>
              <div className="label">Confidence</div>
              <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-bg-hover">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400"
                  style={{ width: `${selected.confidence ?? 0}%` }}
                />
              </div>
              <div className="number mt-1 text-xs text-slate-400">{selected.confidence ?? 0}%</div>
            </div>

            {selected.reason && (
              <div className="rounded-lg border border-line bg-bg-soft p-3">
                <div className="label mb-1">Why</div>
                <p className="text-xs leading-relaxed text-slate-300">{selected.reason}</p>
              </div>
            )}

            <div className="flex justify-between border-t border-line pt-3 text-[11px] text-slate-600">
              <span>Created {selected.created_at ? timeAgo(selected.created_at) : "—"}</span>
              <button
                onClick={() => setSelected(null)}
                className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-300"
              >
                <X className="h-3 w-3" /> Close
              </button>
            </div>

            {selected.status !== "CLOSED" && (
              <div className="flex gap-2 border-t border-line pt-3">
                {selected.status === "PENDING" || selected.status === "ACTIVE" ? (
                  <Button
                    variant="danger"
                    className="flex-1"
                    loading={updating}
                    onClick={() => setSignalStatus(selected, "CANCELLED")}
                  >
                    Cancel signal
                  </Button>
                ) : (
                  <Button className="flex-1" loading={updating} onClick={() => resetSignal(selected)}>
                    Re-open
                  </Button>
                )}
                {(selected.status === "PENDING" || selected.status === "ACTIVE") && (
                  <Button
                    variant="secondary"
                    className="flex-1"
                    loading={updating}
                    onClick={() => setSignalStatus(selected, "CLOSED")}
                  >
                    Mark closed
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </DashboardPage>
  );
}