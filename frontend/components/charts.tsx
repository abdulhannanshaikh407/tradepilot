import React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const tooltipStyle = {
  background: "#0f1626",
  border: "1px solid #1e2a44",
  borderRadius: "10px",
  fontSize: "12px",
  color: "#e5e9f0",
};

const axisTick = { fill: "#64748b", fontSize: 11 };

/* ------------------------------------------------------------------ */
/* Equity curve (equity vs time)                                       */
/* ------------------------------------------------------------------ */
export function EquityCurve({
  data,
  height = 260,
}: {
  data: { timestamp: string; equity: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#1e2a44" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="timestamp"
          tick={axisTick}
          tickLine={false}
          axisLine={{ stroke: "#1e2a44" }}
          minTickGap={32}
        />
        <YAxis
          tick={axisTick}
          tickLine={false}
          axisLine={false}
          domain={["auto", "auto"]}
          tickFormatter={(v: number) => v.toLocaleString()}
          width={72}
        />
        <Tooltip contentStyle={tooltipStyle} />
        <Area
          type="monotone"
          dataKey="equity"
          stroke="#10b981"
          strokeWidth={2}
          fill="url(#equityFill)"
          dot={false}
          activeDot={{ r: 4, fill: "#10b981", stroke: "#0b1120" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Monthly performance bars                                            */
/* ------------------------------------------------------------------ */
export function MonthlyPerformance({
  data,
  height = 220,
}: {
  data: { period: string; pnl: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1e2a44" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="period" tick={axisTick} tickLine={false} axisLine={{ stroke: "#1e2a44" }} />
        <YAxis tick={axisTick} tickLine={false} axisLine={false} width={60} />
        <Tooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: "rgba(30,42,68,0.35)" }}
        />
        <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.pnl >= 0 ? "#10b981" : "#ef4444"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Win / loss distribution                                             */
/* ------------------------------------------------------------------ */
export function WinLossDonut({
  wins,
  losses,
  height = 200,
}: {
  wins: number;
  losses: number;
  height?: number;
}) {
  const data = [
    { name: "Wins", value: wins, color: "#10b981" },
    { name: "Losses", value: losses, color: "#ef4444" },
  ].filter((d) => d.value > 0);
  if (data.length === 0) {
    return <div className="py-8 text-center text-xs text-slate-500">No trades yet</div>;
  }
  return (
    <div className="flex items-center gap-4">
      <ResponsiveContainer width="60%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={52}
            outerRadius={80}
            paddingAngle={3}
            stroke="#0f1626"
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
        </PieChart>
      </ResponsiveContainer>
      <div className="space-y-3">
        {data.map((d) => (
          <div key={d.name}>
            <div className="flex items-center gap-2 text-xs">
              <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
              <span className="text-slate-400">{d.name}</span>
              <span className="number ml-auto font-semibold text-slate-200">{d.value}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Strategy comparison (grouped bar)                                   */
/* ------------------------------------------------------------------ */
export function StrategyComparison({
  data,
  height = 260,
}: {
  data: { name: string; win_rate: number; return_percent: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1e2a44" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fill: "#64748b", fontSize: 10 }}
          tickLine={false}
          axisLine={{ stroke: "#1e2a44" }}
          interval={0}
        />
        <YAxis tick={axisTick} tickLine={false} axisLine={false} width={48} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(30,42,68,0.35)" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
        <Bar dataKey="win_rate" name="Win rate %" fill="#38bdf8" radius={[4, 4, 0, 0]} />
        <Bar dataKey="return_percent" name="Return %" fill="#10b981" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Asset performance                                                   */
/* ------------------------------------------------------------------ */
export function AssetPerformance({
  data,
  height = 220,
}: {
  data: { symbol: string; net_pnl: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1e2a44" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="symbol" tick={axisTick} tickLine={false} axisLine={{ stroke: "#1e2a44" }} />
        <YAxis tick={axisTick} tickLine={false} axisLine={false} width={56} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(30,42,68,0.35)" }} />
        <Bar dataKey="net_pnl" name="Net P&L ($)" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.net_pnl >= 0 ? "#10b981" : "#ef4444"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}