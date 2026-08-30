import React, { createContext, useCallback, useContext, useState } from "react";
import clsx from "clsx";
import { CheckCircle2, Loader2, X, XCircle } from "lucide-react";

/* ------------------------------------------------------------------ */
/* Spinner / Skeleton                                                  */
/* ------------------------------------------------------------------ */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("animate-spin", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={clsx("animate-pulse rounded-md bg-bg-hover", className)} />
  );
}

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: React.ReactNode;
}

export function Button({
  variant = "primary",
  loading,
  icon,
  children,
  disabled,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={clsx(`btn-${variant}`, className)}
      {...rest}
    >
      {loading ? <Spinner className="h-4 w-4" /> : icon}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */
export function Card({
  title,
  subtitle,
  children,
  actions,
  className,
  id,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div id={id} className={clsx("card shadow-card", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between border-b border-line px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stat card                                                           */
/* ------------------------------------------------------------------ */
export function StatCard({
  label,
  value,
  change,
  icon,
  tone = "default",
  loading,
}: {
  label: string;
  value: React.ReactNode;
  change?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "default" | "green" | "red" | "info";
  loading?: boolean;
}) {
  const toneClass = {
    default: "text-slate-100",
    green: "text-emerald-400",
    red: "text-red-400",
    info: "text-sky-400",
  }[tone];
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
          {label}
        </span>
        {icon && <span className="text-slate-500">{icon}</span>}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <div className={clsx("number mt-1.5 text-2xl font-bold", toneClass)}>
          {value}
        </div>
      )}
      {change && <div className="mt-1 text-xs text-slate-500">{change}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Badges                                                              */
/* ------------------------------------------------------------------ */
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING: "bg-warn/15 text-amber-300",
    ACTIVE: "bg-info/15 text-sky-300",
    TARGET_HIT: "bg-accent/15 text-emerald-300",
    STOP_HIT: "bg-danger/15 text-red-300",
    EXPIRED: "bg-slate-500/15 text-slate-400",
    CANCELLED: "bg-slate-500/15 text-slate-400",
    OPEN: "bg-info/15 text-sky-300",
    CLOSED: "bg-accent/15 text-emerald-300",
  };
  return (
    <span className={clsx("chip", map[status] || "bg-slate-500/15 text-slate-400")}>
      {status.replace("_", " ")}
    </span>
  );
}

export function DirectionBadge({ direction }: { direction: string }) {
  const isLong = direction.toUpperCase() === "LONG";
  return (
    <span
      className={clsx(
        "chip font-semibold",
        isLong ? "bg-accent/15 text-emerald-400" : "bg-danger/15 text-red-400"
      )}
    >
      <span className={clsx("h-1.5 w-1.5 rounded-full", isLong ? "bg-emerald-400" : "bg-red-400")} />
      {direction.toUpperCase()}
    </span>
  );
}

export function SourceBadge({ source }: { source: string }) {
  const sourceLower = (source || "").toLowerCase();
  if (sourceLower.includes("tradingview")) {
    return <span className="chip bg-info/15 text-sky-300">TradingView</span>;
  }
  if (sourceLower.includes("openai")) {
    return <span className="chip bg-accent/15 text-emerald-300">AI</span>;
  }
  if (sourceLower.includes("demo") || sourceLower.includes("heuristic")) {
    return <span className="chip bg-warn/15 text-amber-300">DEMO</span>;
  }
  if (sourceLower.includes("youtube")) {
    return <span className="chip bg-purple-500/15 text-purple-300">YouTube</span>;
  }
  if (sourceLower.includes("webhook")) {
    return <span className="chip bg-info/15 text-sky-300">Webhook</span>;
  }
  return <span className="chip bg-slate-500/15 text-slate-400">{source || "manual"}</span>;
}

export function ConfidenceBar({ value }: { value?: number | null }) {
  const v = value ?? 0;
  const color = v >= 70 ? "bg-emerald-400" : v >= 45 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-bg-hover">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${v}%` }} />
      </div>
      <span className="number text-xs text-slate-400">{v}%</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Empty state                                                         */
/* ------------------------------------------------------------------ */
export function EmptyState({
  title,
  message,
  icon,
  action,
}: {
  title: string;
  message?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      {icon && <div className="mb-3 text-slate-600">{icon}</div>}
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      {message && <p className="mt-1 max-w-sm text-xs text-slate-500">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Modal                                                               */
/* ------------------------------------------------------------------ */
export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div
        className={clsx(
          "relative z-10 max-h-[85vh] w-full overflow-y-auto rounded-2xl border border-line bg-bg-card shadow-card animate-fade-in",
          wide ? "max-w-3xl" : "max-w-lg"
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Toasts                                                              */
/* ------------------------------------------------------------------ */
interface ToastItem {
  id: number;
  kind: "success" | "error" | "info";
  message: string;
}

const ToastContext = createContext<{
  toast: (message: string, kind?: ToastItem["kind"]) => void;
}>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, kind: ToastItem["kind"] = "info") => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => {
      setItems((prev) => prev.filter((i) => i.id !== id));
    }, 4200);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={clsx(
              "pointer-events-auto flex items-start gap-2 rounded-xl border bg-bg-card px-4 py-3 shadow-card animate-slide-up",
              item.kind === "success" && "border-emerald-500/40",
              item.kind === "error" && "border-red-500/40",
              item.kind === "info" && "border-line"
            )}
          >
            {item.kind === "success" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />}
            {item.kind === "error" && <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />}
            {item.kind === "info" && <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-sky-400" />}
            <span className="text-xs text-slate-200">{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
export function RuleText({ rule }: { rule: { condition: string; params: Record<string, unknown> } }) {
  const p = rule.params || {};
  const map: Record<string, string> = {
    rsi_above: `RSI above ${p.level}`,
    rsi_below: `RSI below ${p.level}`,
    rsi_cross_above: `RSI crosses back above ${p.level}`,
    rsi_cross_below: `RSI crosses below ${p.level}`,
    price_above_ma: `Price above ${String(p.ma || "EMA")} ${p.period}`,
    price_below_ma: `Price below ${String(p.ma || "EMA")} ${p.period}`,
    price_cross_above_ma: `Price crosses above ${String(p.ma || "EMA")} ${p.period}`,
    price_cross_below_ma: `Price crosses below ${String(p.ma || "EMA")} ${p.period}`,
    ma_cross_above: `${p.fast}-${String(p.ma)} crosses above ${p.slow}-${String(p.ma)}`,
    ma_cross_below: `${p.fast}-${String(p.ma)} crosses below ${p.slow}-${String(p.ma)}`,
    macd_above: "MACD above signal line",
    macd_below: "MACD below signal line",
    macd_cross_above: "MACD crosses above signal line",
    macd_cross_below: "MACD crosses below signal line",
    price_breakout_above: `Breakout above ${p.period}-bar high`,
    price_breakdown_below: `Breakdown below ${p.period}-bar low`,
    price_above: `Price above ${p.level}`,
    price_below: `Price below ${p.level}`,
    always: "Always true",
  };
  return <>{map[rule.condition] || rule.condition}</>;
}

export function riskColor(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-slate-400";
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return "text-slate-400";
}