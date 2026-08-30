export const colors = {
  bg: "#0B1120",
  card: "#111A2E",
  border: "#1F2A44",
  text: "#E6EDF7",
  muted: "#8B9BB4",
  primary: "#3B82F6",
  up: "#22C55E",
  down: "#EF4444",
  warn: "#F59E0B",
};

export const formatMoney = (v?: number | null): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const formatPrice = (v?: number | null): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v);
};

export const formatPct = (v?: number | null): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
};

export const formatDate = (iso?: string | null): string => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
};