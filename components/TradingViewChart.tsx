import React, { useEffect, useRef } from "react";

export const TV_PRESETS = [
  { label: "XAUUSD", symbol: "OANDA:XAUUSD", change: 1 },
  { label: "XAGUSD", symbol: "OANDA:XAGUSD", change: 0.98 },
  { label: "BTCUSD", symbol: "BINANCE:BTCUSDT", change: 0.75 },
  { label: "ETHUSD", symbol: "BINANCE:ETHUSDT", change: 0.72 },
  { label: "EURUSD", symbol: "FX:EURUSD", change: 0.67 },
  { label: "US30", symbol: "US30", change: 0.6 },
  { label: "SPX500", symbol: "SPX500", change: 0.58 },
  { label: "US100", symbol: "US100", change: 0.55 },
  { label: "USOIL", symbol: "USOIL", change: 0.5 },
  { label: "GBPUSD", symbol: "FX:GBPUSD", change: 0.65 },
  { label: "USDJPY", symbol: "FX:USDJPY", change: 0.62 },
  { label: "SOLUSD", symbol: "BINANCE:SOLUSDT", change: 0.7 },
];

export function canonicalTvSymbol(symbol: string): string {
  const hit = TV_PRESETS.find((p) => p.label.replace("/", "") === symbol.replace("/", "").toUpperCase());
  return hit ? hit.symbol : symbol;
}

const WIDGET_URL = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

export default function TVChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    el.innerHTML = "";
    const script = document.createElement("script");
    script.src = WIDGET_URL;
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: canonicalTvSymbol(symbol),
      interval: "60",
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "rgba(9, 14, 22, 1)",
      gridColor: "rgba(30, 41, 59, 0.4)",
      hide_top_toolbar: false,
      allow_symbol_change: true,
      save_image: false,
      studies: ["STD;RSI", "STD;MACD"],
      support_host: true,
    });
    el.appendChild(script);

    return () => {
      el.innerHTML = "";
    };
  }, [symbol]);

  return <div ref={containerRef} className="h-[560px] w-full" />;
}