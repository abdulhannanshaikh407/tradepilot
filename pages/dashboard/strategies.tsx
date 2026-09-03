import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Head from "next/head";
import { Search, SlidersHorizontal, Trash2 } from "lucide-react";

import DashboardPage from "components/DashboardPage";
import { Button, Card, DirectionBadge, EmptyState, Skeleton, SourceBadge, useToast } from "components/ui";
import { api } from "lib/api";
import type { Strategy } from "lib/types";

export default function Strategies() {
  const { toast } = useToast();
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [search, setSearch] = useState("");
  const [asset, setAsset] = useState("");
  const [direction, setDirection] = useState("");
  const [filters, setFilters] = useState<{ assets: string[]; timeframes: string[]; directions: string[] } | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (asset) params.set("asset", asset);
    if (direction) params.set("direction", direction);
    const [list, f] = await Promise.all([
      api<Strategy[]>(`/strategies?${params.toString()}`),
      api<any>("/strategies/filters"),
    ]);
    setStrategies(list);
    setFilters(f);
  }, [search, asset, direction]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const remove = async (id: number) => {
    setDeleting(id);
    try {
      await api(`/strategies/${id}`, { method: "DELETE" });
      toast("Strategy deleted", "success");
      load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Delete failed", "error");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <DashboardPage>
      <Head>
        <title>Strategies — TradePilot AI</title>
      </Head>

      <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold text-white">Strategies</h1>
          <p className="text-xs text-slate-500">{strategies?.length ?? 0} extracted rule-sets</p>
        </div>
        <Link href="/dashboard/analyzer" className="btn-primary">
          Analyze a video
        </Link>
      </div>

      <Card className="mb-6">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              className="input pl-9"
              placeholder="Search strategies…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <SlidersHorizontal className="my-2 h-4 w-4 shrink-0 text-slate-600 sm:hidden" />
          <select className="input sm:w-44" value={asset} onChange={(e) => setAsset(e.target.value)}>
            <option value="">All assets</option>
            {filters?.assets.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <select className="input sm:w-44" value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="">All directions</option>
            <option value="LONG">Long</option>
            <option value="SHORT">Short</option>
          </select>
        </div>
      </Card>

      {!strategies ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : strategies.length === 0 ? (
        <Card>
          <EmptyState
            title="No strategies yet"
            message="Analyze a YouTube video to extract your first ruleset, or use a demo video."
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {strategies.map((s) => (
            <Link key={s.id} href={`/dashboard/strategies/${s.id}`} className="card group p-5 transition hover:border-accent/50 hover:shadow-glow">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-sm font-bold text-white group-hover:text-emerald-300">
                      {s.name}
                    </h3>
                    {s.is_demo && <span className="chip bg-warn/15 text-amber-300">DEMO</span>}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">via <SourceBadge source={s.source} /></div>
                </div>
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    remove(s.id);
                  }}
                  disabled={deleting === s.id}
                  className="rounded-lg p-1.5 text-slate-600 hover:bg-danger-soft hover:text-red-300"
                  title="Delete strategy"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-slate-200">{s.asset}</span>
                <span className="chip border-line bg-bg-soft">{s.timeframe}</span>
                <DirectionBadge direction={s.direction} />
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {(s.indicators || []).slice(0, 4).map((ind, i) => (
                  <span key={i} className="chip border-line bg-bg-soft text-slate-400">
                    {ind.name}
                    {ind.period ? ` (${ind.period})` : ""}
                  </span>
                ))}
              </div>

              <div className="mt-4 flex items-center justify-between text-[11px] text-slate-600">
                <span className="line-clamp-1 pr-2">{s.description || "No description"}</span>
                <span className="chip bg-accent-soft text-emerald-300">View →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </DashboardPage>
  );
}