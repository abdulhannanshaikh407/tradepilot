import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Save,
  Settings2,
  Trash2,
  TrendingDown,
  TrendingUp,
  Zap,
  X,
  ChevronDown,
} from "lucide-react";
import { api } from "lib/api";
import { useAuth } from "lib/auth";
import { useRouter } from "next/router";
import type { Strategy } from "lib/types";

// ---------------------------------------------------------------------------
// Custom node types
// ---------------------------------------------------------------------------

interface NodeData {
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  indicator?: string;
  params?: Record<string, number>;
  condition?: string;
  level?: number;
  type?: string;
  stopLoss?: number;
  takeProfit?: number;
  risk?: number;
  [key: string]: unknown;
}

const INDICATOR_OPTIONS = [
  { value: "RSI", label: "RSI", defaults: { period: 14 } },
  { value: "SMA", label: "SMA", defaults: { period: 50 } },
  { value: "EMA", label: "EMA", defaults: { period: 200 } },
  { value: "MACD", label: "MACD", defaults: { fast: 12, slow: 26, signal: 9 } },
  { value: "Bollinger Bands", label: "Bollinger Bands", defaults: { period: 20, std: 2 } },
  { value: "ATR", label: "ATR", defaults: { period: 14 } },
  { value: "Stochastic", label: "Stochastic", defaults: { k: 14, d: 3 } },
  { value: "ADX", label: "ADX", defaults: { period: 14 } },
];

const CONDITION_OPTIONS: Record<string, { value: string; label: string }[]> = {
  RSI: [
    { value: "rsi_above", label: "RSI Above" },
    { value: "rsi_below", label: "RSI Below" },
    { value: "rsi_cross_above", label: "RSI Cross Above" },
    { value: "rsi_cross_below", label: "RSI Cross Below" },
  ],
  SMA: [
    { value: "price_above_ma", label: "Price Above SMA" },
    { value: "price_below_ma", label: "Price Below SMA" },
    { value: "ma_cross_above", label: "SMA Cross Above" },
    { value: "ma_cross_below", label: "SMA Cross Below" },
  ],
  EMA: [
    { value: "price_above_ma", label: "Price Above EMA" },
    { value: "price_below_ma", label: "Price Below EMA" },
    { value: "ma_cross_above", label: "EMA Cross Above" },
    { value: "ma_cross_below", label: "EMA Cross Below" },
  ],
  MACD: [
    { value: "macd_above", label: "MACD Above Signal" },
    { value: "macd_below", label: "MACD Below Signal" },
    { value: "macd_cross_above", label: "MACD Cross Above Signal" },
    { value: "macd_cross_below", label: "MACD Cross Below Signal" },
  ],
  "Bollinger Bands": [
    { value: "price_below_ma", label: "Price Below Lower Band" },
    { value: "price_above_ma", label: "Price Above Upper Band" },
  ],
  ATR: [],
  Stochastic: [
    { value: "rsi_above", label: "K Above Level" },
    { value: "rsi_below", label: "K Below Level" },
  ],
  ADX: [
    { value: "rsi_above", label: "ADX Above Level" },
    { value: "rsi_below", label: "ADX Below Level" },
  ],
};

