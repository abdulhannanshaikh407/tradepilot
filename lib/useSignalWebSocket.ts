import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, getToken } from "./api";
import type { Signal } from "./types";

interface SignalEvent {
  type: "new_signal";
  signal: Signal;
}

export function useSignalWebSocket(onSignal?: (signal: Signal) => void) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onSignalRef = useRef(onSignal);
  onSignalRef.current = onSignal;

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) return;

    const wsUrl = API_URL.replace(/^http/, "ws");
    const url = `${wsUrl}/ws/signals?token=${token}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        // Send periodic pings to keep alive
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 30000);
        ws.addEventListener("close", () => clearInterval(pingInterval));
      };

      ws.onmessage = (event) => {
        if (event.data === "pong") return;
        try {
          const data: SignalEvent = JSON.parse(event.data);
          if (data.type === "new_signal" && data.signal) {
            onSignalRef.current?.(data.signal);
          }
        } catch {
          // ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // Reconnect after 3 seconds
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