// --- Indicator Node ---
function IndicatorNode({ data, id }: { data: NodeData; id: string }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState((data.indicator as string) || "RSI");
  const [params, setParams] = useState<Record<string, number>>(
    (data.params as Record<string, number>) || { period: 14 }
  );

  const handleSave = () => {
    data.onUpdate(id, { indicator: name, params });
    setEditing(false);
  };

  return (
    <div className="min-w-[220px] rounded-xl border border-blue-500/40 bg-[#0d1b2a] shadow-lg">
      <div className="flex items-center justify-between rounded-t-xl bg-blue-500/10 px-4 py-2">
        <span className="flex items-center gap-2 text-xs font-bold text-blue-300">
          <Activity className="h-3.5 w-3.5" /> INDICATOR
        </span>
        <button
          onClick={() => setEditing(!editing)}
          className="text-slate-500 hover:text-blue-300"
        >
          <Settings2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="px-4 py-3">
        {editing ? (
          <div className="space-y-2">
            <select
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                const opt = INDICATOR_OPTIONS.find((i) => i.value === e.target.value);
                if (opt) setParams({ ...opt.defaults } as unknown as Record<string, number>);
              }}
              className="w-full rounded border border-line bg-bg px-2 py-1.5 text-xs text-slate-200"
            >
              {INDICATOR_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {name !== "MACD" && (
              <div>
                <label className="text-[10px] text-slate-500">Period</label>
                <input
                  type="number"
                  value={params.period || 14}
                  onChange={(e) => setParams({ ...params, period: Number(e.target.value) })}
                  className="w-full rounded border border-line bg-bg px-2 py-1 text-xs text-slate-200"
                />
              </div>
            )}
            {name === "MACD" && (
              <div className="grid grid-cols-3 gap-1">
                <div>
                  <label className="text-[10px] text-slate-500">Fast</label>
                  <input
                    type="number"
                    value={params.fast || 12}
                    onChange={(e) => setParams({ ...params, fast: Number(e.target.value) })}
                    className="w-full rounded border border-line bg-bg px-1 py-1 text-xs text-slate-200"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500">Slow</label>
                  <input
                    type="number"
                    value={params.slow || 26}
                    onChange={(e) => setParams({ ...params, slow: Number(e.target.value) })}
                    className="w-full rounded border border-line bg-bg px-1 py-1 text-xs text-slate-200"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500">Signal</label>
                  <input
                    type="number"
                    value={params.signal || 9}
                    onChange={(e) => setParams({ ...params, signal: Number(e.target.value) })}
                    className="w-full rounded border border-line bg-bg px-1 py-1 text-xs text-slate-200"
                  />
                </div>
              </div>
            )}
            <button onClick={handleSave} className="w-full rounded bg-blue-500/20 py-1 text-[11px] font-medium text-blue-300 hover:bg-blue-500/30">
              Apply
            </button>
          </div>
        ) : (
          <div>
            <div className="text-sm font-semibold text-white">{name}</div>
            <div className="mt-1 text-[11px] text-slate-500">
              {name === "MACD"
                ? `${params.fast}/${params.slow}/${params.signal}`
                : `Period: ${params.period || 14}`}
            </div>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-blue-400 !w-3 !h-3 !border-2 !border-[#0d1b2a]" />
    </div>
  );
}

// --- Condition Node ---
function ConditionNode({ data, id }: { data: NodeData; id: string }) {
  const [editing, setEditing] = useState(false);
  const [condition, setCondition] = useState((data.condition as string) || "rsi_cross_above");
  const [level, setLevel] = useState((data.level as number) || 30);

  const handleSave = () => {
    data.onUpdate(id, { condition, level });
    setEditing(false);
  };

  return (
    <div className="min-w-[220px] rounded-xl border border-amber-500/40 bg-[#0d1b2a] shadow-lg">
      <Handle type="target" position={Position.Top} className="!bg-amber-400 !w-3 !h-3 !border-2 !border-[#0d1b2a]" />
      <div className="flex items-center justify-between rounded-t-xl bg-amber-500/10 px-4 py-2">
        <span className="flex items-center gap-2 text-xs font-bold text-amber-300">
          <Zap className="h-3.5 w-3.5" /> CONDITION
        </span>
        <button onClick={() => setEditing(!editing)} className="text-slate-500 hover:text-amber-300">
          <Settings2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="px-4 py-3">
        {editing ? (
          <div className="space-y-2">
            <select
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              className="w-full rounded border border-line bg-bg px-2 py-1.5 text-xs text-slate-200"
            >
              {Object.entries(CONDITION_OPTIONS).map(([group, opts]) => (
                <optgroup key={group} label={group}>
                  {opts.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <div>
              <label className="text-[10px] text-slate-500">Level</label>
              <input
                type="number"
                value={level}
                onChange={(e) => setLevel(Number(e.target.value))}
                className="w-full rounded border border-line bg-bg px-2 py-1 text-xs text-slate-200"
              />
            </div>
            <button onClick={handleSave} className="w-full rounded bg-amber-500/20 py-1 text-[11px] font-medium text-amber-300 hover:bg-amber-500/30">
              Apply
            </button>
          </div>
        ) : (
          <div>
            <div className="text-sm font-semibold text-white">
              {condition.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">Level: {level}</div>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400 !w-3 !h-3 !border-2 !border-[#0d1b2a]" />
    </div>
  );
}

// --- Entry/Exit Node ---
function EntryExitNode({ data }: { data: NodeData }) {
  const isEntry = data.type === "entry";
  return (
    <div className={`min-w-[180px] rounded-xl border ${isEntry ? "border-emerald-500/40" : "border-red-500/40"} bg-[#0d1b2a] shadow-lg`}>
      <Handle type="target" position={Position.Top} className={`!bg-${isEntry ? "emerald" : "red"}-400 !w-3 !h-3 !border-2 !border-[#0d1b2a]`} />
      <div className={`rounded-t-xl px-4 py-2 ${isEntry ? "bg-emerald-500/10" : "bg-red-500/10"}`}>
        <span className={`flex items-center gap-2 text-xs font-bold ${isEntry ? "text-emerald-300" : "text-red-300"}`}>
          {isEntry ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          {isEntry ? "ENTRY" : "EXIT"}
        </span>
      </div>
      <div className="px-4 py-3">
        <div className="text-[11px] text-slate-400">
          {isEntry ? "Connect indicators & conditions above" : "Connect exit conditions above"}
        </div>
      </div>
    </div>
  );
}

// --- Risk Management Node ---
function RiskNode({ data, id }: { data: NodeData; id: string }) {
  const [editing, setEditing] = useState(false);
  const [sl, setSl] = useState((data.stopLoss as number) || 2.0);
  const [tp, setTp] = useState((data.takeProfit as number) || 4.0);
  const [risk, setRisk] = useState((data.risk as number) || 1.0);

  const handleSave = () => {
    data.onUpdate(id, { stopLoss: sl, takeProfit: tp, risk });
    setEditing(false);
  };

  return (
    <div className="min-w-[200px] rounded-xl border border-purple-500/40 bg-[#0d1b2a] shadow-lg">
      <Handle type="target" position={Position.Top} className="!bg-purple-400 !w-3 !h-3 !border-2 !border-[#0d1b2a]" />
      <div className="flex items-center justify-between rounded-t-xl bg-purple-500/10 px-4 py-2">
        <span className="flex items-center gap-2 text-xs font-bold text-purple-300">
          <Settings2 className="h-3.5 w-3.5" /> RISK MANAGEMENT
        </span>
        <button onClick={() => setEditing(!editing)} className="text-slate-500 hover:text-purple-300">
          <Settings2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="px-4 py-3">
        {editing ? (
          <div className="space-y-2">
            <div>
              <label className="text-[10px] text-slate-500">Stop Loss %</label>
              <input
                type="number"
                step="0.1"
                value={sl}
                onChange={(e) => setSl(Number(e.target.value))}
                className="w-full rounded border border-line bg-bg px-2 py-1 text-xs text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-500">Take Profit %</label>
              <input
                type="number"
                step="0.1"
                value={tp}
                onChange={(e) => setTp(Number(e.target.value))}
                className="w-full rounded border border-line bg-bg px-2 py-1 text-xs text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-500">Risk Per Trade %</label>
              <input
                type="number"
                step="0.1"
                value={risk}
                onChange={(e) => setRisk(Number(e.target.value))}
                className="w-full rounded border border-line bg-bg px-2 py-1 text-xs text-slate-200"
              />
            </div>
            <button onClick={handleSave} className="w-full rounded bg-purple-500/20 py-1 text-[11px] font-medium text-purple-300 hover:bg-purple-500/30">
              Apply
            </button>
          </div>
        ) : (
          <div className="space-y-1 text-[11px]">
            <div className="flex justify-between text-slate-400">
              <span>Stop Loss</span>
              <span className="text-red-400">{sl}%</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Take Profit</span>
              <span className="text-emerald-400">{tp}%</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Risk/Trade</span>
              <span className="text-purple-400">{risk}%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const nodeTypes: any = {
  indicator: IndicatorNode,
  condition: ConditionNode,
  entry: EntryExitNode,
  exit: EntryExitNode,
  risk: RiskNode,
};

// ---------------------------------------------------------------------------
// Sidebar panel for adding nodes
// ---------------------------------------------------------------------------

function AddNodePanel({ onAdd }: { onAdd: (type: string) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="absolute left-4 top-4 z-10">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg border border-line bg-bg-card px-3 py-2 text-xs font-medium text-slate-200 shadow-lg hover:bg-bg-hover"
      >
        <Zap className="h-3.5 w-3.5 text-emerald-400" />
        Add Node
        <ChevronDown className={`h-3.5 w-3.5 text-slate-500 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 w-56 space-y-1 rounded-xl border border-line bg-bg-card p-2 shadow-xl">
          <button onClick={() => { onAdd("indicator"); setOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-blue-500/10 hover:text-blue-300">
            <Activity className="h-3.5 w-3.5" /> Indicator
          </button>
          <button onClick={() => { onAdd("condition"); setOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-amber-500/10 hover:text-amber-300">
            <Zap className="h-3.5 w-3.5" /> Condition
          </button>
          <button onClick={() => { onAdd("entry"); setOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-emerald-500/10 hover:text-emerald-300">
            <TrendingUp className="h-3.5 w-3.5" /> Entry Point
          </button>
          <button onClick={() => { onAdd("exit"); setOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-red-500/10 hover:text-red-300">
            <TrendingDown className="h-3.5 w-3.5" /> Exit Point
          </button>
          <button onClick={() => { onAdd("risk"); setOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 hover:bg-purple-500/10 hover:text-purple-300">
            <Settings2 className="h-3.5 w-3.5" /> Risk Management
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main builder page
// ---------------------------------------------------------------------------

function BuilderCanvas() {
  const { user } = useAuth();
  const router = useRouter();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [strategyName, setStrategyName] = useState("My Strategy");
  const [asset, setAsset] = useState("BTC/USD");
  const [timeframe, setTimeframe] = useState("4H");
  const [direction, setDirection] = useState<"LONG" | "SHORT">("LONG");
  const [saving, setSaving] = useState(false);
  const [showPinescript, setShowPinescript] = useState(false);
  const [pinescript, setPinescript] = useState("");
  const [loadedStrategyId, setLoadedStrategyId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const onUpdateRef = useRef<(nodeId: string, newData: Record<string, unknown>) => void>(() => {});

  // Load existing strategy or seed default nodes for new strategy
  useEffect(() => {
    const strategyId = router.query.id ? Number(router.query.id) : null;
    if (!strategyId || !user) {
      // New strategy — seed default starter graph: Indicator → Condition → Entry, Risk → Exit
      if (nodes.length === 0) {
        const indicatorId = "indicator-default";
        const conditionId = "condition-default";
        const entryId = "entry-default";
        const riskId = "risk-default";
        const exitId = "exit-default";
        setNodes([
          { id: indicatorId, type: "indicator", position: { x: 250, y: 0 }, data: { onUpdate: () => {}, indicator: "RSI", params: { period: 14 } } },
          { id: conditionId, type: "condition", position: { x: 250, y: 150 }, data: { onUpdate: () => {}, condition: "rsi_cross_above", level: 30 } },
          { id: entryId, type: "entry", position: { x: 250, y: 300 }, data: { onUpdate: () => {}, type: "entry" } },
          { id: riskId, type: "risk", position: { x: 100, y: 450 }, data: { onUpdate: () => {}, stopLoss: 2.0, takeProfit: 4.0, risk: 1.0 } },
          { id: exitId, type: "exit", position: { x: 400, y: 450 }, data: { onUpdate: () => {}, type: "exit" } },
        ]);
        setEdges([
          { id: "e-ind-cond", source: indicatorId, target: conditionId, animated: true, style: { stroke: "#6366f1" } },
          { id: "e-cond-entry", source: conditionId, target: entryId, animated: true, style: { stroke: "#6366f1" } },
          { id: "e-risk-exit", source: riskId, target: exitId, animated: true, style: { stroke: "#6366f1" } },
        ]);
      }
      return;
    }

    setLoading(true);
    api<Strategy>(`/strategies/${strategyId}`)
      .then((strategy) => {
        setLoadedStrategyId(strategy.id);
        setStrategyName(strategy.name);
        setAsset(strategy.asset);
        setTimeframe(strategy.timeframe);
        setDirection(strategy.direction as "LONG" | "SHORT");

        // Convert saved rules back into nodes/edges
        const newNodes: Node[] = [];
        const newEdges: Edge[] = [];
        let y = 0;

        // Indicators → indicator nodes
        for (const ind of strategy.indicators || []) {
          const id = `indicator-${ind.name}-${ind.period || 14}`;
          newNodes.push({
            id,
            type: "indicator",
            position: { x: 250, y },
            data: { onUpdate: onUpdateRef.current, indicator: ind.name, params: { period: ind.period || 14, fast: ind.fast, slow: ind.slow, signal: ind.signal } },
          });
          y += 150;
        }

        // Entry rules → condition nodes connected to entry
        const entryNodeId = "entry-loaded";
        newNodes.push({
          id: entryNodeId,
          type: "entry",
          position: { x: 250, y },
          data: { onUpdate: onUpdateRef.current, type: "entry" },
        });
        y += 150;

        for (const rule of strategy.entry_rules || []) {
          const id = `condition-entry-${rule.condition}-${Math.random().toString(36).slice(2, 6)}`;
          newNodes.push({
            id,
            type: "condition",
            position: { x: 250, y },
            data: { onUpdate: onUpdateRef.current, condition: rule.condition, level: rule.params?.level || 30 },
          });
          newEdges.push({
            id: `e-${id}-${entryNodeId}`,
            source: id,
            target: entryNodeId,
            animated: true,
            style: { stroke: "#6366f1" },
          });
          y += 150;
        }

        // Exit rules → condition nodes connected to exit
        const exitNodeId = "exit-loaded";
        newNodes.push({
          id: exitNodeId,
          type: "exit",
          position: { x: 400, y },
          data: { onUpdate: onUpdateRef.current, type: "exit" },
        });
        const exitY = y;
        y += 150;

        for (const rule of strategy.exit_rules || []) {
          const id = `condition-exit-${rule.condition}-${Math.random().toString(36).slice(2, 6)}`;
          newNodes.push({
            id,
            type: "condition",
            position: { x: 400, y },
            data: { onUpdate: onUpdateRef.current, condition: rule.condition, level: rule.params?.level || 70 },
          });
          newEdges.push({
            id: `e-${id}-${exitNodeId}`,
            source: id,
            target: exitNodeId,
            animated: true,
            style: { stroke: "#6366f1" },
          });
          y += 150;
        }

        // Risk management node
        const riskNodeId = "risk-loaded";
        newNodes.push({
          id: riskNodeId,
          type: "risk",
          position: { x: 100, y: exitY },
          data: {
            onUpdate: onUpdateRef.current,
            stopLoss: strategy.stop_loss_value || 2.0,
            takeProfit: strategy.take_profit_value || 4.0,
            risk: strategy.risk_per_trade || 1.0,
          },
        });
        newEdges.push({
          id: `e-risk-${exitNodeId}`,
          source: riskNodeId,
          target: exitNodeId,
          animated: true,
          style: { stroke: "#6366f1" },
        });

        // Wire indicators to first conditions if edges aren't already set
        const indicatorNodes = newNodes.filter((n) => n.type === "indicator");
        const entryConditionNodes = newNodes.filter((n) => n.type === "condition" && n.id.startsWith("condition-entry-"));
        for (let i = 0; i < Math.min(indicatorNodes.length, entryConditionNodes.length); i++) {
          if (!newEdges.find((e) => e.source === indicatorNodes[i].id)) {
            newEdges.push({
              id: `e-auto-${indicatorNodes[i].id}-${entryConditionNodes[i].id}`,
              source: indicatorNodes[i].id,
              target: entryConditionNodes[i].id,
              animated: true,
              style: { stroke: "#6366f1" },
            });
          }
        }

        setNodes(newNodes);
        setEdges(newEdges);
      })
      .catch(() => {
        // If load fails, seed defaults
        setNodes([]);
        setEdges([]);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query.id, user]);

  const onUpdate = useCallback(
    (nodeId: string, newData: Record<string, unknown>) => {
      setNodes((nds: Node[]) =>
        nds.map((n: Node) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...newData } } : n
        )
      );
    },
    [setNodes]
  );

  // Keep ref in sync so useEffect-seeded nodes get the real callback
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  const addNode = useCallback(
    (type: string) => {
      const id = `${type}-${Date.now()}`;
      const position = {
        x: Math.random() * 400 + 100,
        y: nodes.length * 120 + 50,
      };

      let nodeData: NodeData = { onUpdate: onUpdateRef.current };
      let nodeType = type;

      if (type === "indicator") {
        nodeData = { ...nodeData, indicator: "RSI", params: { period: 14 } };
      } else if (type === "condition") {
        nodeData = { ...nodeData, condition: "rsi_cross_above", level: 30 };
      } else if (type === "entry") {
        nodeData = { ...nodeData, type: "entry" };
        nodeType = "entry";
      } else if (type === "exit") {
        nodeData = { ...nodeData, type: "exit" };
        nodeType = "exit";
      } else if (type === "risk") {
        nodeData = { ...nodeData, stopLoss: 2.0, takeProfit: 4.0, risk: 1.0 };
      }

      const newNode: Node = { id, type: nodeType, position, data: nodeData };
      setNodes((nds: Node[]) => [...nds, newNode]);
    },
    [nodes.length, setNodes]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({ ...connection, animated: true, style: { stroke: "#6366f1" } }, eds));
    },
    [setEdges]
  );

  const buildConfig = useCallback(() => {
    const indicatorNodes = nodes.filter((n) => n.type === "indicator");
    const conditionNodes = nodes.filter((n) => n.type === "condition");
    const riskNodes = nodes.filter((n) => n.type === "risk");

    const indicators = indicatorNodes.map((n) => ({
      name: n.data.indicator,
      ...n.data.params,
    }));

    const entryRuleIds = edges
      .filter((e) => nodes.find((n) => n.id === e.target && n.type === "entry"))
      .map((e) => e.source);
    const exitRuleIds = edges
      .filter((e) => nodes.find((n) => n.id === e.target && n.type === "exit"))
      .map((e) => e.source);

    const entryRules = conditionNodes
      .filter((n) => entryRuleIds.includes(n.id))
      .map((n) => ({ condition: n.data.condition, params: { level: n.data.level } }));

    const exitRules = conditionNodes
      .filter((n) => exitRuleIds.includes(n.id))
      .map((n) => ({ condition: n.data.condition, params: { level: n.data.level } }));

    const risk = riskNodes[0]?.data || {};

    return {
      name: strategyName,
      asset,
      timeframe,
      direction,
      indicators,
      entry_rules: entryRules.length > 0 ? entryRules : [{ condition: "rsi_cross_above", params: { period: 14, level: 30 } }],
      confirmation_rules: [],
      exit_rules: exitRules.length > 0 ? exitRules : [{ condition: "rsi_above", params: { period: 14, level: 70 } }],
      stop_loss_type: "percent",
      stop_loss_value: risk.stopLoss || 2.0,
      take_profit_type: "percent",
      take_profit_value: risk.takeProfit || 4.0,
      risk_per_trade: risk.risk || 1.0,
    };
  }, [nodes, edges, strategyName, asset, timeframe, direction]);

  const handleSave = async () => {
    if (!user) return router.push("/login");
    setSaving(true);
    try {
      const config = buildConfig();
      if (loadedStrategyId) {
        // Update existing strategy
        await api(`/strategies/${loadedStrategyId}`, {
          method: "PUT",
          body: JSON.stringify({ ...config, source: "builder" }),
        });
      } else {
        // Create new strategy
        await api("/strategies", {
          method: "POST",
          body: JSON.stringify({ ...config, source: "builder" }),
        });
      }
      router.push("/dashboard/strategies");
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleGeneratePinescript = async () => {
    try {
      const config = buildConfig();
      const res = await api<{ pinescript: string }>("/pinescript/generate", {
        method: "POST",
        body: JSON.stringify(config),
      });
      setPinescript(res.pinescript);
      setShowPinescript(true);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex h-[calc(100vh-120px)] flex-col gap-4">
      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={strategyName}
          onChange={(e) => setStrategyName(e.target.value)}
          className="rounded-lg border border-line bg-bg-card px-3 py-2 text-sm font-semibold text-white"
          placeholder="Strategy name"
        />
        <select
          value={asset}
          onChange={(e) => setAsset(e.target.value)}
          className="rounded-lg border border-line bg-bg-card px-3 py-2 text-xs text-slate-200"
        >
          <option>BTC/USD</option>
          <option>ETH/USD</option>
          <option>SOL/USD</option>
          <option>EUR/USD</option>
          <option>GOLD</option>
          <option>NAS100</option>
          <option>US500</option>
        </select>
        <select
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
          className="rounded-lg border border-line bg-bg-card px-3 py-2 text-xs text-slate-200"
        >
          <option>5m</option>
          <option>15m</option>
          <option>1H</option>
          <option>4H</option>
          <option>1D</option>
        </select>
        <button
          onClick={() => setDirection(direction === "LONG" ? "SHORT" : "LONG")}
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium ${
            direction === "LONG"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-red-500/40 bg-red-500/10 text-red-300"
          }`}
        >
          {direction === "LONG" ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
          {direction}
        </button>

        <div className="flex-1" />

        <button
          onClick={handleGeneratePinescript}
          className="flex items-center gap-2 rounded-lg border border-line bg-bg-card px-3 py-2 text-xs font-medium text-slate-300 hover:bg-bg-hover"
        >
          PineScript
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary"
        >
          <Save className="h-3.5 w-3.5" />
          {saving ? "Saving..." : "Save Strategy"}
        </button>
      </div>

      {/* Canvas */}
      <div className="relative flex-1 overflow-hidden rounded-xl border border-line bg-[#0a0f1a]">
        <AddNodePanel onAdd={addNode} />
        <ReactFlow
          ref={reactFlowWrapper}
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
          className="bg-[#0a0f1a]"
        >
          <Controls className="!bg-bg-card !border-line !rounded-lg" />
          <MiniMap
            nodeStrokeColor="#334155"
            nodeColor="#1e293b"
            nodeBorderRadius={8}
            className="!bg-bg-card !border-line"
          />
          <Background gap={20} size={1} color="#1e293b" />
        </ReactFlow>
      </div>

      {/* Pinescript modal */}
      {showPinescript && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="mx-4 w-full max-w-2xl rounded-2xl border border-line bg-bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-line px-6 py-4">
              <h3 className="text-sm font-bold text-white">Generated PineScript</h3>
              <button onClick={() => setShowPinescript(false)} className="text-slate-500 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6">
              <pre className="max-h-96 overflow-auto rounded-lg bg-[#0a0f1a] p-4 text-xs text-emerald-300">
                {pinescript}
              </pre>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(pinescript);
                }}
                className="btn-primary mt-4"
              >
                Copy to Clipboard
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function BuilderPage() {
  return (
    <ReactFlowProvider>
      <BuilderCanvas />
    </ReactFlowProvider>
  );
}
